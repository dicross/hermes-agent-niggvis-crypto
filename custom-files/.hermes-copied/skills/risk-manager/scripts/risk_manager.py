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

Stores config in ~/.hermes/memories/risk-config.json
Reads trades from ~/.hermes/memories/trade-journal.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.expanduser("~/.hermes/memories/risk-config.json")
JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")

DEFAULT_CONFIG = {
    "mode": "paper",
    "max_trade_sol": 0.1,
    "max_positions": 5,
    "daily_loss_limit_pct": -20,
    "min_safety_score": 60,
    "stop_loss_pct": -30,
    "take_profit_min_pct": 100,
    "total_budget_sol": 1.0,
    "kill_switch": False,
    "kill_reason": None,
    "kill_time": None,
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        _save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    # Merge with defaults for any missing keys
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def _save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, default=str)
    os.replace(tmp, CONFIG_PATH)


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

    # 7. Budget check
    invested = _get_total_invested(journal)
    if invested + args.amount > cfg["total_budget_sol"]:
        reasons.append(f"Budget exceeded: {invested:.4f} + {args.amount} > {cfg['total_budget_sol']} SOL")
        approved = False

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
    print(f"  Budget used:    {invested:.4f} / {cfg['total_budget_sol']} SOL")
    print(f"  Budget free:    {cfg['total_budget_sol'] - invested:.4f} SOL")

    pnl_icon = "✅" if daily_pnl >= 0 else "⚠️"
    print(f"\n  Daily P&L:      {pnl_icon} {daily_pnl:+.1f}% (limit: {cfg['daily_loss_limit_pct']}%)")
    print(f"  Trades today:   {len(closed_today)} closed")

    print(f"\n  Limits:")
    print(f"    Max trade:    {cfg['max_trade_sol']} SOL")
    print(f"    Stop loss:    {cfg['stop_loss_pct']}%")
    print(f"    Take profit:  {cfg['take_profit_min_pct']}% min")
    print(f"    Min safety:   {cfg['min_safety_score']}")


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

        if key not in DEFAULT_CONFIG:
            print(f"❌ Unknown config key: {key}")
            print(f"   Valid keys: {', '.join(DEFAULT_CONFIG.keys())}")
            sys.exit(1)

        # Type coercion
        default_type = type(DEFAULT_CONFIG[key])
        if default_type == bool:
            value = value.lower() in ("true", "1", "yes")
        elif default_type == float:
            value = float(value)
        elif default_type == int:
            value = int(value)

        old_val = cfg.get(key)
        cfg[key] = value
        _save_config(cfg)
        print(f"✅ {key}: {old_val} → {value}")
    else:
        print("⚙️ RISK CONFIG\n")
        for k, v in cfg.items():
            print(f"  {k}: {v}")
        print(f"\n  Config file: {CONFIG_PATH}")


def cmd_limits(args):
    """Show hard limits summary."""
    cfg = _load_config()
    print("🛡️ HARD LIMITS\n")
    print(f"  Max single trade:     {cfg['max_trade_sol']} SOL")
    print(f"  Max open positions:   {cfg['max_positions']}")
    print(f"  Total budget:         {cfg['total_budget_sol']} SOL")
    print(f"  Daily loss limit:     {cfg['daily_loss_limit_pct']}%")
    print(f"  Stop loss per trade:  {cfg['stop_loss_pct']}%")
    print(f"  Min take profit:      {cfg['take_profit_min_pct']}%")
    print(f"  Min safety score:     {cfg['min_safety_score']}")
    print(f"\n  Mode: {cfg['mode'].upper()}")
    print(f"  Kill switch: {'🔴 ON' if cfg['kill_switch'] else '🟢 OFF'}")


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
