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
PENDING_EVALUATION_DIR = os.path.expanduser("~/.hermes/cron/pending-evaluations")
CRON_JOBS_PATH = os.path.expanduser("~/.hermes/cron/jobs.json")
ENV_FILE = os.path.expanduser("~/.hermes/.env")


def _load_env_file():
    """Load environment variables from ~/.hermes/.env if not already set.

    This ensures scripts work identically whether run manually or via systemd
    (which uses EnvironmentFile). Only sets vars that are not already in env.
    """
    if not os.path.exists(ENV_FILE):
        return
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_env_file()


def _get_solana_rpc_url() -> str:
    """Get Solana RPC URL with fallback mechanism.

    Priority order:
    1. HELIUS_API_KEY environment variable -> construct Helius URL
    2. SOLANA_RPC_URL environment variable (direct override)
    3. wallet.rpc_url from trading-config.yaml (with env var interpolation)
    4. Hardcoded public default
    """
    # 1. Check for Helius API key and construct URL if present
    helius_key = os.environ.get("HELIUS_API_KEY")
    if helius_key:
        return f"https://mainnet.helius-rpc.com/?api-key={helius_key}"

    # 2. Direct environment override
    env_rpc = os.environ.get("SOLANA_RPC_URL")
    if env_rpc:
        return env_rpc

    # 3. Load from config file
    try:
        config_path = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f)
                if cfg and isinstance(cfg, dict):
                    wallet_cfg = cfg.get("wallet", {})
                    if wallet_cfg and isinstance(wallet_cfg, dict):
                        rpc_url = wallet_cfg.get("rpc_url")
                        if rpc_url and isinstance(rpc_url, str):
                            return os.path.expandvars(rpc_url)
            except ImportError:
                with open(config_path) as f:
                    for line in f:
                        if line.strip().startswith("rpc_url:"):
                            rpc_url = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if rpc_url:
                                return os.path.expandvars(rpc_url)
    except Exception:
        pass

    # 4. Hardcoded public default
    return SOLANA_MAINNET_RPC

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
            eval_pending = s.get("evaluation_pending", False)
            strat_type = s.get("exit_strategy_type")
            strat_detail = s.get("exit_strategy_detail", "")
            tiers = s.get("tiers_triggered", [])
            eff_sl = s.get("effective_sl", -30)

            # Status icon
            if eval_pending:
                icon = "🧠"
            elif trailing:
                icon = "🚀"
            elif strat_type == "hold":
                icon = "💎"
            elif pnl >= 0:
                icon = "🟢"
            else:
                icon = "🔴"

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

            # Tier & strategy status
            if tiers:
                sl_label = "entry" if eff_sl == 0 else (f"+{eff_sl}%" if eff_sl > 0 else f"{eff_sl}%")
                tier_str = "/".join(f"{int(t)}%" for t in sorted(tiers))
                print(f"     🔒 Tiers: {tier_str} │ SL floor: {sl_label}")

            if eval_pending:
                print(f"     ⏳ LLM evaluation in progress...")
            elif strat_detail:
                strat_icons = {"trailing": "📈", "hold": "💎", "hard_tp": "🎯", "partial_sell": "✂️"}
                si = strat_icons.get(strat_type, "📊")
                print(f"     {si} Strategy: {strat_detail}")
            elif be and not tiers:
                print(f"     🔒 Break-even active (SL → entry price)")

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

    sys.stdout.flush()


def _http_get(url: str, timeout: int = 5) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-guardian/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
# Multi-provider price fetch (rotate to avoid rate limits)
# ---------------------------------------------------------------------------

_price_provider_index: int = 0  # Rotates each tick


def _fetch_prices_dexscreener(addresses: list) -> dict:
    """DEXScreener: batch fetch up to 30 tokens in one call. 300 RPM limit."""
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


def _fetch_prices_jupiter(addresses: list) -> dict:
    """Jupiter Price API v2: batch fetch. 600 RPM limit."""
    if not addresses:
        return {}
    ids = ",".join(addresses)
    url = f"https://api.jup.ag/price/v2?ids={ids}"
    data = _http_get(url)
    if not data or not isinstance(data, dict):
        return {}
    prices = data.get("data", {})
    result = {}
    for addr in addresses:
        token_data = prices.get(addr, {})
        price = token_data.get("price")
        if price:
            result[addr] = {
                "price_usd": float(price),
                "market_cap": 0,
                "liquidity_usd": 0,
            }
    return result


