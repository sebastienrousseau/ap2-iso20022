<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# ap2-iso20022 Architecture

A map of the codebase for new contributors and maintainers. The goal is
that anyone can navigate, extend, and reason about ap2-iso20022 without
prior context.

## The pipeline

```
AP2 mandate / x402 payment payload
        |
        v
ap2_iso20022/bridge.py       (from_ap2, from_x402 -> canonical mandate)
        |
        v
ap2_iso20022/bridge.py       (check_mandate and the other guardrails:
        |                     spend caps, expiry, signature, permit)
        v
ap2_iso20022/bridge.py       (to_pain001, to_pacs008 -> ISO 20022 record)
        |
        v
pain001 / pacs008            (generate the wire-valid XML; not this package)
```

The MCP server (`ap2_iso20022/server.py`) is a thin layer over the
bridge: every tool is a small adapter that calls one bridge function and
returns a JSON-serialisable result. An MCP client reaches it over stdio,
streamable HTTP or SSE.

**Nothing here moves money.** The bridge normalises, checks and converts.
Generating and sending the ISO 20022 message is a separate, explicit
step the caller takes with `pain001` or `pacs008`.

## Module map

| Area | Module | Responsibility |
| :--- | :--- | :--- |
| **Bridge** | `ap2_iso20022/bridge.py` | The library: normalisation, guardrails, conversion, the price oracle |
| **Server** | `ap2_iso20022/server.py` | The MCP server, all tool / resource / prompt registrations |
| **Entry point** | `ap2_iso20022.server:main` (console script: `ap2-iso20022-mcp`) | Launches the server over stdio, or over streamable HTTP / SSE with `--transport` (`_cli.py` + `_transports.py`, ADR 0001) |
| **SDK shim** | `ap2_iso20022/_mcp_compat.py` | Builds the server on either supported major of the `mcp` SDK (2.x `MCPServer`, 1.x `FastMCP`) |
| **Version** | `ap2_iso20022/__init__.py` | Single source of truth (`__version__`) |
| **Tests** | `tests/test_bridge.py`, `tests/test_server.py`, `tests/test_transports.py`, `tests/test_mcp_sdk_compat.py`, `tests/test_suite_conformance.py` | The bridge, the tool surface, the command line, the SDK shim, and the shared suite conformance gate |
| **Examples** | `examples/01_ap2_to_pain001.py`, `examples/02_x402_to_pacs008.py`, `examples/03_guardrails.py` | Runnable walkthroughs; CI runs every one |
| **Benchmarks** | `benches/bench_bridge.py` | Per-payment cost; `docs/index.md` explains the result |
| **Release helpers** | `scripts/verify_versions.py`, `scripts/check_suite_consistency.py` | Assert every restatement of the version agrees; compare the tree against what PyPI has published |

## Tools, resources, prompts

The current MCP surface:

- **Tools** - `normalize_ap2`, `normalize_x402`, `check_mandate`,
  `to_pain001`, `to_pacs008`, `check_agent_spend_limits`,
  `validate_mandate_expiry`, `normalize_token_amount`,
  `verify_x402_signature`, `validate_eip712_permit`, and
  `get_token_fiat_rate` (the one tool that makes an outbound call; needs
  the `oracle` extra).
- **Resources** - `ap2://guardrails` (the policy ids) and
  `ap2://guardrails/{policy_id}` (the policy `check_mandate` enforces,
  as JSON).
- **Prompts** - `audit_agent_spending_mandate(agent_id=...)` (normalise,
  guardrail, then convert, in that order).

## Key design decisions

- **Transform and validate, never settle.** No function in the package
  initiates a payment, sends a message or calls a settlement endpoint.
  That separation is what lets an agent hold this library without
  holding the ability to spend.
- **One canonical mandate.** Both protocols normalise to one plain dict;
  every guardrail and converter speaks it (`docs/index.md`).
- **Errors as data.** Tools never raise. A `ValueError` becomes an
  `{"error": ...}` payload so the agent can reason about failure without
  parsing tracebacks.
- **The caller supplies the clock.** `validate_mandate_expiry`,
  `validate_eip712_permit` and `check_mandate(as_of=...)` compare against
  a time the caller passes; the server never reads the clock.
- **Rejection costs what acceptance costs.** Signature recovery runs
  either way, so there is no early exit to time
  (`benches/bench_bridge.py` reports the ratio).
- **Loopback by default.** stdio needs no socket. The HTTP transports
  bind `127.0.0.1` unless told otherwise and add no authentication of
  their own; a routable deployment sits behind a gateway (ADR 0001).
- **One outbound call, and it is named.** `get_token_fiat_rate` is the
  only function that reaches the network; `httpx` is an optional extra
  and imported lazily so the core never needs it.
- **Coverage enforced at 100%** line+branch; only the SDK-major branch
  that cannot be installed alongside the other is `# pragma: no cover`.

## Extension points

- **Add a guardrail or converter:** add a function in
  `ap2_iso20022/bridge.py` with a test for the refusal path as well as
  the acceptance path (`CONTRIBUTING.md`).
- **Add a tool:** add a function under `@server.tool(...)` in
  `ap2_iso20022/server.py`; pair it with tests in
  `tests/test_server.py` and add it to `EXPECTED_TOOLS` there.
- **Add a resource:** `@server.resource("ap2://...")` decorator.
- **Add a prompt:** `@server.prompt()` decorator.

## Where to look first

- Runnable examples: [`examples/`](examples/)
- The canonical mandate and every function: [`docs/index.md`](docs/index.md)
- Decisions: [`docs/adr/`](docs/adr/index.md)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Release process: [`RELEASING.md`](RELEASING.md)
