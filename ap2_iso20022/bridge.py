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

"""Bridge agent-payment mandates to ISO 20022 bank-rail instructions.

Agentic-payment protocols -- Google's **AP2** (Agent Payments Protocol, using
signed mandates) and Coinbase's **x402** (HTTP-402 payment requirements) -- sit
*above* the settlement layer: they express an agent's authorisation to pay, not
the bank message that moves the money. This module bridges that gap. It
normalises an AP2 or x402 payload into a canonical *mandate*, checks it against
its own guardrails (required fields, spending cap, expiry, authorisation
proof), and converts it into a record that feeds straight into ``pain001`` /
``pacs008`` to become a wire-valid ISO 20022 message.

Nothing here *moves* money: the bridge only transforms and validates. Producing
the ISO record is deliberately separate from generating and sending it, so the
money-movement step stays an explicit, guarded action for the caller.

The canonical mandate is a plain dict:

    mandate_id, payer_name, payer_account_iban, payer_agent_bic,
    payee_name, payee_account_iban, payee_agent_bic,
    amount, currency, reference, execution_date,
    max_amount, expiry, proof_type, proof_value
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Core economic fields a mandate must carry to become a payment instruction.
_REQUIRED = (
    "payer_name",
    "payer_account_iban",
    "payee_name",
    "payee_account_iban",
    "amount",
    "currency",
)


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first present, non-empty value among ``keys``."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _to_decimal(value: Any) -> Decimal | None:
    """Coerce a value to Decimal via str (no binary-float noise); None if bad."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_mandate(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalise a mandate dict.

    Raises:
        ValueError: if a required economic field is missing or the amount is
            not a positive number.
    """
    mandate = {
        "mandate_id": str(raw.get("mandate_id", "") or ""),
        "payer_name": str(raw.get("payer_name", "") or ""),
        "payer_account_iban": str(raw.get("payer_account_iban", "") or ""),
        "payer_agent_bic": str(raw.get("payer_agent_bic", "") or ""),
        "payee_name": str(raw.get("payee_name", "") or ""),
        "payee_account_iban": str(raw.get("payee_account_iban", "") or ""),
        "payee_agent_bic": str(raw.get("payee_agent_bic", "") or ""),
        "amount": raw.get("amount"),
        "currency": str(raw.get("currency", "") or "").upper(),
        "reference": str(raw.get("reference", "") or ""),
        "execution_date": str(raw.get("execution_date", "") or ""),
        "max_amount": raw.get("max_amount"),
        "expiry": str(raw.get("expiry", "") or ""),
        "proof_type": str(raw.get("proof_type", "") or ""),
        "proof_value": str(raw.get("proof_value", "") or ""),
    }
    missing = [f for f in _REQUIRED if not mandate.get(f)]
    if missing:
        raise ValueError(
            f"mandate is missing required field(s): {', '.join(missing)}"
        )
    amount = _to_decimal(mandate["amount"])
    if amount is None or amount <= 0:
        raise ValueError("mandate 'amount' must be a positive number")
    mandate["amount"] = str(amount)
    return mandate


def from_ap2(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise an AP2 mandate (Intent/Cart) into a canonical mandate.

    Tolerant of key spelling: AP2 payloads vary, so several likely field names
    are tried for each canonical field.
    """
    raw = {
        "mandate_id": _first(payload, ("mandate_id", "id", "intent_id")),
        "payer_name": _first(payload, ("payer_name", "payer", "debtor_name")),
        "payer_account_iban": _first(
            payload, ("payer_account_iban", "payer_account", "debtor_iban")
        ),
        "payer_agent_bic": _first(payload, ("payer_agent_bic", "debtor_bic")),
        "payee_name": _first(
            payload,
            ("payee_name", "merchant", "merchant_name", "creditor_name"),
        ),
        "payee_account_iban": _first(
            payload, ("payee_account_iban", "payee_account", "creditor_iban")
        ),
        "payee_agent_bic": _first(
            payload, ("payee_agent_bic", "creditor_bic")
        ),
        "amount": _first(payload, ("amount", "value", "total")),
        "currency": _first(payload, ("currency", "currency_code", "ccy")),
        "reference": _first(payload, ("reference", "description", "memo")),
        "execution_date": _first(payload, ("execution_date", "due_date")),
        "max_amount": _first(payload, ("max_amount", "spending_limit", "cap")),
        "expiry": _first(payload, ("expiry", "expires_at", "valid_until")),
        "proof_type": _first(payload, ("proof_type", "signature_type")),
        "proof_value": _first(
            payload, ("proof_value", "signature", "jws", "proof")
        ),
    }
    return normalize_mandate({k: v for k, v in raw.items() if v is not None})


