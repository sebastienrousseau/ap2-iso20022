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

"""Tests for the ap2-iso20022 MCP server tool surface."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")
pytest.importorskip("eth_account")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

import ap2_iso20022.server as srv  # noqa: E402
from ap2_iso20022 import __version__, bridge  # noqa: E402

# A publicly-known throwaway test key (Hardhat account #1). NEVER a real key.
_TEST_PRIVKEY = (
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
)

EXPECTED_TOOLS = {
    "normalize_ap2",
    "normalize_x402",
    "check_mandate",
    "to_pain001",
    "to_pacs008",
    "get_token_fiat_rate",
    "check_agent_spend_limits",
    "validate_mandate_expiry",
    "normalize_token_amount",
    "verify_x402_signature",
    "validate_eip712_permit",
}

_AP2 = {
    "id": "AP2-1",
    "payer": "Alice",
    "payer_account": "DE89370400440532013000",
    "merchant_name": "Bob",
    "payee_account": "GB29NWBK60161331926819",
    "amount": "100.00",
    "currency": "EUR",
    "signature": "sig",
    "signature_type": "jws",
}


def _registered_tool_names() -> set[str]:
    manager = getattr(srv.server, "_tool_manager", None)
    if manager is not None and hasattr(manager, "list_tools"):
        return {tool.name for tool in manager.list_tools()}
    tools = asyncio.run(srv.server.list_tools())  # pragma: no cover
    return {tool.name for tool in tools}  # pragma: no cover


def test_all_tools_registered():
    assert _registered_tool_names() == EXPECTED_TOOLS


def test_server_version_override():
    assert srv.server._mcp_server.version == __version__


def test_normalize_ap2_happy_and_error():
    ok = srv.normalize_ap2(_AP2)
    assert ok["mandate"]["payer_name"] == "Alice"
    err = srv.normalize_ap2({"payer": "only"})
    assert "error" in err


def test_normalize_x402_happy_and_error():
    ok = srv.normalize_x402(
        {
            "recipient": "M",
            "payTo": "0xabc0000000000000000000000000000000000000",
            "from": "A",
            "from_address": "0xdef0000000000000000000000000000000000000",
            "maxAmountRequired": "9.99",
            "asset": "USDC",
        }
    )
    assert ok["mandate"]["currency"] == "USDC"
    err = srv.normalize_x402({"asset": "USDC"})
    assert "error" in err


def test_check_mandate_tool():
    mandate = srv.normalize_ap2(_AP2)["mandate"]
    res = srv.check_mandate(mandate)
    assert res["ok"] is True


def test_to_pain001_tool_happy_and_error():
    mandate = srv.normalize_ap2(_AP2)["mandate"]
    ok = srv.to_pain001(mandate)
    assert ok["record"]["debtor_account_IBAN"] == "DE89370400440532013000"
    err = srv.to_pain001({"payer_name": "x"})
    assert "error" in err


def test_to_pacs008_tool_happy_and_error():
    mandate = srv.normalize_ap2(_AP2)["mandate"]
    ok = srv.to_pacs008(mandate)
    assert ok["record"]["interbank_settlement_currency"] == "EUR"
    err = srv.to_pacs008({"payer_name": "x"})
    assert "error" in err


def test_get_token_fiat_rate_tool_delegates(monkeypatch):
    # The tool is a thin pass-through to the bridge; assert it forwards args
    # and returns the bridge result unchanged (bridge parsing is tested in
    # test_bridge.py against a mocked HTTP boundary).
    seen = {}

    def fake_rate(symbol, fiat="USD"):
        seen["args"] = (symbol, fiat)
        return {"token": symbol, "rate": "1.0", "source": "coingecko"}

    monkeypatch.setattr(srv.bridge, "get_token_fiat_rate", fake_rate)
    res = srv.get_token_fiat_rate("USDC", "EUR")
    assert seen["args"] == ("USDC", "EUR")
    assert res == {"token": "USDC", "rate": "1.0", "source": "coingecko"}


def test_get_token_fiat_rate_tool_annotation_is_open_world():
    assert srv._ORACLE_READ.openWorldHint is True
    assert srv._PURE_READ.openWorldHint is False


def test_check_agent_spend_limits_tool_happy_and_error():
    ok = srv.check_agent_spend_limits("agent-1", 50)
    assert ok["is_allowed"] is True
    err = srv.check_agent_spend_limits("agent-1", "not-a-number")
    assert "error" in err


def test_validate_mandate_expiry_tool_happy_and_error():
    ok = srv.validate_mandate_expiry(2000, 1000)
    assert ok["is_valid"] is True
    err = srv.validate_mandate_expiry("bad", 1000)
    assert "error" in err


def test_normalize_token_amount_tool_happy_and_error():
    ok = srv.normalize_token_amount(1_000_000, "USDC")
    assert ok["amount"] == "1"
    assert ok["decimals"] == 6
    err = srv.normalize_token_amount(1_000_000, "DOGE")
    assert "error" in err


def test_verify_x402_signature_tool_happy_and_error():
    acct = Account.from_key(_TEST_PRIVKEY)
    mandate_json = '{"payer":"Alice","amount":"1.00"}'
    signed = acct.sign_message(encode_defunct(text=mandate_json))
    ok = srv.verify_x402_signature(
        mandate_json, signed.signature.hex(), acct.address
    )
    assert ok["is_valid"] is True
    assert ok["recovered_address"].lower() == acct.address.lower()
    err = srv.verify_x402_signature(mandate_json, "0xnothex", acct.address)
    assert "error" in err


def test_validate_eip712_permit_tool_happy_and_error():
    permit = {
        "owner": "0x" + "a" * 40,
        "spender": "0x" + "b" * 40,
        "value": "1000000",
        "nonce": "0",
        "deadline": "2000",
    }
    ok = srv.validate_eip712_permit(permit, 1000)
    assert ok["is_valid"] is True
    err = srv.validate_eip712_permit(permit, "bad")
    assert "error" in err


def test_main_runs_server(monkeypatch):
    called = {}
    monkeypatch.setattr(
        srv.server, "run", lambda: called.setdefault("ran", True)
    )
    srv.main()
    assert called["ran"] is True


# --- prompt -----------------------------------------------------------------


def test_audit_prompt_registered():
    names = {p.name for p in srv.server._prompt_manager.list_prompts()}
    assert "audit_agent_spending_mandate" in names


def test_audit_prompt_default_and_named_agent():
    # Default (empty) branch: no specific agent named.
    generic = srv.audit_agent_spending_mandate()
    assert "the AP2 agent" in generic
    # Named branch: the agent id is woven into the guidance.
    named = srv.audit_agent_spending_mandate("agent-77")
    assert "agent-77" in named
    # Both teach the full workflow in order.
    for text in (generic, named):
        assert "normalize_ap2" in text
        assert "normalize_x402" in text
        assert "check_mandate" in text
        assert "to_pain001" in text
        assert "to_pacs008" in text


# --- resources --------------------------------------------------------------


def test_guardrails_static_resource_lists_ids():
    resources = {
        str(r.uri) for r in srv.server._resource_manager.list_resources()
    }
    assert "ap2://guardrails" in resources
    payload = json.loads(srv.guardrail_policies())
    assert payload == {"policies": ["default"]}


def test_guardrails_templated_resource_registered():
    templates = {
        t.uri_template for t in srv.server._resource_manager.list_templates()
    }
    assert "ap2://guardrails/{policy_id}" in templates


def test_guardrail_policy_default_reflects_check_mandate():
    policy = json.loads(srv.guardrail_policy("default"))
    assert policy["policy_id"] == "default"
    # Required fields are sourced from the bridge, so they cannot drift.
    assert policy["required_fields"] == list(bridge._REQUIRED)
    assert policy["spend_cap"]["severity"] == "violation"
    assert policy["expiry"]["severity"] == "violation"
    # Missing proof is only a warning, matching check_mandate.
    assert policy["proof"]["severity"] == "warning"


def test_guardrail_policy_unknown_id_returns_error():
    err = json.loads(srv.guardrail_policy("nope"))
    assert "error" in err
    assert "nope" in err["error"]
