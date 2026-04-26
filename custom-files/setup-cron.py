#!/usr/bin/env python3
"""
Setup cron jobs for Niggvis crypto trading agent.

Run from repo root on WSL after skills are installed:
    python3 custom-files/setup-cron.py

Or from anywhere:
    python3 /path/to/setup-cron.py

This writes directly to ~/.hermes/cron/jobs.json using the Hermes cron API.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
CRON_DIR = HERMES_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"

# ---------------------------------------------------------------------------
# Job definitions
# ---------------------------------------------------------------------------

JOBS = [
    {
        "name": "token-scan",
        "schedule": "every 15m",
        "skills": ["crypto-scanner", "onchain-analyzer", "trade-executor", "risk-manager", "trade-journal"],
        "deliver": "telegram",
        "prompt": (
            "Scan for new trending Solana tokens. Use crypto-scanner trending --limit 10. "
            "For promising tokens with liquidity > $10k, check the trading config first: "
            "run `python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-get can_open_new_positions` "
            "to check if new positions are allowed. "
            "If can_open_new_positions is false, do NOT buy anything and respond [SILENT]. "
            "If can_open_new_positions is true, go straight to executor.py buy "
            "(it runs full analyze + risk check internally). Do NOT run analyzer.py safety manually. "
            "Position size is auto-calculated from config. "
            "RESPONSE RULES: "
            "- If you executed a BUY: report token name, safety score, amount, price, tx link. "
            "- If NO buy was made (no candidates, all blocked, insufficient balance, new positions disabled): respond [SILENT]"
        ),
    },
    {
        "name": "position-check",
        "schedule": "every 30m",
        "skills": ["trade-executor", "trade-journal", "crypto-scanner"],
        "deliver": "telegram",
        "prompt": (
            "Check all open positions for exit signals. Use trade-executor check-exits. "
            "If any stop-loss or trailing stop is triggered, execute the sell immediately. "
            "RESPONSE RULES: "
            "- If you executed a SELL (SL/TP/trailing triggered): report token, entry/exit price, P&L%, reason, tx link. "
            "- If a position moved more than 50% since last check (up or down): report the alert. "
            "- If NO sells and no big moves: respond [SILENT]"
        ),
    },
    {
        "name": "trend-analysis",
        "schedule": "every 240m",
        "skills": ["crypto-scanner", "trade-journal"],
        "deliver": "local",
        "prompt": (
            "Run a market trend analysis. Use crypto-scanner metas to check trending categories. "
            "Then crypto-scanner trending --limit 20 for top movers. Identify which categories "
            "are hot (AI, meme, gaming, DeFi). Compare with our open positions - are we aligned "
            "with trends? Write a brief trend report (5 lines max)."
        ),
    },
    {
        "name": "morning-report",
        "schedule": "0 8 * * *",
        "skills": ["trade-executor", "risk-manager", "trade-journal"],
        "deliver": "telegram",
        "prompt": (
            "Morning portfolio report. Run trade-executor portfolio, risk-manager status, "
            "trade-journal stats --days 1. Summarize in 5-8 lines: open positions, P&L, "
            "wallet balance, risk status, plan for today."
        ),
    },
    {
        "name": "daily-summary",
        "schedule": "0 23 * * *",
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "deliver": "telegram",
        "prompt": (
            "End of day trading summary with self-learning. "
            "Step 1: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py update` to analyze trades. "
            "Step 2: Run trade-journal stats --days 1. "
            "Step 3: Check trade-executor portfolio. "
            "Step 4: Run risk-manager status. "
            "Step 5: Write a daily recap in 8-10 lines: trades, P&L, lessons learned, what to watch tomorrow. "
            "Step 6: If you see a pattern that suggests a config change (e.g. too many losses → lower position size, "
            "SL too tight/loose, etc.), you MUST actually run the config-propose command — do NOT just mention it:\n"
            "  python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose "
            "--key <KEY> --value <VALUE> --reason \"<REASON>\"\n"
            "Example keys: position_pct, stop_loss_pct, min_safety_score, min_liquidity_usd, slippage_bps.\n"
            "If no pattern warrants a change, skip this step. "
            "IMPORTANT: Do NOT just write 'suggest config change' or 'propose via config-propose' — "
            "you must actually execute the command. The proposal will be sent to Damian for approval."
        ),
    },
    {
        "name": "weekly-recap",
        "schedule": "0 10 * * 0",
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "deliver": "telegram",
        "prompt": (
            "Weekly trading recap. "
            "Step 1: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py update --days 7`. "
            "Step 2: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns`. "
            "Step 3: Run trade-journal stats --days 7. "
            "Step 4: Analyze: total P&L, win rate, best/worst trades, which signals worked. "
            "Step 5: Based on patterns, if a config change is warranted, EXECUTE this command:\n"
            "  python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose "
            "--key <KEY> --value <VALUE> --reason \"<REASON>\"\n"
            "Do NOT just write 'suggest X' — actually run config-propose. "
            "The proposal will be sent to Damian for approval. "
            "Keep report to 10-15 lines."
        ),
    },
    {
        "name": "position-evaluator",
        "schedule": "every 9999m",
        "paused": True,
        "skills": ["trade-executor", "trade-journal", "risk-manager", "crypto-scanner", "onchain-analyzer"],
        "deliver": "telegram",
        "prompt": (
            "You are the Position Evaluator. Guardian triggered you because a position "
            "crossed an evaluation tier.\n\n"
            "Step 1: List files in ~/.hermes/cron/pending-evaluations/ to find pending trade(s).\n"
            "  Each file is named <trade_id>.json and contains: trade_id, token, address, entry_price.\n"
            "  Process ALL pending files (there may be multiple concurrent evaluations).\n"
            "  For each pending file:\n\n"
            "Step 2: Read trade-journal to find that trade (token address, entry price, "
            "current P&L, amount, time held).\n"
            "Step 3: Fetch fresh token data from DEXScreener:\n"
            "  python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py info <TOKEN_ADDRESS>\n"
            "Step 4: Analyze the position. Consider:\n"
            "  - Price momentum (1h, 6h, 24h changes)\n"
            "  - Buy/sell ratio (are buyers dominant?)\n"
            "  - Volume relative to market cap (healthy trading activity?)\n"
            "  - Liquidity depth (enough to exit safely?)\n"
            "  - Is this organic growth or a pump that will dump?\n"
            "  - How long has the position been held?\n"
            "  - Market context (is the whole market up or just this token?)\n\n"
            "Step 5: Decide ONE of these strategies:\n"
            "  a) HOLD — momentum is strong, keep riding. Set review_at_pct (when to re-evaluate).\n"
            "  b) TRAILING — set trailing stop. Specify trailing_pct and trailing_from_pct.\n"
            "  c) PARTIAL_SELL — sell a portion (e.g. 50%). Specify sell_pct and remaining strategy.\n"
            "  d) HARD_TP — set hard take-profit at a specific %.\n\n"
            "Step 6: Write exit_strategy to the trade in journal. Use this exact Python command:\n"
            "  python3 -c \"\n"
            "import json, os\n"
            "j = json.load(open(os.path.expanduser('~/.hermes/memories/trade-journal.json')))\n"
            "for t in j['trades']:\n"
            "  if t['id'] == TRADE_ID and t['status'] == 'open':\n"
            "    t['exit_strategy'] = {\n"
            "      'type': 'hold|trailing|partial_sell|hard_tp',\n"
            "      'trailing_pct': 25,\n"
            "      'trailing_from_pct': 200,\n"
            "      'sell_pct': 50,\n"
            "      'hard_tp_pct': 300,\n"
            "      'review_at_pct': 300,\n"
            "      'sl_pct': 20,\n"
            "      'reason': 'Your reasoning here'\n"
            "    }\n"
            "    t['evaluation_pending'] = False\n"
            "    break\n"
            "json.dump(j, open(os.path.expanduser('~/.hermes/memories/trade-journal.json'), 'w'), indent=2)\n"
            "\"\n"
            "  (Fill in only the fields relevant to your chosen strategy.)\n\n"
            "Step 7: Delete the pending file after processing:\n"
            "  rm ~/.hermes/cron/pending-evaluations/<trade_id>.json\n\n"
            "Step 8: Report your decision.\n"
            "  Read evaluation_detail from trading-config.yaml notifications section.\n"
            "  If 'full': explain your reasoning in 5-10 lines.\n"
            "  If 'short': one-line summary like 'HOLD #25 ADHD — strong momentum, review at 300%'.\n"
            "  If notifications.on_evaluation_complete is false: respond [SILENT].\n\n"
            "IMPORTANT:\n"
            "- Do NOT execute sells yourself. Only write strategy to journal. Guardian sells.\n"
            "- For partial_sell: write the sell_pct. Guardian will execute the partial sell.\n"
            "- Always set sl_pct (minimum stop-loss floor as % profit from entry).\n"
            "- Process ALL pending files in one session, not just the first one.\n"
            "- If you cannot fetch data or analyze: write default strategy from config "
            "(risk.default_exit_strategy) and note the failure reason."
        ),
    },
]

# ---------------------------------------------------------------------------
# Schedule parsing (matches Hermes cron/jobs.py format exactly)
# ---------------------------------------------------------------------------

import re


def parse_schedule(schedule_str: str) -> dict:
    """Parse schedule string into Hermes-compatible format."""
    s = schedule_str.strip()
    s_lower = s.lower()

    # "every Xm/h/d" → interval
    if s_lower.startswith("every "):
        duration = s[6:].strip().lower()
        match = re.match(r'^(\d+)\s*(m|h|d)', duration)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            multipliers = {'m': 1, 'h': 60, 'd': 1440}
            minutes = value * multipliers[unit]
            return {"kind": "interval", "minutes": minutes, "display": f"every {minutes}m"}

    # Cron expression (5 space-separated fields)
    parts = s.split()
    if len(parts) >= 5 and all(re.match(r'^[\d\*\-,/]+$', p) for p in parts[:5]):
        return {"kind": "cron", "expr": s, "display": s}

    raise ValueError(f"Cannot parse schedule: {s}")


def compute_next_run(schedule: dict) -> str:
    now = datetime.now(timezone.utc)
    kind = schedule.get("kind")
    if kind == "interval":
        minutes = schedule.get("minutes", 15)
        return (now + timedelta(minutes=minutes)).isoformat()
    elif kind == "cron":
        # Without croniter, approximate — scheduler will fix it
        return (now + timedelta(minutes=1)).isoformat()
    return (now + timedelta(minutes=1)).isoformat()


# ---------------------------------------------------------------------------
# Logic (matches Hermes jobs.json format: {"jobs": [...]})
# ---------------------------------------------------------------------------


def load_jobs() -> list:
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, "r") as f:
        data = json.load(f)
    # Hermes format: {"jobs": [...], "updated_at": "..."}
    if isinstance(data, dict):
        return data.get("jobs", [])
    # Fallback: bare list (shouldn't happen with correct format)
    if isinstance(data, list):
        return data
    return []


def save_jobs(jobs: list):
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    tmp = str(JOBS_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"jobs": jobs, "updated_at": now}, f, indent=2, default=str)
    os.replace(tmp, str(JOBS_FILE))
    try:
        os.chmod(str(JOBS_FILE), 0o600)
    except OSError:
        pass


def make_job(definition: dict) -> dict:
    """Create a job dict matching Hermes cron/jobs.py create_job() output."""
    now = datetime.now(timezone.utc).isoformat()
    job_id = uuid.uuid4().hex[:12]
    schedule = parse_schedule(definition["schedule"])
    skills = definition["skills"]

    return {
        "id": job_id,
        "name": definition["name"],
        "prompt": definition["prompt"],
        "skills": skills,
        "skill": skills[0] if skills else None,
        "model": None,
        "provider": None,
        "base_url": None,
        "script": None,
        "schedule": schedule,
        "schedule_display": schedule.get("display", definition["schedule"]),
        "repeat": {"times": None, "completed": 0},
        "enabled": not definition.get("paused", False),
        "state": "paused" if definition.get("paused") else "scheduled",
        "paused_at": now if definition.get("paused") else None,
        "paused_reason": "Triggered on-demand by guardian" if definition.get("paused") else None,
        "created_at": now,
        "next_run_at": None if definition.get("paused") else compute_next_run(schedule),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        "deliver": definition.get("deliver", "local"),
        "origin": None,
    }


def main():
    print("🕐 Setting up cron jobs for Niggvis trading agent...\n")

    existing = load_jobs()
    existing_names = {j.get("name") for j in existing}

    added = 0
    skipped = 0

    for defn in JOBS:
        name = defn["name"]
        if name in existing_names:
            print(f"  ⏭ {name} — already exists, skipping")
            skipped += 1
        else:
            job = make_job(defn)
            existing.append(job)
            print(f"  ✅ {name} — created ({defn['schedule']})")
            added += 1

    save_jobs(existing)

    print(f"\n📊 Result: {added} added, {skipped} skipped")
    print(f"   Jobs file: {JOBS_FILE}")
    print(f"\n   Verify: hermes → /cron list")
    print(f"\n⚠️  Make sure gateway is running:")
    print(f"   hermes gateway")
    print(f"   # or as service:")
    print(f"   hermes gateway install")

    # croniter check
    try:
        import croniter
        print(f"\n   ✅ croniter installed")
    except ImportError:
        print(f"\n   ⚠️  croniter not installed — cron expressions (daily/weekly) won't fire.")
        print(f"   Fix: pip install croniter")


if __name__ == "__main__":
    main()
