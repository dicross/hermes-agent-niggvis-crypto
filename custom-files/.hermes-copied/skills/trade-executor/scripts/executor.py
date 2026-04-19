#!/usr/bin/env python3
"""
Trade Executor — Buy & sell on Solana (paper + real mode).

Usage:
 python3 executor.py buy --token <address> --amount <SOL> --reason "why"
 python3 executor.py sell --id <trade_id> --reason "why"
 python3 executor.py check-exits [--stop-loss] [--take-profit]
 python3 executor.py portfolio
 python3 executor.py mode [paper|real]

Integrates: risk-manager (pre-trade check), onchain-analyzer (safety),
 trade-journal (logging), DEXScreener (prices).
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
RISK_CONFIG_PATH = os.path.expanduser("~/.hermes/memories/risk-config.json")
SKILLS_DIR = os.path.expanduser("~/.hermes/skills")
DEXSCREENER_BASE = "https://api.dexscreener.com"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _http_get(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-trade-executor/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return None


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _get_price(address: str) -> float | None:
    """Get current USD price from DEXScreener."""
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{address}"
    data = _http_get(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    # Best liquidity pair
    pairs = sorted(data, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
    price = pairs[0].get("priceUsd")
    return float(price) if price else None


def _run_skill(script: str, args: list) -> tuple[int, str]:
    """Run another skill script and capture output."""
    cmd = [sys.executable, script] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout + result.stderr
    except Exception as e:
        return 1, str(e)


def _get_risk_config() -> dict:
    defaults = {
        "mode": "paper",
        "stop_loss_pct": -30,
        "take_profit_min_pct": 100,
    }
    cfg = _load_json(RISK_CONFIG_PATH)
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_buy(args):
    """Execute a buy (paper or real)."""
    cfg = _get_risk_config()
    mode = cfg["mode"]

    print(f"🔄 Processing BUY ({mode.upper()} mode)...\n")

    # 1. Get current price
    price = _get_price(args.token)
    if price is None:
        print("❌ Cannot fetch price from DEXScreener. Aborting.")
        sys.exit(1)
    print(f"💰 Price: ${price}")

    # 2. Safety check via onchain-analyzer
    analyzer_script = os.path.join(SKILLS_DIR, "onchain-analyzer", "scripts", "analyzer.py")
    safety_score = None
    if os.path.exists(analyzer_script):
        print("🔍 Running safety check...")
        rc, output = _run_skill(analyzer_script, ["analyze", args.token])
        # Parse safety score from output
        for line in output.split("\n"):
            if "Safety Score:" in line and "/100" in line:
                try:
                    parts = line.split("Score:")[1].strip()
                    score_str = parts.split("/")[0].split()[-1]
                    safety_score = int(score_str)
                except (ValueError, IndexError) as e:
                    print(f"⚠️ Could not parse safety score: {e}")
        if safety_score is not None:
            print(f"  Safety score: {safety_score}/100")
    else:
        print("⚠️ onchain-analyzer not installed, skipping safety check")

    # 3. Risk manager check
    risk_script = os.path.join(SKILLS_DIR, "risk-manager", "scripts", "risk_manager.py")
    if os.path.exists(risk_script):
        print("🛡️ Running risk check...")
        risk_args = ["check", "--amount", str(args.amount), "--token", args.token]
        if safety_score is not None:
            risk_args += ["--safety-score", str(safety_score)]
        rc, output = _run_skill(risk_script, risk_args)
        if rc != 0:
            print(f"\n🚫 TRADE BLOCKED by risk-manager:")
            for line in output.strip().split("\n"):
                if line.strip() and "JSON" not in line and not line.startswith("{") and not line.startswith("}"):
                    print(f"  {line.strip()}")
            sys.exit(1)
        print("✅ Risk check passed")
    else:
        print("⚠️ risk-manager not installed, skipping risk check")

    # 4. Log trade via journal
    journal_script = os.path.join(SKILLS_DIR, "trade-journal", "scripts", "journal.py")
    if os.path.exists(journal_script):
        journal_args = [
            "add",
            "--token", args.token_name or args.token[:12],
            "--address", args.token,
            "--amount", str(args.amount),
            "--price", str(price),
            "--reason", args.reason,
        ]
        if mode == "paper":
            journal_args.append("--paper")

        rc, output = _run_skill(journal_script, journal_args)
        print(f"\n{output.strip()}")
    else:
        print("\n⚠️ trade-journal not installed, trade not logged")

    # 5. Real mode — future Trojan integration
    if mode == "real":
        print("\n⚠️ REAL MODE: Trojan integration not yet implemented.")
        print("Trade logged but NOT executed on-chain.")
        print("Execute manually via Trojan: /buy <address> <amount>")


def cmd_sell(args):
    """Close a position (sell)."""
    cfg = _get_risk_config()
    mode = cfg["mode"]

    # Load journal to find the trade
    journal = _load_json(JOURNAL_PATH)
    trade = None
    for t in journal.get("trades", []):
        if t["id"] == args.id:
            trade = t
            break

    if not trade:
        print(f"❌ Trade #{args.id} not found.")
        sys.exit(1)
    if trade["status"] == "closed":
        print(f"⚠️ Trade #{args.id} is already closed.")
        sys.exit(1)

    # Get current price
    price = _get_price(trade["address"])
    if price is None:
        print("❌ Cannot fetch price. Use trade-journal close manually with --exit-price.")
        sys.exit(1)

    print(f"🔄 Processing SELL ({mode.upper()} mode)...\n")
    print(f"Token: {trade['token']}")
    print(f"Entry: ${trade['entry_price']} → Current: ${price}")

    # Close via journal
    journal_script = os.path.join(SKILLS_DIR, "trade-journal", "scripts", "journal.py")
    if os.path.exists(journal_script):
        rc, output = _run_skill(journal_script, [
            "close",
            "--id", str(args.id),
            "--exit-price", str(price),
            "--reason", args.reason,
        ])
        print(f"\n{output.strip()}")

    if mode == "real":
        print("\n⚠️ REAL MODE: Execute sell manually via Trojan: /sell <address>")


def cmd_check_exits(args):
    """Check open positions for exit signals."""
    cfg = _get_risk_config()
    journal = _load_json(JOURNAL_PATH)
    open_trades = [t for t in journal.get("trades", []) if t["status"] == "open"]

    if not open_trades:
        print("📭 No open positions.")
        return

    sl_pct = cfg.get("stop_loss_pct", -30)
    tp_pct = cfg.get("take_profit_min_pct", 100)

    print(f"🔍 Checking {len(open_trades)} open positions...\n")
    print(f"Stop loss: {sl_pct}% | Take profit: +{tp_pct}%\n")

    alerts = []

    for t in open_trades:
        addr = t.get("address", "")
        price = _get_price(addr) if addr else None

        if price is None:
            print(f"#{t['id']} {t['token']}: ⚠️ Cannot fetch price")
            continue

        entry = float(t["entry_price"])
        pnl_pct = ((price - entry) / entry * 100) if entry > 0 else 0

        icon = "🟢" if pnl_pct >= 0 else "🔴"
        print(f"#{t['id']} {t['token']}: ${entry:.8f} → ${price:.8f} ({pnl_pct:+.1f}%) {icon}")

        if pnl_pct <= sl_pct and (not args.take_profit):
            alerts.append({"id": t["id"], "token": t["token"], "type": "STOP_LOSS", "pnl": pnl_pct})
            print(f"  🚨 STOP LOSS triggered ({pnl_pct:.1f}% <= {sl_pct}%)")

        if pnl_pct >= tp_pct and (not args.stop_loss):
            alerts.append({"id": t["id"], "token": t["token"], "type": "TAKE_PROFIT", "pnl": pnl_pct})
            print(f"  🎯 TAKE PROFIT target reached ({pnl_pct:.1f}% >= +{tp_pct}%)")

    if alerts:
        print(f"\n⚡ {len(alerts)} exit signal(s):")
        for a in alerts:
            print(f"  {a['type']}: #{a['id']} {a['token']} ({a['pnl']:+.1f}%)")
        print("\nTo auto-sell: python3 executor.py sell --id <N> --reason 'stop loss'")
    else:
        print("\n✅ No exit signals.")


def cmd_portfolio(args):
    """Show current holdings with live prices."""
    journal = _load_json(JOURNAL_PATH)
    open_trades = [t for t in journal.get("trades", []) if t["status"] == "open"]

    if not open_trades:
        print("📭 No open positions.")
        return

    print(f"📊 PORTFOLIO ({len(open_trades)} positions)\n")
    total_invested = 0
    total_value = 0

    for t in open_trades:
        addr = t.get("address", "")
        price = _get_price(addr) if addr else None
        entry = float(t["entry_price"])
        amount = float(t["amount_sol"])
        paper = "📝" if t.get("paper") else "💰"

        total_invested += amount

        if price:
            pnl_pct = ((price - entry) / entry * 100) if entry > 0 else 0
            icon = "🟢" if pnl_pct >= 0 else "🔴"
            current_sol = amount * (1 + pnl_pct / 100)
            total_value += current_sol
            print(f"{paper} #{t['id']} {t['token']:<12} {amount:.4f} SOL ${entry:.8f} → ${price:.8f} {pnl_pct:+.1f}% {icon}")
        else:
            total_value += amount
            print(f"{paper} #{t['id']} {t['token']:<12} {amount:.4f} SOL ${entry:.8f} → ??? ⚠️")

    unrealized_pnl = total_value - total_invested
    pnl_pct_total = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
    print(f"\nInvested: {total_invested:.4f} SOL")
    print(f"Value: {total_value:.4f} SOL")
    print(f"P&L: {unrealized_pnl:+.4f} SOL ({pnl_pct_total:+.1f}%)")


def cmd_mode(args):
    """View or set trading mode."""
    cfg = _get_risk_config()

    if args.new_mode:
        if args.new_mode not in ("paper", "real"):
            print("❌ Mode must be 'paper' or 'real'")
            sys.exit(1)
        old = cfg["mode"]
        cfg["mode"] = args.new_mode
        os.makedirs(os.path.dirname(RISK_CONFIG_PATH), exist_ok=True)
        tmp = RISK_CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, RISK_CONFIG_PATH)
        print(f"Mode: {old.upper()} → {args.new_mode.upper()}")
        if args.new_mode == "real":
            print("⚠️ REAL MODE — trades will be logged as real. Trojan integration pending.")
    else:
        print(f"Current mode: {cfg['mode'].upper()}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Trade Executor — Buy & sell on Solana"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # buy
    p_buy = sub.add_parser("buy", help="Buy a token")
    p_buy.add_argument("--token", required=True, help="Token mint address")
    p_buy.add_argument("--token-name", default=None, help="Token name/symbol")
    p_buy.add_argument("--amount", type=float, required=True, help="Amount in SOL")
    p_buy.add_argument("--reason", required=True, help="Buy reason")
    p_buy.set_defaults(func=cmd_buy)

    # sell
    p_sell = sub.add_parser("sell", help="Sell / close position")
    p_sell.add_argument("--id", type=int, required=True, help="Trade ID")
    p_sell.add_argument("--reason", default="Manual sell", help="Sell reason")
    p_sell.set_defaults(func=cmd_sell)

    # check-exits
    p_exits = sub.add_parser("check-exits", help="Check exit signals")
    p_exits.add_argument("--stop-loss", action="store_true", help="Only check stop-loss")
    p_exits.add_argument("--take-profit", action="store_true", help="Only check take-profit")
    p_exits.set_defaults(func=cmd_check_exits)

    # portfolio
    p_port = sub.add_parser("portfolio", help="Show holdings")
    p_port.set_defaults(func=cmd_portfolio)

    # mode
    p_mode = sub.add_parser("mode", help="View/set trading mode")
    p_mode.add_argument("new_mode", nargs="?", help="paper or real")
    p_mode.set_defaults(func=cmd_mode)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
