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

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

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


def _decimal_or_raise(value: Any, name: str) -> Decimal:
    """Coerce ``value`` to Decimal or raise ``ValueError`` naming the field."""
    number = _to_decimal(value)
    if number is None:
        raise ValueError(f"{name} must be a number")
    return number


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


# CoinGecko public simple-price endpoint (no API key). Token symbols map to
# CoinGecko coin ids; the vs_currency is the lower-cased fiat code.
_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
_TOKEN_IDS = {
    "USDC": "usd-coin",
    "USDT": "tether",
    "EURC": "euro-coin",
    "ETH": "ethereum",
    "SOL": "solana",
}


def get_token_fiat_rate(
    token_symbol: str, fiat_currency: str = "USD"
) -> dict[str, Any]:
    """Fetch a spot token->fiat rate from the CoinGecko public API.

    Unlike the rest of this module this reaches an external service, so it is
    an *open-world* read: the returned rate is a live spot price, not a
    guarantee, and repeated calls may differ.

    ``httpx`` is an optional dependency behind the ``oracle`` extra and is
    imported lazily, so importing this module never requires it.

    Args:
        token_symbol: One of the supported symbols (USDC, USDT, EURC, ETH,
            SOL); matched case-insensitively.
        fiat_currency: Fiat currency code to price in (default ``USD``).

    Returns:
        On success ``{"token", "fiat_currency", "rate", "source"}`` where
        ``rate`` is a Decimal-safe string. Mirrors the module's error
        convention with ``{"error": ...}`` for an unsupported symbol, a
        missing ``oracle`` extra, or a failed fetch.
    """
    symbol = str(token_symbol or "").upper()
    coin_id = _TOKEN_IDS.get(symbol)
    if coin_id is None:
        return {
            "error": (
                f"unsupported token symbol {token_symbol!r}; supported: "
                f"{', '.join(sorted(_TOKEN_IDS))}"
            )
        }

    try:
        import httpx
    except ImportError:
        return {
            "error": (
                "the price oracle requires the optional 'oracle' extra; "
                "install it with: pip install ap2-iso20022[oracle]"
            )
        }

    vs = str(fiat_currency or "USD").lower()
    try:
        response = httpx.get(
            _COINGECKO_URL,
            params={"ids": coin_id, "vs_currencies": vs},
            timeout=10.0,
        )
        response.raise_for_status()
        rate = response.json()[coin_id][vs]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        # Transport failure, non-2xx status, or an unexpected payload shape.
        return {"error": "oracle fetch failed"}

    return {
        "token": symbol,
        "fiat_currency": vs.upper(),
        "rate": str(rate),
        "source": "coingecko",
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


# --- Tier-2 guardrails: agent spend, expiry, token, Web3 --------------------
#
# These are stateless, pure validators over their arguments. Anything that
# needs "now" or a running spend total is supplied by the caller -- the server
# never reads a clock or persists state, keeping every tool deterministic.


# ISO 4217-style USD stablecoin / native-token base-unit precision. Base units
# (the on-chain integer) divided by 10**decimals give the human amount.
_TOKEN_DECIMALS = {
    "USDC": 6,
    "USDT": 6,
    "EURC": 6,
    "ETH": 18,
    "SOL": 9,
}

# EIP-2612 permit fields that must be present and well-formed.
_PERMIT_FIELDS = ("owner", "spender", "value", "nonce", "deadline")

_HEX_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _is_hex_address(value: Any) -> bool:
    """Return True if ``value`` looks like a 20-byte 0x-prefixed address."""
    return bool(_HEX_ADDRESS_RE.match(str(value)))


def check_agent_spend_limits(
    agent_id: str,
    proposed_amount_usd: Any,
    per_tx_cap: Any = 1000,
    daily_cap: Any = 5000,
    monthly_cap: Any = 20000,
    spent_today: Any = 0,
    spent_month: Any = 0,
) -> dict[str, Any]:
    """Check a proposed agent spend against per-tx / daily / monthly caps.

    Stateless: the caller passes the current ``spent_today`` / ``spent_month``
    running totals; nothing is persisted here. ``remaining_daily_cap`` is the
    headroom left today before this transaction (``daily_cap - spent_today``).

    Raises:
        ValueError: if the proposed amount is not positive, or any cap/total is
            not a number.
    """
    amount = _decimal_or_raise(proposed_amount_usd, "proposed_amount_usd")
    if amount <= 0:
        raise ValueError("proposed_amount_usd must be a positive number")
    per_tx = _decimal_or_raise(per_tx_cap, "per_tx_cap")
    daily = _decimal_or_raise(daily_cap, "daily_cap")
    monthly = _decimal_or_raise(monthly_cap, "monthly_cap")
    today = _decimal_or_raise(spent_today, "spent_today")
    month = _decimal_or_raise(spent_month, "spent_month")

    violations: list[str] = []
    if amount > per_tx:
        violations.append(
            f"proposed amount {amount} exceeds per-transaction cap {per_tx}"
        )
    if today + amount > daily:
        violations.append(
            f"daily spend {today + amount} would exceed daily cap {daily}"
        )
    if month + amount > monthly:
        violations.append(
            f"monthly spend {month + amount} would exceed monthly cap "
            f"{monthly}"
        )

    return {
        "is_allowed": not violations,
        "remaining_daily_cap": str(daily - today),
        "violations": violations,
    }


def validate_mandate_expiry(
    expiration_timestamp: Any, now_timestamp: Any
) -> dict[str, Any]:
    """Check a mandate's expiry by unix-epoch (seconds) comparison.

    The caller supplies ``now_timestamp`` -- the server never reads the system
    clock, so the check stays deterministic. A mandate is valid while ``now``
    is strictly before ``expiration``.

    Raises:
        ValueError: if either timestamp is not a number.
    """
    expiration = _decimal_or_raise(
        expiration_timestamp, "expiration_timestamp"
    )
    now = _decimal_or_raise(now_timestamp, "now_timestamp")
    return {"is_valid": now < expiration}


def normalize_token_amount(
    raw_base_units: Any, token_symbol: Any
) -> dict[str, Any]:
    """Normalise raw on-chain base units to a human token amount.

    Divides ``raw_base_units`` by ``10**decimals`` for the token's precision
    (USDC/USDT/EURC=6, SOL=9, ETH=18) and trims trailing zeros.

    Raises:
        ValueError: on an unsupported token, a non-numeric amount, or a
            negative amount.
    """
    symbol = str(token_symbol or "").upper()
    if symbol not in _TOKEN_DECIMALS:
        raise ValueError(f"unsupported token: {token_symbol!r}")
    decimals = _TOKEN_DECIMALS[symbol]
    raw = _decimal_or_raise(raw_base_units, "raw_base_units")
    if raw < 0:
        raise ValueError("raw_base_units must be non-negative")
    # scaleb shifts the decimal point without rounding the coefficient; format
    # 'f' forces fixed-point (never scientific), then trim the fraction. The
    # '.' introduced by decimals >= 6 makes the strip safe for whole amounts.
    fixed = format(raw.scaleb(-decimals), "f")
    amount = fixed.rstrip("0").rstrip(".")
    return {"amount": amount, "decimals": decimals}


def verify_x402_signature(
    mandate_json: str, signature_hex: str, expected_address: str
) -> dict[str, Any]:
    """Verify an x402 EIP-191 ``personal_sign`` over the mandate JSON.

    Recovers the signer from the signature using ``eth_account`` and compares
    it (case-insensitively) to ``expected_address``.

    Raises:
        ValueError: if the signature is malformed and no signer can be
            recovered.
    """
    message = encode_defunct(text=mandate_json)
    try:
        recovered = Account.recover_message(message, signature=signature_hex)
    except Exception as exc:  # malformed signature / bad hex / wrong length
        raise ValueError(f"malformed signature: {exc}") from exc
    is_valid = str(recovered).lower() == str(expected_address).lower()
    return {"is_valid": is_valid, "recovered_address": str(recovered)}


def validate_eip712_permit(
    permit: dict[str, Any], now_timestamp: Any
) -> dict[str, Any]:
    """Validate the EIP-2612 permit fields and its deadline.

    Checks ``owner``/``spender``/``value``/``nonce``/``deadline`` are present
    and well-formed (addresses are 0x-prefixed 20-byte hex; value/nonce/
    deadline are numeric) and that ``deadline`` is not before the
    caller-supplied ``now_timestamp``.

    Raises:
        ValueError: if ``now_timestamp`` is not a number.
    """
    violations: list[str] = []

    missing = [f for f in _PERMIT_FIELDS if permit.get(f) in (None, "")]
    if missing:
        violations.append(f"missing permit field(s): {', '.join(missing)}")

    for field in ("owner", "spender"):
        value = permit.get(field)
        if value not in (None, "") and not _is_hex_address(value):
            violations.append(f"{field} is not a valid address: {value!r}")

    for field in ("value", "nonce", "deadline"):
        value = permit.get(field)
        if value not in (None, "") and _to_decimal(value) is None:
            violations.append(f"{field} is not a valid number: {value!r}")

    now = _decimal_or_raise(now_timestamp, "now_timestamp")
    deadline = _to_decimal(permit.get("deadline"))
    if deadline is not None and deadline < now:
        violations.append(f"permit deadline {deadline} is in the past")

    return {"is_valid": not violations, "violations": violations}
