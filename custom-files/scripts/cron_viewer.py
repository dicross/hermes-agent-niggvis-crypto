#!/usr/bin/env python3
"""
Cron Viewer — Browse cron job outputs easily.

Usage:
    python3 cron_viewer.py                      # Show all jobs + last run summary
    python3 cron_viewer.py --job token-scan     # Show outputs for specific job
    python3 cron_viewer.py --last 3             # Last 3 outputs per job
    python3 cron_viewer.py --job token-scan --read last   # Read last output
    python3 cron_viewer.py --job token-scan --read 2      # Read 2nd most recent
    python3 cron_viewer.py --tail 50            # Last 50 lines of guardian log
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
CRON_DIR = HERMES_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"
OUTPUT_DIR = CRON_DIR / "output"
GUARDIAN_LOG = CRON_DIR / "guardian.log"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_jobs() -> list:
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE) as f:
        data = json.load(f)
    return data.get("jobs", []) if isinstance(data, dict) else data


def get_outputs(job_id: str) -> list:
    """Get sorted list of output files for a job."""
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists():
        return []
    files = sorted(job_dir.glob("*.md"), reverse=True)
    return files


def extract_response(filepath: Path) -> str:
    """Extract just the ## Response section from cron output."""
    content = filepath.read_text()
    marker = "## Response"
    idx = content.rfind(marker)
    if idx >= 0:
        return content[idx + len(marker):].strip()
    # Fallback: last 30 lines
    lines = content.strip().split("\n")
    return "\n".join(lines[-30:])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_overview(args):
    """Show all jobs with status."""
    jobs = load_jobs()
    if not jobs:
        print("No cron jobs found.")
        return

    print("📋 CRON JOBS OVERVIEW\n")
    print(f"  {'Name':<20} {'Schedule':<15} {'Runs':>5} {'Last Status':>12} {'Last Run'}")
    print(f"  {'-'*20} {'-'*15} {'-'*5} {'-'*12} {'-'*20}")

    for j in jobs:
        name = j.get("name", "?")[:20]
        schedule = j.get("schedule_display", "?")[:15]
        runs = j.get("repeat", {}).get("completed", 0) if isinstance(j.get("repeat"), dict) else 0
        status = j.get("last_status", "—")
        last_run = j.get("last_run_at", "—")
        if last_run and last_run != "—":
            try:
                dt = datetime.fromisoformat(last_run)
                last_run = dt.strftime("%m-%d %H:%M")
            except Exception:
                last_run = last_run[:16]

        state = "🟢" if j.get("enabled") else "⏸️"
        print(f"  {state} {name:<18} {schedule:<15} {runs:>5} {status:>12} {last_run}")

    # Show outputs count
    print(f"\n  Output dir: {OUTPUT_DIR}")

    for j in jobs:
        outputs = get_outputs(j["id"])
        if outputs:
            latest = outputs[0]
            resp = extract_response(latest)
            # First meaningful line
            first_line = ""
            for line in resp.split("\n"):
                line = line.strip()
                if line and line != "[SILENT]":
                    first_line = line[:80]
                    break
            if first_line:
                print(f"\n  📄 {j.get('name', '?')} (last): {first_line}...")


def cmd_job_detail(args):
    """Show outputs for a specific job."""
    jobs = load_jobs()
    job = None
    for j in jobs:
        if j.get("name") == args.job or j.get("id") == args.job:
            job = j
            break

    if not job:
        print(f"Job '{args.job}' not found.")
        print(f"Available: {', '.join(j.get('name', '?') for j in jobs)}")
        return

    outputs = get_outputs(job["id"])

    if args.read:
        # Read specific output
        idx = 0 if args.read == "last" else int(args.read) - 1
        if idx >= len(outputs):
            print(f"Only {len(outputs)} outputs available.")
            return
        filepath = outputs[idx]
        print(f"📄 {job.get('name')} — {filepath.name}\n")
        resp = extract_response(filepath)
        print(resp)
        return

    # List recent outputs
    limit = args.last or 5
    print(f"📋 {job.get('name')} — last {min(limit, len(outputs))} runs\n")
    print(f"  Schedule: {job.get('schedule_display')}")
    print(f"  Total runs: {job.get('repeat', {}).get('completed', 0)}")
    print(f"  Last status: {job.get('last_status', '?')}")
    print()

    for i, fp in enumerate(outputs[:limit]):
        resp = extract_response(fp)
        is_silent = resp.strip() == "[SILENT]"
        if is_silent:
            print(f"  [{i+1}] {fp.name} — [SILENT]")
        else:
            # First 2 meaningful lines
            lines = [l.strip() for l in resp.split("\n") if l.strip()][:2]
            preview = " | ".join(lines)[:100]
            print(f"  [{i+1}] {fp.name}")
            print(f"      {preview}")
        print()

    print(f"  Read full: python3 cron_viewer.py --job {args.job} --read 1")


def cmd_tail_guardian(args):
    """Show last N lines of guardian log."""
    if not GUARDIAN_LOG.exists():
        print("Guardian log not found. Start guardian first:")
        print("  python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch")
        return

    with open(GUARDIAN_LOG) as f:
        lines = f.readlines()

    n = args.tail or 30
    for line in lines[-n:]:
        print(line.rstrip())


def main():
    parser = argparse.ArgumentParser(description="Cron Viewer — browse job outputs")
    parser.add_argument("--job", help="Job name or ID to inspect")
    parser.add_argument("--last", type=int, help="Show last N outputs")
    parser.add_argument("--read", help="Read output: 'last' or number (1=most recent)")
    parser.add_argument("--tail", type=int, nargs="?", const=30, help="Show guardian log (last N lines)")

    args = parser.parse_args()

    if args.tail is not None:
        cmd_tail_guardian(args)
    elif args.job:
        cmd_job_detail(args)
    else:
        cmd_overview(args)


if __name__ == "__main__":
    main()
