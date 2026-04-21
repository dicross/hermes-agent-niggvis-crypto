# Session Analysis Report

**Date**: 2026-04-20  
**Sessions**: 7  
**Tool calls**: 26  

| Metric | Count |
|--------|-------|
| Buys executed | 2 |
| Sells executed | 1 |
| Trades blocked | 6 |
| Errors | 2 |
| Config changes | 1 |
| Silent sessions | 3 |

## Wallet Balance

| Time | Balance (SOL) |
|------|---------------|
| 2026-04-20 21:25 | 0.1062 |
| 2026-04-20 22:21 | 0.1095 |
| 2026-04-20 23:00 | 0.1284 |
| **Delta** | **+0.0223** |

## Trades Executed

| Time | Token | Amount (SOL) | Price | Safety | Tx |
|------|-------|-------------|-------|--------|-----|
| 23:04 | TARDI | 0.0100 | $0.002094 | 80 | 5MrnsyRrrced... |
| 23:27 | IMOUT | 0.0100 | $1.439e-05 | 60 | 3JdQ121UV364... |

## Sells Executed

- **212518** SELL HOLD — P&L: -8.72%

## Blocked Trades (grouped)

| Reason | Count |
|--------|-------|
| unknown | 2 |
| duplicate (#17) + max positions reached | 1 |
| duplicate (#17) | 1 |
| duplicate (#18) | 1 |
| safety 55 | 1 |

## Errors

- **230031**: `{"status": "error", "output": "Learning update failed: /home/niggvis/projects/hermes-agent-niggvis-crypto/venv/bin/python: can't open file '/home/nigg`
- **230031**: `{"output": "📊 TRADING STATS (last 1 days)\n\n  Total trades: 10 (4 open, 6 closed)\n  Paper: 0 closed | Real: 6 closed\n\n  Win rate: 33.3% (2W / 4L)\`

## Config Changes

- **212518**: propose min_liquidity_usd=15000: approved by user: raise liquidity filter from 10K to 15K to reduce rug risk and 

## Agent Responses (non-silent)

**212518** (interactive):
> ✅ **CONFIG APPLIED — MIN LIQUIDITY UPGRADED TO $15K**    Zmiana zastosowana:   - **`min_liquidity_usd`**: `10 000 → 15 000`   - **Powód**: approved by user: raise liquidity filter from 10K to 15K to reduce rug risk and improve execution quality    📌 **Co to oznacza dla Ciebie?**   - **Nie kupimy już

**230436** (cron):
> ✅ BUY EXECUTED — TARDI (4JBeo37fKhEsTXp6PtAYktYRnDAa8DcXZaZ4tTuPpump)  - **Token**: TARDI - **Safety Score**: 80/100 - **Amount**: 0.0100 SOL - **Entry Price**: $0.002094 - **Transaction**: https://solscan.io/tx/5MrnsyRrrcedMZcoQT3DzJfHNQGSNFbDwV9xWAhtQoTrRPLD8zkZNe4YVgkagik2CZzjx4q44zhrd7ThojhZSn2G

**232750** (cron):
> ✅ BOUGHT: I AM OUT (IMOUT)   - **Safety Score**: 60   - **Amount**: 0.0100 SOL   - **Price**: $0.00001439   - **Transaction**: https://solscan.io/tx/3JdQ121UV364aS7z4qosf2BwHXGwF8GbNRvP7uhBUivh98k1rf1AAXcGLQtAeq3ZtPvVXAhw481wrJiTSsQJcrUX

**230031** (cron):
> Daily trading recap:   - Closed 6 trades today: 2 wins, 4 losses; net P&L +13.9% ($0.0070 SOL).   - Top performers: MAGA (+17%), Retardoid (+36.8%), SCHIZO (+14.3%), FOF (+2%).   - 4 open positions remain, all in profit with avg gain +17.5%.   - Risk manager confirms kill switch OFF, daily loss limi

## All Sessions

| File | Type | Calls | Status |
|------|------|-------|--------|
| session_20260420_212518_8a9cd1d6.json | interactive | 6 | 1 sell, 1 cfg |
| session_cron_36cac1573e00_20260420_222140.json | cron | 3 | 1 blocked, SILENT |
| session_cron_36cac1573e00_20260420_230436.json | cron | 7 | 1 buy, 5 blocked |
| session_cron_36cac1573e00_20260420_232750.json | cron | 2 | 1 buy |
| session_cron_b9e450064246_20260420_230031.json | cron | 6 | 2 err |
| session_cron_ddb1dd8f4608_20260420_223527.json | cron | 1 | SILENT |
| session_cron_ddb1dd8f4608_20260420_231853.json | cron | 1 | SILENT |
