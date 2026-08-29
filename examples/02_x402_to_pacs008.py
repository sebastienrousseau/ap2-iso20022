#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright (C) 2023-2026 Sebastien Rousseau. All rights reserved.
"""An x402 payment requirement becomes a pacs.008 record.

x402 is the HTTP 402 revival: a server answers a request with what it wants
paid, and the agent pays to continue. That is a settlement instruction in
everything but format. This turns it into one a correspondent bank accepts.

Run with ``python examples/02_x402_to_pacs008.py``.
"""

from ap2_iso20022.bridge import check_mandate, from_x402, to_pacs008

X402_REQUIREMENT = {
    "resource": "https://api.example.com/premium-feed",
    "recipient": "Data Vendor Ltd",
    "payTo": "GB29NWBK60161331926819",
    "payee_agent_bic": "NWBKGB2L",
    "maxAmountRequired": "5.00",
    "asset": "USDC",
    "from": "Research Agent",
    "from_address": "DE89370400440532013000",
    "payer_agent_bic": "DEUTDEFF",
    "scheme": "exact",
    "signature": "0xdeadbeef",
    "signature_type": "eip712",
}


def main() -> None:
    """Normalise an x402 requirement and settle it over a bank rail."""
    mandate = from_x402(X402_REQUIREMENT)
    print("canonical mandate")
    for key in (
        "mandate_id",
        "payer_name",
        "payee_name",
        "amount",
        "currency",
    ):
        print(f"  {key:20} {mandate.get(key)!r}")

    verdict = check_mandate(mandate)
    print(f"\nguardrails            ok={verdict['ok']}")
    for violation in verdict["violations"]:
        print(f"  - {violation}")
    for warning in verdict["warnings"]:
        print(f"  ! {warning}")

    if not verdict["ok"]:
        print("\nRefused. A failed mandate produces no ISO record.")
        return

    record = to_pacs008(mandate)
    print("\npacs.008 record")
    for key in sorted(record):
        print(f"  {key:32} {record[key]!r}")


if __name__ == "__main__":
    main()
