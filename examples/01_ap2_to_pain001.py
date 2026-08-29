#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (C) 2023-2026 Sebastien Rousseau. All rights reserved.
"""An AP2 mandate becomes a pain.001 record.

AP2 says *an agent is authorised to pay*. It does not say how the money
moves. This turns that authorisation into the record a bank rail accepts.

Nothing here moves money. The bridge transforms and checks; generating and
sending the message stays a separate, explicit step for the caller.

Run with ``python examples/01_ap2_to_pain001.py``.
"""

from ap2_iso20022.bridge import check_mandate, from_ap2, to_pain001

AP2_INTENT = {
    "intent_id": "AP2-9",
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


def main() -> None:
    """Normalise, check, and convert an AP2 intent."""
    mandate = from_ap2(AP2_INTENT)
    print("canonical mandate")
    for key in ("mandate_id", "payer_name", "amount", "currency", "reference"):
        print(f"  {key:20} {mandate.get(key)!r}")

    # `check_mandate` answers under the key "ok". The other checks in this
    # module answer under "is_valid" or "is_allowed" -- see docs/index.md,
    # which records the inconsistency rather than pretending it away.
    verdict = check_mandate(mandate, as_of="2026-03-01")
    print(f"\nguardrails            ok={verdict['ok']}")
    for violation in verdict["violations"]:
        print(f"  - {violation}")
    for warning in verdict["warnings"]:
        print(f"  ! {warning}")

    if not verdict["ok"]:
        print("\nRefused. No ISO record is produced from a failed mandate.")
        return

    record = to_pain001(mandate)
    print("\npain.001 record")
    for key in sorted(record):
        print(f"  {key:26} {record[key]!r}")


if __name__ == "__main__":
    main()
