---
name: crypto-scanner
description: Scan for new and trending tokens on Solana using DEXScreener API. Filters by liquidity, volume, age, and contract safety. No API key required.
version: 1.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Trading, Scanner, DEXScreener, DeFi, Memecoin]
    related_skills: [solana, trade-journal]
---

# Crypto Scanner — Solana Token Discovery

Scan DEXScreener for new and trending tokens on Solana.
Filters by liquidity, volume, pair age, and basic contract checks.
3 commands: scan (new tokens), trending (top boosts), search (by query).

No API key needed. Uses only Python standard library (urllib, json, argparse).

---

## When to Use

- User asks to scan for new tokens on Solana
- User wants to find trending/hot memecoins
- User asks "what's pumping right now?"
- User wants to discover new trading opportunities
- Cron job: periodic scan for new token alerts
- User asks to search for a specific token or category

---

## Prerequisites

Python 3.11+ with standard library only. No external packages.

Optional: Solana RPC for contract checks (mint/freeze authority).
Set `SOLANA_RPC_URL` env variable for private RPC (faster, no rate limits).

---

## Quick Reference

IMPORTANT: Always use FULL paths.
Script dir: `~/.hermes/skills/crypto-scanner/scripts/`

```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py scan [--min-liq N] [--min-vol N] [--max-age N] [--limit N] [--check-contract]
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending [--limit N]
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py search <query> [--min-liq N] [--min-vol N]
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py metas
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py token <address>
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py new-pairs [--limit N]
```

---

## Procedure

### 1. Scan New Token Profiles

Find recently created token profiles on Solana. Filters by liquidity and volume.

```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py scan \
  --min-liq 5000 \
  --min-vol 10000 \
  --max-age 24 \
  --limit 20 \
  --check-contract
```

Flags:
- `--min-liq N` — minimum liquidity in USD (default: 5000)
- `--min-vol N` — minimum 24h volume in USD (default: 10000)
- `--max-age N` — max pair age in hours (default: 24)
- `--limit N` — max results to show (default: 20)
- `--check-contract` — check mint/freeze authority via Solana RPC (slower)

Output: list of tokens sorted by volume with liquidity, price, age, buys/sells, socials.

### 2. Trending Tokens (Top Boosts)

Find tokens with the most active boosts (promoted/trending on DEXScreener).

```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 10
```

### 3. Search by Query

Search for specific tokens or categories.

```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py search "pepe" --min-liq 5000
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py search "ai agent" --min-vol 50000
```

### 4. Trending Metas (Categories)

See what categories/narratives are trending (AI, meme, gaming, etc.).

```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py metas
```

---

## Interpreting Results

- **Liquidity > $20K**: decent, lower risk of rug
- **Liquidity $5-20K**: thin, higher slippage and risk
- **Liquidity < $5K**: avoid (default filter)
- **Buy/Sell ratio**: >80% buys = FOMO, be cautious
- **Age < 1h**: very early, highest risk
- **Age 1-4h**: discovery phase, good entry if contract is clean
- **Age 4-24h**: established trend, verify before entry
- **Boosts**: paid promotion, not organic — verify independently

## Contract Check Results (--check-contract)

- ✅ `mint: revoked` — safe, no new tokens can be minted
- ❌ `mint: ACTIVE` — dev can print tokens, HIGH RISK
- ✅ `freeze: revoked` — safe, your tokens can't be frozen
- ❌ `freeze: ACTIVE` — dev can freeze your wallet, HIGH RISK

---

## Pitfalls

- **DEXScreener rate limits**: 300 req/min for pair data, 60 req/min for profiles/boosts.
- **Token profiles are self-submitted**: having a profile doesn't mean legitimacy.
- **Contract check uses Solana RPC**: public RPC has rate limits. Use private RPC for production.
- **Not all scams are detectable**: honeypots, hidden mint via proxy, etc. Always DYOR.
- **pairCreatedAt** is in milliseconds since epoch.

---

## Verification

```bash
# Quick test — should show trending tokens
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 5
```
