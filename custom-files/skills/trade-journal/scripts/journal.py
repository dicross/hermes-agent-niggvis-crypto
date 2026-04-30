#!/usr/bin/env python3
"""
Trade Journal — Log and analyze crypto trades.

Usage:
    python3 journal.py add --token NAME --address ADDR --amount SOL --price PRICE --reason "why"
    python3 journal.py close --id N --exit-price PRICE --reason "why sold"
    python3 journal.py show [--limit N] [--open-only]
    python3 journal.py stats [--days N]
    python3 journal.py export [--format csv]

Stores data in ~/.hermes/memories/trade-journal.json
No external packages required.
"""

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
TRADING_CONFIG_PATH = os.path.expanduser("~/.hermes/memories/trading-config.yaml")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load() -> dict:
    """Load journal from disk."""
    if not os.path.exists(JOURNAL_PATH):
        return {"trades": [], "next_id": 1}
    with open(JOURNAL_PATH, "r") as f:
        return json.load(f)


def _save(data: dict):
    """Save journal to disk (atomic write)."""
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    tmp = JOURNAL_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, JOURNAL_PATH)


def _now_iso() -> str:
    """ISO timestamp in local timezone (reads display_timezone from config)."""
    if os.path.exists(TRADING_CONFIG_PATH):
        try:
            with open(TRADING_CONFIG_PATH) as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("display_timezone:"):
                        tz_name = s.split(":", 1)[1].strip().strip('"').strip("'")
                        if tz_name:
                            return datetime.now(ZoneInfo(tz_name)).isoformat()
        except Exception:
            pass
    return datetime.now().astimezone().isoformat()


