#!/usr/bin/env python3
"""
Fund Tests Helper - Create funding transaction for all pending tests

This script:
1. Reads the state file to find all CREATED tests
2. Creates a single transaction with one output per test
3. Updates state file with funding txid:vout for each test

The key insight: Even if multiple tests share the same ADDRESS,
they need separate UTXOs (identified by amount) to be swept independently.

Usage:
    python fund_tests.py --locktime=280338
    python fund_tests.py --locktime=280338 --dry-run  # Show what would be funded
"""

from network_config import configure_electrum, NETWORK_FLAG, NETWORK_NAME
configure_electrum()

import sys
import os
import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# Add paths
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from test_e2e_stateful import StateManager


def get_unfunded_tests(state: StateManager) -> List[Tuple[str, str, Dict]]:
    """
    Get all tests that need funding.
    
    Returns:
        List of (category, variant, test_data) tuples
    """
    unfunded = []
    
    for category, variants in state.state.items():
        if not category.startswith('cltv_'):
            continue
        for variant, tests in variants.items():
            for test in tests:
                if test.get('status') == 'CREATED' and not test.get('funding_txid'):
                    unfunded.append((category, variant, test))
    
    return unfunded


def print_funding_summary(unfunded: List[Tuple[str, str, Dict]]):
    """Print summary of tests to fund."""
    print("\n" + "="*80)
 print(" TESTS TO FUND")
    print("="*80)
    
    total_sats = 0
    outputs_by_address = {}
    
    for category, variant, test in unfunded:
        address = test['address']
        amount = test['amount_sats']
        path = test.get('path', 'sweep')
        total_sats += amount
        
        # Group by address
        if address not in outputs_by_address:
            outputs_by_address[address] = []
        outputs_by_address[address].append({
            'amount': amount,
            'path': path,
            'category': category,
            'variant': variant,
        })
    
    print(f"\nUnique addresses: {len(outputs_by_address)}")
    print(f"Total outputs: {len(unfunded)}")
    print(f"Total amount: {total_sats} sats")
    
    print("\n" + "-"*80)
    for address, outputs in outputs_by_address.items():
 print(f"\n {address}")
        for out in outputs:
            print(f"   └─ {out['amount']} sats ({out['category']} {out['variant']} - {out['path']})")
    
    return outputs_by_address, total_sats


