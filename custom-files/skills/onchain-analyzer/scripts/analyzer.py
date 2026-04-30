#!/usr/bin/env python3
"""
OnChain Analyzer — Solana token security & analysis.

Usage:
    python3 analyzer.py analyze <address> [--full]
    python3 analyzer.py safety <address>
    python3 analyzer.py holders <address> [--top N]
    python3 analyzer.py liquidity <address>

Uses Solana RPC + DEXScreener. No paid API keys for basic analysis.
"""

import argparse
import base64
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_FILE = os.path.expanduser("~/.hermes/.env")


def _load_env_file():
    """Load ~/.hermes/.env into os.environ (only unset vars)."""
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
        from pathlib import Path
        config_path = Path.home() / ".hermes" / "memories" / "trading-config.yaml"
        if config_path.exists():
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
    return "https://api.mainnet-beta.solana.com"


# Maintain backward compatibility with existing global variable
SOLANA_RPC_URL = _get_solana_rpc_url()
DEXSCREENER_BASE = "https://api.dexscreener.com"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _http_get(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-onchain-analyzer/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def _solana_rpc(method: str, params: list) -> dict | None:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        SOLANA_RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "hermes-onchain-analyzer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return result.get("result")
    except Exception as e:
        print(f"RPC error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def get_token_account_info(address: str) -> dict | None:
    """Get token mint account info from Solana RPC."""
    result = _solana_rpc("getAccountInfo", [
        address,
        {"encoding": "jsonParsed"},
    ])
    if not result or not result.get("value"):
        return None
    return result["value"]


def get_token_supply(address: str) -> dict | None:
    """Get token supply."""
    return _solana_rpc("getTokenSupply", [address])


def get_token_largest_accounts(address: str) -> list | None:
    """Get largest token holders."""
    result = _solana_rpc("getTokenLargestAccounts", [address])
    if not result or not result.get("value"):
        return None
    return result["value"]


def get_dex_data(address: str) -> dict | None:
    """Get DEXScreener data for token."""
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{address}"
    data = _http_get(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    # Return the pair with highest liquidity
    pairs = sorted(data, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
    return pairs[0] if pairs else None


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def check_contract_safety(address: str) -> dict:
    """Check mint authority, freeze authority, upgrade authority."""
    info = get_token_account_info(address)
    result = {
        "mint_authority": "unknown",
        "freeze_authority": "unknown",
        "supply": "unknown",
        "decimals": "unknown",
        "is_initialized": False,
        "flags": [],
        "score": 0,
    }

    if not info:
        result["flags"].append("CANNOT_READ_ACCOUNT")
        return result

    data = info.get("data", {})
    if isinstance(data, dict) and data.get("parsed"):
        parsed = data["parsed"]
        mint_info = parsed.get("info", {})

        result["is_initialized"] = mint_info.get("isInitialized", False)
        result["decimals"] = mint_info.get("decimals", "unknown")
        result["supply"] = mint_info.get("supply", "unknown")

        # Mint authority
        mint_auth = mint_info.get("mintAuthority")
        if mint_auth is None or mint_auth == "":
            result["mint_authority"] = "revoked"
            result["score"] += 25
        else:
            result["mint_authority"] = mint_auth
            result["flags"].append("MINT_AUTHORITY_ACTIVE")

        # Freeze authority
        freeze_auth = mint_info.get("freezeAuthority")
        if freeze_auth is None or freeze_auth == "":
            result["freeze_authority"] = "none"
            result["score"] += 20
        else:
            result["freeze_authority"] = freeze_auth
            result["flags"].append("FREEZE_AUTHORITY_ACTIVE")
    else:
        result["flags"].append("CANNOT_PARSE_ACCOUNT")

    return result


def check_holders(address: str, top_n: int = 10) -> dict:
    """Analyze token holder distribution."""
    accounts = get_token_largest_accounts(address)
    supply_data = get_token_supply(address)

    result = {
        "top_holders": [],
        "top_concentration_pct": 0,
        "holder_count_estimate": 0,
        "flags": [],
        "score": 0,
    }

    if not accounts:
        result["flags"].append("CANNOT_READ_HOLDERS")
        return result

    total_supply = 0
    if supply_data and supply_data.get("value"):
        total_supply = float(supply_data["value"].get("amount", 0))

    top_total = 0
    for i, acc in enumerate(accounts[:top_n]):
        amount = float(acc.get("amount", 0))
        ui_amount = float(acc.get("uiAmount", 0) or 0)
        pct = (amount / total_supply * 100) if total_supply > 0 else 0
        top_total += pct

        result["top_holders"].append({
            "rank": i + 1,
            "address": acc.get("address", "unknown"),
            "amount": ui_amount,
            "pct": round(pct, 2),
        })

    result["top_concentration_pct"] = round(top_total, 2)

    # Score holder distribution
    if top_total < 40:
        result["score"] = 20
    elif top_total < 70:
        result["score"] = 10
        result["flags"].append("HIGH_CONCENTRATION")
    else:
        result["score"] = 0
        result["flags"].append("EXTREME_CONCENTRATION")

    return result


def check_liquidity(address: str) -> dict:
    """Check liquidity from DEXScreener."""
    dex = get_dex_data(address)
    result = {
        "liquidity_usd": 0,
        "dex": "unknown",
        "pair_address": "unknown",
        "pair_age_hours": 0,
        "volume_24h": 0,
        "txns_24h": {"buys": 0, "sells": 0},
        "flags": [],
        "score": 0,
    }

    if not dex:
        result["flags"].append("NO_DEX_DATA")
        return result

    liq = float(dex.get("liquidity", {}).get("usd", 0) or 0)
    result["liquidity_usd"] = liq
    result["dex"] = dex.get("dexId", "unknown")
    result["pair_address"] = dex.get("pairAddress", "unknown")
    result["volume_24h"] = float(dex.get("volume", {}).get("h24", 0) or 0)

    txns = dex.get("txns", {}).get("h24", {})
    result["txns_24h"] = {
        "buys": txns.get("buys", 0),
        "sells": txns.get("sells", 0),
    }

    # Pair age
    created = dex.get("pairCreatedAt")
    if created:
        try:
            age_ms = time.time() * 1000 - float(created)
            result["pair_age_hours"] = round(age_ms / 3600000, 1)
        except (ValueError, TypeError):
            pass

    # Score liquidity
    if liq >= 50000:
        result["score"] += 15
    elif liq >= 10000:
        result["score"] += 8
        result["flags"].append("LOW_LIQUIDITY")
    else:
        result["flags"].append("VERY_LOW_LIQUIDITY")

    # Score pair age
    age_h = result["pair_age_hours"]
    if age_h >= 24:
        result["score"] += 10
    elif age_h >= 1:
        result["score"] += 5
        result["flags"].append("NEW_PAIR")
    else:
        result["flags"].append("VERY_NEW_PAIR")

    return result


def get_dex_socials(address: str) -> dict:
    """Check if token has socials/website on DEXScreener."""
    dex = get_dex_data(address)
    result = {"has_website": False, "has_socials": False, "score": 0, "flags": []}

    if not dex:
        return result

    info = dex.get("info", {})
    websites = info.get("websites", [])
    socials = info.get("socials", [])

    result["has_website"] = len(websites) > 0
    result["has_socials"] = len(socials) > 0

    if result["has_website"] and result["has_socials"]:
        result["score"] = 10
    elif result["has_website"] or result["has_socials"]:
        result["score"] = 5
    else:
        result["flags"].append("NO_SOCIALS")

    return result


def calculate_safety_score(contract: dict, holders: dict, liquidity: dict, socials: dict) -> int:
    """Calculate overall safety score 0-100."""
    score = contract["score"] + holders["score"] + liquidity["score"] + socials["score"]
    return min(score, 100)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_analyze(args):
    """Full token analysis."""
    addr = args.address
    print(f"🔍 Analyzing {addr}...\n")

    contract = check_contract_safety(addr)
    holders = check_holders(addr)
    liquidity = check_liquidity(addr)
    socials = get_dex_socials(addr)
    score = calculate_safety_score(contract, holders, liquidity, socials)

    all_flags = contract["flags"] + holders["flags"] + liquidity["flags"] + socials["flags"]

    # Header
    dex = get_dex_data(addr)
    if dex:
        name = dex.get("baseToken", {}).get("name", "Unknown")
        symbol = dex.get("baseToken", {}).get("symbol", "???")
        price = dex.get("priceUsd", "?")
        mcap = dex.get("marketCap", 0)
        print(f"  Token: {name} ({symbol})")
        print(f"  Price: ${price}")
        print(f"  Market Cap: ${mcap:,.0f}" if mcap else "  Market Cap: unknown")
        print()

    # Safety score
    if score >= 70:
        icon = "✅"
        verdict = "CONSIDER"
    elif score >= 40:
        icon = "⚠️"
        verdict = "CAUTION"
    else:
        icon = "🚫"
        verdict = "AVOID"
    print(f"  Safety Score: {icon} {score}/100 — {verdict}")
    print()

    # Contract
    print("  📋 CONTRACT:")
    print(f"    Mint authority: {contract['mint_authority']}")
    print(f"    Freeze authority: {contract['freeze_authority']}")
    print(f"    Decimals: {contract['decimals']}")
    print()

    # Holders
    print("  👥 HOLDERS:")
    print(f"    Top 10 concentration: {holders['top_concentration_pct']}%")
    if args.full and holders["top_holders"]:
        for h in holders["top_holders"][:10]:
            whale = " 🐋" if h["pct"] > 10 else ""
            print(f"    #{h['rank']}: {h['address'][:16]}... — {h['pct']}%{whale}")
    print()

    # Liquidity
    print("  💧 LIQUIDITY:")
    print(f"    USD: ${liquidity['liquidity_usd']:,.0f}")
    print(f"    DEX: {liquidity['dex']}")
    print(f"    Volume 24h: ${liquidity['volume_24h']:,.0f}")
    print(f"    Txns 24h: {liquidity['txns_24h']['buys']}B / {liquidity['txns_24h']['sells']}S")
    print(f"    Pair age: {liquidity['pair_age_hours']}h")
    print()

    # Socials
    print("  🌐 SOCIALS:")
    print(f"    Website: {'✅' if socials['has_website'] else '❌'}")
    print(f"    Socials: {'✅' if socials['has_socials'] else '❌'}")
    print()

    # Flags
    if all_flags:
        print(f"  🚩 FLAGS: {', '.join(all_flags)}")
    else:
        print("  🚩 FLAGS: None — clean")
    print()

    # JSON output for piping
    print("---JSON---")
    print(json.dumps({
        "address": addr,
        "safety_score": score,
        "verdict": verdict,
        "flags": all_flags,
        "contract": contract,
        "holders_concentration": holders["top_concentration_pct"],
        "liquidity_usd": liquidity["liquidity_usd"],
        "pair_age_hours": liquidity["pair_age_hours"],
    }, indent=2))


def cmd_safety(args):
    """Quick safety check only."""
    addr = args.address
    print(f"🔐 Quick safety check: {addr[:16]}...\n")

    contract = check_contract_safety(addr)

    if not contract["flags"]:
        print("  ✅ SAFE — Mint revoked, no freeze authority")
    elif "MINT_AUTHORITY_ACTIVE" in contract["flags"] and "FREEZE_AUTHORITY_ACTIVE" in contract["flags"]:
        print("  🚫 DANGER — Both mint and freeze authority active!")
    elif contract["flags"]:
        print(f"  ⚠️ WARNING — {', '.join(contract['flags'])}")

    print(f"\n  Mint authority: {contract['mint_authority']}")
    print(f"  Freeze authority: {contract['freeze_authority']}")
    print(f"  Score (contract only): {contract['score']}/45")


def cmd_holders(args):
    """Top holder analysis."""
    addr = args.address
    print(f"👥 Top {args.top} holders for {addr[:16]}...\n")

    holders = check_holders(addr, args.top)

    if not holders["top_holders"]:
        print("  Could not fetch holder data.")
        return

    print(f"  Top {args.top} concentration: {holders['top_concentration_pct']}%\n")

    for h in holders["top_holders"]:
        whale = " 🐋" if h["pct"] > 10 else ""
        print(f"  #{h['rank']:>2}: {h['address'][:20]}...  {h['amount']:>16,.2f}  ({h['pct']:>5.1f}%){whale}")

    if holders["flags"]:
        print(f"\n  Flags: {', '.join(holders['flags'])}")


def cmd_liquidity(args):
    """Liquidity depth check."""
    addr = args.address
    print(f"💧 Liquidity for {addr[:16]}...\n")

    liq = check_liquidity(addr)

    if "NO_DEX_DATA" in liq["flags"]:
        print("  No DEX data found for this token.")
        return

    print(f"  Liquidity: ${liq['liquidity_usd']:,.0f}")
    print(f"  DEX: {liq['dex']}")
    print(f"  Pair: {liq['pair_address']}")
    print(f"  Volume 24h: ${liq['volume_24h']:,.0f}")
    print(f"  Txns 24h: {liq['txns_24h']['buys']}B / {liq['txns_24h']['sells']}S")
    print(f"  Age: {liq['pair_age_hours']} hours")

    if liq["flags"]:
        print(f"\n  Flags: {', '.join(liq['flags'])}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="OnChain Analyzer — Solana token security & analysis"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Full token analysis")
    p_analyze.add_argument("address", help="Token mint address")
    p_analyze.add_argument("--full", action="store_true", help="Include holder list")
    p_analyze.set_defaults(func=cmd_analyze)

    # safety
    p_safety = sub.add_parser("safety", help="Quick safety check")
    p_safety.add_argument("address", help="Token mint address")
    p_safety.set_defaults(func=cmd_safety)

    # holders
    p_holders = sub.add_parser("holders", help="Top holder analysis")
    p_holders.add_argument("address", help="Token mint address")
    p_holders.add_argument("--top", type=int, default=10, help="Number of top holders")
    p_holders.set_defaults(func=cmd_holders)

    # liquidity
    p_liq = sub.add_parser("liquidity", help="Liquidity depth check")
    p_liq.add_argument("address", help="Token mint address")
    p_liq.set_defaults(func=cmd_liquidity)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
