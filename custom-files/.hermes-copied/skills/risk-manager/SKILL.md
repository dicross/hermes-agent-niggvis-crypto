---
name: risk-manager
description: Enforce trading limits, rugpull detection, daily loss limits, and kill switch. Safety layer for all crypto trades. Reads from trading-config.yaml.
version: 2.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Risk, Safety, Limits, Rugpull, KillSwitch]
    related_skills: [onchain-analyzer, trade-executor, trade-journal]
---
 
# Risk Manager — Trading Safety Layer
 
Enforces hard trading limits, checks safety before buys, tracks daily P&L,
and provides a kill switch. Every trade MUST pass through risk-manager.
 
---
 
## When to Use
 
- ALWAYS before executing a trade (buy or sell)
- User asks "can I buy this?" — run `check` first
- Periodic: `status` to see daily P&L vs limits
- Emergency: `kill` to halt all trading
- After config changes: `config` to verify limits
 
---
 
## Prerequisites
 
Python 3.11+ with standard library only.
Reads limits from `~/.hermes/memories/risk-config.json`.
Reads trade data from `~/.hermes/memories/trade-journal.json`.
 
---
 
## Quick Reference
 
```
python3 risk_manager.py check --amount <SOL> --token <address> [--safety-score N]
python3 risk_manager.py status
python3 risk_manager.py kill [--reason "why"]
python3 risk_manager.py resume
python3 risk_manager.py config [--set key=value]
python3 risk_manager.py limits
```
 
---
 
## Commands
 
### `check` — Pre-Trade Approval
 
Must be called before EVERY buy. Returns APPROVED or BLOCKED with reason.
 
```bash
python3 risk_manager.py check --amount 0.05 --token <address> --safety-score 75
```
 
Checks:
1. Kill switch not active
2. Amount <= max trade size (default 0.1 SOL)
3. Open positions < max positions (default 5)
4. Daily loss not exceeded (default -20%)
5. Safety score >= minimum (default 60)
6. Same token not already in portfolio (no doubling down)
 
### `status` — Current Risk Dashboard
 
```bash
python3 risk_manager.py status
```
 
Shows:
- Kill switch: ON/OFF
- Mode: PAPER / REAL
- Open positions: N / max
- Daily P&L: X% (limit: -20%)
- Budget remaining: X SOL
- Trades today: N
 
### `kill` — Emergency Stop
 
```bash
python3 risk_manager.py kill --reason "suspicious activity"
```
 
Halts ALL trading. Agent cannot buy until `resume` is called.
Also triggered by Telegram `/stop` command.
 
### `resume` — Resume Trading
 
```bash
python3 risk_manager.py resume
```
 
Clears kill switch. Requires explicit action.
 
### `config` — View/Set Limits
 
```bash
python3 risk_manager.py config                          # show all
python3 risk_manager.py config --set max_trade_sol=0.05 # change limit
python3 risk_manager.py config --set mode=paper         # paper/real
```
 
### `limits` — Show All Hard Limits
 
```bash
python3 risk_manager.py limits
```
 
---
 
## Default Limits (risk-config.json)
 
```json
{
  "mode": "paper",
  "max_trade_sol": 0.1,
  "max_positions": 5,
  "daily_loss_limit_pct": -20,
  "min_safety_score": 60,
  "stop_loss_pct": -30,
  "take_profit_min_pct": 100,
  "total_budget_sol": 1.0,
  "kill_switch": false,
  "kill_reason": null,
  "kill_time": null
}
```
 
---
 
## Integration
 
- **trade-executor** → calls `check` before every buy
- **onchain-analyzer** → provides safety-score to `check`
- **trade-journal** → provides daily P&L data
- **cron** → periodic `status` check, auto-kill if limits hit
 
---
 
## Safety Rules (non-negotiable)
 
1. Kill switch overrides everything
2. Paper mode = no real transactions, only journal entries
3. Daily loss limit = auto-kill if exceeded
4. No trade without safety check (onchain-analyzer)
5. Budget is hard capped — no "just one more"
