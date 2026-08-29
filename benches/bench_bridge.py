#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (C) 2023-2026 Sebastien Rousseau. All rights reserved.
"""What the bridge costs per payment, and where the cost sits.

An agent making one large payment is not the interesting case. The
interesting case is an agent making a great many small ones — an x402 client
paying per API call, a procurement agent settling dozens of line items — and
there the per-payment cost is the whole cost.

That cost is not evenly spread. Normalising a payload and building an ISO
record is dictionary work. **Recovering a signer from an ECDSA signature is
elliptic-curve arithmetic**, and it is expected to dominate by orders of
magnitude. Knowing by how much decides whether a batch of a thousand
mandates is a second's work or a minute's.

Three things are measured:

* **The pipeline without cryptography** — ``from_ap2``, ``from_x402``,
  ``check_mandate``, ``to_pain001``, ``to_pacs008``. These should be
  microseconds.
* **``verify_x402_signature``** — the expensive one, reported beside the
  rest so the ratio is visible rather than assumed.
* **Verification that fails against verification that succeeds.** A
  signature check that returns faster when it *rejects* leaks information
  about how far it got. Recovery has to happen either way, so the two
  should cost the same; a large gap is worth investigating.

Run::

    python benches/bench_bridge.py
    python benches/bench_bridge.py --json
    python benches/bench_bridge.py --quick     # what CI runs

Nothing here asserts a threshold: wall-clock is not comparable between
machines, and a flaky performance gate teaches people to ignore red. CI
runs ``--quick`` so a benchmark that has stopped compiling against the
current API fails the build instead of rotting into a file that reads as
verified and is not.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

from ap2_iso20022 import bridge  # noqa: E402

AP2_INTENT = {
    "intent_id": "AP2-BENCH",
    "payer": "Alice Agent",
    "payer_account": "DE89370400440532013000",
    "payer_agent_bic": "DEUTDEFF",
    "merchant_name": "Bob Merchant",
    "payee_account": "GB29NWBK60161331926819",
    "payee_agent_bic": "NWBKGB2L",
    "value": "250.00",
    "currency_code": "EUR",
    "memo": "Order 42",
    "execution_date": "2026-03-02",
    "signature": "eyJhbGciOiJFUzI1NiJ9.demo.signature",
    "signature_type": "jws",
    "max_amount": "500.00",
    "expiry": "2026-12-31",
}

X402_REQUIREMENT = {
    "resource": "https://api.example.com/feed",
    "recipient": "Data Vendor Ltd",
    "payTo": "GB29NWBK60161331926819",
    "maxAmountRequired": "5.00",
    "asset": "USDC",
    "from": "Research Agent",
    "from_address": "DE89370400440532013000",
    "scheme": "exact",
    "signature": "0xdeadbeef",
}


def _best(call, repeats: int) -> float:
    """Best-of timing after one untimed warm-up.

    The minimum is the least noisy estimator available; the mean follows
    whatever else the machine is doing. The warm-up matters here because
    ``eth_account`` builds its curve tables lazily on first use.
    """
    call()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    return min(samples)


def _signed_mandate() -> tuple[str, str, str]:
    """A real signature over a real payload, and the address that made it."""
    account = Account.create()
    mandate_json = json.dumps({"mandate_id": "M-BENCH", "amount": "5.00"})
    signed = Account.sign_message(
        encode_defunct(text=mandate_json), private_key=account.key
    )
    return mandate_json, signed.signature.hex(), account.address


def run(quick: bool) -> dict:
    repeats = 20 if quick else 200
    crypto_repeats = 5 if quick else 30

    mandate_ap2 = bridge.from_ap2(AP2_INTENT)
    mandate_json, signature_hex, address = _signed_mandate()
    wrong_address = "0x" + "0" * 40

    steps = [
        ("from_ap2", lambda: bridge.from_ap2(AP2_INTENT)),
        ("from_x402", lambda: bridge.from_x402(X402_REQUIREMENT)),
        ("check_mandate", lambda: bridge.check_mandate(mandate_ap2)),
        ("to_pain001", lambda: bridge.to_pain001(mandate_ap2)),
        ("to_pacs008", lambda: bridge.to_pacs008(mandate_ap2)),
        (
            "check_agent_spend_limits",
            lambda: bridge.check_agent_spend_limits("agent-1", "50.00"),
        ),
        (
            "validate_mandate_expiry",
            lambda: bridge.validate_mandate_expiry(2_000, now_timestamp=1_000),
        ),
        (
            "normalize_token_amount",
            lambda: bridge.normalize_token_amount(1_000_000, "USDC"),
        ),
    ]
    rows = [
        {"step": name, "us": _best(call, repeats) * 1e6, "crypto": False}
        for name, call in steps
    ]

    accept = _best(
        lambda: bridge.verify_x402_signature(
            mandate_json, signature_hex, address
        ),
        crypto_repeats,
    )
    reject = _best(
        lambda: bridge.verify_x402_signature(
            mandate_json, signature_hex, wrong_address
        ),
        crypto_repeats,
    )
    rows.append(
        {"step": "verify_x402_signature", "us": accept * 1e6, "crypto": True}
    )

    return {
        "steps": rows,
        "signature": {
            "accept_us": accept * 1e6,
            "reject_us": reject * 1e6,
            "reject_over_accept": reject / accept if accept else 0.0,
        },
    }


def render(results: dict) -> None:
    print(f"{'step':>26}{'us/call':>12}{'calls/sec':>14}")
    print("-" * 52)
    for row in results["steps"]:
        rate = 1e6 / row["us"] if row["us"] else 0.0
        print(f"{row['step']:>26}{row['us']:>12.2f}{rate:>14,.0f}")

    plain = [r["us"] for r in results["steps"] if not r["crypto"]]
    crypto = [r["us"] for r in results["steps"] if r["crypto"]]
    if plain and crypto:
        ratio = crypto[0] / max(plain)
        total_plain = sum(plain)
        print(
            f"\n  Signature recovery costs {ratio:,.0f}x the dearest "
            f"non-cryptographic step, and {crypto[0] / total_plain:,.0f}x "
            f"the whole rest of the pipeline put together."
        )
        print(
            f"  A thousand mandates: about "
            f"{total_plain * 1000 / 1e6:.2f} s of bridge work against "
            f"{crypto[0] * 1000 / 1e6:.1f} s if every one is verified. "
            f"Verify once per mandate, not once per conversion."
        )

    sig = results["signature"]
    print("\nsignature verification — accepted against rejected")
    print(
        f"  accept {sig['accept_us']:,.0f} us, reject "
        f"{sig['reject_us']:,.0f} us — ratio {sig['reject_over_accept']:.2f}"
    )
    print(
        "  Near 1.00 is what you want. Recovery has to happen either way,\n"
        "  so a rejection that returns markedly faster would mean the check\n"
        "  short-circuits before doing the work — and the timing would leak\n"
        "  how far it got. Read it across runs: these are sub-millisecond\n"
        "  measurements and one row is noise."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--quick", action="store_true", help="fewer repeats, as CI runs"
    )
    args = parser.parse_args()

    results = run(quick=args.quick)
    if args.json:
        json.dump(results, sys.stdout, indent=1)
        print()
    else:
        render(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