def create_funding_transaction(outputs_by_address: Dict, dry_run: bool = False) -> str:
    """
    Create a transaction funding all test addresses.
    
    Args:
        outputs_by_address: Dict mapping address -> list of output specs
        dry_run: If True, just print what would be done
    
    Returns:
        Funding transaction ID
    """
    electrum_python = Path.home() / "src/electrum/venv/bin/python3"
    electrum_path = Path.home() / "src/electrum/run_electrum"
    
    # Build outputs dict for payto command: {"address1": amount1, ...}
    # Problem: payto only supports one output per address
    # Solution: Use paytomany or create multiple transactions
    
    # For now, let's collect all outputs and use paytomany format
    all_outputs = []
    for address, outputs in outputs_by_address.items():
        for out in outputs:
            all_outputs.append((address, out['amount']))
    
    if dry_run:
        print("\n" + "="*80)
 print(" DRY RUN - Would create transaction with:")
        print("="*80)
        for addr, amount in all_outputs:
            print(f"   {addr}: {amount} sats")
        print(f"\n   Total outputs: {len(all_outputs)}")
        print(f"   Total amount: {sum(a for _, a in all_outputs)} sats")
        return None
    
    # Build paytomany outputs JSON
    # Format: [["address1", amount1], ["address2", amount2], ...]
    outputs_json = json.dumps([[addr, amount / 100_000_000] for addr, amount in all_outputs])
    
 print(f"\n Creating transaction...")
    print(f"   Outputs: {len(all_outputs)}")
    
    # Create unsigned transaction
    result = subprocess.run(
        [str(electrum_python), str(electrum_path), NETWORK_FLAG, 
         "paytomany", outputs_json],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
 print(f" Failed to create transaction: {result.stderr}")
        print(f"   stdout: {result.stdout[:200]}")
        return None
    
    # Parse the transaction - paytomany returns hex directly or wrapped in JSON
    tx_hex = result.stdout.strip()
    try:
        tx_data = json.loads(tx_hex)
        if isinstance(tx_data, dict) and 'hex' in tx_data:
            tx_hex = tx_data['hex']
        elif isinstance(tx_data, str):
            tx_hex = tx_data
    except json.JSONDecodeError:
        # Not JSON, assume it's raw hex
        tx_hex = tx_hex.strip('"').strip("'")
    
 print(f" Transaction created")
    
    # Sign and broadcast
 print(f" Signing...")
    result = subprocess.run(
        [str(electrum_python), str(electrum_path), NETWORK_FLAG,
         "signtransaction", tx_hex],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
 print(f" Failed to sign: {result.stderr}")
        print(f"   stdout: {result.stdout[:200]}")
        return None
    
    # Parse signed transaction - may be JSON or raw hex
    signed_hex = result.stdout.strip()
    try:
        signed_data = json.loads(signed_hex)
        signed_hex = signed_data.get('hex') or (signed_data if isinstance(signed_data, str) else signed_hex)
    except json.JSONDecodeError:
        # Not JSON, assume it's raw hex
        signed_hex = signed_hex.strip('"').strip("'")
    
 print(f" Broadcasting...")
    result = subprocess.run(
        [str(electrum_python), str(electrum_path), NETWORK_FLAG,
         "broadcast", signed_hex],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
 print(f" Failed to broadcast: {result.stderr}")
        return None
    
    txid = result.stdout.strip().strip('"')
 print(f" Broadcast successful!")
    print(f"   TXID: {txid}")
    
    return txid


def update_state_with_funding(
    state: StateManager,
    unfunded: List[Tuple[str, str, Dict]],
    txid: str,
    outputs_by_address: Dict
):
    """
    Update state file with funding transaction details.
    
    This maps each test to its specific UTXO based on amount.
    """
 print(f"\n Updating state file...")
    
    # Build a map of (address, amount) -> vout index
    # We need to know the output order in the transaction
    vout_map = {}
    vout = 0
    for address, outputs in outputs_by_address.items():
        for out in sorted(outputs, key=lambda x: x['amount']):
            vout_map[(address, out['amount'])] = vout
            vout += 1
    
    # Update each test
    for category, variant, test in unfunded:
        address = test['address']
        amount = test['amount_sats']
        
        test_vout = vout_map.get((address, amount))
        if test_vout is not None:
            test['funding_txid'] = txid
            test['funding_vout'] = test_vout
            test['status'] = 'FUNDED'
 print(f" {category} {variant} ({test.get('path')}): vout={test_vout}")
    
    state.save()
 print(f"\n State file updated!")


def main():
    parser = argparse.ArgumentParser(description='Fund all pending E2E tests')
    parser.add_argument('--locktime', type=int, required=True, help='Locktime for state file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be funded')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    args = parser.parse_args()
    
    state = StateManager(locktime=args.locktime)
    
    unfunded = get_unfunded_tests(state)
    
    if not unfunded:
 print(" All tests already funded!")
        return
    
    outputs_by_address, total_sats = print_funding_summary(unfunded)
    
    if args.dry_run:
        create_funding_transaction(outputs_by_address, dry_run=True)
        return
    
    # Confirm
    if not args.yes:
 print(f"\n About to fund {len(unfunded)} tests with {total_sats} sats")
        response = input("Continue? [y/N] ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
    
    txid = create_funding_transaction(outputs_by_address)
    
    if txid:
        update_state_with_funding(state, unfunded, txid, outputs_by_address)
 print(f"\n All tests funded!")
        print(f"   TX: {txid}")
        print(f"   Wait for confirmation, then run tests to sweep.")


if __name__ == '__main__':
    main()

