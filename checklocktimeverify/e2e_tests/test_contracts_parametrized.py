#!/usr/bin/env python3
"""
Parametrized Contract Tests - Single Test, All Contracts

This file uses ContractDefinition as the SINGLE SOURCE OF TRUTH for tests.
One parametrized test function generates all test cases automatically.

Instead of 20+ separate test functions, we have:
    1 test × 5 contracts × 2 output_types × N paths = all tests

To add a new contract type:
    1. Add ContractDefinition in contracts/definitions.py
    2. Tests are automatically generated!

Usage:
    pytest test_contracts_parametrized.py -v -s --locktime=<height+1>
    pytest test_contracts_parametrized.py -v -s -k "escrow"  # Just escrow
    pytest test_contracts_parametrized.py -v -s -k "taproot"  # Just taproot
"""

# Configure network
from network_config import configure_electrum, NETWORK_NAME
configure_electrum()

import sys
import os
import pytest
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

# Add paths
ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
if os.path.exists(ELECTRUM_DIR):
    sys.path.insert(0, ELECTRUM_DIR)

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

# Import from cltv_lib
from cltv_lib.contracts import CONTRACTS, ContractDefinition, SpendingPath
from cltv_lib.builders.unified.generic import build_contract

# Import test utilities
from unified_test_builder import build_e2e_test, get_test_amount
from test_e2e_stateful import StateManager
from test_helpers import log_test_info
from sweep_utils import sweep_funded_output
from dest_utils import get_sweep_destination
from broadcast_utils import broadcast_transaction, get_explorer_url


# ============================================================================
# TEST CASE GENERATION
# ============================================================================

@dataclass
class TestCase:
    """A single test case generated from ContractDefinition."""
    contract_name: str
    output_type: str  # 'p2wsh' or 'taproot'
    path_name: str
    path: SpendingPath
    test_id: str  # For pytest
    

def generate_test_cases() -> List[TestCase]:
    """
    Generate all test cases from ContractDefinition.
    
    This is the SINGLE SOURCE OF TRUTH - tests are derived from contracts.
    """
    cases = []
    
    for contract_name, contract in CONTRACTS.items():
        for output_type in ['p2wsh', 'taproot']:
            for path in contract.paths:
                test_id = f"{contract_name}_{output_type}_{path.name}"
                cases.append(TestCase(
                    contract_name=contract_name,
                    output_type=output_type,
                    path_name=path.name,
                    path=path,
                    test_id=test_id,
                ))
    
    return cases


# Generate test cases at module load time
TEST_CASES = generate_test_cases()

# Create pytest parameter list
TEST_PARAMS = [(tc.contract_name, tc.output_type, tc.path_name, tc.path) 
               for tc in TEST_CASES]
TEST_IDS = [tc.test_id for tc in TEST_CASES]


# ============================================================================
# KEY FIXTURES HELPER
# ============================================================================

