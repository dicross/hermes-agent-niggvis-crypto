# Session Analysis Report

**Date**: 2026-04-21  
**Sessions**: 26  
**Tool calls**: 213  

| Metric | Count |
|--------|-------|
| Buys executed | 3 |
| Sells executed | 2 |
| Trades blocked | 60 |
| Errors | 3 |
| Config changes | 8 |
| Silent sessions | 14 |

## Wallet Balance

| Time | Balance (SOL) |
|------|---------------|
| 2026-04-21 20:12 | 0.0884 |
| 2026-04-21 20:20 | 0.0884 |
| 2026-04-21 21:33 | 0.0712 |
| 2026-04-21 21:53 | 0.0712 |
| 2026-04-21 22:15 | 0.0712 |
| 2026-04-21 22:36 | 0.0712 |
| 2026-04-21 22:56 | 0.0912 |
| 2026-04-21 23:00 | 0.0912 |
| **Delta** | **+0.0028** |

## Trades Executed

| Time | Token | Amount (SOL) | Price | Safety | Tx |
|------|-------|-------------|-------|--------|-----|
| 20:28 | DUMBMONEY | 0.0150 | $0.002428 | 80 | EQ1HVk7XTwD6... |
| 20:05 | IMOUT | 0.0150 | $3.529e-05 | 65 | 4dVzrRoJHk9v... |
| 20:26 | DUMBMONEY | 0.0150 | $0.002428 | 80 | EQ1HVk7XTwD6... |

## Sells Executed

