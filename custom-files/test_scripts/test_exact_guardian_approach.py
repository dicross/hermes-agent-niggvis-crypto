#!/usr/bin/env python3
import urllib.request
import json
import os

def _http_get(url: str, timeout: int = 5) -> dict | list | None:
    """HTTP GET request with JSON response - copied exactly from guardian.py"""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "hermes-guardian/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def _fetch_sol_price() -> float:
    """Get current SOL/USD price from Jupiter Price API - copied exactly from guardian.py"""
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
    price = _fetch_sol_price()
    print(f"SOL price using exact guardian approach: {price}")