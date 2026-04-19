---
name: trending-token-pipeline
description: Complete workflow for scanning trending Solana tokens, running safety analysis, and executing paper trades. Handles safety score discrepancies between quick check and full analysis.
version: 1.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Trading, Scanner, Pipeline, Workflow]
    related_skills: [crypto-scanner, onchain-analyzer, risk-manager, trade-executor, trade-journal]
---

# Trending Token Pipeline — End-to-End Workflow

Complete workflow for discovering, analyzing, and trading trending Solana tokens.

## When to Use
- Cron job: periodic scan for new opportunities
- User asks: "scan for trending tokens and trade the best one"
- Want to execute the full discovery → analysis → trade pipeline

## Workflow Steps

### 1. Scan Trending Tokens
```bash
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 10
```

### 2. Quick Safety Check (Top 3)
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py safety <address>
```
Filter: Keep tokens with SAFE contract (mint/freeze revoked).

### 3. Full Analysis (Candidates with liq > $10K)
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze <address>
```
Look for:
- Safety score >= 60/100
- Liquidity > $10K
- Has website/socials (bonus points)
- Pair age > 4h (more established)

### 4. Risk Check
```bash
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py check --amount 0.05 --token <address> --safety-score <score>
```

### 5. Execute Trade (Paper Mode)
If risk check APPROVED:
```bash
python3 ~/.hermes/skills/trade-journal/scripts/journal.py add \
  --token "<SYMBOL>" \
  --address "<address>" \
  --amount 0.05 \
  --price <current_price> \
  --reason "<safety score, liq, age, socials, why>" \
  --paper
```

## ⚠️ Known Issue: Safety Score Mismatch

The `executor.py buy` command uses the **contract-only safety score** (45/45 max) from `analyzer.py safety`, not the **full safety score** (0-100) from `analyzer.py analyze`.

**Contract-only score**: Only checks mint/freeze authority (max 45 points)
**Full safety score**: Includes contract + liquidity + age + socials + holders (max 100 points)

### Workaround
When a token has:
- Contract score: 45/45 (SAFE)
- Full score: 60-70/100 (meets min_safety_score of 60)

The executor will block it because it only sees the contract portion. **Solution**: Skip `executor.py buy` and directly log to journal using `journal.py add --paper` after manual risk approval.

## Example Output Format

```
📊 SCAN SUMMARY
### Tokens Analyzed (Top 3 Trending)
| Rank | Token | Safety | Liquidity | Age | Verdict |
|------|-------|--------|---------|-----|---------|
| #1 | MINI MU | 63/100 | $38.7K | 9.3h | ⚠️ Caution |
| #2 | EUPHORIA | 68/100 | $28.1K | 21.0h | ✅ Selected |

### ✅ Trade Executed
- Token: EUPHORIA (address...)
- Entry: 0.0001141
- Amount: 0.05 SOL (paper)
- Safety: 68/100
- Trade ID: #1 (OPEN)
```

## Pitfalls
- **RPC rate limits**: Public Solana RPC may return 429 errors. Use private RPC for production.
- **pumpswap tokens**: Holder data often unavailable, flagged as `CANNOT_READ_HOLDERS`.
- **New pairs**: Tokens <24h old carry higher risk even with safe contracts.
- **Safety score confusion**: Always use full `analyze` score for decision making, not quick `safety` score.
