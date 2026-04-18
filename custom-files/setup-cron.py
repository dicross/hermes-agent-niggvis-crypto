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
        "schedule_display": "every 15m",
        "schedule": {"kind": "interval", "minutes": 15, "display": "every 15m"},
        "skills": ["crypto-scanner", "onchain-analyzer", "trade-executor", "risk-manager", "trade-journal"],
        "prompt": (
            "Scan for new trending Solana tokens. Use crypto-scanner trending --limit 10, "
            "then for the top 3 run onchain-analyzer safety. Report any token with safety "
            "score >= 60 and liquidity > $10k. If you find a good candidate, run the full "
            "pipeline: analyze -> risk check -> paper buy if approved. Be concise."
        ),
    },
    {
        "name": "position-check",
        "schedule_display": "every 60m",
        "schedule": {"kind": "interval", "minutes": 60, "display": "every 60m"},
        "skills": ["trade-executor", "trade-journal", "crypto-scanner"],
        "prompt": (
            "Check all open positions for exit signals. Use trade-executor check-exits. "
            "If any stop-loss is triggered, execute the sell immediately. For take-profit "
            "signals, evaluate if we should hold or sell based on current momentum. Report results."
        ),
    },
    {
        "name": "trend-analysis",
        "schedule_display": "every 240m",
        "schedule": {"kind": "interval", "minutes": 240, "display": "every 240m"},
        "skills": ["crypto-scanner", "trade-journal"],
        "prompt": (
            "Run a market trend analysis. Use crypto-scanner metas to check trending categories. "
            "Then crypto-scanner trending --limit 20 for top movers. Identify which categories "
            "are hot (AI, meme, gaming, DeFi). Compare with our open positions - are we aligned "
            "with trends? Write a brief trend report."
        ),
    },
    {
        "name": "morning-report",
        "schedule_display": "0 8 * * *",
        "schedule": {"kind": "cron", "expr": "0 8 * * *", "display": "0 8 * * *"},
        "skills": ["trade-executor", "risk-manager", "trade-journal"],
        "prompt": (
            "Morning portfolio report. Run trade-executor portfolio to show all positions with "
            "live prices. Then risk-manager status for risk dashboard. Then trade-journal stats "
            "--days 1 for yesterday's performance. Summarize: open positions, unrealized P&L, "
            "daily P&L, budget usage, any concerns."
        ),
    },
    {
        "name": "daily-summary",
        "schedule_display": "0 23 * * *",
        "schedule": {"kind": "cron", "expr": "0 23 * * *", "display": "0 23 * * *"},
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "prompt": (
            "End of day trading summary. Run trade-journal stats --days 1 for today's trades. "
            "Check trade-executor portfolio for open positions. Run risk-manager status. Write "
            "a daily recap: trades made, wins/losses, lessons learned, what to watch tomorrow. "
            "If daily loss limit was approached, flag it."
        ),
    },
    {
        "name": "weekly-recap",
        "schedule_display": "0 10 * * 0",
        "schedule": {"kind": "cron", "expr": "0 10 * * 0", "display": "0 10 * * 0"},
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "prompt": (
            "Weekly trading recap. Run trade-journal stats --days 7. Analyze: total P&L, win rate, "
            "best/worst trades, average hold time, which token categories performed best. Compare "
            "paper vs real results. Identify patterns - what worked, what didn't. Suggest adjustments "
            "to strategy for next week. Export trades: trade-journal export."
        ),
    },
]

# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------


def load_jobs() -> list:
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, "r") as f:
        return json.load(f)


def save_jobs(jobs: list):
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(JOBS_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(jobs, f, indent=2, default=str)
    os.replace(tmp, str(JOBS_FILE))
    try:
        os.chmod(str(JOBS_FILE), 0o600)
    except OSError:
        pass


def compute_next_run(schedule: dict) -> str:
    now = datetime.now(timezone.utc)
    kind = schedule.get("kind")
    if kind == "interval":
        minutes = schedule.get("minutes", 15)
        next_run = now + timedelta(minutes=minutes)
    elif kind == "cron":
        # Simple next-run calculation without croniter
        # Just set it to now + 1 minute, the scheduler will compute the real next
        next_run = now + timedelta(minutes=1)
    else:
        next_run = now + timedelta(minutes=1)
    return next_run.isoformat()


def make_job(definition: dict) -> dict:
    now = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    return {
        "id": job_id,
        "name": definition["name"],
        "prompt": definition["prompt"],
        "schedule": definition["schedule"],
        "state": "active",
        "skills": definition["skills"],
        "skill": definition["skills"][0] if definition["skills"] else None,
        "repeat": None,
        "deliver": None,
        "origin": None,
        "model": None,
        "provider": None,
        "base_url": None,
        "script": None,
        "created_at": now.isoformat(),
        "next_run_at": compute_next_run(definition["schedule"]),
        "last_run_at": None,
        "last_status": None,
        "run_count": 0,
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
            print(f"  ✅ {name} — created ({defn['schedule_display']})")
            added += 1

    save_jobs(existing)

    print(f"\n📊 Result: {added} added, {skipped} skipped")
    print(f"   Jobs file: {JOBS_FILE}")
    print(f"\n   Verify: hermes → /cron list")
    print(f"\n⚠️  Make sure gateway is running:")
    print(f"   hermes gateway")
    print(f"   # or as service:")
    print(f"   hermes gateway install")

    # Also ensure croniter is installed (needed for cron expressions)
    try:
        import croniter
        print(f"\n   ✅ croniter installed")
    except ImportError:
        print(f"\n   ⚠️  croniter not installed! Cron expressions won't work.")
        print(f"   Fix: pip install croniter")


if __name__ == "__main__":
    main()
