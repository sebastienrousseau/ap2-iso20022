<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.4] - 2026-08-29

The first release since 0.0.2. **`0.0.3` was bumped in the tree but never
tagged or published**, so everything below has been sitting unreleased —
including a `cryptography` advisory floor that has therefore never reached a
dependent.

This release also brings the repository onto the suite conformance gate. It
had no `CHANGELOG.md`, no `CONTRIBUTING.md`, no `SECURITY.md`, and no
`docs/`, `examples/` or `benches/` directory.

### Fixed

- **`cryptography` floored at 50.0.0**, the release patching a
  high-severity advisory (#7, #8). Cut as `0.0.3` in the tree and never
  published, so no dependent has had it until now.

### Added

- **`benches/bench_bridge.py`** — per-payment cost, which is the only cost
  that matters for an agent making many small payments.

  The result is stark and was not previously measured: **signature recovery
  costs about 1,450x the dearest other step**, and roughly **360x the whole
  rest of the pipeline combined**. Normalising, checking and converting a
  mandate is around 10 microseconds; verifying its signature is about
  **3.8 milliseconds**.

  The practical consequence is a design rule: **verify once per mandate,
  not once per conversion**, and treat roughly **266 verifications per
  second** as the single-core ceiling. An x402 client paying per API call
  meets that long before it meets anything else here.

  Rejection is measured against acceptance too (~1.05). Recovery has to
  happen either way, so a rejection returning markedly faster would mean an
  early exit whose timing leaks how far the check got.

- **`docs/index.md`** — the canonical mandate, every function, and a
  section on what conversion does *not* check.

- **`examples/`** — three runnable examples: AP2 to `pain.001`, x402 to
  `pacs.008`, and the guardrails.

- **`SECURITY.md`** and **`CONTRIBUTING.md`**, both stating the rule that
  matters most: nothing in this package may move money.

- **`tests/test_suite_conformance.py`** — invariants shared across the
  suite, vendored from one canonical copy and checksummed by its own test.

### Documented

Writing the examples surfaced three behaviours that were not written down
anywhere. None is changed here; all three are now recorded in
`docs/index.md`:

- **`from_x402` does not read agent BICs.** A `pacs.008` built from an x402
  payload carries **empty** `debtor_agent_bic` and `creditor_agent_bic`.
- **A missing `execution_date` becomes `1970-01-01`** in
  `interbank_settlement_date` — the Unix epoch, silently.
- **A token symbol passes straight through**: `asset: "USDC"` becomes
  `interbank_settlement_currency: "USDC"`, where ISO 20022 expects ISO 4217.

`check_mandate` returns `ok: True` for all three. Schema validation
downstream at generation is the intended backstop; that split is
deliberate, but a caller who is not validating before sending should check
these.

- **An API inconsistency, recorded rather than smoothed over.**
  `check_mandate` answers under `ok`, while `validate_mandate_expiry` and
  `verify_x402_signature` answer under `is_valid` and
  `check_agent_spend_limits` under `is_allowed`.

## [0.0.2] - 2026-07-16

### Added

- Spend-cap, expiry, token-normalisation, Web3 signature and price-oracle
  tools (#5).
- Prompts and resources, for parity across the MCP suite (#4).
- `glama.json`, so Glama can build the server.

### Fixed

- `mcp` capped below 2.0. 2.0 removed `mcp.server.fastmcp`, the import this
  server uses (#3).
- The MCP inspector spawns the `ap2-iso20022-mcp` console script rather
  than `ap2-iso20022`.

### Changed

- Release workflow emits real provenance and an SBOM on publish (#2).
- Licensing ships as `Apache-2.0 OR MIT` (#9).

## [0.0.1] - 2026-07-02

Initial release: the AP2/x402 to ISO 20022 bridge, with `from_ap2`,
`from_x402`, `check_mandate`, `to_pain001` and `to_pacs008`, and an MCP
server exposing them as agent tools.

[0.0.4]: https://github.com/sebastienrousseau/ap2-iso20022/releases/tag/v0.0.4
[0.0.2]: https://github.com/sebastienrousseau/ap2-iso20022/releases/tag/v0.0.2
[0.0.1]: https://github.com/sebastienrousseau/ap2-iso20022/releases/tag/v0.0.1
