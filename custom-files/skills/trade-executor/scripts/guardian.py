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
    python3 guardian.py --watch --history 5      # Show last 5 runs
    python3 guardian.py --dry-run    # Check but don't sell
    python3 guardian.py --no-tui     # Disable screen clearing (for logs)

VPS/SSH — run inside tmux or screen so it survives disconnect:
    tmux new -s guardian
    python3 guardian.py --watch
    # Ctrl+B then D to detach
    # tmux attach -t guardian  to reattach

Designed to be lightweight — no LLM calls, just API + math.
Run alongside hermes gateway for real-time protection.
"""

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import fcntl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
TRADING_CONFIG_PATH = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
GUARDIAN_LOCK = os.path.expanduser("~/.hermes/cron/.guardian.lock")
GUARDIAN_LOG = os.path.expanduser("~/.hermes/cron/guardian.log")
DEXSCREENER_BASE = "https://api.dexscreener.com"
SKILLS_DIR = os.path.expanduser("~/.hermes/skills")

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

# Run history for TUI display
_run_history: deque = deque(maxlen=10)
_current_run_lines: list = []
_tui_enabled: bool = True
_history_size: int = 3


def _local_now() -> datetime:
    """Return current local time (uses system timezone)."""
    return datetime.now().astimezone()


def log(msg: str):
    ts = _local_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    _current_run_lines.append(line)
    # Always append to log file (with UTC for consistency)
    try:
        with open(GUARDIAN_LOG, "a") as f:
            ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts_utc}] {msg}\n")
    except Exception:
        pass


def _flush_run():
    """Save current run lines to history and reset."""
    global _current_run_lines
    if _current_run_lines:
        _run_history.append(list(_current_run_lines))
        _current_run_lines = []


def _render_tui():
    """Clear screen and render last N runs + current."""
    if not _tui_enabled:
        # Fallback: just print current run lines normally
        for line in _current_run_lines:
            print(line)
        return

    term_width = shutil.get_terminal_size((80, 24)).columns
    separator = "─" * min(term_width, 72)

    # Clear screen — use os.system('clear') as fallback for WSL
    os.system('clear')

    # Header
    now = _local_now().strftime("%H:%M:%S %Z")
    print(f"🛡️  GUARDIAN  │  {now}  │  interval: {_watch_interval}s  │  history: {_history_size}")
    print(separator)

    # Previous runs (gray = dimmed)
    GRAY = "\033[90m"
    RESET = "\033[0m"
    history_to_show = list(_run_history)[-_history_size:]
    if history_to_show:
        for i, run_lines in enumerate(history_to_show):
            for line in run_lines:
                print(f"{GRAY}  {line}{RESET}")
            if i < len(history_to_show) - 1:
                print(f"{GRAY}  {separator}{RESET}")
        print(separator)

    # Current run (normal color = bright)
    if _current_run_lines:
        for line in _current_run_lines:
            print(f"  {line}")
    else:
        print("  Waiting for next check...")

    # Footer
    print(separator)
    next_check = _local_now().strftime("%H:%M:%S")
    print(f"  Next check in ~{_watch_interval}s  │  Ctrl+C to stop")

    sys.stdout.flush()


# Watch interval (set from args)
_watch_interval: int = 120


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


def _parse_yaml_flat(path: str) -> dict:
    """Minimal YAML parser for trading config."""
    if not os.path.exists(path):
        return {}
    result = {}
    stack = [(0, result)]
    with open(path) as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            content = stripped.strip()
            if ":" not in content:
                continue
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            if val and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]
            if val == "" or val == "[]":
                if val == "[]":
                    parent[key] = []
                else:
                    child = {}
                    parent[key] = child
                    stack.append((indent, child))
            else:
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.lower() in ("null", "none"):
                    val = None
                else:
                    try:
                        val = int(val)
                    except ValueError:
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                parent[key] = val
    return result


def _cfg(cfg: dict, *keys, default=None):
    d = cfg
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
        if d is None:
            return default
    return d


def save_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _execute_jupiter_sell(address: str) -> bool:
    """Execute real sell via Jupiter. Returns True if successful."""
    jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
    if not os.path.exists(jupiter_script):
        log("  ⚠️ jupiter_swap.py not found — cannot execute real sell")
        return False
    try:
        import subprocess
        # Use python_bin from config (venv with solders)
        tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)
        python_bin = _cfg(tcfg, "python_bin", default=sys.executable)
        if isinstance(python_bin, str):
            python_bin = os.path.expanduser(python_bin)
        if not os.path.exists(python_bin):
            python_bin = sys.executable
        result = subprocess.run(
            [python_bin, jupiter_script, "sell", "--token", address, "--pct", "100"],
            capture_output=True, text=True, timeout=60
        )
        if "Success" in result.stdout:
            log(f"  🔗 Jupiter sell executed")
            return True
        else:
            log(f"  ⚠️ Jupiter sell may have failed: {result.stdout[-200:]}")
            return False
    except Exception as e:
        log(f"  ❌ Jupiter sell error: {e}")
        return False


def check_positions(dry_run: bool = False) -> list:
    """Check all open positions. Returns list of actions taken."""
    journal = load_json(JOURNAL_PATH)
    tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)

    trades = journal.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not open_trades:
        return []

    sl_pct = _cfg(tcfg, "risk", "stop_loss_pct", default=-30)
    tp_pct = _cfg(tcfg, "risk", "take_profit_pct", default=100)
    kill = _cfg(tcfg, "risk", "kill_switch", default=False)
    mode = _cfg(tcfg, "mode", default="paper")

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
                # Real mode: execute Jupiter sell first
                if mode == "real":
                    _execute_jupiter_sell(addr)
                # Close trade in journal
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
                if mode == "real":
                    _execute_jupiter_sell(addr)
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
                if mode == "real":
                    _execute_jupiter_sell(addr)
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = datetime.now(timezone.utc).isoformat()
                t["exit_reason"] = f"Kill switch ({_cfg(tcfg, 'risk', 'kill_reason', default='manual')})"
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
    global _tui_enabled, _history_size, _watch_interval

    parser = argparse.ArgumentParser(description="Position Guardian — fast price monitor")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring loop")
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds (default: 120)")
    parser.add_argument("--history", type=int, default=3, help="Number of past runs to display (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't execute sells")
    parser.add_argument("--no-tui", action="store_true", help="Disable TUI (plain log output, good for piping)")
    args = parser.parse_args()

    _tui_enabled = not args.no_tui and sys.stdout.isatty()
    _history_size = args.history
    _watch_interval = args.interval

    if args.watch:
        if not acquire_lock():
            print("Guardian already running (lock held). Exiting.")
            sys.exit(0)

        log(f"Guardian started (interval: {args.interval}s, dry-run: {args.dry_run})")
        _render_tui()
        try:
            while True:
                _flush_run()
                try:
                    ts = _local_now().strftime("%H:%M:%S")
                    log(f"🔍 Check #{len(_run_history) + 1} at {ts}")
                    actions = check_positions(dry_run=args.dry_run)
                    if actions:
                        log(f"  → {len(actions)} action(s) taken")
                    else:
                        log("  ✅ No exit signals")
                except Exception as e:
                    log(f"  ❌ Error: {e}")
                _render_tui()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            log("Guardian stopped (Ctrl+C)")
            if _tui_enabled:
                print("\n👋 Guardian stopped.")
        finally:
            release_lock()
    else:
        _tui_enabled = False  # One-shot always plain
        log("🛡️ Guardian one-shot check")
        actions = check_positions(dry_run=args.dry_run)
        if not actions:
            log("  No exit signals.")
        for line in _current_run_lines:
            print(line)


if __name__ == "__main__":
    main()
