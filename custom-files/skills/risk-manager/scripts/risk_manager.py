#!/usr/bin/env python3
"""
Risk Manager — Trading safety layer.

Usage:
    python3 risk_manager.py check --amount <SOL> --token <address> [--safety-score N]
    python3 risk_manager.py status
    python3 risk_manager.py kill [--reason "why"]
    python3 risk_manager.py resume
    python3 risk_manager.py config [--set key=value]
    python3 risk_manager.py limits

Reads trading config from: ~/.hermes/memories/trading-config.yaml
Reads trades from: ~/.hermes/memories/trade-journal.json
Kill switch state: ~/.hermes/memories/risk-state.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
STATE_PATH = os.path.expanduser("~/.hermes/memories/risk-state.json")
JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")

# ---------------------------------------------------------------------------
# YAML parser (minimal, no dependencies)
# ---------------------------------------------------------------------------


def _parse_yaml_flat(path: str) -> dict:
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


DEFAULT_CONFIG = {
    "mode": "paper",
    "max_trade_sol": 0.15,
    "max_positions": 5,
    "daily_loss_limit_pct": -20,
    "min_safety_score": 60,
    "stop_loss_pct": -30,
    "take_profit_pct": 100,
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load config from trading-config.yaml, flatten into risk-manager format."""
    tcfg = _parse_yaml_flat(CONFIG_PATH)
    state = _load_state()
    return {
        "mode": _cfg(tcfg, "mode", default="paper"),
        "max_trade_sol": _cfg(tcfg, "position_sizing", "max_trade_sol", default=0.15),
        "max_positions": _cfg(tcfg, "position_sizing", "max_positions", default=5),
        "daily_loss_limit_pct": _cfg(tcfg, "risk", "daily_loss_limit_pct", default=-20),
        "min_safety_score": _cfg(tcfg, "filters", "min_safety_score", default=60),
        "stop_loss_pct": _cfg(tcfg, "risk", "stop_loss_pct", default=-30),
        "take_profit_pct": _cfg(tcfg, "risk", "take_profit_pct", default=100),
        "kill_switch": state.get("kill_switch", False),
        "kill_reason": state.get("kill_reason"),
        "kill_time": state.get("kill_time"),
    }


def _load_state() -> dict:
    """Load kill switch state."""
    if not os.path.exists(STATE_PATH):
        return {"kill_switch": False}
    with open(STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_PATH)


def _save_config(cfg: dict):
    """Save kill switch state only (other config lives in YAML)."""
    state = {
        "kill_switch": cfg.get("kill_switch", False),
        "kill_reason": cfg.get("kill_reason"),
        "kill_time": cfg.get("kill_time"),
    }
    _save_state(state)


def _load_journal() -> dict:
    if not os.path.exists(JOURNAL_PATH):
        return {"trades": [], "next_id": 1}
    with open(JOURNAL_PATH, "r") as f:
        return json.load(f)


def _get_open_trades(journal: dict) -> list:
    return [t for t in journal["trades"] if t["status"] == "open"]


def _get_today_closed(journal: dict) -> list:
    today = datetime.now(timezone.utc).date()
    closed = []
    for t in journal["trades"]:
        if t["status"] == "closed" and t.get("exit_time"):
            try:
                exit_date = datetime.fromisoformat(t["exit_time"]).date()
                if exit_date == today:
                    closed.append(t)
            except (ValueError, TypeError):
                pass
    return closed


def _get_daily_pnl(journal: dict) -> float:
    """Calculate today's total P&L in %."""
    closed_today = _get_today_closed(journal)
    if not closed_today:
        return 0.0
    return sum(t.get("pnl_pct", 0) for t in closed_today)


def _get_total_invested(journal: dict) -> float:
    """Sum of SOL in open positions."""
    return sum(float(t.get("amount_sol", 0)) for t in _get_open_trades(journal))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_check(args):
    """Pre-trade approval check."""
    cfg = _load_config()
    journal = _load_journal()

    reasons = []
    approved = True

    # 1. Kill switch
    if cfg["kill_switch"]:
        reasons.append(f"KILL SWITCH active: {cfg.get('kill_reason', 'no reason')}")
        approved = False

    # 2. Amount limit
    if args.amount > cfg["max_trade_sol"]:
        reasons.append(f"Amount {args.amount} SOL > max {cfg['max_trade_sol']} SOL")
        approved = False

    # 3. Open positions limit
    open_trades = _get_open_trades(journal)
    if len(open_trades) >= cfg["max_positions"]:
        reasons.append(f"Open positions {len(open_trades)} >= max {cfg['max_positions']}")
        approved = False

    # 4. Daily loss limit
    daily_pnl = _get_daily_pnl(journal)
    if daily_pnl <= cfg["daily_loss_limit_pct"]:
        reasons.append(f"Daily P&L {daily_pnl:.1f}% <= limit {cfg['daily_loss_limit_pct']}%")
        approved = False

    # 5. Safety score
    if args.safety_score is not None and args.safety_score < cfg["min_safety_score"]:
        reasons.append(f"Safety score {args.safety_score} < min {cfg['min_safety_score']}")
        approved = False

    # 6. Duplicate token check
    if args.token:
        for t in open_trades:
            if t.get("address") == args.token:
                reasons.append(f"Already have open position in this token (trade #{t['id']})")
                approved = False
                break

    # 7. Budget check — use wallet balance concept via position sizing
    # (no more total_budget_sol — it's dynamic now based on wallet balance)
    # We check max_positions and max_trade_sol instead

    # Output
    if approved:
        print(f"✅ APPROVED — {cfg['mode'].upper()} mode")
        print(f"  Amount: {args.amount} SOL")
        print(f"  Open positions: {len(open_trades)}/{cfg['max_positions']}")
        print(f"  Daily P&L: {daily_pnl:+.1f}%")
        print(f"  Budget: {invested:.4f}/{cfg['total_budget_sol']} SOL")
        if args.safety_score is not None:
            print(f"  Safety score: {args.safety_score}")
    else:
        print("🚫 BLOCKED")
        for r in reasons:
            print(f"  ✗ {r}")

    # Machine-readable output
    print("\n---JSON---")
    print(json.dumps({
        "approved": approved,
        "mode": cfg["mode"],
        "reasons": reasons,
        "open_positions": len(open_trades),
        "daily_pnl_pct": daily_pnl,
        "budget_used": invested,
    }, indent=2))

    sys.exit(0 if approved else 1)


