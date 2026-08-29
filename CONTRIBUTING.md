<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Contributing

Thanks for looking. This package does one thing: it turns an agent-payment
authorisation into a bank instruction, with the checks that belong in
between.

## Before you open a pull request

Everything CI checks, you can run locally:

```sh
pip install -e ".[dev]"
pytest                                  # tests plus the coverage gate
ruff check ap2_iso20022/ tests/ examples/ benches/
black --check ap2_iso20022/ tests/ examples/ benches/
mypy ap2_iso20022/
python benches/bench_bridge.py --quick  # the benchmark still runs
```

`pytest` fails below **100% branch coverage**. That is not ambitious for a
package this size, and the branches that go untested are the refusal paths —
which is where a payments bridge earns its keep.

## The rule that matters most

**Nothing in this package may move money.** The bridge transforms and
validates. If a change would let this code initiate a payment, send a
message, or call a settlement endpoint, it belongs in a different package.
That separation is what lets an agent hold this library without holding the
ability to spend.

## Changing a guardrail

`verify_x402_signature`, `validate_eip712_permit`,
`check_agent_spend_limits` and `validate_mandate_expiry` are the security
boundary. A change to any of them needs:

- a test for the **refusal** path, not only the acceptance path;
- a note in `SECURITY.md` if the shape of what is refused changes;
- for signature verification, a check that rejection still costs roughly
  what acceptance costs — `benches/bench_bridge.py` reports the ratio, and a
  rejection that returns early would leak how far the check got.

## Benchmarks

`benches/` measures per-payment cost, because an agent making many small
payments is the case that matters. It asserts nothing — wall-clock is not
comparable between machines — but CI runs it with `--quick` so a benchmark
that stops compiling fails the build rather than rotting.

If you make signature verification cheaper, say so in the changelog with the
before and after. It is currently ~1,450x the dearest other step and is the
only number here worth optimising.

## The shared conformance file

`tests/test_suite_conformance.py` is generated from one canonical copy shared
across all 32 repositories in the suite. **Do not edit it here.** A local
edit fails `test_this_file_is_the_canonical_copy` by design; the point is
that no repository can quietly weaken a shared gate.

## Versioning

**Versions increment by 0.0.1.** `0.1.0` follows `0.0.999`, not `0.0.9`.

The version appears in `pyproject.toml` and `ap2_iso20022/__init__.py`.
Change both and add a `CHANGELOG.md` entry; the conformance tests check they
agree.

## Licence

Apache-2.0 OR MIT, at your option. By contributing you agree your work is
released under the same dual grant.
