<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Security Policy

## Supported versions

This project is in its `0.0.x` series; only the most recent release line
receives fixes.

| Version | Supported |
| ------- | --------- |
| 0.0.4   | :white_check_mark: |
| < 0.0.4 | :x:               |

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/sebastienrousseau/ap2-iso20022/security/advisories/new).
Please do not open a public issue for a security problem.

Include what you did, what happened, and what you expected. A payload that
reproduces it is worth more than a description of it.

## What this package is, and is not

**It does not move money.** The bridge normalises an AP2 or x402
authorisation, checks it, and produces a record. Generating and sending the
ISO 20022 message is a separate, explicit step the caller takes. That
boundary is deliberate: an agent-facing component should not also be the
thing that can initiate a payment.

**It is not an authorisation service.** `verify_x402_signature` recovers a
signer and compares it to the address the mandate names. It does not decide
whether that signer *should* be allowed to pay — that is your policy, and
`check_agent_spend_limits` is a floor, not a substitute for one.

## Where the security boundary sits

Three functions decide whether an agent's claim is honoured:

- `verify_x402_signature` — cryptographic proof the mandate is the one its
  holder signed.
- `validate_eip712_permit` — structural and temporal validity of a permit.
- `check_agent_spend_limits` / `validate_mandate_expiry` — the caps and the
  clock.

A signature that recovers to the wrong address returns `is_valid: False`
with `recovered_address` populated. **Treat that as a refusal, not a
warning.** The mandate is genuinely signed; it is simply not signed by the
party it names, which is precisely the shape a substitution attack takes.

Rejection is measured to cost the same as acceptance
(`benches/bench_bridge.py`, ratio ~1.05). Recovery happens either way, so
there is no early exit to time. If that ratio ever moves materially below
1.00, treat it as a finding.

## What the bridge does not check

Conversion builds a record; schema validation is downstream at generation.
`check_mandate` returns `ok: True` for a mandate that produces a settlement
date of `1970-01-01`, a token symbol where ISO 4217 is expected, or empty
agent BICs. See `docs/index.md`. If you are not validating downstream before
sending, check these yourself.

## Dependencies

Cryptography comes from `eth-account`. Report vulnerabilities in it upstream;
this project will take the patched release and cut a version.
