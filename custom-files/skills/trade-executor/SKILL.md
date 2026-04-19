---
name: trade-executor
description: Execute crypto trades on Solana via Jupiter API — paper mode (simulation) and real mode (on-chain). Integrates with risk-manager for pre-trade checks, trade-journal for logging, and jupiter_swap for execution.
version: 2.0.0
author: Niggvis (Hermes Agent)
license: MIT
metadata:
  hermes:
    tags: [Solana, Crypto, Trading, Execution, Jupiter, Paper]
    related_skills: [risk-manager, onchain-analyzer, trade-journal, crypto-scanner]
---
 
# Trade Executor — Buy & Sell on Solana via Jupiter
 
Executes trades in paper mode (simulation with journal logging) or real mode
(on-chain swaps via Jupiter V2 Meta-Aggregator). All trades go through
risk-manager first. Position sizing is dynamic based on wallet balance.
 
---
 
## When to Use
 
- Agent decides to buy a token after analysis
- Agent decides to sell (take profit, stop loss, manual)
- User says "buy X" or "sell X"
- Cron: auto-sell on stop-loss / take-profit triggers
- Portfolio check: evaluate open positions for exit
- Config changes: propose changes for Damian's approval
 
---
 
## Prerequisites
 
Python 3.11+.
For real mode: `pip install solders` (Solana transaction signing).
Config: `~/.hermes/memories/trading-config.yaml`
Keypair: `~/.hermes/secrets/trading-wallet.json`
 
---
 
## Quick Reference
 
IMPORTANT: Always use FULL paths starting with `~/.hermes/skills/`.
Script dir: `~/.hermes/skills/trade-executor/scripts/`
 
```bash
# Executor (high-level — integrates all skills)
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <address> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <address> --amount 0.05 --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <trade_id> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <trade_id> --pct 50 --reason "partial TP"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py check-exits
python3 ~/.hermes/skills/trade-executor/scripts/executor.py portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode paper
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode real
 
# Jupiter Swap (low-level — direct on-chain)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py balance --token <address>
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <address> --amount-sol 0.05
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py sell --token <address> --pct 100
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py quote --token <address> --amount-sol 0.05
 
# Guardian (fast price monitor, no LLM — runs separately)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --dry-run
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --history 20
```
 
---
 
## Architecture
 
```
executor.py -> risk-manager -> onchain-analyzer -> jupiter_swap.py -> Jupiter V2 -> Solana
guardian.py -> DEXScreener prices -> SL/TP check -> jupiter_swap.py sell (real) / journal close (paper)
```
 
## Config
 
Central config: `~/.hermes/memories/trading-config.yaml`
 
Key settings: mode, position_sizing, risk (SL/TP/trailing), jupiter (slippage), filters.
 
## How to Change SL, TP, Trailing Stop, and Other Config
 
Use `config-propose` to request a change. This logs a proposal that Damian must approve.
 
```bash
# Change stop-loss from -30% to -20%
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key stop_loss_pct --value "-20" --reason "tighter SL for volatile market"
 
# Change take-profit from 100% to 50%
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key take_profit_pct --value "50" --reason "lower TP for quicker exits"
 
# Change trailing stop from 15% to 10%
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key trailing_stop_pct --value "10" --reason "tighter trailing for memecoins"
 
# Disable trailing stop (instant sell at TP)
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key trailing_stop_pct --value "0" --reason "disable trailing, sell at TP"
 
# Change position size from 5% to 3%
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key position_pct --value "3.0" --reason "smaller positions in bear market"
 
# Change slippage from 1500 to 2500 bps (15% to 25%)
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose \
  --key slippage_bps --value "2500" --reason "higher slippage for low-liq tokens"
```
 
After Damian approves on Telegram, apply with:
```bash
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-apply --index <N>
```
 
### Config keys reference
| Key | Current | Description |
|-----|---------|-------------|
| `stop_loss_pct` | -30 | Auto-sell if position drops below this % |
| `take_profit_pct` | 100 | Auto-sell if position rises above this % |
| `trailing_stop_pct` | 15 | After TP hit, trail by this % (0=disabled) |
| `position_pct` | 5.0 | % of wallet balance per trade |
| `max_trade_sol` | 0.15 | Hard max per trade in SOL |
| `min_trade_sol` | 0.01 | Hard min per trade in SOL |
| `max_positions` | 5 | Max open positions at once |
| `slippage_bps` | 1500 | Slippage tolerance (100=1%) |
| `daily_loss_limit_pct` | -20 | Stop trading if daily loss exceeds |
| `min_safety_score` | 60 | Min safety score from analyzer |
| `min_liquidity_usd` | 10000 | Min liquidity to buy |
| `mode` | real | paper or real |
 
### How trailing stop works
When a position hits `take_profit_pct` (e.g. +100%), Guardian does NOT sell immediately.
Instead it activates trailing: if price drops `trailing_stop_pct` (e.g. 15%) from the peak,
GUARDIAN sells. This lets winners run. Set `trailing_stop_pct: 0` to sell instantly at TP.
