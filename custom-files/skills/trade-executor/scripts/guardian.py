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
    python3 guardian.py --watch      # Continuous loop (adaptive interval, 1s TUI refresh)
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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
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

# ---------------------------------------------------------------------------
# TUI state
# ---------------------------------------------------------------------------

_tui_enabled: bool = True
_alerts: deque = deque(maxlen=8)      # Recent events shown in TUI
_price_cache: dict = {}               # address -> {price_usd, market_cap, liquidity_usd}
_position_states: dict = {}           # trade_id -> display data for TUI
_sol_price_usd: float = 0.0
_wallet_balance_sol: float = 0.0
_wallet_pubkey_str: str = ""
_last_price_fetch_time: float = 0.0
_last_wallet_sync_time: float = 0.0
_num_open: int = 0
_watch_interval: int = 120
_dry_run_mode: bool = False


_display_tz = None  # Will be set from config (e.g. "Europe/Warsaw")


def _init_display_tz():
    """Read display_timezone from trading-config.yaml once."""
    global _display_tz
    if _display_tz is not None:
        return
    try:
        tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)
        tz_name = _cfg(tcfg, "display_timezone", default="")
        if tz_name:
            _display_tz = ZoneInfo(tz_name)
    except Exception:
        pass
    if _display_tz is None:
        _display_tz = datetime.now().astimezone().tzinfo  # system default


def _local_now() -> datetime:
    """Return current local time — uses config timezone if set, else system."""
    _init_display_tz()
    return datetime.now(_display_tz)


def _now_local_iso() -> str:
    """ISO timestamp in local timezone (with offset)."""
    return _local_now().isoformat()


def log(msg: str, alert: bool = False):
    """Write to log file only for alerts (significant events). Always print in no-TUI mode."""
    if alert:
        try:
            with open(GUARDIAN_LOG, "a") as f:
                ts_utc = _local_now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts_utc}] {msg}\n")
        except Exception:
            pass
        ts = _local_now().strftime("%H:%M:%S")
        _alerts.append(f"[{ts}] {msg}")
    if not _tui_enabled:
        ts = _local_now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {msg}")


def _fmt_usd(v: float) -> str:
    """Format USD value compactly."""
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    if v >= 0.01:
        return f"${v:.2f}"
    return f"${v:.4f}"


def _fmt_price(v: float) -> str:
    """Format token price with appropriate precision."""
    if v == 0:
        return "$0"
    if v >= 1:
        return f"${v:.4f}"
    if v >= 0.001:
        return f"${v:.6f}"
    if v >= 0.000001:
        return f"${v:.4e}"
    return f"${v:.2e}"


