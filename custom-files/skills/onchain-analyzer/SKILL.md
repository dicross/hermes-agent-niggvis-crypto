---
name: onchain-analyzer
description: Analyze Solana tokens on-chain — contract safety, holder distribution, liquidity, smart money signals. Uses Solana RPC + DEXScreener. No paid API keys required for basic analysis.
version: 1.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, OnChain, Analysis, Security, SmartMoney, Rugpull]
    related_skills: [crypto-scanner, trade-journal, risk-manager]
---
 
# OnChain Analyzer — Solana Token Security & Analysis
 
Deep on-chain analysis of Solana tokens before buying.
Checks contract safety, holder distribution, liquidity depth, and basic smart money signals.
 
---
 
## When to Use
 
- Before any buy decision — ALWAYS run `analyze` first
- User asks "is this token safe?"
- User asks to check a contract / token address
- User wants holder distribution or top holders
- User asks about liquidity depth
- Cron: pre-buy safety check in automated pipeline
 
---
 
## Prerequisites
 
Python 3.11+ with standard library only.
Optional: `SOLANA_RPC_URL` env variable for private RPC (recommended for speed).
Default: `https://api.mainnet-beta.solana.com` (public, rate-limited).
 
---
 
## Quick Reference
 
IMPORTANT: Always use FULL paths.
Script dir: `~/.hermes/skills/onchain-analyzer/scripts/`
 
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze <token_address> [--full]
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py safety <token_address>
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py holders <token_address> [--top N]
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py liquidity <token_address>
```
 
---
 
## Commands
 
### `analyze` — Full Token Analysis
 
Runs all checks and outputs a combined report with a safety score (0-100).
 
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze So11111111111111111111111111111111111111112
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze <address> --full   # Include holder list
```
 
Output includes:
- Token metadata (name, symbol, supply)
- Contract safety (mint authority, freeze authority, upgrade authority)
- Liquidity info (USD value, locked status estimate)
- Holder distribution (concentration, top holders %)
- DEXScreener data (price, volume, txns, socials)
- Safety score with risk flags
 
### `safety` — Quick Safety Check Only
 
Fast check — contract authorities only. Use for bulk screening.
 
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py safety <address>
```
 
Returns: SAFE / WARNING / DANGER with specific flags.
 
### `holders` — Top Holder Analysis
 
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py holders <address> --top 10
```
 
Shows top holders, concentration %, and flags whale wallets.
 
### `liquidity` — Liquidity Depth Check
 
```bash
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py liquidity <address>
```
 
Shows liquidity pools, USD value, and basic lock status.
 
---
 
## Safety Score Breakdown
 
| Check | Weight | SAFE | WARNING | DANGER |
|-------|--------|------|---------|--------|
| Mint authority | 25 | Revoked/None | Active but known | Active unknown |
| Freeze authority | 20 | None | Active known | Active unknown |
| Top 10 holders % | 20 | <40% | 40-70% | >70% |
| Liquidity USD | 15 | >$50k | $10k-$50k | <$10k |
| Pair age | 10 | >24h | 1-24h | <1h |
| Socials/website | 10 | Has both | Has one | None |
 
Score 70+ = Consider buying | 40-69 = Caution | <40 = Avoid
 
---
 
## Integration with Other Skills
 
- **crypto-scanner** → finds tokens → **onchain-analyzer** checks safety
- **risk-manager** → calls `safety` before approving any trade
- **trade-journal** → safety score logged with each trade entry
 
---
 
## Example Agent Workflow
 
```
1. crypto-scanner trending --limit 10
2. For each token: onchain-analyzer safety <address>
3. Filter: only score >= 70
4. onchain-analyzer analyze <best_candidate> --full
5. If passes → trade-executor paper-buy (or real with risk-manager approval)
```
