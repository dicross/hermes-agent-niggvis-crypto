#!/usr/bin/env python3
# Exact copy of the working approach from guardian.py

import urllib.request
import json

def _http_get(url: str, timeout: int = 5):
    """HTTP GET request with JSON response - EXACT COPY FROM GUARDIAN.PY"""
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
    """Get current SOL/USD price from Jupiter Price API - EXACT COPY FROM GUARDIAN.PY"""
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
    print("Testing EXACT guardian.py approach...")
    price = _fetch_sol_price()
    print(f"SOL price: {price}")
    
    if price == 0.0:
        print("DEBUGGING: Let's see what _http_get returns...")
        url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
        data = _http_get(url)
        print(f"_http_get returned: {data}")
        print(f"Type: {type(data)}")
        if data:
            print(f"Is dict: {isinstance(data, dict)}")
            if isinstance(data, dict):
                print(f"Keys: {list(data.keys())}")
                if 'data' in data:
                    print(f"data['data']: {data['data']}")
                    print(f"Type of data['data']: {type(data['data'])}")
                    if isinstance(data['data'], dict):
                        sol_key = "So11111111111111111111111111111111111111112"
                        print(f"Looking for key '{sol_key}' in data['data']")
                        if sol_key in data['data']:
                            print(f"Found: {data['data'][sol_key]}")
                            price_inner = data['data'][sol_key].get('price')
                            print(f"Price inner: {price_inner}")
                        else:
                            print(f"Key '{sol_key}' NOT FOUND in data['data']")
                            print(f"Available keys: {list(data['data'].keys())}")