#!/usr/bin/env python3
"""
Crypto Scanner — Scan DEXScreener for new/trending Solana tokens.

Usage:
    python3 scanner.py scan [--min-liq N] [--min-vol N] [--max-age N] [--limit N] [--check-contract]
    python3 scanner.py trending [--limit N]
    python3 scanner.py search <query> [--min-liq N] [--min-vol N]
    python3 scanner.py metas

No external packages required — uses only Python standard library.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEXSCREENER_BASE = "https://api.dexscreener.com"
SOLANA_RPC_URL = os.environ.get(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)
CHAIN = "solana"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get(url: str, retries: int = 2) -> dict | list | None:
    """GET JSON from URL with retries on 429."""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            print(f"HTTP {e.code} for {url}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return None
    return None


def _solana_rpc(method: str, params: list) -> dict | None:
    """Call Solana JSON-RPC."""
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        SOLANA_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"RPC error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Contract checks (Solana RPC)
# ---------------------------------------------------------------------------


def check_token_authorities(mint_address: str) -> dict:
    """Check mint and freeze authority for a Solana SPL token."""
    result = {"mint_authority": "unknown", "freeze_authority": "unknown"}
    resp = _solana_rpc(
        "getAccountInfo",
        [mint_address, {"encoding": "jsonParsed"}],
    )
    if not resp or "result" not in resp:
        return result
    value = resp["result"].get("value")
    if not value:
        return result
    parsed = value.get("data", {}).get("parsed", {})
    info = parsed.get("info", {})
    mint_auth = info.get("mintAuthority")
    freeze_auth = info.get("freezeAuthority")
    result["mint_authority"] = "ACTIVE" if mint_auth else "revoked"
    result["freeze_authority"] = "ACTIVE" if freeze_auth else "revoked"
    return result


# ---------------------------------------------------------------------------
# DEXScreener API
# ---------------------------------------------------------------------------


def get_latest_profiles() -> list:
    """Get latest token profiles (may include all chains)."""
    data = _get(f"{DEXSCREENER_BASE}/token-profiles/latest/v1")
    if not data:
        return []
    if isinstance(data, list):
        return [p for p in data if p.get("chainId") == CHAIN]
    return []


def get_top_boosts() -> list:
    """Get tokens with most active boosts."""
    data = _get(f"{DEXSCREENER_BASE}/token-boosts/top/v1")
    if not data:
        return []
    if isinstance(data, list):
        return [p for p in data if p.get("chainId") == CHAIN]
    if isinstance(data, dict):
        items = data.get("data", data.get("tokens", []))
        if isinstance(items, list):
            return [p for p in items if p.get("chainId") == CHAIN]
    return []


def get_token_pairs(token_address: str) -> list:
    """Get all pools/pairs for a given token address on Solana."""
    data = _get(
        f"{DEXSCREENER_BASE}/token-pairs/v1/{CHAIN}/{token_address}"
    )
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("pairs", [])
    return []


def search_pairs(query: str) -> list:
    """Search for pairs matching a query string."""
    encoded = urllib.request.quote(query)
    data = _get(f"{DEXSCREENER_BASE}/latest/dex/search?q={encoded}")
    if not data:
        return []
    pairs = data.get("pairs", [])
    return [p for p in pairs if p.get("chainId") == CHAIN]


def get_trending_metas() -> list:
    """Get trending meta categories."""
    data = _get(f"{DEXSCREENER_BASE}/metas/trending/v1")
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Filtering & display
# ---------------------------------------------------------------------------


def _age_hours(pair: dict) -> float | None:
    """Calculate pair age in hours from pairCreatedAt (ms timestamp)."""
    created = pair.get("pairCreatedAt")
    if not created:
        return None
    try:
        created_sec = int(created) / 1000
        now = time.time()
        return (now - created_sec) / 3600
    except (ValueError, TypeError):
        return None


def _format_usd(val) -> str:
    """Format a number as USD string."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.0f}"
    except (ValueError, TypeError):
        return "N/A"


def _format_age(hours: float | None) -> str:
    if hours is None:
        return "N/A"
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def filter_pairs(
    pairs: list,
    min_liq: float = 5000,
    min_vol: float = 10000,
    max_age_hours: float = 24,
) -> list:
    """Filter pairs by liquidity, volume, and age."""
    filtered = []
    for p in pairs:
        liq = (p.get("liquidity") or {}).get("usd")
        vol = (p.get("volume") or {}).get("h24")
        age = _age_hours(p)

        if liq is not None and float(liq) < min_liq:
            continue
        if vol is not None and float(vol) < min_vol:
            continue
        if age is not None and max_age_hours > 0 and age > max_age_hours:
            continue

        filtered.append(p)

    # Sort by volume descending
    def vol_key(x):
        v = (x.get("volume") or {}).get("h24")
        return float(v) if v else 0

    filtered.sort(key=vol_key, reverse=True)
    return filtered