def get_keys_for_contract(contract_name: str, fixtures: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the appropriate keys for a contract type.
    
    Args:
        contract_name: 'hodl', 'escrow', etc.
        fixtures: Dict containing fixture functions
    
    Returns:
        Dict of keypairs for the contract
    """
    if contract_name == 'hodl':
        kp = fixtures['generate_keypair']('hodl')
        return {'': kp}  # Empty name for simple
    
    elif contract_name == 'escrow':
        alice, bob, lenny = fixtures['alice_bob_keypairs']()
        return {'alice': alice, 'bob': bob, 'lenny': lenny}
    
    elif contract_name == 'twofactor':
        user, service = fixtures['twofactor_keypairs']()
        return {'user': user, 'service': service}
    
    elif contract_name == 'payment_channel':
        sender, receiver = fixtures['payment_keypairs']()
        return {'sender': sender, 'receiver': receiver}
    
    elif contract_name == 'data_publishing':
        publisher, buyer = fixtures['data_publishing_keypairs']()
        return {'publisher': publisher, 'buyer': buyer}
    
    elif contract_name == 'decaying_multisig':
        multisig_keypairs = fixtures['multisig_keypairs']()
        return {
            'member1': multisig_keypairs[0],
            'member2': multisig_keypairs[1], 
            'member3': multisig_keypairs[2],
            'member4': multisig_keypairs[3],
            'member5': multisig_keypairs[4]
        }
    
    else:
        raise ValueError(f"Unknown contract: {contract_name}")


def get_params_for_contract(
    contract_name: str, 
    keys: Dict[str, Any], 
    locktime: int,
    fixtures: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build params dict for a contract type.
    """
    params = {'locktime': locktime}
    
    for role, keypair in keys.items():
        if role:
            params[role] = keypair['pubkey_compressed']
        else:
            params['pubkey'] = keypair['pubkey_compressed']
    
    # Special case: data_publishing needs data_hash
    if contract_name == 'data_publishing':
        test_data_preimage = fixtures['test_data_preimage']
        params['data_hash'] = test_data_preimage['data_hash']
    
    return params


# ============================================================================
# THE PARAMETRIZED TEST
# ============================================================================

@pytest.mark.e2e
@pytest.mark.parametrize(
    "contract_name,output_type,path_name,path",
    TEST_PARAMS,
    ids=TEST_IDS
)
def test_contract(
    contract_name: str,
    output_type: str,
    path_name: str,
    path: SpendingPath,
    # Fixtures
    generate_keypair,
    alice_bob_keypairs,
    twofactor_keypairs,
    payment_keypairs,
    data_publishing_keypairs,
    multisig_keypairs,
    test_data_preimage,
    locktime_value,
    current_height,
    request,  # For dynamic test numbering
):
    """
    Universal contract test.
    
    This single test function handles ALL contracts, output types, and paths.
    The ContractDefinition is the source of truth.
    
    IMPORTANT: Each test uses a UNIQUE locktime (base + test_number) to ensure
    each test has a unique address. This allows independent funding and sweeping.
    """
    # Pack fixtures for helper functions
    fixtures = {
        'generate_keypair': generate_keypair,
        'alice_bob_keypairs': alice_bob_keypairs,
        'twofactor_keypairs': twofactor_keypairs,
        'payment_keypairs': payment_keypairs,
        'data_publishing_keypairs': data_publishing_keypairs,
        'multisig_keypairs': multisig_keypairs,
        'test_data_preimage': test_data_preimage,
    }
    
    # Get test number from position in test list
    test_id = f"{contract_name}_{output_type}_{path_name}"
    test_number = TEST_IDS.index(test_id) + 1
    
    # CRITICAL: Use unique locktime per test to get unique addresses
    # This allows independent funding and sweeping of each path
    # Default locktime diff is 1 block (locktime_value + 1)
    test_locktime = locktime_value + 1
    
    # Initialize state manager (still keyed by base locktime for grouping)
    state = StateManager(locktime=locktime_value)
    
    # Check for existing test (filter by path)
    all_tests = state.get_tests(f'cltv_{contract_name}', output_type)
    existing = [t for t in all_tests if t.get('path') == path_name]
    if existing:
        test_data = existing[0]
        status = test_data.get('status', 'CREATED')
        
        log_test_info(
            f"{contract_name.title()} {output_type.upper()} ({path_name})",
            test_data,
            current_height,
            path_name
        )
        
        if status == 'FUNDED':
            _handle_funded_test(test_data, state, current_height, path)
        elif status == 'SWEPT':
            print(f" Already swept! TX: {test_data.get('sweep_txid')}")
        
        return
    
    # Generate new test
    print(f"\n{'='*80}")
    print(f" NEW TEST #{test_number}: {contract_name.title()} {output_type.upper()} ({path.display_name})")
    print(f"{'='*80}")
    
    # Get keys and params (use test_locktime for unique address)
    keys = get_keys_for_contract(contract_name, fixtures)
    params = get_params_for_contract(contract_name, keys, test_locktime, fixtures)
    
    # Build test data using unified builder
    extra_fields = {}
    if contract_name == 'data_publishing':
        extra_fields['data_preimage'] = test_data_preimage['data_hex']
        extra_fields['data_hash'] = test_data_preimage['data_hash']
    
    test_data = build_e2e_test(
        contract_name=contract_name,
        params=params,
        output_type=output_type,
        test_number=test_number,
        current_height=current_height,
        path=path_name,
        keys=keys,
        notes=f"{CONTRACTS[contract_name].name} - {path.display_name}",
        base_locktime=locktime_value,  # Store both for reference
        **extra_fields
    )
    
    # Save to state
    state.add_test(f'cltv_{contract_name}', output_type, test_data)
    state.save()
    
    # Print summary
    print(f"\n Test #{test_number} Created:")
    print(f"   Contract: {CONTRACTS[contract_name].name}")
    print(f"   Output Type: {output_type.upper()}")
    print(f"   Path: {path.display_name}")
    print(f"   Address: {test_data['address']}")
    print(f"   Locktime: {test_locktime} (base: {locktime_value} + test: {test_number})")
    print(f"   Requires Locktime: {'Yes' if path.requires_locktime else 'No'}")
    print(f"   Amount: {get_test_amount(test_number)} sats")
    print(f"\n   Required Keys: {', '.join(path.required_keys)}")
    print(f" UNIQUE ADDRESS per test - fund this specific address")


def _handle_funded_test(test_data: dict, state: StateManager, current_height: int, path: SpendingPath):
    """Handle funded test - attempt sweep if conditions met."""
    print(f"\n Test funded!")
    print(f"   TX: {test_data.get('funding_txid')}")
    print(f"   Amount: {test_data.get('amount_sats')} sats")
    
    locktime = test_data.get('locktime', 0)
    path_name = test_data.get('path', 'sweep')
    
    # Check locktime
    is_locked = current_height < locktime
    if is_locked and path.requires_locktime:
        blocks_remaining = locktime - current_height
        print(f" Locked: {blocks_remaining} blocks until height {locktime}")
        print(f" Path '{path_name}' requires locktime - skipping")
        return
    
    if is_locked and not path.requires_locktime:
        print(f" Path '{path_name}' is cooperative - can sweep now!")
    
    # Attempt sweep
    print(f"\n Sweeping via path: {path_name}")
    
    destination = get_sweep_destination(test_data)
    
    try:
        sweep_txid = sweep_funded_output(
            test_data=test_data,
            destination_address=destination,
            current_height=current_height,
            fee_sats=200,
            path=path_name
        )
        
        if sweep_txid:
            print(f" Sweep successful!")
            print(f"   TX: {sweep_txid}")
            print(f"   Explorer: {get_explorer_url(sweep_txid)}")
            
            test_data['status'] = 'SWEPT'
            test_data['sweep_txid'] = sweep_txid
            state.save()
        else:
            print(f" Sweep returned None")
            
    except Exception as e:
        print(f" Sweep failed: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# SUMMARY FUNCTIONS
# ============================================================================

def print_test_matrix():
    """Print the test matrix generated from ContractDefinition."""
    print("\n" + "="*80)
    print(" TEST MATRIX (Generated from ContractDefinition)")
    print("="*80)
    
    for contract_name, contract in CONTRACTS.items():
        print(f"\n{contract.icon} {contract.name}")
        print(f"   BIP Reference: {contract.bip_reference}")
        print(f"   Paths:")
        for path in contract.paths:
            locktime_note = "" if path.requires_locktime else ""
            print(f"      {locktime_note} {path.name}: {path.display_name}")
        print(f"   Tests: {len(contract.paths)} paths × 2 output_types = {len(contract.paths) * 2}")
    
    total = sum(len(c.paths) * 2 for c in CONTRACTS.values())
    print(f"\n{'='*80}")
    print(f"TOTAL: {total} tests from {len(CONTRACTS)} contracts")
    print("="*80)


if __name__ == '__main__':
    # Print test matrix when run directly
    print_test_matrix()
    
    print("\n\nTo run tests:")
    print("  pytest test_contracts_parametrized.py -v -s --locktime=<HEIGHT>")

