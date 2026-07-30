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

"""Unit tests for the AP2/x402 -> ISO 20022 bridge."""

import builtins

import httpx
import pytest
import respx

from ap2_iso20022 import bridge

_ORACLE_URL = "https://api.coingecko.com/api/v3/simple/price"


def _canonical(**over):
    base = {
        "mandate_id": "M-1",
        "payer_name": "Alice Agent",
        "payer_account_iban": "DE89370400440532013000",
        "payer_agent_bic": "DEUTDEFF",
        "payee_name": "Bob Merchant",
        "payee_account_iban": "GB29NWBK60161331926819",
        "payee_agent_bic": "NWBKGB2L",
        "amount": "100.00",
        "currency": "eur",
        "reference": "Order 42",
        "execution_date": "2026-03-02",
        "proof_type": "jws",
        "proof_value": "eyJ...sig",
    }
    base.update(over)
    return base


# --- helpers ----------------------------------------------------------------


def test_to_decimal_variants():
    assert bridge._to_decimal(None) is None
    assert bridge._to_decimal("") is None
    assert bridge._to_decimal("1.50") == __import__("decimal").Decimal("1.50")
    assert bridge._to_decimal("nope") is None


def test_parse_when_variants():
    assert bridge._parse_when("") is None
    assert bridge._parse_when("bad") is None
    assert bridge._parse_when("2026-03-02T10:00:00Z") is not None


# --- normalize --------------------------------------------------------------


def test_normalize_uppercases_currency_and_stringifies_amount():
    m = bridge.normalize_mandate(_canonical())
    assert m["currency"] == "EUR"
    assert m["amount"] == "100.00"


def test_normalize_missing_required_raises():
    with pytest.raises(ValueError, match="missing required field"):
        bridge.normalize_mandate({"payer_name": "A"})


def test_normalize_non_positive_amount_raises():
    with pytest.raises(ValueError, match="positive number"):
        bridge.normalize_mandate(_canonical(amount="0"))
    with pytest.raises(ValueError, match="positive number"):
        bridge.normalize_mandate(_canonical(amount="nan-ish"))


# --- adapters ---------------------------------------------------------------


def test_from_ap2_maps_alternate_keys():
    m = bridge.from_ap2(
        {
            "intent_id": "AP2-9",
            "payer": "Alice",
            "payer_account": "DE89370400440532013000",
            "merchant_name": "Bob",
            "payee_account": "GB29NWBK60161331926819",
            "value": "250.00",
            "currency_code": "USD",
            "memo": "coffee",
            "signature": "sig123",
            "signature_type": "jws",
        }
    )
    assert m["mandate_id"] == "AP2-9"
    assert m["payer_name"] == "Alice"
    assert m["payee_name"] == "Bob"
    assert m["currency"] == "USD"
    assert m["proof_value"] == "sig123"


def test_from_x402_maps_crypto_fields():
    m = bridge.from_x402(
        {
            "resource": "https://api/x",
            "recipient": "Merchant",
            "payTo": "0xabc0000000000000000000000000000000000000",
            "maxAmountRequired": "5.00",
            "asset": "USDC",
            "from": "Agent",
            "from_address": "0xdef0000000000000000000000000000000000000",
            "scheme": "exact",
            "payload": "authblob",
        }
    )
    assert m["payee_account_iban"].startswith("0x")
    assert m["currency"] == "USDC"
    assert m["max_amount"] == "5.00"
    assert m["proof_type"] == "exact"


# --- guardrail --------------------------------------------------------------


def test_check_mandate_ok():
    res = bridge.check_mandate(bridge.normalize_mandate(_canonical()))
    assert res["ok"] is True
    assert res["violations"] == [] and res["warnings"] == []


def test_check_mandate_missing_fields():
    res = bridge.check_mandate({"amount": "1", "currency": "EUR"})
    assert res["ok"] is False
    assert any("missing required" in v for v in res["violations"])


def test_check_mandate_cap_exceeded():
    m = _canonical(amount="500.00", max_amount="100.00")
    res = bridge.check_mandate(bridge.normalize_mandate(m))
    assert res["ok"] is False
    assert any("exceeds spending cap" in v for v in res["violations"])


def test_check_mandate_cap_ok_when_no_cap():
    res = bridge.check_mandate(bridge.normalize_mandate(_canonical()))
    assert not any("cap" in v for v in res["violations"])


def test_check_mandate_expiry_violation_and_skip():
    expired = bridge.normalize_mandate(
        _canonical(expiry="2026-01-01T00:00:00")
    )
    res = bridge.check_mandate(expired, as_of="2026-06-01T00:00:00")
    assert any("expired" in v for v in res["violations"])
    # No as_of -> expiry check skipped even though expiry is set.
    assert bridge.check_mandate(expired)["ok"] is True


def test_check_mandate_warns_without_proof():
    m = bridge.normalize_mandate(_canonical(proof_type="", proof_value=""))
    res = bridge.check_mandate(m)
    assert res["ok"] is True
    assert any("no authorisation proof" in w for w in res["warnings"])


