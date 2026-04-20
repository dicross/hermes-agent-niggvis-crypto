#!/usr/bin/env python3
"""
Position Guardian — Adaptive price monitor (no LLM, lightweight).

Checks current prices of open positions against stop-loss, take-profit,
and trailing-stop thresholds. If triggered, executes sell via Jupiter.

Adaptive interval (from trading-config.yaml → guardian section):
  - idle (120s default): no open positions
  - active (20s default): positions open, normal range
  - hot (10s default): position near SL or TP (within hot_zone_pct)

Usage:
    python3 guardian.py              # One-shot check
    python3 guardian.py --watch      # Continuous loop (adaptive interval)
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
GATEWAY_CONFIG_PATH = os.path.expanduser("~/.hermes/gateway.json")
HERMES_CONFIG_PATH = os.path.expanduser("~/.hermes/config.yaml")
GUARDIAN_LOCK = os.path.expanduser("~/.hermes/cron/.guardian.lock")
GUARDIAN_LOG = os.path.expanduser("~/.hermes/cron/guardian.log")
DEXSCREENER_BASE = "https://api.dexscreener.com"
SOLANA_MAINNET_RPC = "https://api.mainnet-beta.solana.com"
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
_check_counter: int = 0


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
    mode_label = "hot" if _watch_interval <= 10 else ("active" if _watch_interval <= 30 else "idle")
    print(f"🛡️  GUARDIAN  │  {now}  │  {_watch_interval}s ({mode_label})  │  history: {_history_size}")
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


def _http_post(url: str, data: dict) -> dict | None:
    """Send JSON POST request. Returns parsed response or None."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "hermes-guardian/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

_telegram_bot_token: str | None = None
_telegram_chat_id: str | None = None
_telegram_loaded: bool = False


def _load_telegram_config():
    """Load Telegram bot token and home chat_id from gateway config."""
    global _telegram_bot_token, _telegram_chat_id, _telegram_loaded
    if _telegram_loaded:
        return
    _telegram_loaded = True

    # Try gateway.json first (legacy), then config.yaml
    gw = {}
    if os.path.exists(GATEWAY_CONFIG_PATH):
        try:
            with open(GATEWAY_CONFIG_PATH) as f:
                gw = json.load(f) or {}
        except Exception:
            pass

    # Extract from platforms → telegram
    platforms = gw.get("platforms", {})
    tg = platforms.get("telegram", {})
    if isinstance(tg, dict):
        _telegram_bot_token = tg.get("token")
        hc = tg.get("home_channel", {})
        if isinstance(hc, dict):
            _telegram_chat_id = str(hc.get("chat_id", ""))


def _is_notification_enabled(event_key: str) -> bool:
    """Check if a specific notification event is enabled in trading-config.yaml.

    event_key: e.g. 'on_stop_loss', 'on_trailing_stop', 'on_breakeven_activated'
    """
    tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)
    return bool(_cfg(tcfg, "notifications", event_key, default=True))


def notify_telegram(message: str, event: str = None):
    """Send a notification to the home Telegram chat. Non-blocking, best-effort.

    event: optional notification key (e.g. 'on_stop_loss'). If set and disabled
           in trading-config.yaml, the message is silently dropped.
    """
    if event and not _is_notification_enabled(event):
        return
    _load_telegram_config()
    if not _telegram_bot_token or not _telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{_telegram_bot_token}/sendMessage"
    _http_post(url, {
        "chat_id": _telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })


# ---------------------------------------------------------------------------
# Wallet sync — reconcile journal with on-chain token balances
# ---------------------------------------------------------------------------

