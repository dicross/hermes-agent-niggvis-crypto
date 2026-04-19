#!/usr/bin/env python3
"""
Trade Executor — Buy & sell on Solana via Jupiter.

Usage:
    python3 executor.py buy --token <address> --reason "why" [--amount <SOL>]
    python3 executor.py sell --id <trade_id> --reason "why" [--pct 100]
    python3 executor.py check-exits
    python3 executor.py portfolio
    python3 executor.py mode [paper|real]
    python3 executor.py config-propose --key <key> --value <val> --reason "why"

Integrates: jupiter_swap (execution), risk-manager (pre-trade check),
            onchain-analyzer (safety), trade-journal (logging).

Config: ~/.hermes/memories/trading-config.yaml
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
TRADING_CONFIG_PATH = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
SKILLS_DIR = os.path.expanduser("~/.hermes/skills")
DEXSCREENER_BASE = "https://api.dexscreener.com"

# ---------------------------------------------------------------------------
# Config (minimal YAML parser — same as in jupiter_swap.py)
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


def load_trading_config() -> dict:
    return _parse_yaml_flat(TRADING_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _http_get(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-trade-executor/2.0",
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


def _save_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def _get_price(address: str) -> float | None:
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{address}"
    data = _http_get(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    pairs = sorted(data, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
    price = pairs[0].get("priceUsd")
    return float(price) if price else None


def _run_skill(script: str, args: list) -> tuple[int, str]:
    tcfg = load_trading_config()
    python_bin = _cfg(tcfg, "python_bin", default=sys.executable)
    if isinstance(python_bin, str):
        python_bin = os.path.expanduser(python_bin)
    if not os.path.exists(python_bin):
        python_bin = sys.executable
    cmd = [python_bin, script] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout + result.stderr
    except Exception as e:
        return 1, str(e)


def _get_wallet_balance() -> float:
    """Get SOL balance from jupiter_swap module."""
    jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
    if not os.path.exists(jupiter_script):
        return 0.0
    rc, output = _run_skill(jupiter_script, ["balance"])
    for line in output.split("\n"):
        if "SOL:" in line and "Token" not in line:
            try:
                return float(line.split(":")[-1].strip())
            except ValueError:
                pass
    return 0.0


def _calculate_position_size(tcfg: dict) -> float:
    """Calculate position size based on wallet balance and config."""
    balance = _get_wallet_balance()
    pct = _cfg(tcfg, "position_sizing", "position_pct", default=5.0)
    min_trade = _cfg(tcfg, "position_sizing", "min_trade_sol", default=0.01)
    max_trade = _cfg(tcfg, "position_sizing", "max_trade_sol", default=0.15)
    min_wallet = _cfg(tcfg, "position_sizing", "min_wallet_balance", default=0.05)

    available = balance - min_wallet
    if available <= min_trade:
        return 0.0

    size = available * (pct / 100.0)
    return max(min_trade, min(max_trade, size))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_buy(args):
    """Execute a buy."""
    tcfg = load_trading_config()
    mode = _cfg(tcfg, "mode", default="paper")

    print(f"🔄 Processing BUY ({mode.upper()} mode)...\n")

    # 1. Position sizing
    if args.amount:
        amount = args.amount
        print(f"  Manual size: {amount:.4f} SOL")
    else:
        amount = _calculate_position_size(tcfg)
        if amount <= 0:
            print("❌ Insufficient balance for auto-sizing. Check wallet or increase funds.")
            sys.exit(1)
        balance = _get_wallet_balance()
        pct = _cfg(tcfg, "position_sizing", "position_pct", default=5.0)
        print(f"  Auto-sized: {amount:.4f} SOL ({pct}% of {balance:.4f} wallet)")

    # 2. Get current price
    price = _get_price(args.token)
    if price is None:
        print("❌ Cannot fetch price from DEXScreener. Aborting.")
        sys.exit(1)
    print(f"  Price: ${price}")

    # 3. Safety check via onchain-analyzer (full analysis, not just contract)
    analyzer_script = os.path.join(SKILLS_DIR, "onchain-analyzer", "scripts", "analyzer.py")
    safety_score = None
    if os.path.exists(analyzer_script):
        print("  Running safety analysis...")
        rc, output = _run_skill(analyzer_script, ["analyze", args.token])
        for line in output.split("\n"):
            if "Safety Score" in line and "/" in line:
                try:
                    # Parse "Safety Score: ✅ 80/100 — CONSIDER"
                    score_part = line.split("/")[0]  # "...80"
                    digits = "".join(c for c in score_part.split()[-1] if c.isdigit())
                    safety_score = int(digits)
                except (ValueError, IndexError):
                    pass
            elif "Score (contract only)" in line and "/" in line and safety_score is None:
                # Fallback: if full analyze fails, use contract-only score
                try:
                    parts = line.split(":")[-1].strip().split("/")
                    safety_score = int(parts[0])
                except (ValueError, IndexError):
                    pass
        if safety_score is not None:
            print(f"  Safety score: {safety_score}")
        else:
            print("  ⚠️ Could not determine safety score")

    # 4. Risk manager check
    risk_script = os.path.join(SKILLS_DIR, "risk-manager", "scripts", "risk_manager.py")
    if os.path.exists(risk_script):
        print("  Running risk check...")
        risk_args = ["check", "--amount", str(amount), "--token", args.token]
        if safety_score is not None:
            risk_args += ["--safety-score", str(safety_score)]
        rc, output = _run_skill(risk_script, risk_args)
        if rc != 0:
            print(f"\n🚫 TRADE BLOCKED by risk-manager:")
            for line in output.strip().split("\n"):
                if line.strip() and "JSON" not in line and not line.startswith("{") and not line.startswith("}"):
                    print(f"  {line.strip()}")
            sys.exit(1)
        print("  ✅ Risk check passed")

    # 5. Execute based on mode
    if mode == "real":
        # Real mode: execute via Jupiter
        jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
        if not os.path.exists(jupiter_script):
            print("\n❌ jupiter_swap.py not found. Install skills first.")
            sys.exit(1)

        print("\n  🚀 Executing on-chain via Jupiter...")
        rc, output = _run_skill(jupiter_script, [
            "buy", "--token", args.token, "--amount-sol", str(amount)
        ])
        print(output)

        # Parse result
        swap_result = {}
        if "---JSON---" in output:
            json_part = output.split("---JSON---")[-1].strip()
            try:
                swap_result = json.loads(json_part)
            except Exception:
                pass

        if swap_result.get("status") != "Success":
            print(f"\n❌ Jupiter swap failed: {swap_result.get('error', 'unknown')}")
            sys.exit(1)

        tx_signature = swap_result.get("signature", "")
    else:
        # Paper mode: just get a quote for logging
        tx_signature = None

    # 6. Log trade via journal
    journal_script = os.path.join(SKILLS_DIR, "trade-journal", "scripts", "journal.py")
    if os.path.exists(journal_script):
        journal_args = [
            "add",
            "--token", args.token_name or args.token[:12],
            "--address", args.token,
            "--amount", str(amount),
            "--price", str(price),
            "--reason", args.reason,
        ]
        if mode == "paper":
            journal_args.append("--paper")

        rc, output = _run_skill(journal_script, journal_args)
        print(f"\n{output.strip()}")

    if mode == "real" and tx_signature:
        print(f"\n  🔗 TX: https://solscan.io/tx/{tx_signature}")


def cmd_sell(args):
    """Close a position (sell)."""
    tcfg = load_trading_config()
    mode = _cfg(tcfg, "mode", default="paper")

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

    price = _get_price(trade["address"])
    if price is None:
        print("❌ Cannot fetch price.")
        sys.exit(1)

    pct = args.pct if hasattr(args, 'pct') else 100
    print(f"🔄 Processing SELL ({mode.upper()} mode)...\n")
    print(f"  Token: {trade['token']}")
    print(f"  Entry: ${trade['entry_price']} → Current: ${price}")
    print(f"  Sell: {pct}% of position")

    tx_signature = None

    if mode == "real":
        jupiter_script = os.path.join(SKILLS_DIR, "trade-executor", "scripts", "jupiter_swap.py")
        if os.path.exists(jupiter_script):
            print("\n  🚀 Executing sell on-chain via Jupiter...")
            rc, output = _run_skill(jupiter_script, [
                "sell", "--token", trade["address"], "--pct", str(pct)
            ])
            print(output)

            swap_result = {}
            if "---JSON---" in output:
                json_part = output.split("---JSON---")[-1].strip()
                try:
                    swap_result = json.loads(json_part)
                except Exception:
                    pass

            if swap_result.get("status") != "Success":
                print(f"\n❌ Jupiter sell failed: {swap_result.get('error', 'unknown')}")
                sys.exit(1)

            tx_signature = swap_result.get("signature", "")

    # Close via journal (full close if pct=100)
    if pct >= 100:
        journal_script = os.path.join(SKILLS_DIR, "trade-journal", "scripts", "journal.py")
        if os.path.exists(journal_script):
            rc, output = _run_skill(journal_script, [
                "close",
                "--id", str(args.id),
                "--exit-price", str(price),
                "--reason", args.reason,
            ])
            print(f"\n{output.strip()}")

    if tx_signature:
        print(f"\n  🔗 TX: https://solscan.io/tx/{tx_signature}")


def cmd_check_exits(args):
    """Check open positions for exit signals."""
    tcfg = load_trading_config()
    journal = _load_json(JOURNAL_PATH)
    open_trades = [t for t in journal.get("trades", []) if t["status"] == "open"]

    if not open_trades:
        print("📭 No open positions.")
        return

    sl_pct = _cfg(tcfg, "risk", "stop_loss_pct", default=-30)
    tp_pct = _cfg(tcfg, "risk", "take_profit_pct", default=100)
    trailing = _cfg(tcfg, "risk", "trailing_stop_pct", default=15)

    print(f"🔍 Checking {len(open_trades)} open positions...\n")
    print(f"  Stop loss: {sl_pct}% | Take profit: +{tp_pct}% | Trailing: {trailing}%\n")

    alerts = []

    for t in open_trades:
        addr = t.get("address", "")
        price = _get_price(addr) if addr else None

        if price is None:
            print(f"  #{t['id']} {t['token']}: ⚠️ Cannot fetch price")
            continue

        entry = float(t["entry_price"])
        pnl_pct = ((price - entry) / entry * 100) if entry > 0 else 0

        icon = "🟢" if pnl_pct >= 0 else "🔴"
        print(f"  #{t['id']} {t['token']}: ${entry:.8f} → ${price:.8f} ({pnl_pct:+.1f}%) {icon}")

        if pnl_pct <= sl_pct:
            alerts.append({"id": t["id"], "token": t["token"], "type": "STOP_LOSS", "pnl": pnl_pct})
            print(f"       🚨 STOP LOSS triggered ({pnl_pct:.1f}% <= {sl_pct}%)")

        elif pnl_pct >= tp_pct:
            trail = float(trailing)
            peak = float(t.get("peak_pnl_pct", 0))
            if pnl_pct > peak:
                peak = pnl_pct
            drop = peak - pnl_pct
            if trail > 0 and drop < trail:
                print(f"       🚀 ABOVE TP — trailing active (peak {peak:+.1f}%, drop {drop:.1f}%, trail at {trail}%)")
            else:
                alerts.append({"id": t["id"], "token": t["token"], "type": "TAKE_PROFIT", "pnl": pnl_pct})
                if trail > 0:
                    print(f"       📉 TRAILING STOP triggered ({pnl_pct:.1f}%, peak {peak:.1f}%, drop {drop:.1f}% >= {trail}%)")
                else:
                    print(f"       🎯 TAKE PROFIT target reached ({pnl_pct:.1f}% >= +{tp_pct}%)")

    if alerts:
        print(f"\n⚡ {len(alerts)} exit signal(s):")
        for a in alerts:
            print(f"  {a['type']}: #{a['id']} {a['token']} ({a['pnl']:+.1f}%)")
        print("\n  Auto-sell: python3 executor.py sell --id <N> --reason 'stop loss'")
    else:
        print("\n  ✅ No exit signals.")


def cmd_portfolio(args):
    """Show current holdings with live prices."""
    tcfg = load_trading_config()
    journal = _load_json(JOURNAL_PATH)
    open_trades = [t for t in journal.get("trades", []) if t["status"] == "open"]

    # Wallet balance
    balance = _get_wallet_balance()
    mode = _cfg(tcfg, "mode", default="paper")

    if not open_trades and balance <= 0:
        print("📭 No open positions and no wallet balance.")
        return

    print(f"📊 PORTFOLIO ({len(open_trades)} positions) — {mode.upper()} mode\n")

    if balance > 0:
        print(f"  💰 Wallet: {balance:.6f} SOL")
        pct = _cfg(tcfg, "position_sizing", "position_pct", default=5.0)
        min_w = _cfg(tcfg, "position_sizing", "min_wallet_balance", default=0.05)
        avail = max(0, balance - min_w)
        max_t = _cfg(tcfg, "position_sizing", "max_trade_sol", default=0.15)
        auto = min(max_t, avail * (pct / 100))
        print(f"  📐 Next trade size: {auto:.4f} SOL ({pct}% of available)")
        print()

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
            print(f"  {paper} #{t['id']} {t['token']:<12} {amount:.4f} SOL  ${entry:.8f} → ${price:.8f}  {pnl_pct:+.1f}% {icon}")
        else:
            total_value += amount
            print(f"  {paper} #{t['id']} {t['token']:<12} {amount:.4f} SOL  ${entry:.8f} → ???  ⚠️")

    if open_trades:
        unrealized_pnl = total_value - total_invested
        pnl_pct_total = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
        print(f"\n  Invested: {total_invested:.4f} SOL")
        print(f"  Value:    {total_value:.4f} SOL")
        print(f"  P&L:      {unrealized_pnl:+.4f} SOL ({pnl_pct_total:+.1f}%)")


def cmd_mode(args):
    """View or set trading mode."""
    tcfg = load_trading_config()
    current = _cfg(tcfg, "mode", default="paper")

    if args.new_mode:
        if args.new_mode not in ("paper", "real"):
            print("❌ Mode must be 'paper' or 'real'")
            sys.exit(1)

        if not os.path.exists(TRADING_CONFIG_PATH):
            print(f"❌ Config not found: {TRADING_CONFIG_PATH}")
            sys.exit(1)

        # Read and replace mode line
        with open(TRADING_CONFIG_PATH) as f:
            content = f.read()

        import re
        new_content = re.sub(
            r'^mode:\s*\w+',
            f'mode: {args.new_mode}',
            content,
            count=1,
            flags=re.MULTILINE,
        )

        with open(TRADING_CONFIG_PATH, "w") as f:
            f.write(new_content)

        print(f"  Mode: {current.upper()} → {args.new_mode.upper()}")
        if args.new_mode == "real":
            print("  ⚠️ REAL MODE — trades will execute on-chain via Jupiter!")
            print("  Make sure wallet has SOL and keypair is set.")
    else:
        print(f"  Current mode: {current.upper()}")
        print(f"  Config: {TRADING_CONFIG_PATH}")


def cmd_config_propose(args):
    """Propose a config change (for agent use — logs intent, requires approval)."""
    tcfg = load_trading_config()
    now = datetime.now(timezone.utc).isoformat()

    proposal = {
        "timestamp": now,
        "key": args.key,
        "proposed_value": args.value,
        "reason": args.reason,
        "status": "pending",
    }

    # Log to proposals file
    proposals_path = os.path.expanduser("~/.hermes/memories/config-proposals.json")
    proposals = _load_json(proposals_path) or {"proposals": []}
    proposals["proposals"].append(proposal)
    _save_json(proposals_path, proposals)

    print(f"📋 CONFIG CHANGE PROPOSAL")
    print(f"  Key:    {args.key}")
    print(f"  Value:  {args.value}")
    print(f"  Reason: {args.reason}")
    print(f"  Status: PENDING — send to Damian for approval via Telegram")
    print(f"\n  To approve: python3 executor.py config-apply --index {len(proposals['proposals'])-1}")


def cmd_config_apply(args):
    """Apply a pending config proposal."""
    proposals_path = os.path.expanduser("~/.hermes/memories/config-proposals.json")
    proposals = _load_json(proposals_path) or {"proposals": []}

    if args.index >= len(proposals["proposals"]):
        print(f"❌ Proposal #{args.index} not found")
        sys.exit(1)

    p = proposals["proposals"][args.index]
    if p.get("status") != "pending":
        print(f"⚠️ Proposal already {p.get('status')}")
        return

    key = p["key"]
    value = p["proposed_value"]

    if not os.path.exists(TRADING_CONFIG_PATH):
        print(f"❌ Config not found: {TRADING_CONFIG_PATH}")
        sys.exit(1)

    # Simple regex replace in YAML
    import re
    with open(TRADING_CONFIG_PATH) as f:
        content = f.read()

    # Match "  key: value" or "key: value"
    pattern = rf'^(\s*){re.escape(key)}:\s*.+$'
    replacement = rf'\g<1>{key}: {value}'
    new_content, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)

    if count == 0:
        print(f"❌ Key '{key}' not found in config")
        p["status"] = "failed"
    else:
        with open(TRADING_CONFIG_PATH, "w") as f:
            f.write(new_content)
        p["status"] = "applied"
        p["applied_at"] = datetime.now(timezone.utc).isoformat()
        print(f"✅ Applied: {key} = {value}")
        print(f"  Reason: {p['reason']}")

    _save_json(proposals_path, proposals)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Trade Executor — Buy & sell on Solana via Jupiter")
    sub = parser.add_subparsers(dest="command", required=True)

    # buy
    p_buy = sub.add_parser("buy", help="Buy a token")
    p_buy.add_argument("--token", required=True, help="Token mint address")
    p_buy.add_argument("--token-name", default=None, help="Token name/symbol")
    p_buy.add_argument("--amount", type=float, default=None, help="Amount in SOL (auto-sized if omitted)")
    p_buy.add_argument("--reason", required=True, help="Buy reason")
    p_buy.set_defaults(func=cmd_buy)

    # sell
    p_sell = sub.add_parser("sell", help="Sell / close position")
    p_sell.add_argument("--id", type=int, required=True, help="Trade ID")
    p_sell.add_argument("--pct", type=float, default=100, help="Percent to sell (default: 100)")
    p_sell.add_argument("--reason", default="Manual sell", help="Sell reason")
    p_sell.set_defaults(func=cmd_sell)

    # check-exits
    p_exits = sub.add_parser("check-exits", help="Check exit signals")
    p_exits.set_defaults(func=cmd_check_exits)

    # portfolio
    p_port = sub.add_parser("portfolio", help="Show holdings")
    p_port.set_defaults(func=cmd_portfolio)

    # mode
    p_mode = sub.add_parser("mode", help="View/set trading mode")
    p_mode.add_argument("new_mode", nargs="?", help="paper or real")
    p_mode.set_defaults(func=cmd_mode)

    # config-propose (for agent self-learning config changes)
    p_propose = sub.add_parser("config-propose", help="Propose config change")
    p_propose.add_argument("--key", required=True, help="Config key to change")
    p_propose.add_argument("--value", required=True, help="New value")
    p_propose.add_argument("--reason", required=True, help="Why this change")
    p_propose.set_defaults(func=cmd_config_propose)

    # config-apply
    p_apply = sub.add_parser("config-apply", help="Apply pending config proposal")
    p_apply.add_argument("--index", type=int, required=True, help="Proposal index")
    p_apply.set_defaults(func=cmd_config_apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
