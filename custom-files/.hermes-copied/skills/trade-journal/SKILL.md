---
name: trade-journal
description: Log and analyze crypto trades on Solana. Tracks entries, exits, P&L, win rate, and patterns. Stores data in JSON for the agent's learning loop.
version: 1.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Trading, Journal, Analytics, Learning]
    related_skills: [crypto-scanner, solana]
---

# Trade Journal — Crypto Trading Log & Analytics

Log trades, track P&L, analyze performance, and identify patterns.
Stores data in `~/.hermes/memories/trade-journal.json`.
5 commands: add, close, show, stats, export.

No external packages required — uses only Python standard library. Enhanced with real-time on-chain validation via DEXScreener API integration during trade analysis (e.g., checking liquidity, volume, and social signals before closing positions).

---

## When to Use

- After buying a token (paper or real) — log the entry
- After selling — close the trade with exit price
- User asks "how am I doing?", "win rate", "show trades"
- Daily/weekly recap — run stats for performance summary
- User wants to export trade history
- **After any trade, review on-chain data (DEXScreener, Solscan) and update entry_reason with key signals** — this turns the journal into a live learning engine.

---

## Quick Reference

```
python3 journal.py add --token NAME --address ADDR --amount SOL --price PRICE --reason "why"
python3 journal.py close --id N --exit-price PRICE --reason "why sold"
python3 journal.py show [--limit N] [--open-only]
python3 journal.py stats [--days N]
python3 journal.py export [--format csv]
```

---

## Procedure

### 1. Log a New Trade (Buy)

```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py add \
  --token "BONK" \
  --address "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" \
  --amount 0.1 \
  --price 0.00001234 \
  --reason "Volume spike +300%, mint revoked, 1.5K holders, smart money buy detected"
```

For paper trades, add `--paper`:
```bash
python3 journal.py add --token "PEPE2" --address "..." --amount 0.05 --price 0.001 \
  --reason "Testing scanner signal" --paper
```

### 2. Close a Trade (Sell)

```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py close \
  --id 1 \
  --exit-price 0.00002468 \
  --reason "Hit 2x target"
```

### 3. Show Recent Trades

```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show --limit 10
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show --open-only
```

### 4. Performance Stats

```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats --days 7
```

Output: total trades, win rate, avg P&L, total P&L, best/worst trade, avg hold time, and **real vs paper trade breakdown**.

### 5. Export

```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py export --format csv
```

Exports full journal with **paper/real flags**, **entry/exit timestamps**, and **on-chain analysis notes** (e.g., 'liquidity > $50K', 'smart money detected') from entry_reason field.

## Pitfalls

- **Journal file**: stored at `~/.hermes/memories/trade-journal.json`. Back up regularly.
- **P&L calculation**: based on entry/exit price × amount. Does not account for fees/slippage.
- **Paper vs real**: paper trades are flagged separately in stats.
- **Trade IDs**: auto-incrementing integers, unique per journal.
- **On-chain context**: entry_reason should include key on-chain metrics (liquidity, volume, holders, contract status) — this data is critical for retrospective analysis and is preserved in exports.

---

## Verification

```bash
# Add a test paper trade and check stats
python3 ~/.hermes/skills/trade-journal/scripts/journal.py add \
  --token "TEST" --address "test123" --amount 0.01 --price 1.0 \
  --reason "test entry" --paper
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show
```