def cmd_status(args):
    """Current risk dashboard."""
    cfg = _load_config()
    journal = _load_journal()
    open_trades = _get_open_trades(journal)
    daily_pnl = _get_daily_pnl(journal)
    invested = _get_total_invested(journal)
    closed_today = _get_today_closed(journal)

    print("📊 RISK DASHBOARD\n")
    print(f"  Mode:           {cfg['mode'].upper()}")

    kill = "🔴 ON" if cfg["kill_switch"] else "🟢 OFF"
    print(f"  Kill switch:    {kill}")
    if cfg["kill_switch"]:
        print(f"    Reason: {cfg.get('kill_reason', '?')}")
        print(f"    Since:  {cfg.get('kill_time', '?')}")

    print(f"\n  Open positions: {len(open_trades)} / {cfg['max_positions']}")
    print(f"  Invested:       {invested:.4f} SOL")

    pnl_icon = "✅" if daily_pnl >= 0 else "⚠️"
    print(f"\n  Daily P&L:      {pnl_icon} {daily_pnl:+.1f}% (limit: {cfg['daily_loss_limit_pct']}%)")
    print(f"  Trades today:   {len(closed_today)} closed")

    print(f"\n  Limits:")
    print(f"    Max trade:    {cfg['max_trade_sol']} SOL")
    print(f"    Stop loss:    {cfg['stop_loss_pct']}%")
    print(f"    Take profit:  {cfg['take_profit_pct']}% min")
    print(f"    Min safety:   {cfg['min_safety_score']}")
    print(f"\n  Config: {CONFIG_PATH}")


def cmd_kill(args):
    """Activate kill switch."""
    cfg = _load_config()
    cfg["kill_switch"] = True
    cfg["kill_reason"] = args.reason or "Manual kill"
    cfg["kill_time"] = datetime.now(timezone.utc).isoformat()
    _save_config(cfg)
    print("🔴 KILL SWITCH ACTIVATED")
    print(f"  Reason: {cfg['kill_reason']}")
    print("  All trading halted. Use `resume` to re-enable.")


def cmd_resume(args):
    """Deactivate kill switch."""
    cfg = _load_config()
    if not cfg["kill_switch"]:
        print("Kill switch is already OFF.")
        return
    cfg["kill_switch"] = False
    cfg["kill_reason"] = None
    cfg["kill_time"] = None
    _save_config(cfg)
    print("🟢 KILL SWITCH DEACTIVATED — trading resumed")


def cmd_config(args):
    """View or set config."""
    cfg = _load_config()

    if args.set:
        key, _, value = args.set.partition("=")
        key = key.strip()
        value = value.strip()

        print(f"\n  ⚠️ Config changes should be made in: {CONFIG_PATH}")
        print(f"  Or use: python3 executor.py config-propose --key {key} --value {value} --reason 'why'")
        print(f"\n  Current {key}: {cfg.get(key, '?')}")
    else:
        print("⚙️ RISK CONFIG (from trading-config.yaml)\n")
        for k, v in cfg.items():
            print(f"  {k}: {v}")
        print(f"\n  Config file: {CONFIG_PATH}")


def cmd_limits(args):
    """Show hard limits summary."""
    cfg = _load_config()
    print("🛡️ HARD LIMITS\n")
    print(f"  Max single trade:     {cfg['max_trade_sol']} SOL")
    print(f"  Max open positions:   {cfg['max_positions']}")
    print(f"  Daily loss limit:     {cfg['daily_loss_limit_pct']}%")
    print(f"  Stop loss per trade:  {cfg['stop_loss_pct']}%")
    print(f"  Min take profit:      {cfg['take_profit_pct']}%")
    print(f"  Min safety score:     {cfg['min_safety_score']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Risk Manager — Trading safety layer"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Pre-trade approval")
    p_check.add_argument("--amount", type=float, required=True, help="Trade amount in SOL")
    p_check.add_argument("--token", default=None, help="Token address")
    p_check.add_argument("--safety-score", type=int, default=None, help="Safety score from analyzer")
    p_check.set_defaults(func=cmd_check)

    # status
    p_status = sub.add_parser("status", help="Risk dashboard")
    p_status.set_defaults(func=cmd_status)

    # kill
    p_kill = sub.add_parser("kill", help="Activate kill switch")
    p_kill.add_argument("--reason", default=None, help="Reason for kill")
    p_kill.set_defaults(func=cmd_kill)

    # resume
    p_resume = sub.add_parser("resume", help="Deactivate kill switch")
    p_resume.set_defaults(func=cmd_resume)

    # config
    p_config = sub.add_parser("config", help="View/set config")
    p_config.add_argument("--set", default=None, help="Set key=value")
    p_config.set_defaults(func=cmd_config)

    # limits
    p_limits = sub.add_parser("limits", help="Show hard limits")
    p_limits.set_defaults(func=cmd_limits)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