def _get_sol_price() -> float:
        """Get current SOL/USD price from DEXScreener."""
        # SOL mint address on Solana
        SOL_ADDRESS = "So11111111111111111111111111111111111111112"
        url = f"https://api.dexscreener.com/tokens/v1/solana/{SOL_ADDRESS}"
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "hermes-trade-journal/2.0",
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if not data or not isinstance(data, list) or len(data) == 0:
                    return 0.0
                pairs = sorted(data, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
                price = pairs[0].get("priceUsd")
                return float(price) if price else 0.0
        except Exception:
            return 0.0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_add(args):
    """Add a new trade entry (buy)."""
    data = _load()
    trade_id = data["next_id"]
    data["next_id"] = trade_id + 1

    # Get SOL/USD price for conversion
    sol_price_usd = _get_sol_price()
    
    # Calculate SOL price per token (SOL/token)
    # If entry_price is USD per token, then SOL per token = USD per token / SOL price in USD
    entry_price_sol = args.price / sol_price_usd if sol_price_usd > 0 else 0
    entry_price_usd = args.price

    trade = {
        "id": trade_id,
        "status": "open",
        "paper": args.paper,
        "token": args.token,
        "address": args.address,
        "amount_sol": args.amount,
        "entry_price_sol": entry_price_sol,
        "entry_price_usd": entry_price_usd,
        "entry_time": _now_iso(),
        "entry_reason": args.reason,
        "exit_price_sol": None,
        "exit_price_usd": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl_pct": None,
        "pnl_sol": None,
    }

    data["trades"].append(trade)
    _save(data)

    mode = "📝 PAPER" if args.paper else "💰 REAL"
    print(f"{mode} Trade #{trade_id} logged:")
    print(f"  Token: {args.token} ({args.address[:12]}...)")
    print(f"  Amount: {args.amount} SOL")
    print(f"  Entry: {entry_price_sol:.6f} SOL/token (${entry_price_usd:.6f})")
    print(f"  Reason: {args.reason}")


def cmd_close(args):
    """Close a trade (sell)."""
    data = _load()
    trade = None
    for t in data["trades"]:
        if t["id"] == args.id:
            trade = t
            break

    if not trade:
        print(f"❌ Trade #{args.id} not found.")
        sys.exit(1)
    if trade["status"] == "closed":
        print(f"⚠ Trade #{args.id} is already closed.")
        sys.exit(1)

    # Get SOL/USD price for conversion
    sol_price_usd = _get_sol_price()
    
    # Calculate exit prices
    exit_price_usd = float(args.exit_price)
    exit_price_sol = exit_price_usd / sol_price_usd if sol_price_usd > 0 else 0
    
    # Entry prices (already stored)
    entry_price_sol = float(trade.get("entry_price_sol", 0))
    entry_price_usd = float(trade.get("entry_price_usd", 0))
    
    # Fallback to old format if new fields don't exist
    if entry_price_sol == 0 and entry_price_usd == 0:
        entry_price_usd = float(trade["entry_price"])
        entry_price_sol = entry_price_usd / sol_price_usd if sol_price_usd > 0 else 0

    # Calculate P&L based on SOL price change
    pnl_pct = ((exit_price_sol - entry_price_sol) / entry_price_sol) * 100 if entry_price_sol > 0 else 0
    
    # SOL P&L based on amount and percentage change
    amount_sol = float(trade["amount_sol"])
    pnl_sol = amount_sol * (pnl_pct / 100)

    trade["status"] = "closed"
    trade["exit_price_sol"] = exit_price_sol
    trade["exit_price_usd"] = exit_price_usd
    trade["exit_time"] = _now_iso()
    trade["exit_reason"] = args.reason
    trade["pnl_pct"] = round(pnl_pct, 2)
    trade["pnl_sol"] = round(pnl_sol, 6)

    _save(data)

    icon = "✅" if pnl_pct >= 0 else "❌"
    print(f"{icon} Trade #{args.id} closed:")
    print(f"  Token: {trade['token']}")
    print(f"  Entry: {entry_price_sol:.6f} SOL/token (${entry_price_usd:.6f}) → Exit: {exit_price_sol:.6f} SOL/token (${exit_price_usd:.6f})")
    print(f"  P&L: {pnl_pct:+.2f}% ({pnl_sol:+.6f} SOL)")
    print(f"  Reason: {args.reason}")

    # Hold time
    try:
        entry_dt = datetime.fromisoformat(trade["entry_time"])
        exit_dt = datetime.fromisoformat(trade["exit_time"])
        hold = exit_dt - entry_dt
        hours = hold.total_seconds() / 3600
        if hours < 1:
            print(f"  Hold time: {int(hold.total_seconds() / 60)} minutes")
        elif hours < 24:
            print(f"  Hold time: {hours:.1f} hours")
        else:
            print(f"  Hold time: {hours / 24:.1f} days")
    except Exception:
        pass


def cmd_show(args):
    """Show recent trades."""
    data = _load()
    trades = data["trades"]

    if args.open_only:
        trades = [t for t in trades if t["status"] == "open"]

    if not trades:
        print("📭 No trades found.")
        return

    trades = trades[-args.limit:]

    print(f"📋 Trades ({len(trades)} shown):\n")
    print(f"  {'ID':>4} {'Status':>6} {'Mode':>5} {'Token':<12} {'Amount':>8} {'Entry':>12} {'Exit':>12} {'P&L':>8}")
    print(f"  {'-'*4} {'-'*6} {'-'*5} {'-'*12} {'-'*8} {'-'*12} {'-'*12} {'-'*8}")

    for t in trades:
        status = "OPEN" if t["status"] == "open" else "CLOSED"
        mode = "PAPER" if t.get("paper") else "REAL"
        token = t["token"][:12]
        amount = f"{float(t['amount_sol']):.4f}"
        # Use new SOL price fields, fallback to old USD prices if needed
        entry_sol = t.get("entry_price_sol")
        if entry_sol is None or entry_sol == "":
            # Fallback: calculate from old entry_price if it's in USD per token
            entry_usd = t.get("entry_price", 0)
            sol_price_usd = _get_sol_price()
            entry_sol = entry_usd / sol_price_usd if sol_price_usd > 0 else 0
        entry = f"{float(entry_sol):.8f}"[:12]
        exit_sol = t.get("exit_price_sol")
        if exit_sol is None or exit_sol == "":
            exit_usd = t.get("exit_price", 0)
            sol_price_usd = _get_sol_price()
            exit_sol = exit_usd / sol_price_usd if sol_price_usd > 0 else 0
        exit_p = f"{float(exit_sol):.8f}"[:12] if t.get("exit_price") is not None else "—"
        pnl = f"{t['pnl_pct']:+.1f}%" if t.get("pnl_pct") is not None else "—"

        print(f"  {t['id']:>4} {status:>6} {mode:>5} {token:<12} {amount:>8} {entry:>12} {exit_p:>12} {pnl:>8}")

    open_count = sum(1 for t in data["trades"] if t["status"] == "open")
    print(f"\n  Open positions: {open_count}")


def cmd_stats(args):
    """Show performance statistics."""
    data = _load()
    trades = data["trades"]

    # Filter by days if specified
    if args.days:
        cutoff = datetime.now().astimezone() - timedelta(days=args.days)
        trades = [
            t for t in trades
            if datetime.fromisoformat(t["entry_time"]) >= cutoff
        ]

    closed = [t for t in trades if t["status"] == "closed"]
    open_trades = [t for t in trades if t["status"] == "open"]
    paper_closed = [t for t in closed if t.get("paper")]
    real_closed = [t for t in closed if not t.get("paper")]

    period = f" (last {args.days} days)" if args.days else " (all time)"

    print(f"📊 TRADING STATS{period}\n")
    print(f"  Total trades: {len(trades)} ({len(open_trades)} open, {len(closed)} closed)")
    print(f"  Paper: {len(paper_closed)} closed | Real: {len(real_closed)} closed")

    if not closed:
        print("\n  No closed trades to analyze.")
        return

    # Win/loss
    wins = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_pct") or 0) <= 0]
    win_rate = len(wins) / len(closed) * 100

    print(f"\n  Win rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")

    # P&L
    pnls_pct = [t.get("pnl_pct", 0) for t in closed]
    pnls_sol = [t.get("pnl_sol", 0) for t in closed]
    avg_pnl = sum(pnls_pct) / len(pnls_pct)
    total_sol = sum(pnls_sol)

    print(f"  Avg P&L: {avg_pnl:+.2f}%")
    print(f"  Total P&L: {total_sol:+.6f} SOL")

    # Best/worst
    best = max(closed, key=lambda t: t.get("pnl_pct", 0))
    worst = min(closed, key=lambda t: t.get("pnl_pct", 0))
    print(f"\n  🏆 Best:  #{best['id']} {best['token']} ({best.get('pnl_pct', 0):+.1f}%)")
    print(f"  💀 Worst: #{worst['id']} {worst['token']} ({worst.get('pnl_pct', 0):+.1f}%)")

    # Avg hold time
    hold_times = []
    for t in closed:
        try:
            entry_dt = datetime.fromisoformat(t["entry_time"])
            exit_dt = datetime.fromisoformat(t["exit_time"])
            hold_times.append((exit_dt - entry_dt).total_seconds() / 3600)
        except Exception:
            pass
    if hold_times:
        avg_hold = sum(hold_times) / len(hold_times)
        if avg_hold < 1:
            print(f"  ⏱ Avg hold: {int(avg_hold * 60)} minutes")
        elif avg_hold < 24:
            print(f"  ⏱ Avg hold: {avg_hold:.1f} hours")
        else:
            print(f"  ⏱ Avg hold: {avg_hold / 24:.1f} days")

    # Win P&L vs Loss P&L
    if wins:
        avg_win = sum(t.get("pnl_pct", 0) for t in wins) / len(wins)
        print(f"\n  Avg win: {avg_win:+.2f}%")
    if losses:
        avg_loss = sum(t.get("pnl_pct", 0) for t in losses) / len(losses)
        print(f"  Avg loss: {avg_loss:+.2f}%")
def cmd_export(args):
    """Export trades to CSV."""
    data = _load()
    trades = data["trades"]

    if not trades:
        print("No trades to export.")
        return

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id", "status", "paper", "token", "address",
            "amount_sol", "entry_price_sol", "entry_price_usd", "entry_time", "entry_reason",
            "exit_price_sol", "exit_price_usd", "exit_time", "exit_reason", "pnl_pct", "pnl_sol",
        ],
    )
    writer.writeheader()
    for t in trades:
        # Build row with new field names, falling back to old field names for USD prices if needed
        row = {
            "id": t.get("id"),
            "status": t.get("status"),
            "paper": t.get("paper"),
            "token": t.get("token"),
            "address": t.get("address"),
            "amount_sol": t.get("amount_sol"),
            "entry_price_sol": t.get("entry_price_sol", ""),
            "entry_price_usd": t.get("entry_price_usd", t.get("entry_price", "")),
            "entry_time": t.get("entry_time"),
            "entry_reason": t.get("entry_reason"),
            "exit_price_sol": t.get("exit_price_sol", ""),
            "exit_price_usd": t.get("exit_price_usd", t.get("exit_price", "")),
            "exit_time": t.get("exit_time"),
            "exit_reason": t.get("exit_reason"),
            "pnl_pct": t.get("pnl_pct"),
            "pnl_sol": t.get("pnl_sol"),
        }
        writer.writerow(row)

    csv_path = os.path.expanduser("~/.hermes/memories/trade-journal.csv")
    with open(csv_path, "w") as f:
        f.write(output.getvalue())

    print(f"📤 Exported {len(trades)} trades to {csv_path}")




# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Trade Journal — Log and analyze crypto trades"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Log a new trade (buy)")
    p_add.add_argument("--token", required=True, help="Token name/symbol")
    p_add.add_argument("--address", required=True, help="Token mint address")
    p_add.add_argument("--amount", type=float, required=True, help="Amount in SOL")
    p_add.add_argument("--price", type=float, required=True, help="Entry price in USD (SOL price will be calculated automatically)")
    p_add.add_argument("--reason", required=True, help="Why this trade")
    p_add.add_argument("--paper", action="store_true", help="Paper trade (not real)")
    p_add.set_defaults(func=cmd_add)

    # close
    p_close = sub.add_parser("close", help="Close a trade (sell)")
    p_close.add_argument("--id", type=int, required=True, help="Trade ID to close")
    p_close.add_argument("--exit-price", type=float, required=True, help="Exit price USD")
    p_close.add_argument("--reason", default="Manual close", help="Why selling")
    p_close.set_defaults(func=cmd_close)

    # show
    p_show = sub.add_parser("show", help="Show recent trades")
    p_show.add_argument("--limit", type=int, default=20, help="Max trades to show")
    p_show.add_argument("--open-only", action="store_true", help="Show only open trades")
    p_show.set_defaults(func=cmd_show)

    # stats
    p_stats = sub.add_parser("stats", help="Performance statistics")
    p_stats.add_argument("--days", type=int, default=0, help="Last N days (0 = all)")
    p_stats.set_defaults(func=cmd_stats)

    # export
    p_export = sub.add_parser("export", help="Export trades to CSV")
    p_export.add_argument(
        "--format", choices=["csv"], default="csv", help="Export format"
    )
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)



if __name__ == "__main__":
    main()