def _batch_fetch_prices(addresses: list) -> dict:
    """Fetch prices rotating between providers each tick.

    Provider rotation: DEXScreener → Jupiter → DEXScreener → ...
    If primary fails, falls back to the other. DEXScreener provides
    richer data (MC, liquidity); Jupiter is faster and has higher RPM.
    """
    global _price_provider_index
    if not addresses:
        return {}

    providers = [
        ("DEXScreener", _fetch_prices_dexscreener),
        ("Jupiter", _fetch_prices_jupiter),
    ]

    idx = _price_provider_index % len(providers)
    _price_provider_index += 1

    name, fetch_fn = providers[idx]
    result = fetch_fn(addresses)

    if not result:
        # Fallback to other provider
        fallback_idx = (idx + 1) % len(providers)
        fb_name, fb_fn = providers[fallback_idx]
        log(f"  ⚠️ {name} failed, falling back to {fb_name}")
        result = fb_fn(addresses)

    # If Jupiter was used (no MC/liq data), merge MC/liq from cache
    if result and idx == 1:
        for addr, pdata in result.items():
            if pdata.get("market_cap", 0) == 0 and addr in _price_cache:
                pdata["market_cap"] = _price_cache[addr].get("market_cap", 0)
                pdata["liquidity_usd"] = _price_cache[addr].get("liquidity_usd", 0)

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
    """Load Telegram bot token and home chat_id from gateway or hermes config."""
    global _telegram_bot_token, _telegram_chat_id, _telegram_loaded
    if _telegram_loaded:
        return
    _telegram_loaded = True

    # Try gateway.json first
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

    # Fallback: hermes config.yaml (platforms.telegram.token / home_channel.chat_id)
    if not _telegram_bot_token or not _telegram_chat_id:
        if os.path.exists(HERMES_CONFIG_PATH):
            try:
                hcfg = _parse_yaml_flat(HERMES_CONFIG_PATH)
                t = _cfg(hcfg, "platforms", "telegram", "token", default="")
                c = _cfg(hcfg, "platforms", "telegram", "home_channel", "chat_id", default="")
                if t:
                    _telegram_bot_token = t
                if c:
                    _telegram_chat_id = str(c)
            except Exception:
                pass

    if _telegram_bot_token and _telegram_chat_id:
        log("Telegram: configured ✅")
    else:
        log("Telegram: NOT configured (no bot token / chat_id in gateway.json or config.yaml)")


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
    result = _http_post(url, {
        "chat_id": _telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })
    if result and not result.get("ok"):
        log(f"  ⚠️ Telegram send failed: {result.get('description', '?')}")


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

    rpc_url = _get_solana_rpc_url()
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
    """Minimal YAML parser for trading config (supports nested dicts + lists)."""
    if not os.path.exists(path):
        return {}
    result = {}
    # stack items: (indent, container)
    # container is dict or list
    stack = [(0, result)]
    with open(path) as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            content = stripped.strip()

            # --- List item: "- key: val" ---
            if content.startswith("- "):
                content = content[2:].strip()
                # Pop stack to find container at proper indent
                while len(stack) > 1 and stack[-1][0] >= indent:
                    stack.pop()
                parent_indent, parent_container = stack[-1]

                # Parent is an empty dict → it was created by "key:" with no value.
                # Convert it to a list in the grandparent dict.
                if isinstance(parent_container, dict) and len(parent_container) == 0 and len(stack) >= 2:
                    _, grandparent = stack[-2]
                    if isinstance(grandparent, dict):
                        for k, v in grandparent.items():
                            if v is parent_container:
                                grandparent[k] = []
                                parent_container = grandparent[k]
                                stack[-1] = (parent_indent, parent_container)
                                break

                if not isinstance(parent_container, list):
                    continue

                # Create new list item dict
                item = {}
                parent_container.append(item)
                if ":" in content:
                    key, _, val = content.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if val and val[0] in ('"', "'") and val[-1] == val[0]:
                        val = val[1:-1]
                    val = _parse_yaml_value(val)
                    item[key] = val
                # Push list item as context for subsequent indented lines
                stack.append((indent, item))
                continue

            if ":" not in content:
                continue
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            if val and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()
            _, parent = stack[-1]
            if not isinstance(parent, dict):
                continue
            if val == "" or val == "[]":
                if val == "[]":
                    parent[key] = []
                else:
                    child = {}
                    parent[key] = child
                    stack.append((indent, child))
            else:
                parent[key] = _parse_yaml_value(val)
    return result


def _parse_yaml_value(val):
    """Convert a YAML scalar string to a Python value."""
    if isinstance(val, str):
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        if val.lower() in ("null", "none"):
            return None
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return val
    return val


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


