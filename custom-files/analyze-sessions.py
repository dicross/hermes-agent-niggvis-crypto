#!/usr/bin/env python3
"""
Session Analyzer — Extract key info from Hermes cron/interactive sessions.

Usage:
    python3 analyze-sessions.py [sessions_dir] [-o report.md]
    python3 analyze-sessions.py ~/.hermes/sessions/
    python3 analyze-sessions.py ~/.hermes/sessions/ -o session-report.md
    python3 analyze-sessions.py   # defaults to current dir, stdout

Output: Markdown report with trades, blocks, errors, config changes, wallet.
With -o flag, saves to file (ready to git commit and share).
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
        "position_checks": [],
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
                token = (_extract(r"Token:\s+([A-Za-z0-9_]+)", content) or "?").strip()
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
                token = (_extract(r"Token:\s+([A-Za-z0-9_]+)", content) or "?").strip()
                pnl = _extract(r"P&L.*?([-+][\d.]+%)", content) or "?"
                result["sells"].append({"token": token, "pnl": pnl})

            # Guardian sells
            if "STOP LOSS" in content or "TRAILING STOP" in content or "TAKE PROFIT" in content:
                for line in content.split("\n"):
                    if any(kw in line for kw in ["STOP LOSS", "TRAILING", "TAKE PROFIT"]):
                        result["sells"].append({"token": "guardian", "reason": line.strip()[:100]})

            # Position checks (from check-exits / guardian cron)
            if "Checking" in content and "open positions" in content:
                # Extract each position line: #10 SCHIZO: $0.001 → $0.002 (+50.0%) 🟢
                for line in content.split("\n"):
                    pos_match = re.search(
                        r"#(\d+)\s+(\S+).*?([+-]?\d+\.\d+%)\s*([🟢🔴])",
                        line,
                    )
                    if pos_match:
                        result["position_checks"].append({
                            "id": pos_match.group(1),
                            "token": pos_match.group(2).rstrip(":"),
                            "pnl": pos_match.group(3),
                            "direction": "up" if "🟢" in line else "down",
                        })

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
                key = (_extract(r"Key:\s+([A-Za-z0-9_]+)", content) or "?").strip()
                val = (_extract(r"Value:\s+([A-Za-z0-9_.+-]+)", content) or "?").strip()
                reason = (_extract(r"Reason:\s+([^\n\\]+)", content) or "").strip()
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
    """Format analysis results as Markdown report."""
    lines = []

    # --- Header ---
    dates = set()
    for s in sessions:
        d = _extract(r"_(\d{8})_", s["file"])
        if d:
            dates.add(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
    date_range = ", ".join(sorted(dates)) if dates else "unknown"
    lines.append(f"# Session Analysis Report")
    lines.append(f"")
    lines.append(f"**Date**: {date_range}  ")
    lines.append(f"**Sessions**: {len(sessions)}  ")

    # --- Summary ---
    total_trades = sum(len(s["trades"]) for s in sessions)
    total_sells = sum(len(s["sells"]) for s in sessions)
    total_blocks = sum(len(s["blocks"]) for s in sessions)
    total_errors = sum(len(s["errors"]) for s in sessions)
    total_config = sum(len(s["config_changes"]) for s in sessions)
    silent_count = sum(1 for s in sessions if s["silent"])
    total_tc = sum(s["tool_calls"] for s in sessions)

    lines.append(f"**Tool calls**: {total_tc}  ")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Buys executed | {total_trades} |")
    lines.append(f"| Sells executed | {total_sells} |")
    lines.append(f"| Trades blocked | {total_blocks} |")
    lines.append(f"| Errors | {total_errors} |")
    lines.append(f"| Config changes | {total_config} |")
    lines.append(f"| Silent sessions | {silent_count} |")
    lines.append("")

    # --- Wallet balance ---
    balances = sorted(
        [(s["file"], s["wallet_balance"]) for s in sessions if s["wallet_balance"]],
        key=lambda x: _extract(r"_(\d{8}_\d{6})", x[0]) or "",  # Sort by timestamp
    )
    if balances:
        lines.append("## Wallet Balance")
        lines.append("")
        lines.append("| Time | Balance (SOL) |")
        lines.append("|------|---------------|")
        for fname, bal in balances:
            ts = _extract(r"_(\d{8}_\d{6})", fname) or "?"
            if len(ts) >= 15:
                ts_fmt = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
            else:
                ts_fmt = ts
            lines.append(f"| {ts_fmt} | {bal:.4f} |")
        if len(balances) >= 2:
            delta = balances[-1][1] - balances[0][1]
            lines.append(f"| **Delta** | **{delta:+.4f}** |")
        lines.append("")

    # --- Trades ---
    if total_trades:
        lines.append("## Trades Executed")
        lines.append("")
        lines.append("| Time | Token | Amount (SOL) | Price | Safety | Tx |")
        lines.append("|------|-------|-------------|-------|--------|-----|")
        for s in sessions:
            for t in s["trades"]:
                ts = _extract(r"_\d{8}_(\d{6})", s["file"]) or "?"
                if len(ts) >= 6:
                    ts_fmt = f"{ts[0:2]}:{ts[2:4]}"
                else:
                    ts_fmt = ts
                tok = t["token"].replace("\n", "").strip()
                sig_short = t["sig"][:12] + "..." if t["sig"] else "-"
                lines.append(f"| {ts_fmt} | {tok} | {t['amount']} | ${t['price']} | {t['safety']} | {sig_short} |")
        lines.append("")

    # --- Sells ---
    if total_sells:
        lines.append("## Sells Executed")
        lines.append("")
        for s in sessions:
            for sell in s["sells"]:
                ts = _extract(r"_\d{8}_(\d{6})", s["file"]) or "?"
                if "reason" in sell:
                    lines.append(f"- **{ts}** {sell['reason']}")
                else:
                    lines.append(f"- **{ts}** SELL {sell['token']} — P&L: {sell['pnl']}")
        lines.append("")

    # --- Position checks (latest snapshot) ---
    # Find the last session that has position check data
    all_checks = []
    for s in sessions:
        if s["position_checks"]:
            all_checks = s["position_checks"]  # Keep overwriting — last one wins
    if all_checks:
        lines.append("## Open Positions (last check)")
        lines.append("")
        lines.append("| # | Token | P&L | Direction |")
        lines.append("|---|-------|-----|-----------|")
        for pc in all_checks:
            arrow = "🟢" if pc["direction"] == "up" else "🔴"
            lines.append(f"| #{pc['id']} | {pc['token']} | {pc['pnl']} | {arrow} |")
        lines.append("")

    # --- Blocks ---
    if total_blocks:
        block_reasons = defaultdict(int)
        for s in sessions:
            for b in s["blocks"]:
                block_reasons[b] += 1
        lines.append("## Blocked Trades (grouped)")
        lines.append("")
        lines.append("| Reason | Count |")
        lines.append("|--------|-------|")
        for reason, count in sorted(block_reasons.items(), key=lambda x: -x[1]):
            lines.append(f"| {reason} | {count} |")
        lines.append("")

    # --- Errors ---
    if total_errors:
        lines.append("## Errors")
        lines.append("")
        for s in sessions:
            for e in s["errors"]:
                ts = _extract(r"_\d{8}_(\d{6})", s["file"]) or "?"
                lines.append(f"- **{ts}**: `{e[:150]}`")
        lines.append("")

    # --- Config changes ---
    if total_config:
        lines.append("## Config Changes")
        lines.append("")
        for s in sessions:
            for c in s["config_changes"]:
                ts = _extract(r"_\d{8}_(\d{6})", s["file"]) or "?"
                lines.append(f"- **{ts}**: {c}")
        lines.append("")

    # --- Agent notable responses ---
    notable = []
    for s in sessions:
        if s["last_response"] and not s["silent"] and len(s["last_response"]) > 80:
            ts = _extract(r"_\d{8}_(\d{6})", s["file"]) or "?"
            # Clean up the response — first 300 chars
            resp = s["last_response"][:300].replace("\n", " ").strip()
            notable.append((ts, s["type"], resp))
    if notable:
        lines.append("## Agent Responses (non-silent)")
        lines.append("")
        for ts, typ, resp in notable:
            lines.append(f"**{ts}** ({typ}):")
            lines.append(f"> {resp}")
            lines.append("")

    # --- Session list ---
    lines.append("## All Sessions")
    lines.append("")
    lines.append("| File | Type | Calls | Status |")
    lines.append("|------|------|-------|--------|")
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
        flag_str = ", ".join(flags) if flags else "clean"
        short_name = s["file"][:55]
        lines.append(f"| {short_name} | {s['type']} | {s['tool_calls']} | {flag_str} |")

    lines.append("")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Hermes session files")
    parser.add_argument("sessions_dir", nargs="?", default=".", help="Directory with session JSON files")
    parser.add_argument("-o", "--output", default=None, help="Save report to file (Markdown)")
    args = parser.parse_args()

    sessions_dir = os.path.expanduser(args.sessions_dir)

    files = sorted(
        os.path.join(sessions_dir, f)
        for f in os.listdir(sessions_dir)
        if f.startswith("session_") and f.endswith(".json")
    )

    if not files:
        print(f"No session files found in {sessions_dir}")
        sys.exit(1)

    sessions = [analyze_session(f) for f in files]
    report = format_report(sessions)

    if args.output:
        out_path = os.path.expanduser(args.output)
        with open(out_path, "w") as f:
            f.write(report)
        print(f"Report saved to {out_path} ({len(sessions)} sessions)")
    else:
        print(report)


if __name__ == "__main__":
    main()