# --- conversion -------------------------------------------------------------


def test_to_pain001_shape_and_keys():
    rec = bridge.to_pain001(_canonical())
    # Exact pain001 field names.
    for k in (
        "id",
        "date",
        "requested_execution_date",
        "debtor_name",
        "debtor_account_IBAN",
        "creditor_name",
        "creditor_account_IBAN",
        "payment_amount",
        "currency",
        "remittance_information",
    ):
        assert k in rec
    assert rec["debtor_account_IBAN"] == "DE89370400440532013000"
    assert rec["payment_amount"] == 100.0
    assert rec["date"] == "2026-03-02"


def test_to_pain001_defaults_id_and_date():
    rec = bridge.to_pain001(_canonical(mandate_id="", execution_date=""))
    assert rec["id"] == "AP2-MANDATE"
    assert rec["date"] == "1970-01-01"  # stable placeholder when unparseable


def test_to_pacs008_shape():
    rec = bridge.to_pacs008(_canonical())
    assert rec["interbank_settlement_amount"] == 100.0
    assert rec["creditor_account_iban"] == "GB29NWBK60161331926819"
    assert rec["creation_date_time"].startswith("2026-03-02T")


# --- get_token_fiat_rate (price oracle) -------------------------------------
#
# The HTTP boundary is mocked with a canned, CoinGecko-shaped payload. The
# `1.00` / `2500.50` figures below are TEST FIXTURES, not verified market
# rates; assertions are about how the tool PARSES the response into its return
# dict, never about a real-world price.


@respx.mock
def test_get_token_fiat_rate_parses_canned_response():
    route = respx.get(_ORACLE_URL).mock(
        return_value=httpx.Response(200, json={"usd-coin": {"usd": 1.00}})
    )
    result = bridge.get_token_fiat_rate("usdc", "usd")
    assert route.called
    assert result == {
        "token": "USDC",
        "fiat_currency": "USD",
        "rate": "1.0",
        "source": "coingecko",
    }


@respx.mock
def test_get_token_fiat_rate_maps_symbol_and_fiat():
    # ETH -> ethereum id, EUR -> lower-cased vs_currency in the request.
    route = respx.get(_ORACLE_URL).mock(
        return_value=httpx.Response(200, json={"ethereum": {"eur": 2500.50}})
    )
    result = bridge.get_token_fiat_rate("ETH", "EUR")
    sent = route.calls.last.request
    assert sent.url.params["ids"] == "ethereum"
    assert sent.url.params["vs_currencies"] == "eur"
    assert result["token"] == "ETH"
    assert result["fiat_currency"] == "EUR"
    assert result["rate"] == "2500.5"


def test_get_token_fiat_rate_unknown_symbol_errors():
    result = bridge.get_token_fiat_rate("DOGE")
    assert "error" in result
    assert "unsupported token symbol" in result["error"]


def test_get_token_fiat_rate_empty_symbol_errors():
    result = bridge.get_token_fiat_rate("")
    assert "error" in result


@respx.mock
def test_get_token_fiat_rate_non_200_errors():
    respx.get(_ORACLE_URL).mock(return_value=httpx.Response(500))
    result = bridge.get_token_fiat_rate("USDC")
    assert result == {"error": "oracle fetch failed"}


@respx.mock
def test_get_token_fiat_rate_transport_error_errors():
    respx.get(_ORACLE_URL).mock(side_effect=httpx.ConnectError("boom"))
    result = bridge.get_token_fiat_rate("USDT")
    assert result == {"error": "oracle fetch failed"}


@respx.mock
def test_get_token_fiat_rate_malformed_payload_errors():
    # 200 OK but the expected coin/currency keys are absent -> KeyError path.
    respx.get(_ORACLE_URL).mock(
        return_value=httpx.Response(200, json={"unexpected": {}})
    )
    result = bridge.get_token_fiat_rate("SOL", "usd")
    assert result == {"error": "oracle fetch failed"}


def test_get_token_fiat_rate_missing_extra_errors(monkeypatch):
    # Simulate httpx not installed (the optional `oracle` extra is absent).
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = bridge.get_token_fiat_rate("USDC")
    assert "error" in result
    assert "pip install ap2-iso20022[oracle]" in result["error"]


# --- tier-2: agent spend limits ---------------------------------------------


def test_spend_limits_allowed_within_all_caps():
    res = bridge.check_agent_spend_limits("agent-1", "50.00")
    assert res["is_allowed"] is True
    assert res["violations"] == []
    assert res["remaining_daily_cap"] == "5000"


def test_spend_limits_daily_cap_exceeded():
    # $6000 proposed with daily_cap $5000 -> not allowed (per_tx raised so the
    # only breach is the daily cap).
    res = bridge.check_agent_spend_limits(
        "agent-1", "6000", per_tx_cap="10000", daily_cap="5000"
    )
    assert res["is_allowed"] is False
    assert any("daily cap" in v for v in res["violations"])
    assert not any("per-transaction" in v for v in res["violations"])


