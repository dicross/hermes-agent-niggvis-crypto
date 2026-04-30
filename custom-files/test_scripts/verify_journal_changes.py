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

def verify_existing_entries():
    print("Verifying changes work with existing journal entries...")
    print("=" * 60)
    
    # Load the journal data
    data = journal._load()
    trades = data["trades"]
    
    print(f"Found {len(trades)} trades in journal")
    print()
    
    for i, trade in enumerate(trades):
        print(f"Trade #{trade['id']}: {trade['token']}")
        print(f"  Status: {trade['status']}")
        print(f"  Amount: {trade['amount_sol']} SOL")
        
        # Check what fields are present
        has_old_format = 'entry_price' in trade and 'exit_price' in trade
        has_new_format = 'entry_price_sol' in trade and 'entry_price_usd' in trade
        
        print(f"  Format: {'OLD' if has_old_format else 'NEW' if has_new_format else 'UNKNOWN'}")
        
        if has_old_format:
            print(f"  Entry price (USD): {trade['entry_price']}")
            print(f"  Exit price (USD): {trade.get('exit_price', 'N/A')}")
            
            # Calculate what SOL prices should be
            sol_price = 150.0
            entry_sol = trade['entry_price'] / sol_price if sol_price > 0 else 0
            exit_price_val = trade.get('exit_price', 0)
            exit_sol = exit_price_val / sol_price if sol_price > 0 else 0
            
            print(f"  Entry price (SOL): {entry_sol:.8f}")
            print(f"  Exit price (SOL): {exit_sol:.8f}")
            
            # Calculate PNL
            if entry_sol > 0:
                pnl_pct = ((exit_sol - entry_sol) / entry_sol) * 100
                pnl_sol = trade['amount_sol'] * (pnl_pct / 100)
                print(f"  PNL: {pnl_pct:.2f}% ({pnl_sol:.6f} SOL)")
            else:
                print(f"  PNL: Unable to calculate (entry SOL price is 0)")
                
        elif has_new_format:
            entry_sol = trade.get('entry_price_sol', 0) or 0
            entry_usd = trade.get('entry_price_usd', 0) or 0
            exit_sol = trade.get('exit_price_sol', 0) or 0
            exit_usd = trade.get('exit_price_usd', 0) or 0
            
            print(f"  Entry price: {entry_sol:.6f} SOL/token (${entry_usd:.6f})")
            print(f"  Exit price: {exit_sol:.6f} SOL/token (${exit_usd:.6f})")
            
            if trade['status'] == 'closed' and entry_sol > 0:
                pnl_pct = ((exit_sol - entry_sol) / entry_sol) * 100
                pnl_sol = trade['amount_sol'] * (pnl_pct / 100)
                print(f"  PNL: {pnl_pct:+.2f}% ({pnl_sol:+.6f} SOL)")
            elif trade['status'] == 'open':
                print(f"  PNL: Position open")
            else:
                print(f"  PNL: Unable to calculate")
        else:
            print(f"  Unknown format")
        
        print()
    
    print("=" * 60)
    print("Verification complete!")

def verify_export_function():
    print("\nTesting export function...")
    print("=" * 60)
    
    # Capture export output
    import io
    import csv
    import sys
    
    # Redirect stdout to capture export output
    old_stdout = sys.stdout
    sys.stdout = captured_output = io.StringIO()
    
    try:
        # Create mock args for export
        class MockArgs:
            pass
        args = MockArgs()
        
        journal.cmd_export(args)
        output = captured_output.getvalue()
        sys.stdout = old_stdout
        
        print("Export output:")
        print(output)
        
        # Check that it contains the expected headers
        if 'entry_price_sol' in output and 'entry_price_usd' in output:
            print("✓ Export includes new SOL price fields")
        else:
            print("✗ Export missing SOL price fields")
            
        # Check that it handles both old and new format entries
        lines = output.strip().split('\n')
        if len(lines) > 1:  # Header + at least one data row
            print(f"✓ Export produced {len(lines)-1} data rows")
        else:
            print("✗ Export produced no data rows")
            
    except Exception as e:
        sys.stdout = old_stdout
        print(f"Error during export: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_existing_entries()
    verify_export_function()