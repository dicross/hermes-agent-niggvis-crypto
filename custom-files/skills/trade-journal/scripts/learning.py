#!/usr/bin/env python3
"""
Trade Learning Engine — Extract patterns from closed trades and update MEMORY.md.

Usage:
    python3 learning.py analyze [--days N]     # Analyze recent trades, print insights
    python3 learning.py update                  # Analyze + append to MEMORY.md
    python3 learning.py patterns                # Show discovered patterns

Reads from trade-journal.json, writes to MEMORY.md.
No LLM needed — pure statistical analysis.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JOURNAL_PATH = os.path.expanduser("~/.hermes/memories/trade-journal.json")
MEMORY_PATH = os.path.expanduser("~/.hermes/memories/MEMORY.md")
LEARNINGS_PATH = os.path.expanduser("~/.hermes/memories/trade-learnings.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _save_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_trades(days: int = 0) -> dict:
    """Analyze closed trades and extract patterns."""
    journal = _load_json(JOURNAL_PATH)
    trades = journal.get("trades", [])

    # Filter by days
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        trades = [
            t for t in trades
            if t.get("entry_time") and datetime.fromisoformat(t["entry_time"]) >= cutoff
        ]

    closed = [t for t in trades if t["status"] == "closed"]
    open_trades = [t for t in trades if t["status"] == "open"]

    if not closed:
        return {"total": 0, "insights": [], "patterns": []}

    wins = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_pct") or 0) <= 0]

    # Basic stats
    win_rate = len(wins) / len(closed) * 100
    avg_win = sum(t.get("pnl_pct", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("pnl_pct", 0) for t in losses) / len(losses) if losses else 0
    total_pnl = sum(t.get("pnl_sol", 0) for t in closed)

    # Hold time analysis
    hold_times_win = []
    hold_times_loss = []
    for t in closed:
        try:
            entry = datetime.fromisoformat(t["entry_time"])
            exit_dt = datetime.fromisoformat(t["exit_time"])
            hours = (exit_dt - entry).total_seconds() / 3600
            if (t.get("pnl_pct") or 0) > 0:
                hold_times_win.append(hours)
            else:
                hold_times_loss.append(hours)
        except Exception:
            pass

    avg_hold_win = sum(hold_times_win) / len(hold_times_win) if hold_times_win else 0
    avg_hold_loss = sum(hold_times_loss) / len(hold_times_loss) if hold_times_loss else 0

    # Entry reason analysis — which keywords correlate with wins/losses
    win_keywords = defaultdict(int)
    loss_keywords = defaultdict(int)
    keywords_to_track = [
        "trending", "safety", "liquidity", "boost", "volume",
        "mint", "freeze", "revoked", "clean", "socials",
        "website", "momentum", "smart money",
    ]

    for t in wins:
        reason = (t.get("entry_reason") or "").lower()
        for kw in keywords_to_track:
            if kw in reason:
                win_keywords[kw] += 1

    for t in losses:
        reason = (t.get("entry_reason") or "").lower()
        for kw in keywords_to_track:
            if kw in reason:
                loss_keywords[kw] += 1

    # Safety score analysis from entry reasons
    safety_scores_win = []
    safety_scores_loss = []
    for t in closed:
        reason = (t.get("entry_reason") or "").lower()
        # Extract safety score from reason like "safety 70" or "safety score 63"
        import re
        match = re.search(r'safety\s*(?:score\s*)?(\d+)', reason)
        if match:
            score = int(match.group(1))
            if (t.get("pnl_pct") or 0) > 0:
                safety_scores_win.append(score)
            else:
                safety_scores_loss.append(score)

    avg_safety_win = sum(safety_scores_win) / len(safety_scores_win) if safety_scores_win else 0
    avg_safety_loss = sum(safety_scores_loss) / len(safety_scores_loss) if safety_scores_loss else 0

    # Liquidity analysis from reasons
    liq_values_win = []
    liq_values_loss = []
    for t in closed:
        reason = (t.get("entry_reason") or "").lower()
        match = re.search(r'liquidity\s*(\d+\.?\d*)\s*k', reason)
        if match:
            liq = float(match.group(1))
            if (t.get("pnl_pct") or 0) > 0:
                liq_values_win.append(liq)
            else:
                liq_values_loss.append(liq)

    # Stop-loss effectiveness
    sl_exceeded = [t for t in losses if abs(t.get("pnl_pct", 0)) > 35]

    # Generate insights
    insights = []

    insights.append(f"Win rate: {win_rate:.0f}% ({len(wins)}W/{len(losses)}L)")
    insights.append(f"Avg win: {avg_win:+.1f}% | Avg loss: {avg_loss:+.1f}%")
    insights.append(f"Net P&L: {total_pnl:+.6f} SOL")

    if avg_hold_win > 0:
        insights.append(f"Avg hold (wins): {avg_hold_win:.1f}h | Avg hold (losses): {avg_hold_loss:.1f}h")

    if avg_safety_win > avg_safety_loss and avg_safety_win > 0:
        insights.append(f"Higher safety scores correlate with wins (avg {avg_safety_win:.0f} vs {avg_safety_loss:.0f})")

    if sl_exceeded:
        insights.append(f"⚠️ {len(sl_exceeded)} trades exceeded stop-loss limit — position monitor too slow")

    # Generate patterns (actionable rules)
    patterns = []

    if avg_safety_win >= 65 and avg_safety_loss < 65:
        patterns.append({
            "rule": f"Raise min safety score to {int(avg_safety_win)}",
            "evidence": f"Wins avg safety {avg_safety_win:.0f}, losses avg {avg_safety_loss:.0f}",
            "confidence": "medium",
        })

    if liq_values_win and liq_values_loss:
        avg_liq_win = sum(liq_values_win) / len(liq_values_win)
        avg_liq_loss = sum(liq_values_loss) / len(liq_values_loss)
        if avg_liq_win > avg_liq_loss * 1.5:
            patterns.append({
                "rule": f"Prefer tokens with liquidity >{avg_liq_win:.0f}K",
                "evidence": f"Wins avg liq {avg_liq_win:.0f}K, losses avg {avg_liq_loss:.0f}K",
                "confidence": "medium",
            })

    if sl_exceeded:
        patterns.append({
            "rule": "Use guardian.py --watch for real-time stop-loss (not hourly cron)",
            "evidence": f"{len(sl_exceeded)} trades lost more than -35% before hourly check",
            "confidence": "high",
        })

    if avg_hold_loss > 0 and avg_hold_loss < 2:
        patterns.append({
            "rule": "Short-lived losing positions suggest bad entry timing",
            "evidence": f"Avg losing trade lasts {avg_hold_loss:.1f}h",
            "confidence": "low",
        })

    # Win/loss by keyword correlation
    for kw in keywords_to_track:
        w = win_keywords.get(kw, 0)
        l = loss_keywords.get(kw, 0)
        if w + l >= 2:
            ratio = w / (w + l) * 100
            if ratio >= 70:
                patterns.append({
                    "rule": f"'{kw}' in entry reason correlates with wins ({ratio:.0f}%)",
                    "evidence": f"{w} wins, {l} losses when '{kw}' mentioned",
                    "confidence": "low" if w + l < 5 else "medium",
                })
            elif ratio <= 30:
                patterns.append({
                    "rule": f"AVOID tokens where '{kw}' is the main signal ({ratio:.0f}% win rate)",
                    "evidence": f"{w} wins, {l} losses",
                    "confidence": "low" if w + l < 5 else "medium",
                })

    return {
        "total": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_pnl_sol": total_pnl,
        "avg_safety_win": avg_safety_win,
        "avg_safety_loss": avg_safety_loss,
        "insights": insights,
        "patterns": patterns,
        "analyzed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_analyze(args):
    """Print analysis."""
    result = analyze_trades(days=args.days)

    if result["total"] == 0:
        print("No closed trades to analyze.")
        return

    period = f" (last {args.days} days)" if args.days else ""
    print(f"📊 TRADE ANALYSIS{period}\n")

    for insight in result["insights"]:
        print(f"  • {insight}")

    if result["patterns"]:
        print(f"\n🧠 DISCOVERED PATTERNS:\n")
        for p in result["patterns"]:
            conf = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p["confidence"], "⚪")
            print(f"  {conf} {p['rule']}")
            print(f"     Evidence: {p['evidence']}")
            print()

    # Save analysis
    _save_json(LEARNINGS_PATH, result)
    print(f"  Saved to {LEARNINGS_PATH}")


def cmd_update(args):
    """Analyze and append learnings to MEMORY.md."""
    result = analyze_trades(days=args.days)

    if result["total"] == 0:
        print("No closed trades to analyze.")
        return

    # Build the learning block
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"\n\n## Learned Patterns ({now}) — Auto-generated\n",
        f"\nBased on {result['total']} closed trades "
        f"({result['wins']}W/{result['losses']}L, {result['win_rate']:.0f}% win rate).\n",
    ]

    if result["insights"]:
        lines.append("\n### Insights\n")
        for insight in result["insights"]:
            lines.append(f"- {insight}\n")

    if result["patterns"]:
        lines.append("\n### Actionable Rules\n")
        for p in result["patterns"]:
            conf = p["confidence"].upper()
            lines.append(f"- [{conf}] {p['rule']}\n")
            lines.append(f"  - Evidence: {p['evidence']}\n")

    lines.append(f"\n_Last updated: {_now_iso()}_\n")

    block = "".join(lines)

    # Append to MEMORY.md
    if not os.path.exists(MEMORY_PATH):
        print(f"MEMORY.md not found at {MEMORY_PATH}")
        return

    # Check if we already wrote today's learnings
    with open(MEMORY_PATH, "r") as f:
        content = f.read()

    marker = f"## Learned Patterns ({now})"
    if marker in content:
        # Replace existing block for today
        start = content.index(marker)
        # Find next ## or end
        next_section = content.find("\n## ", start + len(marker))
        if next_section == -1:
            content = content[:start].rstrip() + block
        else:
            content = content[:start].rstrip() + block + content[next_section:]
        with open(MEMORY_PATH, "w") as f:
            f.write(content)
        print(f"♻️ Updated today's learnings in MEMORY.md")
    else:
        with open(MEMORY_PATH, "a") as f:
            f.write(block)
        print(f"📝 Appended learnings to MEMORY.md")

    # Also save JSON
    _save_json(LEARNINGS_PATH, result)
    print(f"   Saved analysis to {LEARNINGS_PATH}")

    # Print summary
    print(f"\n   Insights: {len(result['insights'])}")
    print(f"   Patterns: {len(result['patterns'])}")
    for p in result["patterns"]:
        print(f"   → {p['rule']}")


def cmd_patterns(args):
    """Show saved patterns."""
    data = _load_json(LEARNINGS_PATH)
    if not data or not data.get("patterns"):
        print("No patterns discovered yet. Run: learning.py analyze")
        return

    print(f"🧠 DISCOVERED PATTERNS (from {data.get('analyzed_at', '?')})\n")
    for p in data["patterns"]:
        conf = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p["confidence"], "⚪")
        print(f"  {conf} {p['rule']}")
        print(f"     {p['evidence']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Trade Learning Engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Analyze trades and show insights")
    p_analyze.add_argument("--days", type=int, default=0, help="Last N days (0=all)")
    p_analyze.set_defaults(func=cmd_analyze)

    p_update = sub.add_parser("update", help="Analyze + update MEMORY.md")
    p_update.add_argument("--days", type=int, default=0, help="Last N days (0=all)")
    p_update.set_defaults(func=cmd_update)

    p_patterns = sub.add_parser("patterns", help="Show discovered patterns")
    p_patterns.set_defaults(func=cmd_patterns)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