def from_x402(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise an x402 payment requirement/receipt into a canonical mandate.

    x402 is crypto-native: ``payTo`` is a recipient address and ``asset`` a
    token. Those map structurally onto the payee account and currency so the
    downstream ISO record can be produced; whether the resulting account is a
    valid IBAN is left to schema validation on generation.
    """
    raw = {
        "mandate_id": _first(payload, ("mandate_id", "id", "resource")),
        "payer_name": _first(payload, ("payer_name", "from", "sender")),
        "payer_account_iban": _first(
            payload, ("payer_account_iban", "payer", "from_address")
        ),
        "payee_name": _first(payload, ("payee_name", "recipient", "to_name")),
        "payee_account_iban": _first(
            payload, ("payee_account_iban", "payTo", "pay_to", "to")
        ),
        "amount": _first(
            payload, ("amount", "maxAmountRequired", "max_amount_required")
        ),
        "currency": _first(payload, ("currency", "asset", "token")),
        "reference": _first(payload, ("reference", "resource", "description")),
        "max_amount": _first(payload, ("max_amount", "maxAmountRequired")),
        "expiry": _first(payload, ("expiry", "expiresAt", "deadline")),
        "proof_type": _first(payload, ("proof_type", "scheme")),
        "proof_value": _first(
            payload, ("proof_value", "payload", "signature")
        ),
    }
    return normalize_mandate({k: v for k, v in raw.items() if v is not None})


def _parse_when(value: str) -> datetime | None:
    """Parse an ISO date/datetime string to a datetime; None if unparseable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_mandate(
    mandate: dict[str, Any], as_of: str | None = None
) -> dict[str, Any]:
    """Guardrail a mandate before it becomes a payment.

    Checks required fields, the spending cap (``amount <= max_amount``),
    expiry (only when both ``expiry`` and ``as_of`` are given), and the
    presence of an authorisation proof.

    Returns:
        ``{"ok": bool, "violations": [...], "warnings": [...]}``.
    """
    violations: list[str] = []
    warnings: list[str] = []

    missing = [f for f in _REQUIRED if not mandate.get(f)]
    if missing:
        violations.append(f"missing required field(s): {', '.join(missing)}")

    amount = _to_decimal(mandate.get("amount"))
    cap = _to_decimal(mandate.get("max_amount"))
    if amount is not None and cap is not None and amount > cap:
        violations.append(f"amount {amount} exceeds spending cap {cap}")

    expiry = _parse_when(str(mandate.get("expiry", "")))
    now = _parse_when(as_of) if as_of else None
    if expiry is not None and now is not None and now > expiry:
        violations.append(f"mandate expired at {mandate['expiry']}")

    if not (mandate.get("proof_type") and mandate.get("proof_value")):
        warnings.append(
            "no authorisation proof present; verify the mandate is signed "
            "before moving money"
        )

    return {
        "ok": not violations,
        "violations": violations,
        "warnings": warnings,
    }


def _today_or(value: str) -> str:
    """Return an ISO date string: the given value, or a stable placeholder."""
    parsed = _parse_when(value)
    if parsed is not None:
        return parsed.date().isoformat()
    return date(1970, 1, 1).isoformat()


def to_pain001(mandate: dict[str, Any]) -> dict[str, Any]:
    """Convert a canonical mandate into a ``pain.001`` record.

    The returned dict uses the exact field names the ``pain001`` library
    expects, so it feeds straight into ``pain001``/``pain001-mcp``
    ``generate_message`` to produce wire-valid XML.
    """
    mandate = normalize_mandate(mandate)
    mid = mandate["mandate_id"] or "AP2-MANDATE"
    exec_date = _today_or(mandate["execution_date"])
    # pain001's schema types amounts as JSON numbers, not strings.
    amount = float(mandate["amount"])
    return {
        "id": mid,
        "date": exec_date,
        "nb_of_txs": 1,
        "ctrl_sum": amount,
        "initiator_name": mandate["payer_name"],
        "payment_information_id": f"{mid}-PMT",
        "payment_method": "TRF",
        "batch_booking": False,
        "service_level_code": "SEPA",
        "requested_execution_date": exec_date,
        "debtor_name": mandate["payer_name"],
        "debtor_account_IBAN": mandate["payer_account_iban"],
        "debtor_agent_BIC": mandate["payer_agent_bic"],
        "charge_bearer": "SLEV",
        "payment_id": mid,
        "payment_amount": amount,
        "currency": mandate["currency"],
        "creditor_agent_BIC": mandate["payee_agent_bic"],
        "creditor_name": mandate["payee_name"],
        "creditor_account_IBAN": mandate["payee_account_iban"],
        "remittance_information": mandate["reference"],
    }


def to_pacs008(mandate: dict[str, Any]) -> dict[str, Any]:
    """Convert a canonical mandate into a ``pacs.008`` (FI-to-FI) record.

    Uses the field names the ``pacs008`` library expects, for interbank
    settlement of an agent-authorised payment.
    """
    mandate = normalize_mandate(mandate)
    mid = mandate["mandate_id"] or "AP2-MANDATE"
    settle_date = _today_or(mandate["execution_date"])
    # pacs008's schema types the settlement amount as a JSON number.
    amount = float(mandate["amount"])
    return {
        "msg_id": mid,
        "creation_date_time": f"{settle_date}T00:00:00",
        "nb_of_txs": 1,
        "settlement_method": "CLRG",
        "interbank_settlement_date": settle_date,
        "end_to_end_id": mid,
        "tx_id": f"{mid}-TX",
        "interbank_settlement_amount": amount,
        "interbank_settlement_currency": mandate["currency"],
        "charge_bearer": "SHAR",
        "debtor_name": mandate["payer_name"],
        "debtor_account_iban": mandate["payer_account_iban"],
        "debtor_agent_bic": mandate["payer_agent_bic"],
        "creditor_agent_bic": mandate["payee_agent_bic"],
        "creditor_name": mandate["payee_name"],
        "creditor_account_iban": mandate["payee_account_iban"],
        "remittance_information": mandate["reference"],
    }