def print_pair(p: dict, idx: int, contract_info: dict | None = None):
    """Print a single pair in readable format."""
    base = p.get("baseToken", {})
    name = base.get("name", "???")
    symbol = base.get("symbol", "???")
    address = base.get("address", "???")
    price = p.get("priceUsd", "N/A")
    liq = (p.get("liquidity") or {}).get("usd")
    vol24 = (p.get("volume") or {}).get("h24")
    vol1h = (p.get("volume") or {}).get("h1")
    mc = p.get("marketCap")
    fdv = p.get("fdv")
    age = _age_hours(p)
    txns = p.get("txns", {})
    # Try h1, h6, h24 for buy/sell data
    buys, sells = 0, 0
    for period in ("h1", "h6", "h24"):
        tx = txns.get(period, {})
        if tx.get("buys") or tx.get("sells"):
            buys = tx.get("buys", 0)
            sells = tx.get("sells", 0)
            break

    url = p.get("url", "")
    socials = p.get("info", {}).get("socials", []) if p.get("info") else []
    social_str = ", ".join(
        f'{s.get("platform", "?")}: {s.get("handle", "?")}'
        for s in (socials or [])
    )

    print(f"\n{'='*60}")
    print(f"  #{idx} {name} ({symbol})")
    print(f"  Address: {address}")
    print(f"  Price: ${price}")
    print(f"  MC: {_format_usd(mc)} | FDV: {_format_usd(fdv)}")
    print(f"  Liquidity: {_format_usd(liq)}")
    print(f"  Volume 24h: {_format_usd(vol24)} | 1h: {_format_usd(vol1h)}")
    print(f"  Age: {_format_age(age)}")
    total_tx = buys + sells
    if total_tx > 0:
        buy_pct = buys / total_tx * 100
        print(f"  Txns: {buys} buys / {sells} sells ({buy_pct:.0f}% buy)")
    if social_str:
        print(f"  Socials: {social_str}")
    if url:
        print(f"  DEXScreener: {url}")

    if contract_info:
        mint = contract_info.get("mint_authority", "unknown")
        freeze = contract_info.get("freeze_authority", "unknown")
        mint_icon = "✅" if mint == "revoked" else "❌"
        freeze_icon = "✅" if freeze == "revoked" else "❌"
        print(f"  Contract: {mint_icon} mint: {mint} | {freeze_icon} freeze: {freeze}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_scan(args):
    """Scan for new tokens by fetching latest profiles then their pair data."""
    print(f"🔍 Scanning Solana for new tokens...")
    print(
        f"   Filters: liq ≥ {_format_usd(args.min_liq)}, "
        f"vol ≥ {_format_usd(args.min_vol)}, "
        f"age ≤ {args.max_age}h"
    )

    # Step 1: Get latest token profiles on Solana
    profiles = get_latest_profiles()
    if not profiles:
        print("No profiles found. Trying search fallback...")
        # Fallback: search for recent Solana tokens
        profiles_fallback = search_pairs("SOL")
        pairs = filter_pairs(
            profiles_fallback, args.min_liq, args.min_vol, args.max_age
        )
    else:
        # Step 2: For each profile, get pair data
        all_pairs = []
        seen_addresses = set()
        for prof in profiles[:50]:  # Limit to avoid rate limits
            addr = prof.get("tokenAddress", "")
            if not addr or addr in seen_addresses:
                continue
            seen_addresses.add(addr)
            token_pairs = get_token_pairs(addr)
            all_pairs.extend(token_pairs)
            time.sleep(0.2)  # Rate limit courtesy

        pairs = filter_pairs(all_pairs, args.min_liq, args.min_vol, args.max_age)

    if not pairs:
        print("\n⚠ No tokens found matching filters. Try lowering thresholds.")
        return

    print(f"\n✅ Found {len(pairs)} tokens matching filters")

    for i, p in enumerate(pairs[: args.limit], 1):
        contract_info = None
        if args.check_contract:
            addr = p.get("baseToken", {}).get("address", "")
            if addr:
                contract_info = check_token_authorities(addr)
                time.sleep(0.3)  # RPC rate limit
        print_pair(p, i, contract_info)

    print(f"\n{'='*60}")
    print(f"  Total: {len(pairs)} tokens | Shown: {min(len(pairs), args.limit)}")
    print(f"  Scan time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


def cmd_trending(args):
    """Show tokens with most active boosts (trending on DEXScreener)."""
    print("🔥 Trending tokens (top boosts) on Solana...")

    boosts = get_top_boosts()
    if not boosts:
        print("No boosted tokens found.")
        return

    # Get pair data for each boosted token
    for i, b in enumerate(boosts[: args.limit], 1):
        addr = b.get("tokenAddress", "")
        if not addr:
            continue
        pairs = get_token_pairs(addr)
        if pairs:
            # Pick the pair with highest liquidity
            pairs.sort(
                key=lambda x: float((x.get("liquidity") or {}).get("usd", 0) or 0),
                reverse=True,
            )
            print_pair(pairs[0], i)
            boost_amount = b.get("totalAmount", b.get("amount", "?"))
            print(f"  Boost: {boost_amount}")
        else:
            print(f"\n  #{i} {addr} (no pair data)")
        time.sleep(0.25)

    print(f"\n  Total boosted Solana tokens: {len(boosts)}")


def cmd_search(args):
    """Search for pairs matching a query."""
    print(f'🔎 Searching Solana pairs for "{args.query}"...')

    pairs = search_pairs(args.query)
    filtered = filter_pairs(pairs, args.min_liq, args.min_vol, max_age_hours=0)

    if not filtered:
        print(f"\n⚠ No Solana pairs found for '{args.query}' with given filters.")
        return

    print(f"\n✅ Found {len(filtered)} matching pairs")
    for i, p in enumerate(filtered[: args.limit], 1):
        print_pair(p, i)


def cmd_metas(args):
    """Show trending meta categories."""
    print("📊 Trending metas (categories/narratives)...\n")

    metas = get_trending_metas()
    if not metas:
        print("No trending metas found.")
        return

    for i, m in enumerate(metas[:20], 1):
        name = m.get("name", "?")
        slug = m.get("slug", "?")
        mc = m.get("marketCap")
        vol = m.get("volume")
        liq = m.get("liquidity")
        count = m.get("tokenCount", 0)
        icon = m.get("icon", {})
        icon_str = icon.get("value", "") if isinstance(icon, dict) else ""
        change = m.get("marketCapChange", {})
        h24_change = change.get("h24")

        change_str = ""
        if h24_change is not None:
            sign = "+" if h24_change >= 0 else ""
            change_str = f" ({sign}{h24_change:.1f}% 24h)"

        print(
            f"  {icon_str} {name} ({slug}) — "
            f"MC: {_format_usd(mc)}{change_str} | "
            f"Vol: {_format_usd(vol)} | "
            f"Liq: {_format_usd(liq)} | "
            f"{count} tokens"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Crypto Scanner — Scan DEXScreener for Solana tokens"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Scan for new tokens")
    p_scan.add_argument("--min-liq", type=float, default=5000, help="Min liquidity USD")
    p_scan.add_argument("--min-vol", type=float, default=10000, help="Min volume 24h USD")
    p_scan.add_argument("--max-age", type=float, default=24, help="Max pair age in hours")
    p_scan.add_argument("--limit", type=int, default=20, help="Max results")
    p_scan.add_argument(
        "--check-contract", action="store_true", help="Check mint/freeze via Solana RPC"
    )
    p_scan.set_defaults(func=cmd_scan)

    # trending
    p_trend = sub.add_parser("trending", help="Trending tokens (top boosts)")
    p_trend.add_argument("--limit", type=int, default=10, help="Max results")
    p_trend.set_defaults(func=cmd_trending)

    # search
    p_search = sub.add_parser("search", help="Search for pairs by query")
    p_search.add_argument("query", help="Search query (token name, symbol, etc.)")
    p_search.add_argument("--min-liq", type=float, default=5000, help="Min liquidity USD")
    p_search.add_argument("--min-vol", type=float, default=0, help="Min volume 24h USD")
    p_search.add_argument("--limit", type=int, default=20, help="Max results")
    p_search.set_defaults(func=cmd_search)

    # metas
    p_metas = sub.add_parser("metas", help="Trending meta categories")
    p_metas.set_defaults(func=cmd_metas)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
