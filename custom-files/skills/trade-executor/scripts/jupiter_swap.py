#!/usr/bin/env python3
"""
Jupiter Swap — On-chain execution via Jupiter V2 Meta-Aggregator.

Usage:
    python3 jupiter_swap.py buy  --token <mint> --amount-sol 0.05
    python3 jupiter_swap.py sell --token <mint> [--pct 100]
    python3 jupiter_swap.py quote --input <mint> --output <mint> --amount <raw>
    python3 jupiter_swap.py balance [--token <mint>]
    python3 jupiter_swap.py wallet

Flow: GET /swap/v2/order → sign → POST /swap/v2/execute
Requires: solders package (pip install solders)

Config: ~/.hermes/memories/trading-config.yaml
Keypair: ~/.hermes/secrets/trading-wallet.json
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Auto-reexec with venv python if solders not available
# ---------------------------------------------------------------------------

def _ensure_solders():
    """If solders is not importable, re-exec with python_bin from config."""
    try:
        import importlib
        importlib.import_module("solders")
        return  # solders available, all good
    except ImportError:
        pass
    # Try to find python_bin from trading-config.yaml
    config_path = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
    python_bin = None
    if os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("python_bin:"):
                    val = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                    python_bin = os.path.expanduser(val)
                    break
    if python_bin and os.path.exists(python_bin) and python_bin != sys.executable:
        os.execv(python_bin, [python_bin] + sys.argv)
    # If we get here, solders truly not available — scripts will fail on import later

_ensure_solders()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_DECIMALS = 9
JUPITER_BASE = "https://api.jup.ag/swap/v2"
SOLANA_RPC_DEFAULT = "https://api.mainnet-beta.solana.com"

CONFIG_PATH = os.path.expanduser("~/.hermes/memories/trading-config.yaml")
KEYPAIR_DEFAULT = os.path.expanduser("~/.hermes/secrets/trading-wallet.json")
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

# ---------------------------------------------------------------------------
# Config loader (minimal YAML parser — avoids external dependency)
# ---------------------------------------------------------------------------


def _parse_yaml_flat(path: str) -> dict:
    """Parse a simple YAML file into nested dict. Handles basic indented keys."""
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

            # Remove quotes
            if val and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]

            # Pop stack to correct indent level
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()

            parent = stack[-1][1]

            if val == "" or val == "[]":
                # Nested dict or empty list
                if val == "[]":
                    parent[key] = []
                else:
                    child = {}
                    parent[key] = child
                    stack.append((indent, child))
            else:
                # Convert types
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.lower() == "null" or val.lower() == "none":
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


def load_config() -> dict:
    """Load trading config with defaults."""
    cfg = _parse_yaml_flat(CONFIG_PATH)
    return cfg


def get_cfg(cfg: dict, *keys, default=None):
    """Nested dict get: get_cfg(cfg, 'jupiter', 'slippage_bps', default=1500)"""
    d = cfg
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
        if d is None:
            return default
    return d


# ---------------------------------------------------------------------------
# Wallet / Keypair
# ---------------------------------------------------------------------------


def _load_keypair_bytes(path: str) -> bytes:
    """Load keypair from JSON array file (Solana CLI format)."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print(f"❌ Keypair not found: {expanded}")
        print("  Create one: solana-keygen new --outfile ~/.hermes/secrets/trading-wallet.json")
        sys.exit(1)

    with open(expanded) as f:
        data = json.load(f)

    if isinstance(data, list):
        return bytes(data)
    elif isinstance(data, str):
        # base58 encoded
        try:
            from solders.keypair import Keypair as SoldersKeypair
            kp = SoldersKeypair.from_base58_string(data)
            return bytes(kp)
        except Exception:
            print("❌ Unsupported keypair format")
            sys.exit(1)
    else:
        print("❌ Unsupported keypair format (expected JSON array)")
        sys.exit(1)


def load_keypair():
    """Load keypair, return (Keypair, pubkey_str)."""
    try:
        from solders.keypair import Keypair as SoldersKeypair
    except ImportError:
        print("❌ solders not installed. Run: pip install solders")
        sys.exit(1)

    cfg = load_config()
    path = get_cfg(cfg, "wallet", "keypair_path", default=KEYPAIR_DEFAULT)
    raw = _load_keypair_bytes(path)
    kp = SoldersKeypair.from_bytes(raw)
    return kp, str(kp.pubkey())


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _http_get(url: str, headers: dict | None = None) -> dict | list | None:
    hdrs = {"Accept": "application/json", "User-Agent": "hermes-jupiter/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body[:500]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return None


def _http_post(url: str, data: dict, headers: dict | None = None) -> dict | None:
    hdrs = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "hermes-jupiter/1.0",
    }
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body[:500]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return None


