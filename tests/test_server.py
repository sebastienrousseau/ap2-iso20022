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

import pytest

pytest.importorskip("mcp")

import ap2_iso20022.server as srv  # noqa: E402
from ap2_iso20022 import __version__  # noqa: E402

EXPECTED_TOOLS = {
    "normalize_ap2",
    "normalize_x402",
    "check_mandate",
    "to_pain001",
    "to_pacs008",
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


def test_main_runs_server(monkeypatch):
    called = {}
    monkeypatch.setattr(
        srv.server, "run", lambda: called.setdefault("ran", True)
    )
    srv.main()
    assert called["ran"] is True
