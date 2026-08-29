#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (C) 2023-2026 Sebastien Rousseau. All rights reserved.
"""The guardrails, and what each one refuses.

An agent authorised to spend is an agent that can spend wrongly. These are
the checks that sit between a mandate and a payment instruction: a spending
cap, an expiry, and a cryptographic proof that the mandate is the one its
holder signed.

Every check here is local. Nothing calls out, and nothing moves money.

Run with ``python examples/03_guardrails.py``.
"""

import json

from eth_account import Account

from ap2_iso20022.bridge import (
    check_agent_spend_limits,
    normalize_token_amount,
    validate_mandate_expiry,
    verify_x402_signature,
)


def spend_limits() -> None:
    """Three caps: per transaction, per day, per month."""
    print("spend limits")
    allowed = check_agent_spend_limits("agent-1", "50.00")
    print(
        f"  $50   allowed={allowed['is_allowed']} "
        f"remaining_daily={allowed['remaining_daily_cap']}"
    )

    refused = check_agent_spend_limits("agent-1", "6000.00", per_tx_cap=10_000)
    print(f"  $6000 allowed={refused['is_allowed']}")
    for violation in refused["violations"]:
        print(f"    - {violation}")


def expiry() -> None:
    """A mandate outlives its usefulness before it outlives its signature."""
    print("\nexpiry")
    live = validate_mandate_expiry(2_000, now_timestamp=1_000)
    print(f"  expires at 2000, now 1000 -> is_valid={live['is_valid']}")
    dead = validate_mandate_expiry(500, now_timestamp=1_000)
    print(f"  expires at  500, now 1000 -> is_valid={dead['is_valid']}")
    for violation in dead.get("violations", []):
        print(f"    - {violation}")


def signature() -> None:
    """Recover the signer and check it is who the mandate claims.

    A signature that verifies against the wrong address is not an error --
    it is a *refusal*, and the distinction matters: the mandate is
    well-formed and signed, just not by the party it names.
    """
    print("\nsignature")
    account = Account.create()
    mandate_json = json.dumps({"mandate_id": "M-1", "amount": "5.00"})
    signed = Account.sign_message(
        __import__(
            "eth_account.messages", fromlist=["encode_defunct"]
        ).encode_defunct(text=mandate_json),
        private_key=account.key,
    )
    signature_hex = signed.signature.hex()

    good = verify_x402_signature(mandate_json, signature_hex, account.address)
    print(f"  correct address -> is_valid={good['is_valid']}")

    other = "0x" + "0" * 40
    bad = verify_x402_signature(mandate_json, signature_hex, other)
    print(
        f"  wrong address   -> is_valid={bad['is_valid']} "
        f"(recovered {bad['recovered_address'][:10]}...)"
    )


def token_amounts() -> None:
    """Base units are not human amounts, and the difference is 10^18."""
    print("\ntoken amounts")
    for raw, symbol in (
        (1_000_000, "USDC"),
        (1_500_000, "USDC"),
        (10**18, "ETH"),
    ):
        result = normalize_token_amount(raw, symbol)
        print(
            f"  {raw:>19} {symbol:<5} -> {result['amount']} "
            f"({result['decimals']} decimals)"
        )


def main() -> None:
    """Run every guardrail demonstration."""
    spend_limits()
    expiry()
    signature()
    token_amounts()


if __name__ == "__main__":
    main()