def test_spend_limits_per_tx_cap_exceeded():
    res = bridge.check_agent_spend_limits(
        "agent-1", "200", per_tx_cap="100", daily_cap="5000"
    )
    assert res["is_allowed"] is False
    assert any("per-transaction cap" in v for v in res["violations"])


def test_spend_limits_monthly_cap_exceeded():
    res = bridge.check_agent_spend_limits(
        "agent-1",
        "1000",
        per_tx_cap="1000",
        daily_cap="100000",
        monthly_cap="20000",
        spent_month="19500",
    )
    assert res["is_allowed"] is False
    assert any("monthly cap" in v for v in res["violations"])


def test_spend_limits_rejects_non_positive_amount():
    with pytest.raises(ValueError, match="positive number"):
        bridge.check_agent_spend_limits("agent-1", "0")


def test_spend_limits_rejects_non_numeric_cap():
    with pytest.raises(ValueError, match="must be a number"):
        bridge.check_agent_spend_limits("agent-1", "10", per_tx_cap="nope")


# --- tier-2: mandate expiry -------------------------------------------------


def test_validate_mandate_expiry_future_valid():
    assert bridge.validate_mandate_expiry(2_000, 1_000)["is_valid"] is True


def test_validate_mandate_expiry_past_invalid():
    # past expiration vs a later now -> expired.
    assert bridge.validate_mandate_expiry(1_000, 2_000)["is_valid"] is False


def test_validate_mandate_expiry_rejects_non_numeric():
    with pytest.raises(ValueError, match="must be a number"):
        bridge.validate_mandate_expiry("soon", 1_000)


# --- tier-2: token amount ---------------------------------------------------


def test_normalize_token_amount_usdc():
    res = bridge.normalize_token_amount(1_000_000, "USDC")
    assert res["amount"] == "1"
    assert res["decimals"] == 6


def test_normalize_token_amount_eth():
    res = bridge.normalize_token_amount(10**18, "eth")
    assert res["amount"] == "1"
    assert res["decimals"] == 18


def test_normalize_token_amount_fractional():
    res = bridge.normalize_token_amount(1_500_000, "USDC")
    assert res["amount"] == "1.5"


def test_normalize_token_amount_unsupported_token():
    with pytest.raises(ValueError, match="unsupported token"):
        bridge.normalize_token_amount(1, "DOGE")


def test_normalize_token_amount_negative_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        bridge.normalize_token_amount(-1, "USDC")


# --- tier-2: x402 signature (self-contained round-trip) ---------------------

pytest.importorskip("eth_account")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

# Publicly-known throwaway test key (Hardhat account #0). NEVER a real key.
_TEST_PRIVKEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)


def test_verify_x402_signature_round_trip_and_tamper():
    acct = Account.from_key(_TEST_PRIVKEY)
    mandate_json = '{"payer":"Alice","payee":"Bob","amount":"100.00"}'
    signed = acct.sign_message(encode_defunct(text=mandate_json))
    sig_hex = signed.signature.hex()

    ok = bridge.verify_x402_signature(mandate_json, sig_hex, acct.address)
    assert ok["is_valid"] is True
    assert ok["recovered_address"].lower() == acct.address.lower()

    # Verifying against a different expected address -> recovers, but mismatch.
    wrong = "0x" + "0" * 40
    mismatch = bridge.verify_x402_signature(mandate_json, sig_hex, wrong)
    assert mismatch["is_valid"] is False


def test_verify_x402_signature_malformed_raises():
    with pytest.raises(ValueError, match="malformed signature"):
        bridge.verify_x402_signature("{}", "0xdeadbeef", "0x" + "0" * 40)


# --- tier-2: EIP-2612 permit ------------------------------------------------


def _permit(**over):
    base = {
        "owner": "0x" + "a" * 40,
        "spender": "0x" + "b" * 40,
        "value": "1000000",
        "nonce": "0",
        "deadline": "2000",
    }
    base.update(over)
    return base


def test_validate_permit_well_formed_future_deadline():
    res = bridge.validate_eip712_permit(_permit(), now_timestamp=1_000)
    assert res["is_valid"] is True
    assert res["violations"] == []


def test_validate_permit_missing_field():
    permit = {"owner": "0x" + "a" * 40}
    res = bridge.validate_eip712_permit(permit, now_timestamp=1_000)
    assert res["is_valid"] is False
    assert any("missing permit field" in v for v in res["violations"])


def test_validate_permit_malformed_and_past_deadline():
    permit = _permit(owner="not-an-address", value="xyz", deadline="500")
    res = bridge.validate_eip712_permit(permit, now_timestamp=1_000)
    assert res["is_valid"] is False
    assert any("not a valid address" in v for v in res["violations"])
    assert any("not a valid number" in v for v in res["violations"])
    assert any("in the past" in v for v in res["violations"])


def test_validate_permit_rejects_non_numeric_now():
    with pytest.raises(ValueError, match="must be a number"):
        bridge.validate_eip712_permit(_permit(), now_timestamp="soon")