- **224717** {"output": "🔍 Checking 6 open positions...\n\n  Stop loss: -30% | Take profit: +100% | Trailing: 15%
- **224717** SELL HOLD — P&L: +101.04%

## Blocked Trades (grouped)

| Reason | Count |
|--------|-------|
| unknown | 18 |
| max positions reached | 15 |
| duplicate (#33) | 4 |
| duplicate (#25) | 4 |
| duplicate (#34) + max positions reached | 4 |
| duplicate (#33) + max positions reached | 4 |
| duplicate (#25) + max positions reached | 4 |
| duplicate (#35) + max positions reached | 4 |
| duplicate (#34) | 2 |
| daily loss limit | 1 |

## Errors

- **230451**: `{"status": "error", "output": "\n--- stderr ---\nTraceback (most recent call last):\n  File \"/tmp/hermes_sandbox_7ps9_kta/script.py\", line 112, in <`
- **230451**: `{"status": "error", "output": "\n--- stderr ---\nTraceback (most recent call last):\n  File \"/tmp/hermes_sandbox_74nvvvh_/script.py\", line 108, in <`
- **230022**: `{"status": "success", "output": "Learning update failed: Traceback (most recent call last):\n  File \"/home/niggvis/.hermes/skills/trade-journal/scrip`

## Config Changes

- **202049**: skill_manage: {"action": "patch", "name": "trending-token-pipeline", "old_string": "### 2. Quick Safety Check (Top 3)\n```bash\npython3 ~/.hermes/skills/onchain-ana
- **202049**: skill_manage: {"action": "patch", "name": "trending-token-pipeline", "new_string": "### 3. Full Analysis (Candidates with liq > $10K)\n```bash\npython3 ~/.hermes/sk
- **202049**: skill_manage: {"action": "patch", "name": "trending-token-pipeline", "new_string": "### 5. Execute Trade (Paper Mode)\nIf risk check APPROVED:\n```bash\npython3 ~/.
- **205012**: ⚠️ DIRECT EDIT: patch on trading-config
- **205012**: skill_manage: {"action": "patch", "name": "crypto-scanner", "old_string": "def cmd_trending(args):\n    \"\"\"Show tokens with most active boosts (trending on DEXSc
- **205012**: skill_manage: {"action": "patch", "name": "crypto-scanner", "old_string": "def cmd_trending(args):\n    \"\"\"Show tokens with most active boosts (trending on DEXSc
- **211214**: skill_manage: {"action": "patch", "name": "crypto-scanner", "old_string": "## Buy Workflow (IMPORTANT — follow exactly)\n\nAfter scanning trending tokens, DO NOT ru
- **211214**: skill_manage: {"action": "patch", "name": "trade-executor", "new_string": "## How to Change SL, TP, Trailing Stop, and Other Config\n\nUse `config-propose` to reque

## Agent Responses (non-silent)

**201200** (interactive):
> Widzę, że masz 5 pozycji — wszystkie zyskowe, z P&L +29.6%. To jest **dobrze**. Ale patrzę na rynki — i coś się dzieje.  ### 🔥 **Federal Oil Fund (FOF)** — to nie jest jeden token. To jest **pompa**. - **18 różnych wersji** na Solanie — wszystkie z tym samym nazwiskiem, ale innymi adresami. - Najnow

**230451** (interactive):
> **✅ DONE — JOURNAL WYCZYŚCZONY!**   Usunięto **6 paper trade’ów** — wszystkie z `paper: true`.   Pozostało **24 real trade’y** — czyste, realne, gotowe do analizy.    ### 🔍 Co dalej?   1. **Learning module** — teraz `learning.py update` zadziała bez błędów (`NoneType P&L` zniknął).   2. **Config pro

**200515** (cron):
> ✅ BOUGHT: IMOUT (DACYVx34V5aQaehN3MZGYxPfoyQYHZSnFAFw3T2Vbonk)   - Safety Score: 65   - Amount: 0.015 SOL   - Entry Price: $0.00003529   - Transaction: https://solscan.io/tx/4dVzrRoJHk9vcjy1JtdbSz9mpFenC7Aqa5rX3j3Pp3jhRa22mqjca5JijZ4rf849VKjfNNpCv8JtgoLDEWeKHJrA

**202656** (cron):
> ✅ EXECUTED BUY: DUMBMONEY (CAjtTHvC878f8cZ4zEwdvgjkjFM7rbYN8Mb1go1cpump)   - Safety score: 80   - Amount: 0.015 SOL   - Entry price: $0.002428   - Transaction: https://solscan.io/tx/EQ1HVk7XTwD65VBQqz85YmemdSNo9VN7tBB7HywXgYhSaQDh6STXnXg4Vw2eagnqJ1waMsWUdbH1bkVN5TWvWU3

**222641** (cron):
> Trending categories: Meme, AI, Dog, Elon Musk, Degen. Top movers include ADHD, BULL, MAGA, and DUMBMONEY. Our open positions (ADHD, BULL, MAGA, HOLD, IMOUT, DUMBMONEY) are fully aligned with these trends. Portfolio at max capacity (6/6). No new buys recommended.

**230022** (cron):
> 📊 DAILY TRADING RECAP — APR 21, 2026  Closed 12 trades today: 4 wins (33%), 8 losses. Net P&L: +0.0015 SOL (+1.25% avg). Portfolio value up 19.7% ($0.0718 SOL) with 5 open positions — maxed at limit. Best trade: MAGA (+90.2%), worst: DUMBMONEY (-14.2%). Learning module failed due to NoneType P&L val

**224717** (cron):
> ✅ SELL EXECUTED: HOLD (Trade #33)  - **Entry Price**: $0.0001151   - **Exit Price**: $0.0002314   - **P&L**: +101.04% (+0.010104 SOL)   - **Reason**: Trailing stop triggered: +101.0% profit, peak +155.9%, drop 54.8% >= 15.0%   - **Hold Time**: 6.5 hours   - **Transaction**: https://solscan.io/tx/4zV

**200303** (cron):
> TRAILING #25 ADHD — position up 93%, momentum slowing, low liquidity. Trail 25% from 100% profit to capture gains while protecting against reversal.

## All Sessions

| File | Type | Calls | Status |
|------|------|-------|--------|
| session_20260421_194059_a914c3.json | interactive | 10 | 7 blocked, SILENT |
| session_20260421_200412_19ed98.json | interactive | 9 | clean |
| session_20260421_201200_51f182.json | interactive | 18 | clean |
| session_20260421_202049_036051.json | interactive | 22 | 3 cfg |
| session_20260421_202810_146d79.json | interactive | 18 | 1 buy, 7 blocked |
| session_20260421_205012_9c1982.json | interactive | 17 | 7 blocked, 3 cfg, SILENT |
| session_20260421_211214_c0d656.json | interactive | 15 | 6 blocked, 2 cfg, SILENT |
| session_20260421_230451_50119f60.json | interactive | 9 | 2 err |
| session_cron_36cac1573e00_20260421_193955.json | cron | 10 | 7 blocked, SILENT |
| session_cron_36cac1573e00_20260421_200515.json | cron | 4 | 1 buy, 2 blocked |
| session_cron_36cac1573e00_20260421_202656.json | cron | 10 | 1 buy, 6 blocked |
| session_cron_36cac1573e00_20260421_204912.json | cron | 10 | 7 blocked, SILENT |
| session_cron_36cac1573e00_20260421_211107.json | cron | 10 | 6 blocked, SILENT |
| session_cron_36cac1573e00_20260421_213313.json | cron | 4 | 1 blocked, SILENT |
| session_cron_36cac1573e00_20260421_215343.json | cron | 3 | 1 blocked, SILENT |
| session_cron_36cac1573e00_20260421_221514.json | cron | 3 | 1 blocked, SILENT |
| session_cron_36cac1573e00_20260421_223626.json | cron | 4 | 1 blocked, SILENT |
| session_cron_36cac1573e00_20260421_225654.json | cron | 4 | 1 blocked, SILENT |
| session_cron_464481e5aba5_20260421_222641.json | cron | 3 | clean |
| session_cron_b9e450064246_20260421_230022.json | cron | 8 | 1 err |
| session_cron_ddb1dd8f4608_20260421_194202.json | cron | 1 | SILENT |
| session_cron_ddb1dd8f4608_20260421_204558.json | cron | 1 | SILENT |
| session_cron_ddb1dd8f4608_20260421_214612.json | cron | 1 | SILENT |
| session_cron_ddb1dd8f4608_20260421_224717.json | cron | 2 | 2 sell |
| session_cron_f60865721cef_20260421_200303.json | cron | 9 | clean |
| session_cron_f60865721cef_20260421_221944.json | cron | 8 | clean |