def _rpc_call(method: str, params: list, rpc_url: str | None = None) -> dict | None:
    """Solana JSON-RPC call with fallback mechanism."""
    # Determine RPC URL with fallback priority:
    # 1. Explicit parameter
    # 2. HELIUS_API_KEY env → construct Helius URL
    # 3. SOLANA_RPC_URL env (direct override)
    # 4. wallet.rpc_url from config (with env interpolation)
    # 5. Hardcoded public default
    if rpc_url is not None:
        url = rpc_url
    else:
        helius_key = os.environ.get("HELIUS_API_KEY")
        env_rpc = os.environ.get("SOLANA_RPC_URL")
        if helius_key:
            url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
        elif env_rpc:
            url = env_rpc
        else:
            cfg = load_config()
            configured_rpc = get_cfg(cfg, "wallet", "rpc_url", default=None)
            if configured_rpc and isinstance(configured_rpc, str):
                url = os.path.expandvars(configured_rpc)
            else:
                url = SOLANA_RPC_DEFAULT

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return _http_post(url, payload)


# ---------------------------------------------------------------------------
# Wallet queries
# ---------------------------------------------------------------------------


def get_sol_balance(pubkey: str) -> float:
    """Get SOL balance in SOL (not lamports)."""
    resp = _rpc_call("getBalance", [pubkey, {"commitment": "confirmed"}])
    if resp and "result" in resp:
        lamports = resp["result"]["value"]
        return lamports / 10**SOL_DECIMALS
    return 0.0


def get_token_balance(pubkey: str, mint: str) -> tuple[float, int, str]:
    """Get SPL token balance. Returns (ui_amount, raw_amount, token_account)."""
    resp = _rpc_call("getTokenAccountsByOwner", [
        pubkey,
        {"mint": mint},
        {"encoding": "jsonParsed", "commitment": "confirmed"},
    ])
    if not resp or "result" not in resp:
        return 0.0, 0, ""

    accounts = resp["result"]["value"]
    if not accounts:
        return 0.0, 0, ""

    # Sum all token accounts for this mint
    total_ui = 0.0
    total_raw = 0
    first_account = ""
    for acc in accounts:
        info = acc["account"]["data"]["parsed"]["info"]
        amount_info = info["tokenAmount"]
        total_ui += float(amount_info.get("uiAmount") or 0)
        total_raw += int(amount_info["amount"])
        if not first_account:
            first_account = acc["pubkey"]

    return total_ui, total_raw, first_account


# ---------------------------------------------------------------------------
# Jupiter API
# ---------------------------------------------------------------------------


