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
        "prompt": (
            "Scan for new trending Solana tokens. Use crypto-scanner trending --limit 10, "
            "then for the top 3 run onchain-analyzer safety. Report any token with safety "
            "score >= 60 and liquidity > $10k. If you find a good candidate, run the full "
            "pipeline: analyze -> risk check -> buy if approved. Position size is auto-calculated "
            "from trading-config.yaml. Mode (paper/real) is read from config. Be concise."
        ),
    },
    {
        "name": "position-check",
        "schedule": "every 30m",
        "skills": ["trade-executor", "trade-journal", "crypto-scanner"],
        "prompt": (
            "Check all open positions for exit signals. Use trade-executor check-exits. "
            "If any stop-loss is triggered, execute the sell immediately (Jupiter sell in real mode). "
            "For take-profit signals, evaluate if we should hold or sell based on current momentum. "
            "Also run trade-executor portfolio to show wallet balance and position summary. Report results."
        ),
    },
    {
        "name": "trend-analysis",
        "schedule": "every 240m",
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
        "schedule": "0 8 * * *",
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
        "schedule": "0 23 * * *",
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "prompt": (
            "End of day trading summary with self-learning. "
            "Step 1: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py update` to analyze trades and update MEMORY.md with new patterns. "
            "Step 2: Run trade-journal stats --days 1. "
            "Step 3: Check trade-executor portfolio. "
            "Step 4: Run risk-manager status. "
            "Step 5: Read the output from learning.py — what patterns were discovered? "
            "Write a daily recap: trades, P&L, lessons learned, discovered patterns, what to watch tomorrow. "
            "Step 6: If any pattern has confidence HIGH, update risk-manager config accordingly "
            "(e.g. raise min_safety_score). "
            "If daily loss limit was approached, flag it."
        ),
    },
    {
        "name": "weekly-recap",
        "schedule": "0 10 * * 0",
        "skills": ["trade-journal", "trade-executor", "risk-manager", "crypto-scanner"],
        "prompt": (
            "Weekly trading recap with deep learning review. "
            "Step 1: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py update --days 7` to refresh MEMORY.md. "
            "Step 2: Run `python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns` to see all discovered patterns. "
            "Step 3: Run trade-journal stats --days 7. Export trades: trade-journal export. "
            "Step 4: Analyze: total P&L, win rate, best/worst trades, avg hold time, which signals worked. "
            "Step 5: Review trade execution quality (slippage, timing). "
            "Step 6: Based on patterns, suggest specific changes to risk-manager config "
            "(min_safety_score, stop_loss_pct, take_profit_min_pct). "
            "Step 7: Update MEMORY.md 'Known Patterns' section with new bullish/bearish signals. "
            "Step 8: If win rate <40%, tighten filters. If >60%, consider loosening slightly."
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
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "created_at": now,
        "next_run_at": compute_next_run(schedule),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        "deliver": "local",
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
