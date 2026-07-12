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


def main() -> None:
    """Run the AP2/x402 bridge MCP server over stdio (``ap2-iso20022-mcp``)."""
    server.run()


if __name__ == "__main__":
    main()
