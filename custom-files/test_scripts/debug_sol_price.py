#!/usr/bin/env python3
import urllib.request
import json

def debug_sol_price():
    url = "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112"
    print(f"Fetching from: {url}")
    
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "hermes-guardian/1.0",
        })
        print("Making request...")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"Response status: {resp.getcode()}")
            print(f"Response headers: {dict(resp.headers)}")
            data = resp.read().decode()
            print(f"Raw response: {data}")
            parsed_data = json.loads(data)
            print(f"Parsed data: {json.dumps(parsed_data, indent=2)}")
            
            # Try to extract SOL price
            sol_data = parsed_data.get("data", {}).get(
                "So11111111111111111111111111111111111111112", {}
            )
            print(f"SOL data: {sol_data}")
            price = sol_data.get("price")
            print(f"Price: {price}")
            if price:
                return float(price)
            else:
                print("No price found in SOL data")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    return 0.0

if __name__ == "__main__":
    price = debug_sol_price()
    print(f"Final SOL price: {price}")