# ap2-iso20022

Turn an agent's authorisation to pay into a bank instruction that will
actually settle.

```python
from ap2_iso20022.bridge import from_ap2, check_mandate, to_pain001

mandate = from_ap2(ap2_intent)
verdict = check_mandate(mandate)
if verdict["ok"]:
    record = to_pain001(mandate)
```

## The gap this fills

**AP2** (Google's Agent Payments Protocol) and **x402** (the HTTP 402 revival)
sit *above* settlement. They express that an agent is authorised to pay. They
say nothing about the message that moves the money.

Banks settle in ISO 20022. So between "the agent may pay £250" and a payment
leaving an account there is a translation nobody had standardised — and it is
the translation where the interesting mistakes live: an expired mandate, a
cap already spent, a signature that verifies against the wrong key.

This package is that translation, plus the checks that belong in it.

**Nothing here moves money.** The bridge transforms and validates. Producing
the ISO record is deliberately separate from generating and sending the
message, so money movement stays an explicit action the caller has to take.

## The canonical mandate

Both protocols normalise to one plain dict. Every function below speaks it.

| Field | Meaning |
|---|---|
| `mandate_id` | The authorisation's own identifier |
| `payer_name`, `payer_account_iban`, `payer_agent_bic` | Who pays, and from where |
| `payee_name`, `payee_account_iban`, `payee_agent_bic` | Who is paid, and to where |
| `amount`, `currency` | What is owed |
| `reference` | What it is for |
| `execution_date` | When it should settle |
| `max_amount` | The ceiling the mandate itself authorises |
| `expiry` | When the authorisation lapses |
| `proof_type`, `proof_value` | How the authorisation is evidenced |

## Normalising

### `from_ap2(payload) -> dict`

Accepts an AP2 intent. Reads `intent_id`/`id`, `payer`, `payer_account`,
`merchant_name`, `payee_account`, `value`, `currency_code`, `memo`,
`signature`, `signature_type`, and their aliases.

### `from_x402(payload) -> dict`

Accepts an x402 payment requirement. Reads `resource`, `from`,
`from_address`, `recipient`, `payTo`, `maxAmountRequired`, `asset`, `scheme`,
`signature`, and their aliases.

> **`from_x402` does not read agent BICs.** There is no `payer_agent_bic` or
> `payee_agent_bic` in its key list, so a `pacs.008` built from an x402
> payload carries **empty agent BICs**. If you are settling over a
> correspondent rail, set them on the mandate yourself after normalising.

## Checking

### `check_mandate(mandate, as_of=None) -> dict`

Returns `{"ok": bool, "violations": [...], "warnings": [...]}`.

> **Note the key.** `check_mandate` answers under `ok`. The other checks
> answer under `is_valid`, and `check_agent_spend_limits` under `is_allowed`.
> That inconsistency is real and is recorded here rather than smoothed over;
> reading the wrong key silently gives you `KeyError` at best and a truthy
> dict at worst.

### `check_agent_spend_limits(agent_id, proposed_amount_usd, per_tx_cap=1000, daily_cap=5000, monthly_cap=20000) -> dict`

Returns `{"is_allowed": bool, "violations": [...], "remaining_daily_cap": ...}`.

### `validate_mandate_expiry(expiration_timestamp, now_timestamp) -> dict`

Returns `{"is_valid": bool, ...}`.

### `verify_x402_signature(mandate_json, signature_hex, expected_address) -> dict`

Recovers the signer from an ECDSA signature and compares it to the address
the mandate names. Returns `{"is_valid": bool, "recovered_address": str}`.

A signature that recovers to a *different* address is a **refusal, not an
error**: the mandate is well-formed and genuinely signed, just not by the
party it claims. `is_valid` is `False` and `recovered_address` tells you who
actually signed it.

### `validate_eip712_permit(permit, now_timestamp) -> dict`

Returns `{"is_valid": bool, "violations": [...]}`.

## Converting

`to_pain001(mandate)` and `to_pacs008(mandate)` produce records that feed
straight into the `pain001` and `pacs008` packages.

### What conversion does *not* check

The bridge builds a record; **schema validation happens downstream at
generation**, which is a deliberate split. What that means in practice is
worth stating, because the conversion itself will not stop you:

- **A missing `execution_date` becomes `1970-01-01`** in
  `interbank_settlement_date` — the Unix epoch, not an error.
- **A token symbol passes straight through.** `asset: "USDC"` becomes
  `interbank_settlement_currency: "USDC"`, where ISO 20022 wants an ISO 4217
  code.
- **Empty agent BICs are produced without complaint** for x402 input, as
  above.

`check_mandate` returns `ok: True` for all three. Check them yourself if you
are not validating downstream before sending.

*Honest limit: this list is what the bridge was observed to emit. Whether
`pain001`/`pacs008` generation rejects each case has not been verified end to
end here, so treat the downstream backstop as intended rather than proven.*

## Performance

[`benches/bench_bridge.py`](../benches/bench_bridge.py) measures per-payment
cost, which is the only cost that matters for an agent making many small
payments.

```
                      step     us/call     calls/sec
                  from_ap2        2.58       387,143
             check_mandate        0.58     1,715,243
                to_pain001        1.46       685,878
     verify_x402_signature     3765.33           266
```

**Signature recovery costs about 1,450x the dearest other step**, and roughly
360x the whole rest of the pipeline combined. A thousand mandates is ~0.01 s
of bridge work and ~3.8 s if every one is verified.

The practical consequence: **verify once per mandate, not once per
conversion**, and treat ~266 verifications/second as the ceiling on a single
core. An x402 client paying per API call will hit that long before it hits
anything else here.

Rejection costs the same as acceptance (ratio ~1.05), which is what you want:
recovery happens either way, so a faster rejection would leak how far the
check got.

## Worked examples

All three run standalone with no arguments and no network:

- [`examples/01_ap2_to_pain001.py`](../examples/01_ap2_to_pain001.py)
- [`examples/02_x402_to_pacs008.py`](../examples/02_x402_to_pacs008.py)
- [`examples/03_guardrails.py`](../examples/03_guardrails.py)

## Related

| Package | What it does |
|---|---|
| [`pain001`](https://pypi.org/project/pain001/) | Turns the record into a credit-transfer initiation |
| [`pacs008`](https://pypi.org/project/pacs008/) | Turns the record into an interbank transfer |
| [`iso20022-mcp`](https://pypi.org/project/iso20022-mcp/) | One gateway across every family |

## Licence

Apache-2.0 OR MIT, at your option.
