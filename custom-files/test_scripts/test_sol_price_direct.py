#!/usr/bin/env python3
import urllib.request
import json

def test_sol_price():
    url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "hermes-guardian/1.0",
        })
        print(f"Making request to: {url}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"Response status: {resp.getcode()}")
            data = json.loads(resp.read().decode())
            print(f"Response data: {json.dumps(data, indent=2)}")
            sol_data = data.get("data", {}).get(
                "So11111111111111111111111111111111111111112", {}
            )
            print(f"SOL data: {sol_data}")
            price = sol_data.get("price")
            print(f"Price: {price}")
            if price:
                return float(price)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    return 0.0

if __name__ == "__main__":
    price = test_sol_price()
    print(f"SOL price: {price}")