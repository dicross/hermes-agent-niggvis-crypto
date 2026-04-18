#!/usr/bin/env bash
# Setup cron jobs for Niggvis crypto trading agent.
# Run on WSL after skills are installed.
#
# Usage: bash custom-files/setup-cron.sh
#
# Prerequisites:
# - hermes installed and in PATH
# - Skills installed (bash custom-files/install-skills.sh)
# - Gateway running (hermes gateway)

set -euo pipefail

HERMES="${HOME}/.local/bin/hermes"

if ! command -v "$HERMES" &>/dev/null; then
    echo "❌ hermes not found at $HERMES"
    exit 1
fi

echo "🕐 Setting up cron jobs for Niggvis trading agent..."
echo ""

# 1. Every 15 minutes: Scan for new tokens
echo "  → Token scanner (every 15 min)"
$HERMES cron create \
    --name "token-scan" \
    --schedule "*/15 * * * *" \
    --prompt "Scan for new trending Solana tokens. Use crypto-scanner trending --limit 10, then for the top 3 run onchain-analyzer safety. Report any token with safety score >= 60 and liquidity > \$10k. If you find a good candidate, run the full pipeline: analyze → risk check → paper buy if approved. Be concise." \
    --skills crypto-scanner,onchain-analyzer,trade-executor,risk-manager,trade-journal \
    2>/dev/null || echo "    (already exists or error)"

# 2. Every hour: Check open positions for exits
echo "  → Position check (hourly)"
$HERMES cron create \
    --name "position-check" \
    --schedule "0 * * * *" \
    --prompt "Check all open positions for exit signals. Use trade-executor check-exits. If any stop-loss is triggered, execute the sell immediately. For take-profit signals, evaluate if we should hold or sell based on current momentum (check DEXScreener volume trend). Report results." \
    --skills trade-executor,trade-journal,crypto-scanner \
    2>/dev/null || echo "    (already exists or error)"

# 3. Every 4 hours: Trend analysis
echo "  → Trend analysis (every 4h)"
$HERMES cron create \
    --name "trend-analysis" \
    --schedule "0 */4 * * *" \
    --prompt "Run a market trend analysis. Use crypto-scanner metas to check trending categories. Then crypto-scanner trending --limit 20 for top movers. Identify which categories are hot (AI, meme, gaming, DeFi). Compare with our open positions — are we aligned with trends? Write a brief trend report." \
    --skills crypto-scanner,trade-journal \
    2>/dev/null || echo "    (already exists or error)"

# 4. 8:00 UTC: Morning portfolio report
echo "  → Portfolio report (8:00 UTC)"
$HERMES cron create \
    --name "morning-report" \
    --schedule "0 8 * * *" \
    --prompt "Morning portfolio report. Run trade-executor portfolio to show all positions with live prices. Then risk-manager status for risk dashboard. Then trade-journal stats --days 1 for yesterday's performance. Summarize: open positions, unrealized P&L, daily P&L, budget usage, any concerns." \
    --skills trade-executor,risk-manager,trade-journal \
    2>/dev/null || echo "    (already exists or error)"

# 5. 23:00 UTC: End of day summary
echo "  → Daily summary (23:00 UTC)"
$HERMES cron create \
    --name "daily-summary" \
    --schedule "0 23 * * *" \
    --prompt "End of day trading summary. Run trade-journal stats --days 1 for today's trades. Check trade-executor portfolio for open positions. Run risk-manager status. Write a daily recap: trades made, wins/losses, lessons learned, what to watch tomorrow. If daily loss limit was approached, flag it." \
    --skills trade-journal,trade-executor,risk-manager,crypto-scanner \
    2>/dev/null || echo "    (already exists or error)"

# 6. Sunday 10:00 UTC: Weekly recap
echo "  → Weekly recap (Sunday 10:00 UTC)"
$HERMES cron create \
    --name "weekly-recap" \
    --schedule "0 10 * * 0" \
    --prompt "Weekly trading recap. Run trade-journal stats --days 7. Analyze: total P&L, win rate, best/worst trades, average hold time, which token categories performed best. Compare paper vs real results. Identify patterns — what worked, what didn't. Suggest adjustments to strategy for next week. Export trades: trade-journal export." \
    --skills trade-journal,trade-executor,risk-manager,crypto-scanner \
    2>/dev/null || echo "    (already exists or error)"

echo ""
echo "✅ Cron jobs configured. Verify with:"
echo "   $HERMES cron list"
echo ""
echo "⚠️  Make sure gateway is running:"
echo "   $HERMES gateway"
echo "   # or as service:"
echo "   $HERMES gateway install"