def jupiter_order(
    input_mint: str,
    output_mint: str,
    amount: int,
    taker: str,
    slippage_bps: int = 1500,
    api_key: str | None = None,
) -> dict | None:
    """GET /swap/v2/order — get quote + assembled transaction."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "taker": taker,
    }
    # Only add slippage if we want manual mode (otherwise ultra mode with auto slippage)
    if slippage_bps:
        params["slippageBps"] = str(slippage_bps)

    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{JUPITER_BASE}/order?{qs}"

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    return _http_get(url, headers=headers)


def jupiter_execute(
    signed_tx_b64: str,
    request_id: str,
    api_key: str | None = None,
) -> dict | None:
    """POST /swap/v2/execute — submit signed transaction."""
    url = f"{JUPITER_BASE}/execute"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    return _http_post(url, {
        "signedTransaction": signed_tx_b64,
        "requestId": request_id,
    }, headers=headers)


def sign_transaction(tx_base64: str, keypair) -> str:
    """Sign a versioned transaction and return base64."""
    from solders.transaction import VersionedTransaction

    tx_bytes = base64.b64decode(tx_base64)
    tx = VersionedTransaction.from_bytes(tx_bytes)

    # Sign with our keypair
    tx = VersionedTransaction(tx.message, [keypair])

    signed_bytes = bytes(tx)
    return base64.b64encode(signed_bytes).decode()


# ---------------------------------------------------------------------------
# Jupiter Limit Order API
# ---------------------------------------------------------------------------


def jupiter_limit_order_quote(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    limit_price_usd: float,
    taker: str,
    api_key: str | None = None,
) -> dict | None:
    """
    Fetch a limit order quote from Jupiter.
    Note: Jupiter Limit Order API differs from Swap API.
    """
    # This is a conceptual implementation.
    # Actual Jupiter Limit Order API endpoint: https://api.jup.ag/limit/v1/quote
    url = "https://api.jup.ag/limit/v1/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_raw),
        "limitPrice": str(limit_price_usd),
        "taker": taker,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{qs}"

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    return _http_get(full_url, headers=headers)

def jupiter_limit_order_create(
    signed_tx_b64: str,
    api_key: str | None = None,
) -> dict | None:
    """
    Submit a signed limit order transaction to Jupiter.
    """
    url = "https://api.jup.ag/limit/v1/create"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    return _http_post(url, {"signedTransaction": signed_tx_b64}, headers=headers)

def jupiter_limit_order_cancel(
    order_id: str,
    api_key: str | None = None,
) -> dict | None:
    """
    Cancel a limit order by ID.
    """
    url = f"https://api.jup.ag/limit/v1/cancel?id={order_id}"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    return _http_get(url, headers=headers)


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------


def swap(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    dry_run: bool = False,
) -> dict:
    """
    Execute a swap. Returns result dict with status, signature, amounts.
    If dry_run=True, only gets quote without executing.
    """
    cfg = load_config()
    kp, pubkey = load_keypair()
    slippage = get_cfg(cfg, "jupiter", "slippage_bps", default=1500)
    api_key = os.environ.get("JUPITER_API_KEY")

    # Step 1: Get order (quote + transaction)
    print(f"  Fetching quote...")
    order = jupiter_order(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount_raw,
        taker=pubkey,
        slippage_bps=slippage,
        api_key=api_key,
    )

    if not order:
        return {"status": "Failed", "error": "Failed to get order from Jupiter"}

    in_amount = int(order.get("inAmount", 0))
    out_amount = int(order.get("outAmount", 0))
    router = order.get("router", "unknown")
    request_id = order.get("requestId", "")

    result = {
        "status": "Quoted",
        "inAmount": in_amount,
        "outAmount": out_amount,
        "router": router,
        "requestId": request_id,
    }

    print(f"  Quote: {in_amount} → {out_amount} (router: {router})")

    if dry_run or not order.get("transaction"):
        return result

    # Step 2: Sign
    print(f"  Signing transaction...")
    try:
        signed_b64 = sign_transaction(order["transaction"], kp)
    except Exception as e:
        return {"status": "Failed", "error": f"Signing failed: {e}"}

    # Step 3: Execute
    print(f"  Executing swap...")
    exec_result = jupiter_execute(signed_b64, request_id, api_key=api_key)

    if not exec_result:
        return {"status": "Failed", "error": "Execute request failed"}

    result["status"] = exec_result.get("status", "Unknown")
    result["signature"] = exec_result.get("signature", "")
    result["inputAmountResult"] = exec_result.get("inputAmountResult")
    result["outputAmountResult"] = exec_result.get("outputAmountResult")
    result["error_code"] = exec_result.get("code", 0)

    return result


def buy_token(token_mint: str, amount_sol: float, dry_run: bool = False) -> dict:
    """Buy token with SOL."""
    lamports = int(amount_sol * 10**SOL_DECIMALS)
    return swap(SOL_MINT, token_mint, lamports, dry_run=dry_run)


def sell_token(token_mint: str, pct: float = 100.0, dry_run: bool = False) -> dict:
    """Sell token for SOL. pct=100 means sell all."""
    kp, pubkey = load_keypair()
    ui_amount, raw_amount, _ = get_token_balance(pubkey, token_mint)

    if raw_amount == 0:
        return {"status": "Failed", "error": "No token balance found"}

    sell_amount = int(raw_amount * (pct / 100.0))
    if sell_amount <= 0:
        return {"status": "Failed", "error": "Sell amount is 0"}

    print(f"  Token balance: {ui_amount} (selling {pct}% = {sell_amount} raw)")
    return swap(token_mint, SOL_MINT, sell_amount, dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


def cmd_buy(args):
    cfg = load_config()
    mode = get_cfg(cfg, "mode", default="paper")
    dry_run = (mode == "paper") or args.dry_run

    kp, pubkey = load_keypair()

    # Position sizing
    if args.amount_sol:
        amount = args.amount_sol
    else:
        # Auto-size from config
        sol_balance = get_sol_balance(pubkey)
        pct = get_cfg(cfg, "position_sizing", "position_pct", default=5.0)
        min_trade = get_cfg(cfg, "position_sizing", "min_trade_sol", default=0.01)
        max_trade = get_cfg(cfg, "position_sizing", "max_trade_sol", default=0.15)
        min_wallet = get_cfg(cfg, "position_sizing", "min_wallet_balance", default=0.05)

        available = sol_balance - min_wallet
        amount = available * (pct / 100.0)
        amount = max(min_trade, min(max_trade, amount))

        if available <= min_trade:
            print(f"❌ Insufficient balance: {sol_balance:.4f} SOL (min wallet: {min_wallet})")
            sys.exit(1)

        print(f"  Auto-sized: {amount:.4f} SOL ({pct}% of {available:.4f} available)")

    action = "DRY RUN" if dry_run else "LIVE"
    print(f"🔄 BUY [{action}] — {amount:.4f} SOL → {args.token[:12]}...\n")

    result = buy_token(args.token, amount, dry_run=dry_run)

    if result["status"] == "Success":
        sig = result.get("signature", "")
        print(f"\n✅ Swap successful!")
        print(f"  Signature: {sig}")
        print(f"  https://solscan.io/tx/{sig}")
    elif result["status"] == "Quoted":
        out = result.get("outAmount", 0)
        print(f"\n📝 Quote (paper mode): would receive ~{out} raw tokens")
    else:
        print(f"\n❌ {result.get('error', 'Unknown error')}")

    # Output for executor integration
    print("\n---JSON---")
    print(json.dumps(result, indent=2, default=str))


def cmd_sell(args):
    cfg = load_config()
    mode = get_cfg(cfg, "mode", default="paper")
    dry_run = (mode == "paper") or args.dry_run

    action = "DRY RUN" if dry_run else "LIVE"
    print(f"🔄 SELL [{action}] — {args.pct}% of {args.token[:12]}...\n")

    result = sell_token(args.token, pct=args.pct, dry_run=dry_run)

    if result["status"] == "Success":
        sig = result.get("signature", "")
        print(f"\n✅ Swap successful!")
        print(f"  Signature: {sig}")
        print(f"  https://solscan.io/tx/{sig}")
    elif result["status"] == "Quoted":
        out = result.get("outAmount", 0)
        out_sol = out / 10**SOL_DECIMALS if out else 0
        print(f"\n📝 Quote (paper mode): would receive ~{out_sol:.6f} SOL")
    else:
        print(f"\n❌ {result.get('error', 'Unknown error')}")

    print("\n---JSON---")
    print(json.dumps(result, indent=2, default=str))


def cmd_quote(args):
    """Quote only, no execution."""
    kp, pubkey = load_keypair()
    cfg = load_config()
    slippage = get_cfg(cfg, "jupiter", "slippage_bps", default=1500)
    api_key = os.environ.get("JUPITER_API_KEY")

    order = jupiter_order(
        input_mint=args.input_mint,
        output_mint=args.output_mint,
        amount=int(args.amount),
        taker=pubkey,
        slippage_bps=slippage,
        api_key=api_key,
    )

    if not order:
        print("❌ Failed to get quote")
        sys.exit(1)

    in_amt = int(order.get("inAmount", 0))
    out_amt = int(order.get("outAmount", 0))
    router = order.get("router", "?")
    fee = order.get("platformFee", {})

    print(f"📊 QUOTE")
    print(f"  Input:  {in_amt} ({args.input_mint[:12]}...)")
    print(f"  Output: {out_amt} ({args.output_mint[:12]}...)")
    print(f"  Router: {router}")
    if fee:
        print(f"  Fee:    {fee.get('feeBps', '?')} bps ({fee.get('amount', '?')} {fee.get('feeMint', '')[:8]}...)")


def cmd_balance(args):
    """Show wallet balances."""
    kp, pubkey = load_keypair()

    sol = get_sol_balance(pubkey)
    print(f"💰 Wallet: {pubkey}")
    print(f"  SOL: {sol:.6f}")

    if args.token:
        ui, raw, acct = get_token_balance(pubkey, args.token)
        print(f"  Token ({args.token[:12]}...): {ui} (raw: {raw})")
        if acct:
            print(f"  Token account: {acct}")


def cmd_limit_sell(args):
    """
    Create a limit sell order (Hard SL).
    Usage: python3 jupiter_swap.py limit-sell --token <mint> --amount <raw> --price <usd>
    """
    cfg = load_config()
    kp, pubkey = load_keypair()
    api_key = os.environ.get("JUPITER_API_KEY")

    print(f"🔄 Creating Limit Sell: {args.token[:12]}... | Amount: {args.amount} | Price: ${args.price}")

    # 1. Get Quote
    quote = jupiter_limit_order_quote(
        input_mint=args.token,
        output_mint=SOL_MINT,
        amount_raw=int(args.amount),
        limit_price_usd=float(args.price),
        taker=pubkey,
        api_key=api_key
    )

    if not quote or "transaction" not in quote:
        print(f"❌ Failed to get limit order quote: {quote}")
        sys.exit(1)

    # 2. Sign
    try:
        signed_b64 = sign_transaction(quote["transaction"], kp)
    except Exception as e:
        print(f"❌ Signing failed: {e}")
        sys.exit(1)

    # 3. Create
    result = jupiter_limit_order_create(signed_b64, api_key=api_key)
    if result and "id" in result:
        print(f"✅ Limit Order Created! ID: {result['id']}")
        print(f"\n---JSON---\n{json.dumps(result, indent=2)}")
    else:
        print(f"❌ Failed to create limit order: {result}")
        sys.exit(1)

def cmd_limit_cancel(args):
    """
    Cancel a limit order.
    Usage: python3 jupiter_swap.py limit-cancel --id <order_id>
    """
    api_key = os.environ.get("JUPITER_API_KEY")
    result = jupiter_limit_order_cancel(args.id, api_key=api_key)
    if result:
        print(f"✅ Order {args.id} cancelled.")
    else:
        print(f"❌ Failed to cancel order {args.id}")
        sys.exit(1)

def cmd_wallet(args):
    """Show wallet info."""
    kp, pubkey = load_keypair()
    sol = get_sol_balance(pubkey)
    cfg = load_config()
    mode = get_cfg(cfg, "mode", default="paper")
    min_wallet = get_cfg(cfg, "position_sizing", "min_wallet_balance", default=0.05)
    max_trade = get_cfg(cfg, "position_sizing", "max_trade_sol", default=0.15)
    pos_pct = get_cfg(cfg, "position_sizing", "position_pct", default=5.0)

    available = max(0, sol - min_wallet)
    auto_size = min(max_trade, available * (pos_pct / 100.0))

    print(f"💰 WALLET")
    print(f"  Address:    {pubkey}")
    print(f"  Balance:    {sol:.6f} SOL")
    print(f"  Available:  {available:.6f} SOL (after {min_wallet} reserve)")
    print(f"  Auto-size:  {auto_size:.6f} SOL per trade ({pos_pct}%)")
    print(f"  Mode:       {mode.upper()}")
    print(f"  Solscan:    https://solscan.io/account/{pubkey}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Jupiter Swap — Solana on-chain execution")
    sub = parser.add_subparsers(dest="command", required=True)

    p_buy = sub.add_parser("buy", help="Buy token with SOL")
    p_buy.add_argument("--token", required=True, help="Token mint address")
    p_buy.add_argument("--amount-sol", type=float, default=None, help="SOL amount (auto-sized if omitted)")
    p_buy.add_argument("--dry-run", action="store_true", help="Quote only, don't execute")
    p_buy.set_defaults(func=cmd_buy)

    p_sell = sub.add_parser("sell", help="Sell token for SOL")
    p_sell.add_argument("--token", required=True, help="Token mint address")
    p_sell.add_argument("--pct", type=float, default=100.0, help="Percent to sell (default: 100)")
    p_sell.add_argument("--dry-run", action="store_true", help="Quote only")
    p_sell.set_defaults(func=cmd_sell)

    p_quote = sub.add_parser("quote", help="Get swap quote")
    p_quote.add_argument("--input-mint", required=True, help="Input token mint")
    p_quote.add_argument("--output-mint", required=True, help="Output token mint")
    p_quote.add_argument("--amount", required=True, help="Amount in smallest unit")
    p_quote.set_defaults(func=cmd_quote)

    p_bal = sub.add_parser("balance", help="Check balances")
    p_bal.add_argument("--token", default=None, help="Token mint to check")
    p_bal.set_defaults(func=cmd_balance)

    p_wallet = sub.add_parser("wallet", help="Wallet info + config")
    p_wallet.set_defaults(func=cmd_wallet)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
