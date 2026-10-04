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

"""Mock-verified tests for the framework adapters.

The agent frameworks (LangChain, CrewAI, LlamaIndex) are heavy and
conflict-prone, so they are NOT installed in the test environment. Instead
each adapter is exercised against a FAKE framework tool factory injected into
``sys.modules``; the fake records exactly what the adapter passes so we can
assert one framework tool per bridge tool, with the right name, description,
JSON input schema and a working callable. The missing-extra ``ImportError``
branch is covered by forcing the lazy import to fail.

This verifies the adapter LOGIC only; it is mock-verified, not live-verified
against the real frameworks.
"""

import sys
import types

import pytest

pytest.importorskip("mcp")

import ap2_iso20022.adapters as adapters  # noqa: E402
import ap2_iso20022.server as srv  # noqa: E402

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


def _bridge_tool_map() -> dict:
    """Return the bridge's tools keyed by name for cross-checking."""
    return {t.name: t for t in srv.server._tool_manager.list_tools()}


class _Recorder:
    """A fake framework tool factory that records the adapter's call kwargs.

    A single class doubles as every framework's tool type: its classmethods
    (``from_function`` / ``from_defaults``) capture the callable, name,
    description and schema the adapter passes and return a lightweight object
    exposing them for assertions.
    """

    def __init__(self, *, func, name, description, schema):
        """Store the recorded attributes of one wrapped tool."""
        self.func = func
        self.name = name
        self.description = description
        self.schema = schema

    @classmethod
    def from_function(cls, *, func, name, description, args_schema):
        """Record a LangChain/CrewAI-style ``from_function`` construction."""
        return cls(
            func=func, name=name, description=description, schema=args_schema
        )

    @classmethod
    def from_defaults(cls, *, fn, name, description, fn_schema):
        """Record a LlamaIndex-style ``from_defaults`` construction."""
        return cls(
            func=fn, name=name, description=description, schema=fn_schema
        )


class _FakeToolException(Exception):
    """Stand-in for ``langchain_core.tools.ToolException``."""


def _inject(monkeypatch, dotted_names, **attrs):
    """Inject fake modules for a dotted import path into ``sys.modules``.

    Each name in ``dotted_names`` becomes an empty module; the attributes in
    ``attrs`` are set on the deepest (last) module so ``from <last> import X``
    resolves them.
    """
    modules = []
    for dotted in dotted_names:
        mod = types.ModuleType(dotted)
        monkeypatch.setitem(sys.modules, dotted, mod)
        modules.append(mod)
    for key, value in attrs.items():
        setattr(modules[-1], key, value)


def _assert_wrapped_all_tools(built):
    """Assert a built adapter list mirrors the bridge tools one-for-one."""
    bridge = _bridge_tool_map()
    assert {item.name for item in built} == EXPECTED_TOOLS
    assert len(built) == len(bridge)
    for item in built:
        source = bridge[item.name]
        assert item.description == source.description
        assert item.schema == source.parameters
        assert item.schema["type"] == "object"


# ---------------------------------------------------------------------------
# _bridge_tools introspection
# ---------------------------------------------------------------------------
def test_bridge_tools_returns_all_registered_tools():
    names = {t.name for t in adapters._bridge_tools()}
    assert names == EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# _wrap_with_tool_exception: both branches (success + error mapping)
# ---------------------------------------------------------------------------
def test_wrap_with_tool_exception_passes_through_result():
    wrapped = adapters._wrap_with_tool_exception(
        lambda **kw: {"echo": kw}, _FakeToolException
    )
    assert wrapped(query="x") == {"echo": {"query": "x"}}


def test_wrap_with_tool_exception_maps_raised_error():
    def _boom(**kwargs):
        raise ValueError("backend blew up")

    wrapped = adapters._wrap_with_tool_exception(_boom, _FakeToolException)
    try:
        wrapped()
        raised = False
    except _FakeToolException as exc:
        raised = True
        assert "backend blew up" in str(exc)
    assert raised is True


# ---------------------------------------------------------------------------
# LangChain adapter
# ---------------------------------------------------------------------------
def test_as_langchain_tools_wraps_every_tool(monkeypatch):
    _inject(
        monkeypatch,
        ["langchain_core", "langchain_core.tools"],
        StructuredTool=_Recorder,
        ToolException=_FakeToolException,
    )
    built = adapters.as_langchain_tools()
    _assert_wrapped_all_tools(built)

    # The recorded callable is the ToolException-wrapping closure; calling it
    # runs the real bridge tool and returns its payload.
    normalize_tool = next(
        i for i in built if i.name == "normalize_token_amount"
    )
    out = normalize_tool.func(raw_base_units=1000000, token_symbol="USDC")
    assert out == {"amount": "1", "decimals": 6}


def test_as_langchain_tools_missing_extra_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_core", None)
    try:
        adapters.as_langchain_tools()
        raised = False
    except ImportError as exc:
        raised = True
        assert "ap2-iso20022[langchain]" in str(exc)
    assert raised is True


# ---------------------------------------------------------------------------
# CrewAI adapter
# ---------------------------------------------------------------------------
def test_as_crewai_tools_wraps_every_tool(monkeypatch):
    _inject(
        monkeypatch,
        ["crewai", "crewai.tools"],
        CrewStructuredTool=_Recorder,
    )
    built = adapters.as_crewai_tools()
    _assert_wrapped_all_tools(built)

    # CrewAI receives the raw bridge callable unchanged.
    bridge = _bridge_tool_map()
    for item in built:
        assert item.func is bridge[item.name].fn


def test_as_crewai_tools_missing_extra_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "crewai", None)
    try:
        adapters.as_crewai_tools()
        raised = False
    except ImportError as exc:
        raised = True
        assert "ap2-iso20022[crewai]" in str(exc)
    assert raised is True


# ---------------------------------------------------------------------------
# LlamaIndex adapter
# ---------------------------------------------------------------------------
def test_as_llamaindex_tools_wraps_every_tool(monkeypatch):
    _inject(
        monkeypatch,
        ["llama_index", "llama_index.core", "llama_index.core.tools"],
        FunctionTool=_Recorder,
    )
    built = adapters.as_llamaindex_tools()
    _assert_wrapped_all_tools(built)

    # LlamaIndex receives the raw bridge callable unchanged.
    bridge = _bridge_tool_map()
    for item in built:
        assert item.func is bridge[item.name].fn


def test_as_llamaindex_tools_missing_extra_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "llama_index", None)
    try:
        adapters.as_llamaindex_tools()
        raised = False
    except ImportError as exc:
        raised = True
        assert "ap2-iso20022[llamaindex]" in str(exc)
    assert raised is True


# ---------------------------------------------------------------------------
# The adapters are plain module functions, not @server.tool: the bridge's
# advertised tool-set must be unchanged by importing/using them.
# ---------------------------------------------------------------------------
def test_adapters_do_not_alter_registered_toolset():
    names = {t.name for t in srv.server._tool_manager.list_tools()}
    assert names == EXPECTED_TOOLS