def _execute_jupiter_sell(address: str, pct: int = 100) -> bool:
    """Execute real sell via Jupiter. Returns True if successful."""
    jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
    if not os.path.exists(jupiter_script):
        log(" ⚠️ jupiter_swap.py not found — cannot execute real sell")
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
            [python_bin, jupiter_script, "sell", "--token", address, "--pct", str(pct)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if "Success" in result.stdout:
            log(f" 🔗 Jupiter sell executed ({pct}%)")
            return True
        else:
            log(f" ⚠️ Jupiter sell may have failed: {result.stdout[-200:]}")
            return False
    except Exception as e:
        log(f" ❌ Jupiter sell error: {e}")
        return False

def _update_on_chain_sl(token_address: str, amount_tokens: float, new_sl_price: float, old_order_id: str | None) -> str | None:
    """
    Updates the on-chain Hard SL by cancelling the old order and creating a new one.
    Returns the new order ID if successful, else None.
    """
    jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
    if not os.path.exists(jupiter_script):
        log(" ⚠️ jupiter_swap.py not found — cannot update on-chain SL")
        return None

    # 1. Cancel old order if it exists
    if old_order_id:
        rc_cancel, _ = subprocess.run(
            [sys.executable, jupiter_script, "limit-cancel", "--id", old_order_id],
            capture_output=True, text=True, timeout=30
        )
        if rc_cancel != 0:
            log(f" ⚠️ Failed to cancel old SL order {old_order_id}, proceeding anyway")

    # 2. Create new order
    # Note: amount_tokens should be raw amount.
    # In a real scenario, we'd fetch the current balance from the wallet.
    rc_create, output = subprocess.run(
        [sys.executable, jupiter_script, "limit-sell",
         "--token", token_address,
         "--amount", str(int(amount_tokens)),
         "--price", f"{new_sl_price:.8f}"],
        capture_output=True, text=True, timeout=30
    )

    if rc_create == 0:
        for line in output.split("\n"):
            if "ID: " in line:
                return line.split("ID: ")[-1].strip()

    log(f" ❌ Failed to create updated on-chain SL: {output}")
    return None


def _close_trade(t: dict, price: float, pnl_pct: float, reason: str, mode: str) -> dict:
    """Mark trade as closed in journal. Returns action dict."""
    t["status"] = "closed"
    t["exit_price"] = price
    t["exit_time"] = _now_local_iso()
    t["exit_reason"] = reason
    t["pnl_pct"] = round(pnl_pct, 2)
    t["pnl_sol"] = round(float(t.get("amount_sol", 0)) * (pnl_pct / 100), 6)
    return {"id": t["id"], "pnl": pnl_pct, "pnl_sol": t["pnl_sol"]}


def _find_evaluator_cron_id(job_name: str) -> str | None:
    """Find cron job ID by name from jobs.json."""
    if not os.path.exists(CRON_JOBS_PATH):
        return None
    try:
        with open(CRON_JOBS_PATH) as f:
            data = json.load(f)
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        for j in jobs:
            if j.get("name") == job_name:
                return j.get("id")
    except Exception:
        pass
    return None


def _trigger_evaluation(trade_id: int, trade: dict, tcfg: dict):
    """Trigger the LLM position evaluator cron job for a trade.

    Writes per-trade pending file (pending-evaluations/<trade_id>.json),
    then runs 'hermes cron run <job_id>'. Each trade gets its own file
    so concurrent evaluations don't overwrite each other.
    """
    # Write per-trade pending evaluation file
    os.makedirs(PENDING_EVALUATION_DIR, exist_ok=True)
    pending = {
        "trade_id": trade_id,
        "token": trade.get("token", "?"),
        "address": trade.get("address", ""),
        "entry_price": trade.get("entry_price"),
        "amount_sol": trade.get("amount_sol"),
        "requested_at": _now_local_iso(),
    }
    pending_path = os.path.join(PENDING_EVALUATION_DIR, f"{trade_id}.json")
    tmp = pending_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(pending, f, indent=2, default=str)
    os.replace(tmp, pending_path)

    # Find the evaluator cron job ID
    job_name = _cfg(tcfg, "risk", "evaluator_cron_job_name", default="position-evaluator")
    job_id = _find_evaluator_cron_id(job_name)
    if not job_id:
        log(f"  ⚠️ Cron job '{job_name}' not found — cannot trigger evaluation", alert=True)
        return

    # Trigger the cron job (non-blocking)
    try:
        hermes_bin = shutil.which("hermes")
        if not hermes_bin:
            hermes_bin = os.path.expanduser("~/.local/bin/hermes")
        subprocess.Popen(
            [hermes_bin, "cron", "run", job_id],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log(f"  🧠 Triggered evaluator for #{trade_id} {trade.get('token', '?')}", alert=True)
    except Exception as e:
        log(f"  ❌ Failed to trigger evaluator: {e}", alert=True)


def check_positions(dry_run: bool = False) -> list:
    """Check all open positions against tiered exit strategy.

    Tiered exit system (when exit_tiers present in config):
      1. Process tiers: ratchet SL up, trigger LLM evaluation
      2. Execute exit_strategy written by evaluator (trailing/hold/partial_sell/hard_tp)
      3. Check SL (effective = max of base SL, tier SL, strategy SL)

    Falls back to legacy TP/trailing/BE when exit_tiers is absent.
    """
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

    base_sl = float(_cfg(tcfg, "risk", "stop_loss_pct", default=-30))
    kill = _cfg(tcfg, "risk", "kill_switch", default=False)
    mode = _cfg(tcfg, "mode", default="paper")

    # Tiered exit config
    exit_tiers_raw = _cfg(tcfg, "risk", "exit_tiers", default=None)
    use_tiers = isinstance(exit_tiers_raw, list) and len(exit_tiers_raw) > 0

    if use_tiers:
        exit_tiers = sorted(exit_tiers_raw, key=lambda x: float(x.get("trigger_pct", 0)))
        default_strat = _cfg(tcfg, "risk", "default_exit_strategy") or {}
        eval_timeout = float(_cfg(tcfg, "risk", "evaluation_timeout_minutes", default=5))
    else:
        # Legacy mode — read old fields
        tp_pct = float(_cfg(tcfg, "risk", "take_profit_pct", default=100))
        trail_pct = float(_cfg(tcfg, "risk", "trailing_stop_pct", default=0))
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
        token_name = t.get("token", "?")
        tid = t["id"]

        # Track peak P&L (always, regardless of mode)
        peak = float(t.get("peak_pnl_pct", 0))
        if pnl_pct > peak:
            t["peak_pnl_pct"] = round(pnl_pct, 2)
            peak = pnl_pct
            journal_dirty = True

        # Cache for adaptive interval
        _last_pnl_cache[tid] = pnl_pct

        # TUI state base
        mcap = _price_cache.get(addr, {}).get("market_cap", 0) if _price_cache else 0
        _position_states[tid] = {
            "token": token_name,
            "address": addr,
            "amount_sol": float(t.get("amount_sol", 0)),
            "entry_price": entry,
            "current_price": price,
            "pnl_pct": pnl_pct,
            "market_cap": mcap,
            "peak_pnl": peak,
            "effective_sl": base_sl,
            # Tier-specific (populated below)
            "tiers_triggered": [],
            "exit_strategy_type": None,
            "exit_strategy_detail": "",
            "evaluation_pending": False,
            "trailing_active": False,
            "trail_remaining": 0.0,
            "breakeven_active": False,
        }

        # ── Kill switch — sell everything ──
        if kill:
            log(f"  🔴 KILL SWITCH — closing #{tid} {token_name}", alert=True)
            if not dry_run:
                if mode == "real":
                    _execute_jupiter_sell(addr)
                info = _close_trade(t, price, pnl_pct,
                    f"Kill switch ({_cfg(tcfg, 'risk', 'kill_reason', default='manual')})", mode)
                notify_telegram(
                    f"🔴 *KILL SWITCH* — #{tid} {token_name}\n"
                    f"P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)",
                    event="on_kill_switch",
                )
            actions.append({"type": "KILL", "id": tid, "pnl": pnl_pct})
            continue

        if use_tiers:
            # ══════════════════════════════════════════════════════════════
            # TIERED EXIT SYSTEM
            # ══════════════════════════════════════════════════════════════
            tiers_triggered = list(t.get("tiers_triggered", []))
            effective_sl = float(t.get("effective_sl_pct", base_sl))
            eval_pending = t.get("evaluation_pending", False)
            eval_requested = t.get("evaluation_requested_at")

            # ── 1. Process tiers ──
            for tier in exit_tiers:
                trigger = float(tier.get("trigger_pct", 0))
                if trigger in tiers_triggered:
                    continue
                if pnl_pct < trigger:
                    continue
                # Tier crossed!
                tiers_triggered.append(trigger)
                new_sl = float(tier.get("new_sl_pct", 0))
                action_type = tier.get("action", "move_sl")
                effective_sl = max(effective_sl, new_sl)

                sl_label = "entry price" if new_sl == 0 else f"+{new_sl}%"
                log(f"  🔒 #{tid} {token_name}: Tier {trigger}% — SL → {sl_label}", alert=True)
                notify_telegram(
                    f"🔒 *Tier {trigger}% reached* — #{tid} {token_name}\n"
                    f"P&L: {pnl_pct:+.1f}% │ SL → {sl_label}",
                    event="on_tier_triggered",
                )

                # Trigger LLM evaluation if configured
                if action_type == "evaluate" and not eval_pending:
                    t["evaluation_pending"] = True
                    t["evaluation_requested_at"] = _now_local_iso()
                    eval_pending = True
                    eval_requested = t["evaluation_requested_at"]
                    if not dry_run:
                        _trigger_evaluation(tid, t, tcfg)
                    else:
                        log(f"  🧠 [DRY-RUN] Would trigger evaluator for #{tid}")

                journal_dirty = True

            # Persist tier state
            t["tiers_triggered"] = tiers_triggered
            t["effective_sl_pct"] = effective_sl

            # ── 2. Check evaluation timeout ──
            if eval_pending and eval_requested:
                try:
                    req_dt = datetime.fromisoformat(eval_requested)
                    elapsed = (_local_now() - req_dt).total_seconds() / 60
                    if elapsed > eval_timeout:
                        log(f"  ⏰ #{tid} {token_name}: Evaluation timeout ({elapsed:.0f}m) — applying default strategy", alert=True)
                        t["exit_strategy"] = {
                            "type": str(default_strat.get("type", "trailing")),
                            "trailing_pct": float(default_strat.get("trailing_pct", 25)),
                            "trailing_from_pct": float(default_strat.get("trailing_from_pct", 200)),
                            "sl_pct": effective_sl,
                            "reason": f"Default — evaluator timeout ({elapsed:.0f}m)",
                        }
                        t["evaluation_pending"] = False
                        eval_pending = False
                        journal_dirty = True
                        # Cleanup pending evaluation file
                        pf = os.path.join(PENDING_EVALUATION_DIR, f"{tid}.json")
                        try:
                            os.remove(pf)
                        except FileNotFoundError:
                            pass
                        notify_telegram(
                            f"⏰ *Evaluator timeout* — #{tid} {token_name}\n"
                            f"Applied default: trailing {default_strat.get('trailing_pct', 25)}% "
                            f"from {default_strat.get('trailing_from_pct', 200)}%",
                            event="on_evaluation_complete",
                        )
                except Exception:
                    pass

            # ── 3. Execute exit strategy (written by LLM evaluator) ──
            strat = t.get("exit_strategy")
            if strat and isinstance(strat, dict):
                stype = strat.get("type", "")
                strat_sl = float(strat.get("sl_pct", 0))
                effective_sl = max(effective_sl, strat_sl)
                t["effective_sl_pct"] = effective_sl

                if stype == "trailing":
                    trail_pct_s = float(strat.get("trailing_pct", 25))
                    trail_from = float(strat.get("trailing_from_pct", 200))

                    if peak >= trail_from:
                        # Trailing active (peak crossed threshold — stays active even if price drops below)
                        drop = peak - pnl_pct
                        if drop >= trail_pct_s:
                            # Trailing stop triggered
                            reason = f"Tiered trailing-stop (peak {peak:.1f}%, drop {drop:.1f}%, trail {trail_pct_s}%)"
                            log(f"  📉 #{tid} {token_name}: {reason}", alert=True)
                            if not dry_run:
                                if mode == "real":
                                    _execute_jupiter_sell(addr)
                                info = _close_trade(t, price, pnl_pct, f"Guardian {reason}", mode)
                                log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}% (peak {peak:+.1f}%)", alert=True)
                                notify_telegram(
                                    f"📉 *TRAILING STOP* — #{tid} {token_name}\n"
                                    f"P&L: {pnl_pct:+.1f}% (peak: {peak:+.1f}%)\n"
                                    f"Entry: ${entry} → Exit: ${price}\n"
                                    f"Profit: {info['pnl_sol']:+.6f} SOL\n"
                                    f"Strategy: {strat.get('reason', 'LLM evaluator')}",
                                    event="on_trailing_stop",
                                )
                            actions.append({"type": "TRAILING_STOP", "id": tid, "pnl": pnl_pct, "peak": peak})
                            continue
                        else:
                            _position_states[tid].update({
                                "trailing_active": True,
                                "trail_remaining": trail_pct_s - drop,
                            })
                            log(f"  🚀 #{tid} {token_name}: {pnl_pct:+.1f}% trailing (peak {peak:+.1f}%, trigger in {trail_pct_s - drop:.1f}%)")
                    else:
                        log(f"  📊 #{tid} {token_name}: {pnl_pct:+.1f}% (trailing arms at {trail_from}%)")

                    _position_states[tid]["exit_strategy_type"] = "trailing"
                    _position_states[tid]["exit_strategy_detail"] = f"trail {trail_pct_s}%↓ from {trail_from}%"

                elif stype == "hard_tp":
                    hard_tp = float(strat.get("hard_tp_pct", 300))
                    if pnl_pct >= hard_tp:
                        reason = f"Hard TP at {hard_tp}%"
                        log(f"  🎯 #{tid} {token_name}: {reason}", alert=True)
                        if not dry_run:
                            if mode == "real":
                                _execute_jupiter_sell(addr)
                            info = _close_trade(t, price, pnl_pct, f"Guardian {reason}", mode)
                            log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}%", alert=True)
                            notify_telegram(
                                f"🎯 *HARD TP* — #{tid} {token_name}\n"
                                f"P&L: {pnl_pct:+.1f}% (target: {hard_tp}%)\n"
                                f"Profit: {info['pnl_sol']:+.6f} SOL",
                                event="on_take_profit",
                            )
                        actions.append({"type": "HARD_TP", "id": tid, "pnl": pnl_pct})
                        continue
                    _position_states[tid]["exit_strategy_type"] = "hard_tp"
                    _position_states[tid]["exit_strategy_detail"] = f"TP@{hard_tp}%"

                elif stype == "hold":
                    review_at = float(strat.get("review_at_pct", 300))
                    if pnl_pct >= review_at and not eval_pending:
                        # Re-evaluate at higher level
                        log(f"  🔄 #{tid} {token_name}: Reached review target {review_at}% — re-evaluating", alert=True)
                        t["evaluation_pending"] = True
                        t["evaluation_requested_at"] = _now_local_iso()
                        # Clear old strategy so evaluator sets a new one
                        t["exit_strategy"] = None
                        journal_dirty = True
                        if not dry_run:
                            _trigger_evaluation(tid, t, tcfg)
                    _position_states[tid]["exit_strategy_type"] = "hold"
                    _position_states[tid]["exit_strategy_detail"] = f"hold→{review_at}%"

                elif stype == "partial_sell":
                    sell_pct = int(strat.get("sell_pct", 50))
                    if not t.get("partial_sell_done"):
                        log(f"  ✂️ #{tid} {token_name}: Partial sell {sell_pct}%", alert=True)
                        if not dry_run:
                            if mode == "real":
                                _execute_jupiter_sell(addr, pct=sell_pct)
                            # Update position size in journal
                            old_amount = float(t.get("amount_sol", 0))
                            sold_amount = old_amount * (sell_pct / 100)
                            t["amount_sol"] = round(old_amount - sold_amount, 6)
                            t["partial_sell_done"] = True
                            t["partial_sell_pct"] = sell_pct
                            t["partial_sell_time"] = _now_local_iso()
                            t["partial_sell_pnl_pct"] = round(pnl_pct, 2)
                            journal_dirty = True
                            # Apply remaining strategy if specified
                            remaining = strat.get("remaining_strategy")
                            if remaining and isinstance(remaining, dict):
                                t["exit_strategy"] = remaining
                            else:
                                # After partial sell, default to trailing on remainder
                                t["exit_strategy"] = {
                                    "type": "trailing",
                                    "trailing_pct": float(strat.get("trailing_pct", 25)),
                                    "trailing_from_pct": pnl_pct,
                                    "sl_pct": effective_sl,
                                    "reason": f"Remainder after {sell_pct}% partial sell",
                                }
                            notify_telegram(
                                f"✂️ *PARTIAL SELL {sell_pct}%* — #{tid} {token_name}\n"
                                f"P&L: {pnl_pct:+.1f}% │ Sold: {sold_amount:.4f} SOL\n"
                                f"Remaining: {t['amount_sol']:.4f} SOL",
                                event="on_trailing_stop",
                            )
                        actions.append({"type": "PARTIAL_SELL", "id": tid, "pnl": pnl_pct, "sell_pct": sell_pct})
                    _position_states[tid]["exit_strategy_type"] = "partial_sell"
                    _position_states[tid]["exit_strategy_detail"] = f"sold {sell_pct}%"

            elif eval_pending:
                _position_states[tid]["evaluation_pending"] = True
                _position_states[tid]["exit_strategy_detail"] = "⏳ evaluating..."
                log(f"  ⏳ #{tid} {token_name}: {pnl_pct:+.1f}% (evaluation pending)")

            else:
                # No strategy yet, no evaluation — just log
                icon = "🟢" if pnl_pct >= 0 else "🔴"
                log(f"  {icon} #{tid} {token_name}: {pnl_pct:+.1f}%")

            # ── 4. Stop-loss check (effective SL — max of base, tier, strategy) ──
            # effective_sl is positive for profit-floor (e.g. +20%) or 0 for BE,
            # base_sl is negative (e.g. -30%)
            if t.get("status") != "closed":
                sl_floor = effective_sl if effective_sl > base_sl else base_sl
                if pnl_pct <= sl_floor:
                    if sl_floor >= 0:
                        sl_label = "entry price" if sl_floor == 0 else f"+{sl_floor}%"
                    else:
                        sl_label = f"{sl_floor}%"
                    log(f"  🚨 STOP_LOSS #{tid} {token_name}: {pnl_pct:+.1f}% (SL {sl_label})", alert=True)
                    if not dry_run:
                        if mode == "real":
                            _execute_jupiter_sell(addr)
                        info = _close_trade(t, price, pnl_pct,
                            f"Guardian tiered-SL ({pnl_pct:.1f}%, floor {sl_label})", mode)
                        log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)", alert=True)
                        notify_telegram(
                            f"🚨 *STOP LOSS* — #{tid} {token_name}\n"
                            f"P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)\n"
                            f"SL floor: {sl_label}\n"
                            f"Entry: ${entry} → Exit: ${price}",
                            event="on_stop_loss",
                        )
                    actions.append({"type": "STOP_LOSS", "id": tid, "pnl": pnl_pct})

            # Update TUI state
            _position_states[tid]["effective_sl"] = effective_sl if effective_sl > base_sl else base_sl
            _position_states[tid]["tiers_triggered"] = tiers_triggered
            _position_states[tid]["peak_pnl"] = peak
            _position_states[tid]["breakeven_active"] = 0 in tiers_triggered or effective_sl == 0

        else:
            # ══════════════════════════════════════════════════════════════
            # LEGACY MODE (no exit_tiers in config)
            # ══════════════════════════════════════════════════════════════
            effective_sl = base_sl

            # Break-even SL
            if be_trigger > 0:
                if t.get("breakeven_active") or peak >= be_trigger or pnl_pct >= be_trigger:
                    effective_sl = 0
                    if not t.get("breakeven_active"):
                        t["breakeven_active"] = True
                        journal_dirty = True
                        log(f"  🔒 #{tid} {token_name}: break-even SL activated (hit {be_trigger}%+)", alert=True)
                        notify_telegram(
                            f"🔒 *Break-even SL activated*\n"
                            f"#{tid} {token_name}: hit {pnl_pct:+.1f}% (trigger: {be_trigger}%)\n"
                            f"SL moved from {base_sl}% → 0% (entry price)",
                            event="on_breakeven_activated",
                        )
                    _position_states[tid]["breakeven_active"] = True

            _position_states[tid]["effective_sl"] = effective_sl

            # Stop-loss
            if pnl_pct <= effective_sl:
                sl_label = "BE 0%" if effective_sl == 0 else f"{effective_sl}%"
                log(f"  🚨 STOP_LOSS #{tid} {token_name}: {pnl_pct:+.1f}% (limit {sl_label})", alert=True)
                if not dry_run:
                    if mode == "real":
                        _execute_jupiter_sell(addr)
                    info = _close_trade(t, price, pnl_pct,
                        f"Guardian auto-stop-loss ({pnl_pct:.1f}%)", mode)
                    log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)", alert=True)
                    notify_telegram(
                        f"🚨 *STOP LOSS* — #{tid} {token_name}\n"
                        f"P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)\n"
                        f"Entry: ${entry} → Exit: ${price}",
                        event="on_stop_loss",
                    )
                actions.append({"type": "STOP_LOSS", "id": tid, "pnl": pnl_pct})

            # Take-profit / trailing
            elif pnl_pct >= tp_pct:
                if trail_pct > 0:
                    drop_from_peak = peak - pnl_pct
                    if drop_from_peak >= trail_pct:
                        log(f"  📉 TRAILING_STOP #{tid} {token_name}: {pnl_pct:+.1f}% (peak {peak:+.1f}%)", alert=True)
                        if not dry_run:
                            if mode == "real":
                                _execute_jupiter_sell(addr)
                            info = _close_trade(t, price, pnl_pct,
                                f"Guardian trailing-stop (peak {peak:.1f}%, drop {drop_from_peak:.1f}%)", mode)
                            log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}%", alert=True)
                            notify_telegram(
                                f"📉 *TRAILING STOP* — #{tid} {token_name}\n"
                                f"P&L: {pnl_pct:+.1f}% (peak: {peak:+.1f}%)\n"
                                f"Profit: {info['pnl_sol']:+.6f} SOL",
                                event="on_trailing_stop",
                            )
                        actions.append({"type": "TRAILING_STOP", "id": tid, "pnl": pnl_pct, "peak": peak})
                    else:
                        _position_states[tid].update({
                            "trailing_active": True,
                            "trail_remaining": trail_pct - drop_from_peak,
                        })
                        log(f"  🚀 #{tid} {token_name}: {pnl_pct:+.1f}% (peak {peak:+.1f}%, trail in {trail_pct - drop_from_peak:.1f}%)")
                else:
                    log(f"  🎯 TAKE_PROFIT #{tid} {token_name}: {pnl_pct:+.1f}%", alert=True)
                    if not dry_run:
                        if mode == "real":
                            _execute_jupiter_sell(addr)
                        info = _close_trade(t, price, pnl_pct,
                            f"Guardian auto-take-profit ({pnl_pct:.1f}%)", mode)
                        log(f"  ✅ Closed #{tid} — P&L: {pnl_pct:+.1f}%", alert=True)
                        notify_telegram(
                            f"🎯 *TAKE PROFIT* — #{tid} {token_name}\n"
                            f"P&L: {pnl_pct:+.1f}% ({info['pnl_sol']:+.6f} SOL)",
                            event="on_take_profit",
                        )
                    actions.append({"type": "TAKE_PROFIT", "id": tid, "pnl": pnl_pct})

            else:
                icon = "🟢" if pnl_pct >= 0 else "🔴"
                log(f"  {icon} #{tid} {token_name}: {pnl_pct:+.1f}%")

    # Save if any changes
    if (actions or journal_dirty) and not dry_run:
        save_json(JOURNAL_PATH, journal)

    return actions


