#!/usr/bin/env python3
import urllib.request
import json

def _http_get(url: str, timeout: int = 5) -> dict | list | None:
    """HTTP GET request with JSON response."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-guardian/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def _fetch_prices_jupiter(addresses: list) -> dict:
    """Jupiter Price API v2: batch fetch. 600 RPM limit."""
    if not addresses:
        return {}
    ids = ",".join(addresses)
    url = f"https://api.jup.ag/price/v2?ids={ids}"
    print(f"Fetching from: {url}")
    data = _http_get(url)
    if not data or not isinstance(data, dict):
        print("No data or not dict")
        return {}
    prices = data.get("data", {})
    print(f"Prices data: {prices}")
    result = {}
    for addr in addresses:
        token_data = prices.get(addr, {})
        price = token_data.get("price")
        if price:
            result[addr] = {
                "price_usd": float(price),
                "market_cap": 0,
                "liquidity_usd": 0,
            }
            print(f"Found price for {addr}: {price}")
        else:
            print(f"No price for {addr} in token_data: {token_data}")
    return result

def _fetch_sol_price() -> float:
    """Get current SOL/USD price from Jupiter Price API."""
    url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
    data = _http_get(url)
    if data and isinstance(data, dict):
        sol_data = data.get("data", {}).get(
            "So11111111111111111111111111111111111111112", {}
        )
        price = sol_data.get("price")
        if price:
            return float(price)
    return 0.0

if __name__ == "__main__":
    print("=== Testing direct SOL price fetch ===")
    sol_price = _fetch_sol_price()
    print(f"Direct SOL price: {sol_price}")
    
    print("\n=== Testing batch fetch ===")
    batch_result = _fetch_prices_jupiter(['So11111111111111111111111111111111111111112'])
    print(f"Batch result: {batch_result}")
    
    if batch_result and 'So11111111111111111111111111111111111111112' in batch_result:
        sol_price_from_batch = batch_result['So11111111111111111111111111111111111111112']['price_usd']
        print(f"SOL price from batch: {sol_price_from_batch}")