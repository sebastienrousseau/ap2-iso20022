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

import pytest

from ap2_iso20022 import bridge


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
