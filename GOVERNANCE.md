<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# ap2-iso20022 Governance

This document describes how ap2-iso20022 is run, how decisions are made,
and how to take on responsibility for it. It exists to make the project
legible and sustainable - and, candidly, to reduce its dependence on any
single person.

## Mission and scope

ap2-iso20022 turns an agent-payment authorisation - an AP2 (Agent
Payments Protocol) mandate or an x402 payment payload - into an ISO
20022 `pain.001` or `pacs.008` record, with the spending-cap, expiry and
authorisation checks that belong in between, and exposes that bridge as
MCP tools, resources and a prompt. It transforms and validates; it never
moves money. Changes are weighed against that scope: correctness,
security, and clarity over feature breadth. A change that would let the
package initiate a payment belongs in a different package.

## Roles

| Role | Who | Can |
| :--- | :--- | :--- |
| **Maintainer** | Listed in [`MAINTAINERS.md`](MAINTAINERS.md) | Merge PRs, cut releases, triage, set direction |
| **Contributor** | Anyone with a merged PR | Propose changes, review, discuss |
| **User** | Everyone | File issues, ask questions, request features |

## Decision making

- **Day-to-day changes** (fixes, docs, tests, additive features within
  scope) proceed by **lazy consensus**: open a PR; if no maintainer
  objects and CI is green, a maintainer merges it.
- **Significant changes** (new public APIs, breaking changes, new
  dependencies, new tools/resources/prompts, any change to a guardrail)
  need explicit approval from a maintainer in the PR, and should start
  as an issue or discussion. Decisions that shape the package are
  written down in [`docs/adr/`](docs/adr/index.md).
- **Disagreement** is resolved by discussion aiming for consensus; if
  none is reached, the lead maintainer decides and records the rationale.

Every change must pass the full quality gate (100% branch coverage,
mypy --strict, ruff, black, CodeQL, the suite conformance test, the
examples and the benchmark) before merge - enforced in CI, not by trust.

## Releases

Releases follow [`RELEASING.md`](RELEASING.md). Only maintainers publish
to PyPI; release authority rests with the lead maintainer and is
expanding to a second maintainer as a standing goal.

## Becoming a maintainer

We actively want more maintainers - it is the single biggest thing that
would de-risk the project.

1. Contribute a few reviewed PRs in an area
   ([`ARCHITECTURE.md`](ARCHITECTURE.md) is the map; good first areas:
   the examples, the docs, a refusal-path test a guardrail is missing).
2. Help triage issues and review others' PRs.
3. Open an issue (or email the lead maintainer) expressing interest.

A maintainer proposes you; with no objection from existing maintainers
within a week, you are added to `MAINTAINERS.md` for your area.

## Sustainability (bus factor)

ap2-iso20022 today has **one** maintainer, which is a real risk for a
package that sits between an agent and a bank instruction. The
mitigations in place:

- **The work is legible:** [`ARCHITECTURE.md`](ARCHITECTURE.md) maps the
  codebase, [`RELEASING.md`](RELEASING.md) documents the release process,
  and the bridge ships with three runnable examples.
- **Quality is enforced by CI,** not by one person's memory.
- **The goal is >= 2 maintainers** with independent release authority.

## Code of conduct & security

Participation is governed by
[`CODE-OF-CONDUCT.md`](CODE-OF-CONDUCT.md). Security issues follow the
private disclosure process in [`SECURITY.md`](SECURITY.md) - please do
not open public issues for vulnerabilities.
