<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# ap2-iso20022 Roadmap

This roadmap tracks what is planned for the AP2 / x402 to ISO 20022
bridge and its MCP server. It summarises the CHANGELOG and the open
issues; it does not promise work that is not tracked there. Releases
ship when the gates pass, not on a calendar.

## v0.0.5 (current)

- The bridge: `from_ap2`, `from_x402`, `check_mandate`, `to_pain001`,
  `to_pacs008`, plus the spend-cap, expiry, token-normalisation, Web3
  signature, EIP-2612 permit and price-oracle helpers.
- Eleven MCP tools over the bridge, two resources (`ap2://guardrails`,
  `ap2://guardrails/{policy_id}`) and one prompt
  (`audit_agent_spending_mandate`).
- 100% branch coverage gate, the shared suite conformance test, a
  per-payment benchmark, and a scheduled check that the tree agrees with
  what PyPI has published.

## Next release (on `main`, unreleased)

- stdio, streamable HTTP (2026-07-28 and 2025-11-25) and SSE from one
  command line (ADR 0001).
- Runs on both supported majors of the `mcp` SDK through a
  compatibility shim; a fresh install gets 2.x.

## Beyond

No further work is scheduled. There are no open feature issues at the
time of writing. Three behaviours recorded in `docs/index.md` are
candidates if a user needs them, none is planned: `from_x402` does not
read agent BICs, a missing `execution_date` becomes `1970-01-01`, and a
token symbol passes through where ISO 4217 is expected.

## Out of scope (handled elsewhere)

- **Generating and sending the XML** - see
  [`pain001`](https://github.com/sebastienrousseau/pain001) and
  [`pacs008`](https://github.com/sebastienrousseau/pacs008-mcp); this
  package produces the record they consume and never moves money.
- **Authorisation policy** - `check_agent_spend_limits` is a floor, not
  a policy engine (`SECURITY.md`).
