# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Model Context Protocol (MCP) server bridging AP2/x402 mandates to ISO 20022.

Exposes the bridge as tools: normalise an AP2 or x402 payload into a canonical
mandate, guardrail it (required fields, spending cap, expiry, authorisation
proof), and convert it into a ``pain.001`` or ``pacs.008`` record ready for the
``pain001`` / ``pacs008`` generators.

These tools only transform and validate -- they never move money. Producing the
ISO record stays separate from generating and sending it, so the actual
payment remains an explicit, guarded step for the caller.

Tools return JSON-serializable data; on a :class:`ValueError` they return an
``{"error": ...}`` payload rather than raising.

Launching the server:
    * As a console script::

        ap2-iso20022-mcp

    * In an MCP client config (e.g. Claude Desktop)::

        {
          "mcpServers": {
            "ap2-iso20022": {
              "command": "ap2-iso20022-mcp"
            }
          }
        }

The server communicates over stdio (FastMCP's default transport).
"""

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ap2_iso20022 import __version__, bridge

server = FastMCP("ap2-iso20022")
# FastMCP does not expose a version kwarg; without this override the MCP SDK's
# own version leaks into serverInfo.version, breaking manifest/runtime
# coherence checks (e.g. Glama scoring).
server._mcp_server.version = __version__

# Every tool is a pure, side-effect-free transform/validator over its
# arguments. Nothing opens a caller-supplied path, reaches an external system,
# or moves money.
_PURE_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_MANDATE_DESC = (
    "A canonical mandate object (see normalize_ap2/normalize_x402 output): "
    "payer_/payee_ name+account_iban, amount, currency, plus optional "
    "reference, execution_date, max_amount, expiry, proof_type/proof_value."
)

# The guardrail policies check_mandate enforces, keyed by id so the templated
# ap2://guardrails/{policy_id} resource can expose more than one later without
# changing shape. Only the single canonical "default" policy exists today. The
# required-field list is sourced from bridge so the published policy can never
# drift from what check_mandate/normalize_mandate actually enforce.
_GUARDRAIL_POLICIES: dict[str, dict[str, Any]] = {
    "default": {
        "policy_id": "default",
        "description": (
            "Guardrails check_mandate enforces on a canonical mandate before "
            "it is converted into an ISO 20022 payment instruction."
        ),
        "required_fields": list(bridge._REQUIRED),
        "spend_cap": {
            "rule": "amount <= max_amount",
            "applies_when": "max_amount is present on the mandate",
            "severity": "violation",
        },
        "expiry": {
            "rule": "as_of <= expiry",
            "applies_when": "both expiry and as_of (the check date) are given",
            "date_format": "ISO 8601 date/datetime (trailing 'Z' accepted)",
            "severity": "violation",
        },
        "proof": {
            "rule": "proof_type and proof_value are both present",
            "applies_when": "always",
            "severity": "warning",
        },
    },
}


@server.tool(
    annotations=_PURE_READ,
    description=(
        "Normalise a Google AP2 (Agent Payments Protocol) mandate payload into "
        "a canonical mandate the other tools accept."
    ),
)
def normalize_ap2(
    payload: Annotated[
        dict[str, Any], Field(description="An AP2 mandate payload.")
    ],
) -> dict[str, Any]:
    """Normalise an AP2 mandate into a canonical mandate."""
    try:
        return {"mandate": bridge.from_ap2(payload)}
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool(
    annotations=_PURE_READ,
    description=(
        "Normalise a Coinbase x402 (HTTP-402) payment requirement/receipt into "
        "a canonical mandate the other tools accept."
    ),
)
def normalize_x402(
    payload: Annotated[
        dict[str, Any], Field(description="An x402 payment payload.")
    ],
) -> dict[str, Any]:
    """Normalise an x402 payment payload into a canonical mandate."""
    try:
        return {"mandate": bridge.from_x402(payload)}
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool(
    annotations=_PURE_READ,
    description=(
        "Guardrail a mandate before it becomes a payment: check required "
        "fields, the spending cap (amount <= max_amount), expiry (when 'as_of' "
        "is supplied), and whether an authorisation proof is present. Returns "
        "ok plus any violations and warnings. Run this before converting."
    ),
)
def check_mandate(
    mandate: Annotated[dict[str, Any], Field(description=_MANDATE_DESC)],
    as_of: Annotated[
        str | None,
        Field(description="ISO date/datetime to evaluate expiry against."),
    ] = None,
) -> dict[str, Any]:
    """Check a mandate against its guardrails."""
    return bridge.check_mandate(mandate, as_of)


@server.tool(
    annotations=_PURE_READ,
    description=(
        "Convert a canonical mandate into a pain.001 record (customer credit "
        "transfer initiation) using the exact field names pain001 expects, so "
        "it feeds straight into pain001 generate_message for wire-valid XML."
    ),
)
def to_pain001(
    mandate: Annotated[dict[str, Any], Field(description=_MANDATE_DESC)],
) -> dict[str, Any]:
    """Convert a mandate into a pain.001 record."""
    try:
        return {"record": bridge.to_pain001(mandate)}
    except ValueError as exc:
        return {"error": str(exc)}


@server.tool(
    annotations=_PURE_READ,
    description=(
        "Convert a canonical mandate into a pacs.008 record (FI-to-FI credit "
        "transfer) using the field names pacs008 expects, for interbank "
        "settlement of an agent-authorised payment."
    ),
)
def to_pacs008(
    mandate: Annotated[dict[str, Any], Field(description=_MANDATE_DESC)],
) -> dict[str, Any]:
    """Convert a mandate into a pacs.008 record."""
    try:
        return {"record": bridge.to_pacs008(mandate)}
    except ValueError as exc:
        return {"error": str(exc)}


@server.prompt(
    title="Audit AP2 Agent Spending Mandate",
    description=(
        "Guidance for auditing an AP2 agent's spending mandate end to end: "
        "normalise the payload, guardrail it, then convert it for settlement."
    ),
)
def audit_agent_spending_mandate(
    agent_id: Annotated[
        str,
        Field(description="The AP2 agent identifier under audit, if known."),
    ] = "",
) -> str:
    """Return step-by-step guidance for auditing an agent's spending mandate."""
    subject = f"AP2 agent '{agent_id}'" if agent_id else "the AP2 agent"
    return (
        f"Audit {subject}'s payment mandate before any money moves, using the "
        "ap2-iso20022 tools in order:\n"
        "1. Normalise the raw payload into a canonical mandate: call "
        "normalize_ap2 for a Google AP2 mandate, or normalize_x402 for a "
        "Coinbase x402 payment requirement/receipt.\n"
        "2. Guardrail the canonical mandate with check_mandate (pass 'as_of' "
        "to evaluate expiry): require 'ok' to be true, treat every entry in "
        "'violations' as a blocker and every 'warnings' entry (e.g. a missing "
        "authorisation proof) as something to resolve before proceeding. The "
        "enforced policy is published at the ap2://guardrails/default "
        "resource.\n"
        "3. Only once the mandate passes, convert it for settlement: "
        "to_pain001 for a customer credit transfer (pain.001) or to_pacs008 "
        "for an FI-to-FI transfer (pacs.008). These transforms never move "
        "money; sending the resulting record stays a separate, explicit "
        "step.\n"
        "Report the spending cap, expiry, and authorisation-proof status you "
        "found, and whether the mandate is safe to settle."
    )


@server.resource(
    "ap2://guardrails",
    title="AP2 Guardrail Policies",
    description="The guardrail policy ids check_mandate can enforce.",
    mime_type="application/json",
)
def guardrail_policies() -> str:
    """List the available guardrail policy ids as JSON."""
    return json.dumps({"policies": list(_GUARDRAIL_POLICIES)})


@server.resource(
    "ap2://guardrails/{policy_id}",
    title="AP2 Guardrail Policy",
    description=(
        "The guardrail policy check_mandate enforces (required fields, spend "
        "cap, expiry, authorisation proof) as JSON, by policy id."
    ),
    mime_type="application/json",
)
def guardrail_policy(
    policy_id: Annotated[
        str, Field(description="Guardrail policy id (e.g. 'default').")
    ],
) -> str:
    """Return one guardrail policy as JSON, or an error for an unknown id."""
    policy = _GUARDRAIL_POLICIES.get(policy_id)
    if policy is None:
        return json.dumps(
            {
                "error": (
                    f"unknown guardrail policy '{policy_id}'; available: "
                    f"{', '.join(_GUARDRAIL_POLICIES)}"
                )
            }
        )
    return json.dumps(policy)


def main() -> None:
    """Run the AP2/x402 bridge MCP server over stdio (``ap2-iso20022-mcp``)."""
    server.run()


if __name__ == "__main__":
    main()