def _render_tui():
    """Clear screen and render position dashboard."""
    if not _tui_enabled:
        return

    term_width = shutil.get_terminal_size((80, 24)).columns
    w = min(term_width, 72)
    sep = "─" * w
    sep_bold = "═" * w

    os.system('clear')

    # --- Header ---
    now = _local_now().strftime("%H:%M:%S")
    mode_label = "hot" if _watch_interval <= 10 else ("active" if _watch_interval <= 30 else "idle")
    dry = " DRY-RUN" if _dry_run_mode else ""
    print(f"🛡️  GUARDIAN  │  {now}  │  ⚡ {_watch_interval}s {mode_label}{dry}  │  Ctrl+C stop")
    print(sep_bold)

    # --- Wallet info ---
    bal_usd = f" ({_fmt_usd(_wallet_balance_sol * _sol_price_usd)})" if _sol_price_usd > 0 else ""
    total_pos_sol = sum(s.get("amount_sol", 0) for s in _position_states.values())
    pos_usd = f" ({_fmt_usd(total_pos_sol * _sol_price_usd)})" if _sol_price_usd > 0 else ""

    print(f"  Wallet: {_wallet_pubkey_str or '?'}")
    print(f"  Balance: {_wallet_balance_sol:.4f} SOL{bal_usd}")
    print(f"  Positions: {_num_open} open │ {total_pos_sol:.4f} SOL{pos_usd}")

    # --- Wallet sync status ---
    if _last_wallet_sync_time > 0:
        ago = int(time.time() - _last_wallet_sync_time)
        sync_ago = f"{ago}s ago" if ago < 60 else f"{ago // 60}m ago"
        print(f"  🔄 Wallet sync: {sync_ago}")

    print(sep)

    # --- Positions ---
    GRAY = "\033[90m"
    RESET = "\033[0m"

    if not _position_states:
        print(f"{GRAY}  No open positions{RESET}")
    else:
        sorted_pos = sorted(
            _position_states.values(),
            key=lambda s: s.get("pnl_pct", 0),
            reverse=True,
        )
        for i, s in enumerate(sorted_pos):
            pnl = s.get("pnl_pct", 0)
            trailing = s.get("trailing_active", False)
            be = s.get("breakeven_active", False)

            # Status icon
            icon = "🚀" if trailing else ("🟢" if pnl >= 0 else "🔴")

            token = s.get("token", "?")
            amount_sol = s.get("amount_sol", 0)
            amount_usd = f" ({_fmt_usd(amount_sol * _sol_price_usd)})" if _sol_price_usd > 0 else ""
            addr = s.get("address", "")
            entry_p = _fmt_price(s.get("entry_price", 0))
            curr_p = _fmt_price(s.get("current_price", 0))
            mcap = s.get("market_cap", 0)
            mcap_str = f" │ MC {_fmt_usd(mcap)}" if mcap > 0 else ""

            print(f"  {icon} {token} — {pnl:+.1f}% — {amount_sol:.4f} SOL{amount_usd}")
            print(f"     {addr}")
            print(f"     • {entry_p} → {curr_p}{mcap_str}")

            # Inline position alerts
            if be:
                eff_sl = s.get("effective_sl", 0)
                print(f"     🔒 Break-even active (SL → {eff_sl}%)")
            if trailing:
                peak = s.get("peak_pnl", 0)
                trail_rem = s.get("trail_remaining", 0)
                print(f"     📈 Trailing: peak {peak:+.1f}%, trigger in {trail_rem:.1f}%")

            if i < len(sorted_pos) - 1:
                print()

    print(sep)

    # --- Recent alerts ---
    if _alerts:
        YELLOW = "\033[93m"
        for a in _alerts:
            print(f"  {YELLOW}{a}{RESET}")
        print(sep)

    # --- Footer ---
    if _last_price_fetch_time > 0:
        price_ago = int(time.time() - _last_price_fetch_time)
        next_in = max(0, _watch_interval - price_ago)
        print(f"  📡 Prices: {price_ago}s ago │ next: {next_in}s")
    else:
        print(f"  📡 Waiting for first price fetch...")

    sys.stdout.flush()


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
# Batch price fetch (single API call for all positions)
# ---------------------------------------------------------------------------

def _batch_fetch_prices(addresses: list) -> dict:
    """Fetch prices for multiple tokens in one DEXScreener API call.

    Returns {address: {price_usd, market_cap, liquidity_usd}}.
    """
    if not addresses:
        return {}
    addrs = ",".join(addresses)
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{addrs}"
    data = _http_get(url)
    if not data or not isinstance(data, list):
        return {}
    result = {}
    for pair in data:
        base = pair.get("baseToken", {})
        addr = base.get("address", "")
        if not addr:
            continue
        liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        if addr not in result or liq > result[addr]["liquidity_usd"]:
            result[addr] = {
                "price_usd": float(pair.get("priceUsd", 0) or 0),
                "market_cap": float(pair.get("marketCap", 0) or pair.get("fdv", 0) or 0),
                "liquidity_usd": liq,
            }
    return result


def _fetch_sol_price() -> float:
    """Get current SOL/USD price from Jupiter Price API."""
    url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
    data = _http_get(url)
    if data and isinstance(data, dict):
        sol_data = data.get("data", {}).get(
            "So11111111111111111111111111111111111111112", {}
        )
        price = sol_data.get("price")
        if price:
            return float(price)
    return 0.0


def _get_sol_balance(pubkey: str, rpc_url: str) -> float:
    """Get SOL balance for a wallet via RPC."""
    resp = _http_post(rpc_url, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [pubkey],
    })
    if resp and "result" in resp:
        lamports = resp["result"].get("value", 0)
        return lamports / 1e9
    return 0.0


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

def _get_token_accounts(wallet_pubkey: str, rpc_url: str) -> dict | None:
    """Get all SPL token accounts for a wallet.

    Queries both classic Token program AND Token-2022 program.
    Returns {mint_address: amount_raw} on success, None on RPC error.
    """
    TOKEN_PROGRAMS = [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # Classic SPL Token
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",   # Token-2022
    ]
    result = {}
    any_success = False

    for program_id in TOKEN_PROGRAMS:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_pubkey,
                {"programId": program_id},
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
        except Exception as e:
            log(f"  ⚠️ RPC error in getTokenAccountsByOwner ({program_id[:8]}...): {e}")
            continue

        if "error" in data:
            log(f"  ⚠️ RPC returned error ({program_id[:8]}...): {data['error']}")
            continue

        any_success = True
        accounts = data.get("result", {}).get("value", [])
        log(f"    RPC {program_id[:8]}...: {len(accounts)} token account(s)")
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint", "")
            amount = info.get("tokenAmount", {}).get("uiAmount", 0) or 0
            if mint and amount > 0:
                result[mint] = amount
            elif mint and amount == 0:
                log(f"    ⚠️ Zero balance: {mint[:12]}... (filtered out)")

    if not any_success:
        return None  # All RPC calls failed

    return result