# ---------------------------------------------------------------------------
# Adaptive interval
# ---------------------------------------------------------------------------

# Cache of last P&L values per trade (set by check_positions)
_last_pnl_cache: dict = {}  # trade_id -> pnl_pct


def _compute_adaptive_interval(tcfg: dict) -> int:
    """Compute check interval based on open positions and proximity to SL/tier thresholds.

    Uses cached P&L from the last check_positions run (no extra API calls).
    In tiered mode, goes hot when near any tier trigger or SL floor.
    """
    idle = int(_cfg(tcfg, "guardian", "interval_idle", default=30))
    active = int(_cfg(tcfg, "guardian", "interval_active", default=5))
    hot = int(_cfg(tcfg, "guardian", "interval_hot", default=1))
    hot_zone = float(_cfg(tcfg, "guardian", "hot_zone_pct", default=15))

    if not _last_pnl_cache:
        return idle

    base_sl = float(_cfg(tcfg, "risk", "stop_loss_pct", default=-30))
    exit_tiers_raw = _cfg(tcfg, "risk", "exit_tiers", default=None)
    use_tiers = isinstance(exit_tiers_raw, list) and len(exit_tiers_raw) > 0

    for tid, pnl_pct in _last_pnl_cache.items():
        # Near base stop-loss
        if pnl_pct <= (base_sl + hot_zone):
            return hot

        if use_tiers:
            # Near any tier trigger or active trailing zone
            for tier in exit_tiers_raw:
                trigger = float(tier.get("trigger_pct", 0))
                if pnl_pct >= (trigger - hot_zone) and pnl_pct <= (trigger + hot_zone):
                    return hot
            # Check effective SL from position state
            ps = _position_states.get(tid)
            if ps:
                eff_sl = ps.get("effective_sl", base_sl)
                if eff_sl > base_sl and pnl_pct <= (eff_sl + hot_zone):
                    return hot
                if ps.get("trailing_active"):
                    return hot
        else:
            tp_pct = float(_cfg(tcfg, "risk", "take_profit_pct", default=100))
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
                        rpc_url = _get_solana_rpc_url()
                        bal = _get_sol_balance(_wallet_pubkey_str, rpc_url)
                        if bal >= 0:
                            _wallet_balance_sol = bal
                    _last_sol_fetch_time = tick_start

                # --- Check positions (SL/TP/trailing/BE/kill) ---
                try:
                    check_positions(dry_run=args.dry_run)
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
