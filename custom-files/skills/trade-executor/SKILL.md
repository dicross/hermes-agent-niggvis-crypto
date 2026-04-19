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
 
```
# Executor (high-level — integrates all skills)
python3 executor.py buy --token <address> --reason "why"
python3 executor.py buy --token <address> --amount 0.05 --reason "why"
python3 executor.py sell --id <trade_id> --reason "why"
python3 executor.py check-exits
python3 executor.py portfolio
python3 executor.py mode [paper|real]
python3 executor.py config-propose --key <key> --value <val> --reason "why"
 
# Jupiter Swap (low-level — direct on-chain)
python3 jupiter_swap.py wallet
python3 jupiter_swap.py buy --token <address> --amount-sol 0.05
python3 jupiter_swap.py sell --token <address> --pct 100
 
# Guardian (fast price monitor, no LLM)
python3 guardian.py --watch
python3 guardian.py --dry-run
```
 
---
 
## Architecture
 
```
executor.py -> risk-manager -> onchain-analyzer -> jupiter_swap.py -> Jupiter V2 -> Solana
guardian.py -> DEXScreener prices -> SL/TP check -> jupiter_swap.py sell (real) / journal close (paper)
```
 
## Config
 
Central config: `~/.hermes/memories/trading-config.yaml`
 
Key settings: mode, position_sizing, risk (SL/TP), jupiter (slippage), filters.
Agent can propose changes via `config-propose` (requires Damian's Telegram approval).
