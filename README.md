# ap2-iso20022: Agent-payment mandates → wire-valid ISO 20022

**Bridge [AP2][ap2] (Google's Agent Payments Protocol) and [x402][x402]
(Coinbase's HTTP-402) mandates into ISO 20022 `pain.001` / `pacs.008` records —
with spending-cap, expiry and authorisation guardrails, and an [MCP][mcp]
server.** These agentic-payment protocols authorise a payment; this library
turns that authorisation into the **bank-rail message that actually settles it**
— the rail the card networks and stablecoins don't cover.

> **Latest release: v0.0.1** — 5 MCP tools over stdio, pure-Python (only `mcp`),
> 100% branch coverage, for Python 3.10+. Output feeds straight into
> [`pain001`][pain001-mcp] / [`pacs008`][pacs008-mcp] to generate wire-valid XML.
> Part of the [ISO 20022 MCP suite](#the-suite).

## Why

An agent with a signed AP2 mandate (or an x402 payment authorisation) can prove
*it's allowed to pay* — but nothing in those protocols emits the `pain.001` a
bank needs to move the money. `ap2-iso20022` is that missing hop. And because
moving money is consequential, it **only transforms and validates** — producing
the ISO record is deliberately separate from generating and sending it, so the
actual payment stays an explicit, guarded step.

## Install

```sh
pip install ap2-iso20022
# or run the MCP server without installing:
uvx ap2-iso20022
```

MCP client config (e.g. Claude Desktop):

```json
{
  "mcpServers": {
    "ap2-iso20022": {
      "command": "ap2-iso20022-mcp"
    }
  }
}
```

## Flow: normalise → guardrail → convert

```python
from ap2_iso20022 import bridge

# 1. Normalise the protocol payload into a canonical mandate.
mandate = bridge.from_ap2({
    "intent_id": "AP2-CoffeeRun-7",
    "payer": "Alice's Shopping Agent",
    "payer_account": "DE89370400440532013000",
    "merchant_name": "Blue Bottle Coffee",
    "payee_account": "GB29NWBK60161331926819",
    "amount": "12.50", "currency": "EUR", "memo": "oat latte",
    "spending_limit": "50.00",
    "signature": "eyJ...", "signature_type": "jws",
})

# 2. Guardrail before it becomes a payment.
check = bridge.check_mandate(mandate, as_of="2026-03-02T09:00:00")
assert check["ok"]          # required fields ok, within cap, not expired, signed

# 3. Convert to a pain.001 record that feeds pain001 -> wire-valid XML.
record = bridge.to_pain001(mandate)   # exact pain001 field names + JSON number amounts
```

## Tools

| Tool | What it does |
| --- | --- |
| `normalize_ap2` | AP2 mandate payload → canonical mandate. |
| `normalize_x402` | x402 payment payload → canonical mandate. |
| `check_mandate` | Guardrail: required fields, spending cap, expiry (with `as_of`), authorisation proof. |
| `to_pain001` | Canonical mandate → `pain.001` record (customer credit transfer). |
| `to_pacs008` | Canonical mandate → `pacs.008` record (FI-to-FI). |

The output field names and types match what `pain001` / `pacs008` expect
(validated against their JSON schemas), so `to_pain001(mandate)` → pain001
`generate_message` → XSD-valid pain.001 with no glue.

## Guardrails

`check_mandate` returns `{ok, violations, warnings}`:
- **required fields** — payer/payee name + account, amount, currency
- **spending cap** — `amount <= max_amount` when a cap is present
- **expiry** — refuses an expired mandate when you pass `as_of`
- **authorisation proof** — warns when no `proof_type`/`proof_value` is present

It never moves money; it tells you whether the mandate is safe to act on.

## The suite

Part of a family of vendor-neutral, Python-native ISO 20022 MCP servers:

- [`iso20022-mcp`][iso20022-mcp] — unified gateway across the families.
- [`pain001-mcp`][pain001-mcp] · [`pacs008-mcp`][pacs008-mcp] — generate the XML this bridge feeds.
- [`reconcile-mcp`][reconcile-mcp] — statement/payment reconciliation.
- [`camt-exceptions`][camt-exceptions] — E&I messages (cancellation, investigation).

## Development

```sh
git clone https://github.com/sebastienrousseau/ap2-iso20022
cd ap2-iso20022
python -m venv .venv && . .venv/bin/activate
pip install -e . && pip install pytest pytest-cov ruff black mypy
pytest                      # 100% branch coverage gate
ruff check ap2_iso20022 tests && black --check ap2_iso20022 tests && mypy ap2_iso20022
```

## Licence

Licensed under the [Apache License, Version 2.0](LICENSE).

---

`mcp-name: io.github.sebastienrousseau/ap2-iso20022`

[mcp]: https://modelcontextprotocol.io
[ap2]: https://github.com/google-agentic-commerce/AP2
[x402]: https://www.x402.org
[iso20022-mcp]: https://github.com/sebastienrousseau/iso20022-mcp
[pain001-mcp]: https://github.com/sebastienrousseau/pain001-mcp
[pacs008-mcp]: https://github.com/sebastienrousseau/pacs008-mcp
[reconcile-mcp]: https://github.com/sebastienrousseau/reconcile-mcp
[camt-exceptions]: https://github.com/sebastienrousseau/camt-exceptions
