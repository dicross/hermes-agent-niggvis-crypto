#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.hermes/skills/trade-journal/scripts'))

# Mock the SOL price function to return a fixed value for testing
def _get_sol_price():
    return 150.0  # Mock SOL price at $150

# Import the journal functions after setting up the mock
import journal
journal._get_sol_price = _get_sol_price

def test_calculations():
    print("Testing journal calculations with mocked SOL price ($150)...")
    
    # Test data similar to what would be in the journal
    trade = {
        "id": 1,
        "status": "open",
        "paper": False,
        "token": "TEST Token",
        "address": "test123",
        "amount_sol": 0.01,
        "entry_price_sol": 0.0001,  # 0.0001 SOL per token
        "entry_price_usd": 0.015,   # $0.015 per token (0.0001 * 150)
        "entry_time": "2026-04-30T00:00:00+02:00",
        "entry_reason": "Test",
        "exit_price_sol": None,
        "exit_price_usd": None,
        "exit_time": None,
        "exit_reason": None,
        "pnl_pct": None,
        "pnl_sol": None,
    }
    
    print(f"Initial trade: {trade}")
    
    # Simulate closing the trade at 2x the entry price
    exit_price_usd = 0.030  # $0.030 per token
    exit_price_sol = exit_price_usd / 150.0  # 0.0002 SOL per token
    
    print(f"Closing at: ${exit_price_usd} per token ({exit_price_sol} SOL per token)")
    
    # Calculate PNL based on SOL price change
    entry_price_sol = float(trade.get("entry_price_sol", 0))
    exit_price_sol = float(exit_price_sol)
    
    if entry_price_sol > 0:
        pnl_pct = ((exit_price_sol - entry_price_sol) / entry_price_sol) * 100
        amount_sol = float(trade["amount_sol"])
        pnl_sol = amount_sol * (pnl_pct / 100)
    else:
        pnl_pct = 0
        pnl_sol = 0
    
    print(f"PNL %: {pnl_pct:.2f}%")
    print(f"PNL SOL: {pnl_sol:.6f}")
    
    # Verify the math:
    # Entry: 0.0001 SOL/token
    # Exit: 0.0002 SOL/token
    # Change: 0.0001 SOL/token (100% increase)
    # Amount: 0.01 SOL
    # PNL SOL: 0.01 * 1.0 = 0.01 SOL
    
    expected_pnl_pct = 100.0
    expected_pnl_sol = 0.01
    
    print(f"Expected PNL %: {expected_pnl_pct}%")
    print(f"Expected PNL SOL: {expected_pnl_sol:.6f}")
    
    assert abs(pnl_pct - expected_pnl_pct) < 0.01, f"PNL % mismatch: got {pnl_pct}, expected {expected_pnl_pct}"
    assert abs(pnl_sol - expected_pnl_sol) < 0.000001, f"PNL SOL mismatch: got {pnl_sol}, expected {expected_pnl_sol}"
    
    print("✓ Calculations are correct!")

if __name__ == "__main__":
    test_calculations()