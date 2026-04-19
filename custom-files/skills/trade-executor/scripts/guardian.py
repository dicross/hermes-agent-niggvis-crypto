#!/usr/bin/env python3
"""
Position Guardian — Fast price monitor (no LLM, runs every 2-3 min).

Checks current prices of open positions against stop-loss and take-profit
thresholds. If triggered, executes the sell via trade-journal directly
(no need to wait for the hourly cron).

Usage:
    python3 guardian.py              # One-shot check
    python3 guardian.py --watch      # Continuous loop (every 2 min)
    python3 guardian.py --watch --interval 180   # Every 3 min
    python3 guardian.py --dry-run    # Check but don't sell

Designed to be lightweight — no LLM calls, just API + math.
Run alongside hermes gateway for real-time protection.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import fcntl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
RISK_CONFIG_PATH = os.path.expanduser("~/.hermes/memories/risk-config.json")
GUARDIAN_LOCK = os.path.expanduser("~/.hermes/cron/.guardian.lock")
GUARDIAN_LOG = os.path.expanduser("~/.hermes/cron/guardian.log")
DEXSCREENER_BASE = "https://api.dexscreener.com"

# ---------------------------------------------------------------------------
# Lock (prevent overlapping runs)
# ---------------------------------------------------------------------------

_lock_fd = None


def acquire_lock() -> bool:
    """Try to acquire exclusive lock. Returns False if already running."""
    global _lock_fd
    os.makedirs(os.path.dirname(GUARDIAN_LOCK), exist_ok=True)
    try:
        _lock_fd = open(GUARDIAN_LOCK, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except (IOError, OSError):
        return False


def release_lock():
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(GUARDIAN_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _http_get(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-guardian/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def get_price(address: str) -> float | None:
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{address}"
    data = _http_get(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    pairs = sorted(
        data,
        key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
        reverse=True,
    )
    price = pairs[0].get("priceUsd")
    return float(price) if price else None


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def check_positions(dry_run: bool = False) -> list:
    """Check all open positions. Returns list of actions taken."""
    journal = load_json(JOURNAL_PATH)
    risk_cfg = load_json(RISK_CONFIG_PATH)

    trades = journal.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not open_trades:
        return []

    sl_pct = risk_cfg.get("stop_loss_pct", -30)
    tp_pct = risk_cfg.get("take_profit_min_pct", 100)
    kill = risk_cfg.get("kill_switch", False)

    actions = []

    for t in open_trades:
        addr = t.get("address", "")
        if not addr:
            continue

        price = get_price(addr)
        if price is None:
            log(f"  #{t['id']} {t.get('token', '?')}: price unavailable")
            continue

        entry = float(t.get("entry_price", 0))
        if entry <= 0:
            continue

        pnl_pct = ((price - entry) / entry) * 100

        # Stop-loss check
        if pnl_pct <= sl_pct:
            action = f"STOP_LOSS #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (limit {sl_pct}%)"
            log(f"  🚨 {action}")

            if not dry_run:
                # Close trade directly in journal
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = datetime.now(timezone.utc).isoformat()
                t["exit_reason"] = f"Guardian auto-stop-loss ({pnl_pct:.1f}%)"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)")

            actions.append({"type": "STOP_LOSS", "id": t["id"], "pnl": pnl_pct})

        # Take-profit check
        elif pnl_pct >= tp_pct:
            action = f"TAKE_PROFIT #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (limit +{tp_pct}%)"
            log(f"  🎯 {action}")

            if not dry_run:
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = datetime.now(timezone.utc).isoformat()
                t["exit_reason"] = f"Guardian auto-take-profit ({pnl_pct:.1f}%)"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)")

            actions.append({"type": "TAKE_PROFIT", "id": t["id"], "pnl": pnl_pct})

        # Kill switch — sell everything
        elif kill:
            log(f"  🔴 KILL SWITCH — closing #{t['id']} {t.get('token', '?')}")
            if not dry_run:
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = datetime.now(timezone.utc).isoformat()
                t["exit_reason"] = f"Kill switch ({risk_cfg.get('kill_reason', 'manual')})"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
            actions.append({"type": "KILL", "id": t["id"], "pnl": pnl_pct})

        else:
            # Normal — just log status
            icon = "🟢" if pnl_pct >= 0 else "🔴"
            log(f"  {icon} #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}%")

    # Save if any changes
    if actions and not dry_run:
        save_json(JOURNAL_PATH, journal)

    return actions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Position Guardian — fast price monitor")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring loop")
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds (default: 120)")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't execute sells")
    args = parser.parse_args()

    if args.watch:
        if not acquire_lock():
            print("Guardian already running (lock held). Exiting.")
            sys.exit(0)

        log(f"🛡️ Guardian started (interval: {args.interval}s, dry-run: {args.dry_run})")
        try:
            while True:
                try:
                    actions = check_positions(dry_run=args.dry_run)
                    if actions:
                        log(f"  → {len(actions)} action(s) taken")
                except Exception as e:
                    log(f"  Error: {e}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            log("Guardian stopped (Ctrl+C)")
        finally:
            release_lock()
    else:
        log("🛡️ Guardian one-shot check")
        actions = check_positions(dry_run=args.dry_run)
        if not actions:
            log("  No exit signals.")


if __name__ == "__main__":
    main()