def _get_token_accounts(wallet_pubkey: str, rpc_url: str) -> dict:
    """Get all SPL token accounts for a wallet. Returns {mint_address: amount_raw}."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_pubkey,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ],
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {}

    result = {}
    accounts = data.get("result", {}).get("value", [])
    for acc in accounts:
        info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
        mint = info.get("mint", "")
        amount = info.get("tokenAmount", {}).get("uiAmount", 0) or 0
        if mint and amount > 0:
            result[mint] = amount
    return result


def _get_wallet_pubkey(tcfg: dict) -> str | None:
    """Read wallet public key from keypair file."""
    kp_path = _cfg(tcfg, "wallet", "keypair_path", default="")
    if not kp_path:
        return None
    kp_path = os.path.expanduser(kp_path)
    if not os.path.exists(kp_path):
        return None
    try:
        with open(kp_path) as f:
            kp_data = json.load(f)
        if isinstance(kp_data, list) and len(kp_data) >= 64:
            # JSON array keypair — first 32 bytes are private, derive public
            # Use solders if available, fallback to base58
            try:
                from solders.keypair import Keypair as SoldersKeypair
                kp = SoldersKeypair.from_bytes(bytes(kp_data[:64]))
                return str(kp.pubkey())
            except ImportError:
                # Without solders, try nacl
                try:
                    import nacl.signing
                    signing_key = nacl.signing.SigningKey(bytes(kp_data[:32]))
                    import base58
                    return base58.b58encode(bytes(signing_key.verify_key)).decode()
                except ImportError:
                    return None
        elif isinstance(kp_data, str):
            return kp_data  # Assume it's already a pubkey string
    except Exception:
        pass
    return None


def sync_journal_with_wallet(dry_run: bool = False) -> list:
    """Check on-chain balances for open positions and close orphans.

    Returns list of trade IDs that were closed (no tokens on-chain).
    """
    journal = load_json(JOURNAL_PATH)
    tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)

    trades = journal.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]
    if not open_trades:
        return []

    rpc_url = _cfg(tcfg, "wallet", "rpc_url", default=SOLANA_MAINNET_RPC)
    wallet_pubkey = _get_wallet_pubkey(tcfg)
    if not wallet_pubkey:
        log("  ⚠️ Cannot read wallet pubkey — skipping wallet sync")
        return []

    token_balances = _get_token_accounts(wallet_pubkey, rpc_url)
    closed_ids = []

    for t in open_trades:
        addr = t.get("address", "")
        if not addr:
            continue

        # Check if we still hold this token on-chain
        on_chain_balance = token_balances.get(addr, 0)
        if on_chain_balance > 0:
            continue  # Still holding — journal is correct

        # Token not on-chain but journal says open → manual close detected
        log(f"  🔄 #{t['id']} {t.get('token', '?')}: no on-chain balance — closing journal entry")
        if not dry_run:
            # Try to get current price for P&L calculation
            price = get_price(addr)
            entry = float(t.get("entry_price", 0))
            if price and entry > 0:
                pnl_pct = ((price - entry) / entry) * 100
            else:
                pnl_pct = 0.0  # Unknown — position was closed externally

            t["status"] = "closed"
            t["exit_price"] = price or 0
            t["exit_time"] = datetime.now(timezone.utc).isoformat()
            t["exit_reason"] = "Wallet sync — token not found on-chain (manual close?)"
            t["pnl_pct"] = round(pnl_pct, 2)
            t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
            closed_ids.append(t["id"])

            notify_telegram(
                f"🔄 *Wallet sync* — closed #{t['id']} {t.get('token', '?')}\n"
                f"Token not found on-chain (manual close?)\n"
                f"P&L: {pnl_pct:+.1f}%",
                event="on_wallet_sync",
            )

    if closed_ids and not dry_run:
        save_json(JOURNAL_PATH, journal)

    return closed_ids


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
    global _last_pnl_cache
    _last_pnl_cache = {}

    journal = load_json(JOURNAL_PATH)
    tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)

    trades = journal.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not open_trades:
        return []

    sl_pct = _cfg(tcfg, "risk", "stop_loss_pct", default=-30)
    tp_pct = _cfg(tcfg, "risk", "take_profit_pct", default=100)
    trail_pct = float(_cfg(tcfg, "risk", "trailing_stop_pct", default=0))
    kill = _cfg(tcfg, "risk", "kill_switch", default=False)
    mode = _cfg(tcfg, "mode", default="paper")
    # Break-even: move SL to 0% when position reaches this profit %
    be_trigger = float(_cfg(tcfg, "risk", "breakeven_trigger_pct", default=0))

    actions = []
    journal_dirty = False

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

        # Cache for adaptive interval (no extra API calls)
        _last_pnl_cache[t["id"]] = pnl_pct

        # Break-even SL: if position ever exceeded be_trigger, effective SL = 0%
        effective_sl = sl_pct
        if be_trigger > 0:
            peak = float(t.get("peak_pnl_pct", 0))
            if peak >= be_trigger or pnl_pct >= be_trigger:
                effective_sl = 0
                # Mark that BE was activated (for logging)
                if not t.get("breakeven_active"):
                    t["breakeven_active"] = True
                    journal_dirty = True
                    log(f"  🔒 #{t['id']} {t.get('token', '?')}: break-even SL activated (hit {be_trigger}%+)")
                    notify_telegram(
                        f"🔒 *Break-even SL activated*\n"
                        f"#{t['id']} {t.get('token', '?')}: hit {pnl_pct:+.1f}% (trigger: {be_trigger}%)\n"
                        f"SL moved from {sl_pct}% → 0% (entry price)",
                        event="on_breakeven_activated",
                    )

        # Stop-loss check (using effective SL — may be 0% if BE activated)
        if pnl_pct <= effective_sl:
            sl_label = f"BE 0%" if effective_sl == 0 else f"{effective_sl}%"
            action = f"STOP_LOSS #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (limit {sl_label})"
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
                notify_telegram(
                    f"🚨 *STOP LOSS* — #{t['id']} {t.get('token', '?')}\n"
                    f"P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)\n"
                    f"Entry: ${entry} → Exit: ${price}",
                    event="on_stop_loss",
                )

            actions.append({"type": "STOP_LOSS", "id": t["id"], "pnl": pnl_pct})

        # Take-profit / trailing stop check
        elif pnl_pct >= tp_pct:
            # Trailing stop enabled: track peak and sell on pullback
            if trail_pct > 0:
                peak = float(t.get("peak_pnl_pct", 0))
                # Update peak if current P&L is higher
                if pnl_pct > peak:
                    t["peak_pnl_pct"] = round(pnl_pct, 2)
                    peak = pnl_pct
                    journal_dirty = True
                 
                drop_from_peak = peak - pnl_pct
                if drop_from_peak >= trail_pct:
                    # Trailing stop triggered — sell
                    action = f"TRAILING_STOP #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (peak {peak:+.1f}%, trail -{trail_pct}%)"
                    log(f"  📉 {action}")
                    if not dry_run:
                        if mode == "real":
                            _execute_jupiter_sell(addr)
                        t["status"] = "closed"
                        t["exit_price"] = price
                        t["exit_time"] = datetime.now(timezone.utc).isoformat()
                        t["exit_reason"] = f"Guardian trailing-stop (peak {peak:.1f}%, drop {drop_from_peak:.1f}%)"
                        t["pnl_pct"] = round(pnl_pct, 2)
                        t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                        log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% (peak was {peak:+.1f}%)")
                        notify_telegram(
                            f"📉 *TRAILING STOP* — #{t['id']} {t.get('token', '?')}\n"
                            f"P&L: {pnl_pct:+.1f}% (peak: {peak:+.1f}%)\n"
                            f"Entry: ${entry} → Exit: ${price}\n"
                            f"Profit: {t['pnl_sol']:+.6f} SOL",
                            event="on_trailing_stop",
                        )
                    actions.append({"type": "TRAILING_STOP", "id": t["id"], "pnl": pnl_pct, "peak": peak})
                else:
                    # Still riding — log status with peak
                    log(f"  🚀 #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (peak {peak:+.1f}%, trail in {trail_pct - drop_from_peak:.1f}%)")
            else:
                # No trailing — instant take-profit (old behavior)
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
                    notify_telegram(
                        f"🎯 *TAKE PROFIT* — #{t['id']} {t.get('token', '?')}\n"
                        f"P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)\n"
                        f"Entry: ${entry} → Exit: ${price}",
                        event="on_take_profit",
                    )
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
                notify_telegram(
                    f"🔴 *KILL SWITCH* — #{t['id']} {t.get('token', '?')}\n"
                    f"P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)",
                    event="on_kill_switch",
                )
            actions.append({"type": "KILL", "id": t["id"], "pnl": pnl_pct})

        else:
            # Normal — just log status
            icon = "🟢" if pnl_pct >= 0 else "🔴"
            log(f"  {icon} #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}%")

    # Save if any changes (sells or peak_pnl updates)
    if (actions or journal_dirty) and not dry_run:
        save_json(JOURNAL_PATH, journal)

    return actions


# ---------------------------------------------------------------------------
# Adaptive interval
# ---------------------------------------------------------------------------

# Cache of last P&L values per trade (set by check_positions)
_last_pnl_cache: dict = {}  # trade_id -> pnl_pct


def _compute_adaptive_interval(tcfg: dict) -> int:
    """Compute check interval based on open positions and proximity to SL/TP.

    Uses cached P&L from the last check_positions run (no extra API calls).

    Reads from trading-config.yaml guardian section:
      guardian:
        interval_idle: 120      # No positions open
        interval_active: 20     # Positions open, normal range
        interval_hot: 10        # Position near SL or TP threshold
        hot_zone_pct: 15        # "Near" = within this % of SL or TP

    Returns interval in seconds.
    """
    idle = int(_cfg(tcfg, "guardian", "interval_idle", default=120))
    active = int(_cfg(tcfg, "guardian", "interval_active", default=20))
    hot = int(_cfg(tcfg, "guardian", "interval_hot", default=10))
    hot_zone = float(_cfg(tcfg, "guardian", "hot_zone_pct", default=15))

    if not _last_pnl_cache:
        return idle

    sl_pct = float(_cfg(tcfg, "risk", "stop_loss_pct", default=-30))
    tp_pct = float(_cfg(tcfg, "risk", "take_profit_pct", default=100))

    for pnl_pct in _last_pnl_cache.values():
        # Near stop-loss: e.g. SL=-30, hot_zone=15 → hot when pnl <= -15
        if pnl_pct <= (sl_pct + hot_zone):
            return hot
        # Near take-profit or above: e.g. TP=100, hot_zone=15 → hot when pnl >= 85
        if pnl_pct >= (tp_pct - hot_zone):
            return hot

    return active


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

        log(f"Guardian started (adaptive interval, dry-run: {args.dry_run})")
        _render_tui()
        global _check_counter
        _sync_counter = 0
        SYNC_EVERY_N_CHECKS = 10  # Wallet sync every N checks (not every cycle)
        try:
            while True:
                _flush_run()
                try:
                    _check_counter += 1
                    _sync_counter += 1
                    ts = _local_now().strftime("%H:%M:%S")
                    log(f"🔍 Check #{_check_counter} at {ts}")

                    # Periodic wallet sync (every N checks)
                    if _sync_counter >= SYNC_EVERY_N_CHECKS:
                        _sync_counter = 0
                        try:
                            closed = sync_journal_with_wallet(dry_run=args.dry_run)
                            if closed:
                                log(f"  🔄 Wallet sync: closed {len(closed)} orphan(s)")
                        except Exception as e:
                            log(f"  ⚠️ Wallet sync error: {e}")

                    actions = check_positions(dry_run=args.dry_run)
                    if actions:
                        log(f"  → {len(actions)} action(s) taken")
                    else:
                        log("  ✅ No exit signals")
                except Exception as e:
                    log(f"  ❌ Error: {e}")

                # Adaptive interval — re-read config each cycle
                tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)
                interval = _compute_adaptive_interval(tcfg)
                _watch_interval = interval
                log(f"  ⏱ Next check in {interval}s")

                _render_tui()
                time.sleep(interval)
        except KeyboardInterrupt:
            log("Guardian stopped (Ctrl+C)")
            if _tui_enabled:
                print("\n👋 Guardian stopped.")
        finally:
            release_lock()
    else:
        _tui_enabled = False  # One-shot always plain
        log("🛡️ Guardian one-shot check")
        # Wallet sync first
        try:
            closed = sync_journal_with_wallet(dry_run=args.dry_run)
            if closed:
                log(f"  🔄 Wallet sync: closed {len(closed)} orphan(s)")
        except Exception as e:
            log(f"  ⚠️ Wallet sync error: {e}")
        actions = check_positions(dry_run=args.dry_run)
        if not actions:
            log("  No exit signals.")
        for line in _current_run_lines:
            print(line)


if __name__ == "__main__":
    main()
