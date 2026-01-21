#!/usr/bin/env python3
"""
Full E2E Test Runner - Generate, Fund, and Sweep ALL contracts and paths

Iterates over the SINGLE SOURCE OF TRUTH (ContractDefinition) to test:
- All 5 contract types
- Both P2WSH and Taproot output types
- All spending paths for each contract

Usage:
    python run_full_e2e.py --wipe          # Fresh start
    python run_full_e2e.py --dry-run       # Show what would happen
    python run_full_e2e.py --locktime=X    # Specific locktime

Requirements:
    - Electrum daemon running: electrum --signet daemon -d
    - Wallet loaded with funds
"""

from network_config import configure_electrum, NETWORK_FLAG, NETWORK_NAME
configure_electrum()

import sys
import os
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Add paths
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import electrum_ecc as ecc
from test_e2e_stateful import StateManager
from unified_test_builder import build_e2e_test, get_test_amount
from sweep_utils import sweep_funded_output
from dest_utils import get_sweep_destination
from broadcast_utils import broadcast_transaction, get_explorer_url
from cltv_lib.contracts import CONTRACTS, ContractDefinition, SpendingPath

# Electrum paths
ELECTRUM_PYTHON = Path.home() / "src/electrum/venv/bin/python3"
ELECTRUM_PATH = Path.home() / "src/electrum/run_electrum"

# Output types to test
OUTPUT_TYPES = ['p2wsh', 'taproot']


