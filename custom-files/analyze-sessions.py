#!/usr/bin/env python3
"""
Session Analyzer — Extract key info from Hermes cron/interactive sessions.

Usage:
    python3 analyze-sessions.py [sessions_dir]
    python3 analyze-sessions.py ~/.hermes/sessions/
    python3 analyze-sessions.py   # defaults to current dir

Output: concise summary of trades, blocks, errors, config changes, wallet.
Copy-paste the output to your AI assistant for analysis.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def analyze_session(filepath: str) -> dict:
    """Analyze a single session file and return structured summary."""
    with open(filepath) as f:
        data = json.load(f)

    msgs = data.get("messages", [])
    result = {
        "file": os.path.basename(filepath),
        "type": "cron" if "cron_" in os.path.basename(filepath) else "interactive",
        "tool_calls": 0,
        "trades": [],
        "sells": [],
        "blocks": [],
        "errors": [],
        "config_changes": [],
        "portfolio": None,
        "wallet_balance": None,
        "silent": False,
        "last_response": "",
    }

    for m in msgs:
        role = m.get("role", "")
        content = str(m.get("content", ""))

        if role == "assistant":
            result["tool_calls"] += len(m.get("tool_calls", []))

            if content.strip():
                result["last_response"] = content

            if "[SILENT]" in content:
                result["silent"] = True

            # Check for direct config edits (forbidden)
            for tc in m.get("tool_calls", []):
                fn = tc.get("function", {}).get("name", "")
                args = str(tc.get("function", {}).get("arguments", ""))
                if fn in ("patch", "write_file") and "trading-config" in args:
                    result["config_changes"].append(
                        f"⚠️ DIRECT EDIT: {fn} on trading-config"
                    )
                if fn == "skill_manage":
                    result["config_changes"].append(
                        f"skill_manage: {args[:150]}"
                    )

        if role == "tool":
            # Successful trades
            if "Processing BUY" in content and "Swap successful" in content:
                token = _extract(r"Token:\s+(\S+)", content) or "?"
                amount = _extract(r"(?:Auto-sized|Manual size):\s+([\d.]+)\s+SOL", content) or "?"
                price = _extract(r"Price:\s+\$([\d.e-]+)", content) or "?"
                score = _extract(r"Safety score:\s+(\d+)", content) or "?"
                sig = _extract(r"Signature:\s+(\S+)", content) or ""
                result["trades"].append({
                    "token": token,
                    "amount": amount,
                    "price": price,
                    "safety": score,
                    "sig": sig[:20] + "..." if sig else "",
                })

            # Blocked trades
            if "BLOCKED" in content:
                reasons = []
                if "Already have open position" in content:
                    tid = _extract(r"trade #(\d+)", content) or "?"
                    reasons.append(f"duplicate (#{tid})")
                if "Safety score" in content and "< min" in content:
                    s = _extract(r"Safety score (\d+) < min (\d+)", content)
                    reasons.append(f"safety {s}" if s else "low safety")
                if "Open positions" in content and ">= max" in content:
                    reasons.append("max positions reached")
                if "Daily" in content and "loss" in content.lower():
                    reasons.append("daily loss limit")
                if not reasons:
                    reasons.append(_extract_between(content, "BLOCKED", "---JSON") or "unknown")
                result["blocks"].append(" + ".join(reasons))

            # Sells
            if "Processing SELL" in content:
                token = _extract(r"Token:\s+(\S+)", content) or "?"
                pnl = _extract(r"P&L.*?([-+][\d.]+%)", content) or "?"
                result["sells"].append({"token": token, "pnl": pnl})

            # Guardian sells
            if "STOP LOSS" in content or "TRAILING STOP" in content or "TAKE PROFIT" in content:
                for line in content.split("\n"):
                    if any(kw in line for kw in ["STOP LOSS", "TRAILING", "TAKE PROFIT"]):
                        result["sells"].append({"token": "guardian", "reason": line.strip()[:100]})

            # Portfolio / wallet
            if "Wallet:" in content:
                bal = _extract(r"Wallet:\s*([\d.]+)\s*SOL", content)
                if bal:
                    result["wallet_balance"] = float(bal)

            if "PORTFOLIO" in content:
                result["portfolio"] = content[:500]

            # Errors (excluding normal rate limits)
            if "Traceback" in content:
                result["errors"].append(content[:200])
            elif "Error" in content and "exit_code" in content:
                ec = _extract(r'"exit_code":\s*(\d+)', content)
                if ec and int(ec) != 0 and "HTTP Error 429" not in content:
                    result["errors"].append(content[:200])

            # Config proposals
            if "CONFIG CHANGE PROPOSAL" in content:
                key = _extract(r"Key:\s+(\S+)", content) or "?"
                val = _extract(r"Value:\s+(\S+)", content) or "?"
                reason = _extract(r"Reason:\s+(.+?)(?:\n|$)", content) or ""
                result["config_changes"].append(f"propose {key}={val}: {reason[:80]}")

    return result


def _extract(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _extract_between(text: str, start: str, end: str) -> str | None:
    s = text.find(start)
    e = text.find(end, s)
    if s >= 0 and e > s:
        return text[s + len(start):e].strip()[:100]
    return None


def format_report(sessions: list[dict]) -> str:
    """Format analysis results as concise report."""
    lines = []
    lines.append(f"=== SESSION ANALYSIS ({len(sessions)} sessions) ===\n")

    # Summary counts
    total_trades = sum(len(s["trades"]) for s in sessions)
    total_sells = sum(len(s["sells"]) for s in sessions)
    total_blocks = sum(len(s["blocks"]) for s in sessions)
    total_errors = sum(len(s["errors"]) for s in sessions)
    total_config = sum(len(s["config_changes"]) for s in sessions)
    silent_count = sum(1 for s in sessions if s["silent"])

    lines.append(f"TOTALS: {total_trades} buys | {total_sells} sells | {total_blocks} blocked | {total_errors} errors | {total_config} config changes | {silent_count} silent")
    lines.append("")

    # Wallet balance progression
    balances = [(s["file"], s["wallet_balance"]) for s in sessions if s["wallet_balance"]]
    if balances:
        lines.append("WALLET:")
        for fname, bal in balances:
            ts = _extract(r"_(\d{8}_\d{6})", fname) or fname[:20]
            lines.append(f"  {ts}: {bal:.4f} SOL")
        lines.append("")

    # All trades
    if total_trades:
        lines.append("TRADES:")
        for s in sessions:
            for t in s["trades"]:
                ts = _extract(r"_(\d{8}_\d{6})", s["file"]) or "?"
                lines.append(f"  {ts} BUY {t['token']} {t['amount']} SOL @ ${t['price']} (safety:{t['safety']}) {t['sig']}")
        lines.append("")

    # All sells
    if total_sells:
        lines.append("SELLS:")
        for s in sessions:
            for sell in s["sells"]:
                ts = _extract(r"_(\d{8}_\d{6})", s["file"]) or "?"
                if "reason" in sell:
                    lines.append(f"  {ts} {sell['reason']}")
                else:
                    lines.append(f"  {ts} SELL {sell['token']} P&L: {sell['pnl']}")
        lines.append("")

    # Blocking summary (grouped by reason)
    if total_blocks:
        block_reasons = defaultdict(int)
        for s in sessions:
            for b in s["blocks"]:
                block_reasons[b] += 1
        lines.append("BLOCKS (grouped):")
        for reason, count in sorted(block_reasons.items(), key=lambda x: -x[1]):
            lines.append(f"  {count}x {reason}")
        lines.append("")

    # Errors
    if total_errors:
        lines.append("ERRORS:")
        for s in sessions:
            for e in s["errors"]:
                ts = _extract(r"_(\d{8}_\d{6})", s["file"]) or "?"
                lines.append(f"  {ts}: {e[:150]}")
        lines.append("")

    # Config changes
    if total_config:
        lines.append("CONFIG CHANGES:")
        for s in sessions:
            for c in s["config_changes"]:
                ts = _extract(r"_(\d{8}_\d{6})", s["file"]) or "?"
                lines.append(f"  {ts}: {c}")
        lines.append("")

    # Session details (only non-silent, non-trivial)
    lines.append("SESSION DETAILS:")
    for s in sessions:
        flags = []
        if s["trades"]:
            flags.append(f"{len(s['trades'])} buy")
        if s["sells"]:
            flags.append(f"{len(s['sells'])} sell")
        if s["blocks"]:
            flags.append(f"{len(s['blocks'])} blocked")
        if s["errors"]:
            flags.append(f"{len(s['errors'])} err")
        if s["config_changes"]:
            flags.append(f"{len(s['config_changes'])} cfg")
        if s["silent"]:
            flags.append("SILENT")

        flag_str = " | ".join(flags) if flags else "clean"
        lines.append(f"  {s['file'][:55]:55} {s['type']:5} {s['tool_calls']:3}tc | {flag_str}")

    return "\n".join(lines)


def main():
    sessions_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    sessions_dir = os.path.expanduser(sessions_dir)

    files = sorted(
        os.path.join(sessions_dir, f)
        for f in os.listdir(sessions_dir)
        if f.startswith("session_") and f.endswith(".json")
    )

    if not files:
        print(f"No session files found in {sessions_dir}")
        sys.exit(1)

    sessions = [analyze_session(f) for f in files]
    print(format_report(sessions))


if __name__ == "__main__":
    main()
