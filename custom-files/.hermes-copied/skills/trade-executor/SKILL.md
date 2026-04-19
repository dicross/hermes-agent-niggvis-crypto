---
name: trade-executor
description: Execute crypto trades on Solana — paper mode (simulation) and real mode (via Trojan on Solana). Integrates with risk-manager for pre-trade checks and trade-journal for logging.
version: 1.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Trading, Execution, Paper, Trojan]
    related_skills: [risk-manager, onchain-analyzer, trade-journal, crypto-scanner]
---
 
# Trade Executor — Buy & Sell on Solana
 
Executes trades in paper mode (simulation with journal logging) or real mode
(via Trojan on Solana Telegram bot). All trades go through risk-manager first.
 
---
 
## When to Use
 
- Agent decides to buy a token after analysis
- Agent decides to sell (take profit, stop loss, manual)
- User says "buy X" or "sell X"
- Cron: auto-sell on stop-loss / take-profit triggers
- Portfolio check: evaluate open positions for exit
 
---
 
## Prerequisites
 
Python 3.11+ with standard library only.
Requires: risk-manager skill, trade-journal skill, onchain-analyzer skill.
For real mode: `TROJAN_BOT_CHAT_ID` env variable (future).
 
---
 
## Quick Reference
 
```
python3 executor.py buy --token <address> --amount <SOL> --reason "why"
python3 executor.py sell --id <trade_id> --reason "why"
python3 executor.py check-exits [--stop-loss] [--take-profit]
python3 executor.py portfolio
python3 executor.py mode [paper|real]
```
 
---
 
## Commands
 
### `buy` — Open a Position
 
```bash
python3 executor.py buy --token <address> --amount 0.05 --reason "trending on DEX, safety 82"
```
 
Pipeline:
1. Fetch current price from DEXScreener
2. Run onchain-analyzer safety check → get safety score
3. Run risk-manager check → APPROVED/BLOCKED
4. If paper mode → log to trade-journal with `--paper` flag
5. If real mode → (future) send buy command to Trojan bot
6. Output: trade confirmation or block reason
 
### `sell` — Close a Position
 
```bash
python3 executor.py sell --id 3 --reason "hit 2x target"
```
 
Pipeline:
1. Fetch current price from DEXScreener
2. Close trade in journal with exit price
3. If real mode → (future) send sell command to Trojan bot
4. Output: P&L summary
 
### `check-exits` — Scan Open Positions for Exit Signals
 
```bash
python3 executor.py check-exits # check all triggers
python3 executor.py check-exits --stop-loss # only stop-loss
python3 executor.py check-exits --take-profit # only take-profit
```
 
For each open position:
- Fetch current price
- Compare to entry price
- If below stop-loss (-30%) → auto-sell (paper or real)
- If above take-profit (min +100%) → flag for review (or auto-sell if configured in risk-manager)

💡 **UPDATED BEHAVIOR**: When a take-profit trigger is hit (e.g. +192% on UNCEROID), the system now logs the exit signal and *waits for manual confirmation* in paper mode. Auto-selling is disabled by default to prevent premature exits on volatile memecoins. The agent will always flag the opportunity and let the user decide — unless `risk-manager` is configured to auto-sell on +150%+ gains. This prevents FOMO-selling on parabolic runs. To enable auto-sell on take-profit, run: `risk-manager set auto-sell-take-profit true`.
 
### `portfolio` — Show Current Holdings
 
```bash
python3 executor.py portfolio
```
 
Shows open positions with current prices, unrealized P&L, and exit signals.
 
### `mode` — Switch Paper/Real
 
```bash
python3 executor.py mode          # show current
python3 executor.py mode paper    # switch to paper
python3 executor.py mode real     # switch to real (requires confirmation)
```
 
---
 
## Paper Trading Flow
 
```
1. crypto-scanner finds interesting token
2. onchain-analyzer checks safety → score 78
3. executor buy --token <addr> --amount 0.05 --reason "..."
   ├─ risk-manager check → APPROVED
   ├─ Get price from DEXScreener
   └─ Log to trade-journal as PAPER trade
4. Cron (hourly): executor check-exits
   ├─ Fetch current prices
   ├─ -30% → auto paper-sell (stop loss)
   └─ +100% → flag or auto paper-sell (take profit)
5. Daily: executor portfolio → summary
```
 
---
 
## Real Trading (Future — Phase 2)
 
When switching to real mode, trade-executor will:
1. Send buy/sell commands to Trojan on Solana (@solaboratorybot)
2. Parse confirmation messages from Trojan
3. Log actual tx hashes in trade-journal
4. Require manual approval (configurable in risk-manager)