def get_current_height() -> int:
    """Get current blockchain height from Electrum daemon."""
    result = subprocess.run(
        [str(ELECTRUM_PYTHON), str(ELECTRUM_PATH), NETWORK_FLAG, "getinfo"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise RuntimeError(f"Failed to get blockchain info: {error_msg}\n"
                          f"Make sure Electrum daemon is running: electrum {NETWORK_FLAG} daemon -d")
    try:
        info = json.loads(result.stdout)
        return info.get('blockchain_height', 0)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON response from daemon: {result.stdout[:200]}")


def generate_keypair(key_name: str) -> Dict[str, Any]:
    """Generate keypair for test keys from single source of truth."""
    from test_keys import get_test_privkey, get_test_pubkey
    privkey = get_test_privkey(key_name)
    return {
        'privkey': privkey,
        'privkey_hex': privkey.get_secret_bytes().hex(),
        'pubkey': get_test_pubkey(key_name),
        'pubkey_compressed': get_test_pubkey(key_name),
    }


def get_test_data_for_contract(contract: ContractDefinition, locktime: int) -> Tuple[Dict[str, Any], Dict[str, Dict]]:
    """
    Build params and keys for a contract from ContractDefinition.
    
    SINGLE SOURCE OF TRUTH: Uses ParamSpec.test_key_name to load keys.
    
    Handles multiple locktime parameters (e.g., locktime_60m, locktime_66m for decaying multisig).
    For contracts with multiple locktimes, sets them with appropriate offsets from base locktime.
    
    Returns:
        (params dict, keys dict, data_preimage, data_hash)
    """
    params = {}
    keys = {}
    
    # Special handling for data_publishing preimage
    data_preimage = None
    data_hash = None
    
    # Collect all locktime parameters
    locktime_params = []
    for param_spec in contract.params:
        # Check if this is a locktime parameter (by name or type)
        if (param_spec.param_type == 'locktime' or 
            param_spec.name.startswith('locktime') or
            'locktime' in param_spec.name.lower()):
            locktime_params.append(param_spec)
    
    # Set locktime parameters
    if len(locktime_params) == 1:
        # Single locktime: use base locktime
        params[locktime_params[0].name] = locktime
        # Also set 'locktime' for backwards compatibility
        if locktime_params[0].name != 'locktime':
            params['locktime'] = locktime
    elif len(locktime_params) > 1:
        # Multiple locktimes: set with offsets (e.g., for decaying multisig)
        # locktime_60m = locktime + 0 (first decay point)
        # locktime_66m = locktime + offset (second decay point)
        # Use 6 block offset for 66m vs 60m (representing 6 months)
        for i, param_spec in enumerate(locktime_params):
            # Offset in blocks: 0 for first, 6 for second (representing ~6 months)
            offset = i * 6
            params[param_spec.name] = locktime + offset
        # Also set 'locktime' for backwards compatibility
        params['locktime'] = locktime
    else:
        # No locktime params: set default for backwards compatibility
        params['locktime'] = locktime
    
    # Process other parameters
    for param_spec in contract.params:
        # Skip locktime params (already handled)
        if param_spec in locktime_params:
            continue
            
        if param_spec.param_type == 'pubkey' and param_spec.test_key_name:
            # Load keypair using test_key_name from ContractDefinition
            keypair = generate_keypair(param_spec.test_key_name)
            params[param_spec.name] = keypair['pubkey_compressed']
            keys[param_spec.name] = keypair  # Use param name as key (e.g., 'alice', not 'alice_key')
            
        elif param_spec.param_type == 'hash160':
            # Generate test preimage and hash for data_publishing
            data_preimage = b"secret data for publishing test"
            from electrum.crypto import hash_160
            data_hash = hash_160(data_preimage).hex()
            params[param_spec.name] = data_hash
            
        elif param_spec.param_type == 'preimage':
            # Will be set after hash is computed
            pass
    
    return params, keys, data_preimage, data_hash


def wipe_state(locktime: int):
    """Delete state file for this locktime."""
    state_file = Path(__file__).parent / f"test_state_{locktime}.json"
    if state_file.exists():
        state_file.unlink()
        print(f"🗑️  Deleted {state_file.name}")
    else:
        print(f"ℹ️  No state file to delete")


def generate_all_tests(state: StateManager, locktime: int, current_height: int) -> List[Dict]:
    """
    Generate test addresses for ALL contracts, output types, and paths.
    
    SINGLE SOURCE OF TRUTH: Iterates over CONTRACTS and their paths.
    """
    print("\n" + "="*80)
    print("📝 GENERATING TEST ADDRESSES FROM SINGLE SOURCE OF TRUTH")
    print("="*80)
    
    tests = []
    test_number = 1
    
    # Iterate over all contracts
    for contract_name, contract in CONTRACTS.items():
        print(f"\n📜 {contract.name} ({len(contract.paths)} paths)")
        
        # Get params and keys for this contract
        params, keys, data_preimage, data_hash = get_test_data_for_contract(contract, locktime)
        
        # Iterate over all output types
        for output_type in OUTPUT_TYPES:
            
            # Iterate over all spending paths
            for path in contract.paths:
                path_name = path.name
                
                # Build test data
                extra_kwargs = {}
                if data_preimage:
                    extra_kwargs['data_preimage'] = data_preimage.hex()
                    extra_kwargs['data_hash'] = data_hash
                
                try:
                    test_data = build_e2e_test(
                        contract_name=contract_name,
                        params=params,
                        output_type=output_type,
                        test_number=test_number,
                        current_height=current_height,
                        path=path_name,
                        keys=keys,
                        **extra_kwargs
                    )
                    
                    # Add to state
                    category = f'cltv_{contract_name}'
                    state.add_test(category, output_type, test_data)
                    tests.append((contract_name, output_type, path_name, test_data))
                    
                    icon = "🔒" if path.requires_locktime else "⚡"
                    print(f"   {icon} #{test_number:2d}. {output_type:7} {path_name:20} {test_data['address'][:25]}...")
                    test_number += 1
                    
                except Exception as e:
                    print(f"   ❌ {output_type} {path_name}: {e}")
    
    state.save()
    
    # Summary
    print("\n" + "-"*80)
    print(f"✅ Generated {len(tests)} test addresses:")
    print(f"   • {len(CONTRACTS)} contracts")
    print(f"   • {len(OUTPUT_TYPES)} output types (P2WSH, Taproot)")
    total_paths = sum(len(c.paths) for c in CONTRACTS.values())
    print(f"   • {total_paths} spending paths total")
    
    return tests


def fund_all_tests(state: StateManager, dry_run: bool = False) -> Optional[str]:
    """Fund all CREATED tests using fund_tests.py logic."""
    from fund_tests import get_unfunded_tests, print_funding_summary, create_funding_transaction, update_state_with_funding
    
    print("\n" + "="*80)
    print("💰 FUNDING TEST ADDRESSES")
    print("="*80)
    
    unfunded = get_unfunded_tests(state)
    
    if not unfunded:
        print("\n✅ All tests already funded!")
        return None
    
    outputs_by_address, total_sats = print_funding_summary(unfunded)
    
    if dry_run:
        print("\n[DRY RUN] Would create transaction but not broadcast")
        return None
    
    txid = create_funding_transaction(outputs_by_address, dry_run=False)
    
    if txid:
        update_state_with_funding(state, unfunded, txid, outputs_by_address)
        print(f"\n✅ Funding TX broadcast: {txid}")
        print(f"   Explorer: {get_explorer_url(txid)}")
    
    return txid


def sweep_all_tests(state: StateManager, current_height: int, dry_run: bool = False) -> List[str]:
    """
    Sweep all funded tests.
    
    SINGLE SOURCE OF TRUTH: Uses SpendingPath.requires_locktime to check if sweep is possible.
    """
    print("\n" + "="*80)
    print("🧹 SWEEPING FUNDED TESTS")
    print("="*80)
    
    sweep_txids = []
    skipped_locked = []
    
    for category, variants in state.state.items():
        if not category.startswith('cltv_'):
            continue
        
        contract_name = category.replace('cltv_', '')
        contract = CONTRACTS.get(contract_name)
        
        for variant, tests in variants.items():
            for test in tests:
                if test.get('status') != 'FUNDED':
                    continue
                
                locktime = test.get('locktime', 0)
                path_name = test.get('path', 'sweep')
                
                # Get path from ContractDefinition (single source of truth)
                path_def = contract.get_path(path_name) if contract else None
                requires_locktime = path_def.requires_locktime if path_def else True
                
                # Check if locked
                is_locked = current_height < locktime
                if is_locked and requires_locktime:
                    blocks_remaining = locktime - current_height
                    skipped_locked.append((test['test_number'], contract_name, path_name, blocks_remaining))
                    continue
                
                icon = "⚡" if not requires_locktime else "🔓"
                print(f"\n{icon} #{test['test_number']} - {contract_name} {variant} ({path_name})")
                
                if dry_run:
                    print("   [DRY RUN] Would sweep")
                    continue
                
                try:
                    destination = get_sweep_destination(test)
                    sweep_txid = sweep_funded_output(
                        test_data=test,
                        destination_address=destination,
                        current_height=current_height,
                        fee_sats=200,
                        path=path_name
                    )
                    
                    if sweep_txid:
                        print(f"   ✅ Swept: {sweep_txid[:16]}...")
                        test['status'] = 'SWEPT'
                        test['sweep_txid'] = sweep_txid
                        state.save()
                        sweep_txids.append(sweep_txid)
                    else:
                        print(f"   ⚠️ Sweep returned None")
                        
                except Exception as e:
                    print(f"   ❌ Sweep failed: {e}")
                    import traceback
                    traceback.print_exc()
    
    # Report skipped locked tests
    if skipped_locked:
        print(f"\n⏳ Skipped {len(skipped_locked)} locked tests (require locktime):")
        for test_num, contract, path, blocks in skipped_locked:
            print(f"   #{test_num} {contract} {path}: {blocks} blocks remaining")
    
    return sweep_txids


def print_summary(tests: List, sweep_txids: List[str], current_height: int, locktime: int):
    """Print final summary with contract/path matrix."""
    print("\n" + "="*80)
    print("📊 TEST MATRIX (Single Source of Truth)")
    print("="*80)
    
    for contract_name, contract in CONTRACTS.items():
        print(f"\n{contract.icon} {contract.name}:")
        for path in contract.paths:
            lock_icon = "🔒" if path.requires_locktime else "⚡"
            keys_str = "+".join(path.required_keys)
            print(f"   {lock_icon} {path.name:20} Keys: {keys_str}")
    
    print("\n" + "-"*80)
    print(f"Total: {len(CONTRACTS)} contracts, {sum(len(c.paths) for c in CONTRACTS.values())} paths")
    print(f"Tests per output type: {sum(len(c.paths) for c in CONTRACTS.values())}")
    print(f"Total tests: {sum(len(c.paths) for c in CONTRACTS.values()) * len(OUTPUT_TYPES)}")


def main():
    parser = argparse.ArgumentParser(description='Run full E2E test cycle for ALL contracts and paths')
    parser.add_argument('--locktime', type=int, help='Locktime (default: current_height - 10)')
    parser.add_argument('--wipe', action='store_true', help='Wipe existing state first')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen')
    parser.add_argument('--skip-fund', action='store_true', help='Skip funding step')
    parser.add_argument('--skip-sweep', action='store_true', help='Skip sweep step')
    parser.add_argument('--show-matrix', action='store_true', help='Show contract/path matrix and exit')
    args = parser.parse_args()
    
    print("="*80)
    print("🚀 FULL E2E TEST RUNNER - ALL CONTRACTS & PATHS")
    print("="*80)
    print(f"Network: {NETWORK_NAME}")
    print(f"Time: {datetime.now().isoformat()}")
    
    # Show matrix if requested
    if args.show_matrix:
        print_summary([], [], 0, 0)
        return
    
    # Get current height
    current_height = get_current_height()
    print(f"Current height: {current_height}")
    
    # Determine locktime
    if args.locktime:
        locktime = args.locktime
    else:
        locktime = current_height - 10
    
    print(f"Locktime: {locktime} ({'already passed' if locktime <= current_height else f'{locktime - current_height} blocks away'})")
    
    # Calculate expected tests
    expected_tests = sum(len(c.paths) for c in CONTRACTS.values()) * len(OUTPUT_TYPES)
    print(f"Expected tests: {expected_tests} ({len(CONTRACTS)} contracts × {len(OUTPUT_TYPES)} types × paths)")
    
    # Wipe if requested
    if args.wipe:
        wipe_state(locktime)
    
    # Initialize state
    state = StateManager(locktime=locktime)
    
    # Check for existing tests
    existing_tests = sum(
        len(tests) for variants in state.state.values() 
        if isinstance(variants, dict)
        for tests in variants.values() if isinstance(tests, list)
    )
    
    if existing_tests == 0:
        tests = generate_all_tests(state, locktime, current_height)
    else:
        print(f"\n✅ Found {existing_tests} existing tests in state")
        tests = []
    
    # Fund
    if not args.skip_fund:
        fund_all_tests(state, dry_run=args.dry_run)
    
    # Sweep
    sweep_txids = []
    if not args.skip_sweep:
        sweep_txids = sweep_all_tests(state, current_height, dry_run=args.dry_run)
        
        if sweep_txids:
            print("\n" + "="*80)
            print("🎉 E2E TEST COMPLETE")
            print("="*80)
            print(f"Swept {len(sweep_txids)} transactions:")
            for txid in sweep_txids:
                print(f"   {get_explorer_url(txid)}")
    
    # Final summary
    print_summary(tests, sweep_txids, current_height, locktime)
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