def _get_wallet_pubkey(tcfg: dict) -> str | None:
    """Read wallet public key from keypair file.

    Tries: 1) solders in current Python, 2) python_bin subprocess, 3) nacl.
    """
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
            # Try solders in current Python
            try:
                from solders.keypair import Keypair as SoldersKeypair
                kp = SoldersKeypair.from_bytes(bytes(kp_data[:64]))
                return str(kp.pubkey())
            except ImportError:
                pass
            # Try python_bin from config (venv with solders)
            python_bin = _cfg(tcfg, "python_bin", default="")
            if python_bin:
                python_bin = os.path.expanduser(str(python_bin))
                if os.path.exists(python_bin):
                    try:
                        result = subprocess.run(
                            [python_bin, "-c",
                             "from solders.keypair import Keypair; import json; "
                             f"kp = Keypair.from_bytes(bytes(json.load(open('{kp_path}'))[:64])); "
                             "print(str(kp.pubkey()))"],
                            capture_output=True, text=True, timeout=10,
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            return result.stdout.strip()
                    except Exception:
                        pass
            # Fallback: nacl
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

    # SAFETY: if RPC call failed, skip sync entirely (don't close real positions)
    if token_balances is None:
        log("  ⚠️ RPC call failed — skipping wallet sync (not closing anything)")
        return []

    # Diagnostic: log what RPC returned vs what journal expects
    expected_mints = {t.get("address", ""): t.get("token", "?") for t in open_trades if t.get("address")}
    found_mints = set(token_balances.keys())
    log(f"  📋 Wallet sync: RPC found {len(found_mints)} tokens, journal expects {len(expected_mints)}", alert=True)
    for addr, name in expected_mints.items():
        if addr in found_mints:
            log(f"    ✅ {name}: found on-chain (balance: {token_balances[addr]})")
        else:
            log(f"    ❌ {name}: NOT found on-chain ({addr[:12]}...)", alert=True)
    # Log unexpected tokens on-chain (not in journal)
    unexpected = found_mints - set(expected_mints.keys())
    if unexpected:
        log(f"    ℹ️ {len(unexpected)} extra token(s) on-chain not in journal")

    closed_ids = []

    for t in open_trades:
        addr = t.get("address", "")
        if not addr:
            continue

        on_chain_balance = token_balances.get(addr, 0)
        if on_chain_balance > 0:
            continue  # Still holding — journal is correct

        # Token not on-chain but journal says open → manual close detected
        log(f"  🔄 #{t['id']} {t.get('token', '?')}: no on-chain balance — closing journal entry", alert=True)
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
            t["exit_time"] = _now_local_iso()
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
    # Use batch cache if available (no extra API call)
    if _price_cache and address in _price_cache:
        p = _price_cache[address].get("price_usd", 0)
        return p if p > 0 else None
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
    global _last_pnl_cache, _position_states, _num_open
    _last_pnl_cache = {}
    _position_states = {}

    journal = load_json(JOURNAL_PATH)
    tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)

    trades = journal.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]
    _num_open = len(open_trades)

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

        # Populate TUI state
        mcap = _price_cache.get(addr, {}).get("market_cap", 0) if _price_cache else 0
        _position_states[t["id"]] = {
            "token": t.get("token", "?"),
            "address": addr,
            "amount_sol": float(t.get("amount_sol", 0)),
            "entry_price": entry,
            "current_price": price,
            "pnl_pct": pnl_pct,
            "market_cap": mcap,
            "breakeven_active": bool(t.get("breakeven_active")),
            "trailing_active": False,
            "peak_pnl": float(t.get("peak_pnl_pct", 0)),
            "trail_remaining": 0.0,
            "effective_sl": sl_pct,
        }

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
                    log(f"  🔒 #{t['id']} {t.get('token', '?')}: break-even SL activated (hit {be_trigger}%+)", alert=True)
                    notify_telegram(
                        f"🔒 *Break-even SL activated*\n"
                        f"#{t['id']} {t.get('token', '?')}: hit {pnl_pct:+.1f}% (trigger: {be_trigger}%)\n"
                        f"SL moved from {sl_pct}% → 0% (entry price)",
                        event="on_breakeven_activated",
                    )
                # Update TUI state
                _position_states[t["id"]]["breakeven_active"] = True
                _position_states[t["id"]]["effective_sl"] = 0

        # Update effective SL in TUI state
        _position_states[t["id"]]["effective_sl"] = effective_sl

        # Stop-loss check (using effective SL — may be 0% if BE activated)
        if pnl_pct <= effective_sl:
            sl_label = f"BE 0%" if effective_sl == 0 else f"{effective_sl}%"
            action = f"STOP_LOSS #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (limit {sl_label})"
            log(f"  🚨 {action}", alert=True)

            if not dry_run:
                # Real mode: execute Jupiter sell first
                if mode == "real":
                    _execute_jupiter_sell(addr)
                # Close trade in journal
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = _now_local_iso()
                t["exit_reason"] = f"Guardian auto-stop-loss ({pnl_pct:.1f}%)"
                t["pnl_pct"] = round(pnl_pct, 2)
                t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)", alert=True)
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
                    log(f"  📉 {action}", alert=True)
                    if not dry_run:
                        if mode == "real":
                            _execute_jupiter_sell(addr)
                        t["status"] = "closed"
                        t["exit_price"] = price
                        t["exit_time"] = _now_local_iso()
                        t["exit_reason"] = f"Guardian trailing-stop (peak {peak:.1f}%, drop {drop_from_peak:.1f}%)"
                        t["pnl_pct"] = round(pnl_pct, 2)
                        t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                        log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% (peak was {peak:+.1f}%)", alert=True)
                        notify_telegram(
                            f"📉 *TRAILING STOP* — #{t['id']} {t.get('token', '?')}\n"
                            f"P&L: {pnl_pct:+.1f}% (peak: {peak:+.1f}%)\n"
                            f"Entry: ${entry} → Exit: ${price}\n"
                            f"Profit: {t['pnl_sol']:+.6f} SOL",
                            event="on_trailing_stop",
                        )
                    actions.append({"type": "TRAILING_STOP", "id": t["id"], "pnl": pnl_pct, "peak": peak})
                else:
                    # Still riding — update TUI state
                    _position_states[t["id"]].update({
                        "trailing_active": True,
                        "peak_pnl": peak,
                        "trail_remaining": trail_pct - drop_from_peak,
                    })
                    log(f"  🚀 #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (peak {peak:+.1f}%, trail in {trail_pct - drop_from_peak:.1f}%)")
            else:
                # No trailing — instant take-profit (old behavior)
                action = f"TAKE_PROFIT #{t['id']} {t.get('token', '?')}: {pnl_pct:+.1f}% (limit +{tp_pct}%)"
                log(f"  🎯 {action}", alert=True)
                if not dry_run:
                    if mode == "real":
                        _execute_jupiter_sell(addr)
                    t["status"] = "closed"
                    t["exit_price"] = price
                    t["exit_time"] = _now_local_iso()
                    t["exit_reason"] = f"Guardian auto-take-profit ({pnl_pct:.1f}%)"
                    t["pnl_pct"] = round(pnl_pct, 2)
                    t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
                    log(f"  ✅ Closed #{t['id']} — P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)", alert=True)
                    notify_telegram(
                        f"🎯 *TAKE PROFIT* — #{t['id']} {t.get('token', '?')}\n"
                        f"P&L: {pnl_pct:+.1f}% ({t['pnl_sol']:+.6f} SOL)\n"
                        f"Entry: ${entry} → Exit: ${price}",
                        event="on_take_profit",
                    )
                actions.append({"type": "TAKE_PROFIT", "id": t["id"], "pnl": pnl_pct})

        # Kill switch — sell everything
        elif kill:
            log(f"  🔴 KILL SWITCH — closing #{t['id']} {t.get('token', '?')}", alert=True)
            if not dry_run:
                if mode == "real":
                    _execute_jupiter_sell(addr)
                t["status"] = "closed"
                t["exit_price"] = price
                t["exit_time"] = _now_local_iso()
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
    idle = int(_cfg(tcfg, "guardian", "interval_idle", default=30))
    active = int(_cfg(tcfg, "guardian", "interval_active", default=5))
    hot = int(_cfg(tcfg, "guardian", "interval_hot", default=1))
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
    global _tui_enabled, _watch_interval, _dry_run_mode, _wallet_pubkey_str
    global _wallet_balance_sol, _sol_price_usd, _price_cache
    global _last_price_fetch_time, _last_wallet_sync_time

    parser = argparse.ArgumentParser(description="Position Guardian — fast price monitor")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring loop")
    parser.add_argument("--interval", type=int, default=0, help="Override initial check interval (0=auto)")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't execute sells")
    parser.add_argument("--no-tui", action="store_true", help="Disable TUI (plain log output, good for piping)")
    args = parser.parse_args()

    _tui_enabled = not args.no_tui and sys.stdout.isatty()
    _dry_run_mode = args.dry_run
    if args.interval > 0:
        _watch_interval = args.interval

    if args.watch:
        if not acquire_lock():
            print("Guardian already running (lock held). Exiting.")
            sys.exit(0)

        log("Guardian started (adaptive interval, dry-run: {})".format(args.dry_run))

        # Initial config read + wallet pubkey
        tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)
        _wallet_pubkey_str = _get_wallet_pubkey(tcfg) or ""

        # Initialize timezone from config (lazy init will also work, but log it now)
        _init_display_tz()
        log(f"Display timezone: {_display_tz}")

        _last_sol_fetch_time = 0.0
        SOL_FETCH_INTERVAL = 30  # SOL price + balance every 30s (not every tick)

        try:
            while True:
                tick_start = time.time()
                tcfg = _parse_yaml_flat(TRADING_CONFIG_PATH)

                # --- Batch price fetch (1 API call) ---
                journal = load_json(JOURNAL_PATH)
                open_trades = [t for t in journal.get("trades", []) if t.get("status") == "open"]
                addrs = [t["address"] for t in open_trades if t.get("address")]
                if addrs:
                    fetched = _batch_fetch_prices(addrs)
                    if fetched:
                        _price_cache = fetched
                else:
                    _price_cache = {}
                _last_price_fetch_time = tick_start

                # --- SOL price + balance (every 30s, not every tick) ---
                if tick_start - _last_sol_fetch_time >= SOL_FETCH_INTERVAL:
                    sol_p = _fetch_sol_price()
                    if sol_p > 0:
                        _sol_price_usd = sol_p
                    if _wallet_pubkey_str:
                        rpc_url = _cfg(tcfg, "wallet", "rpc_url", default=SOLANA_MAINNET_RPC)
                        bal = _get_sol_balance(_wallet_pubkey_str, rpc_url)
                        if bal >= 0:
                            _wallet_balance_sol = bal
                    _last_sol_fetch_time = tick_start

                # --- Check positions (SL/TP/trailing/BE/kill) ---
                try:
                    actions = check_positions(dry_run=args.dry_run)
                    if actions:
                        log(f"→ {len(actions)} action(s) taken", alert=True)
                except Exception as e:
                    log(f"❌ Position check error: {e}", alert=True)

                # --- Wallet sync (opt-in, default disabled) ---
                wallet_sync_enabled = bool(_cfg(tcfg, "guardian", "wallet_sync_enabled", default=False))
                sync_interval = int(_cfg(tcfg, "guardian", "wallet_sync_interval_s", default=300))
                if wallet_sync_enabled and tick_start - _last_wallet_sync_time >= sync_interval:
                    if _wallet_pubkey_str:
                        try:
                            closed = sync_journal_with_wallet(dry_run=args.dry_run)
                            if closed:
                                log(f"🔄 Wallet sync: closed {len(closed)} orphan(s)", alert=True)
                        except Exception as e:
                            log(f"⚠️ Wallet sync error: {e}")
                    _last_wallet_sync_time = tick_start

                # --- Adaptive interval ---
                _watch_interval = _compute_adaptive_interval(tcfg)

                # --- Render ---
                _render_tui()

                # --- Sleep for remaining time in interval ---
                elapsed = time.time() - tick_start
                sleep_time = max(0.1, _watch_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            log("Guardian stopped (Ctrl+C)")
            if _tui_enabled:
                print("\n👋 Guardian stopped.")
        finally:
            release_lock()
    else:
        # One-shot mode (plain output)
        _tui_enabled = False
        log("🛡️ Guardian one-shot check")
        try:
            closed = sync_journal_with_wallet(dry_run=args.dry_run)
            if closed:
                log(f"  🔄 Wallet sync: closed {len(closed)} orphan(s)")
        except Exception as e:
            log(f"  ⚠️ Wallet sync error: {e}")
        actions = check_positions(dry_run=args.dry_run)
        if not actions:
            log("  No exit signals.")


if __name__ == "__main__":
    main()
