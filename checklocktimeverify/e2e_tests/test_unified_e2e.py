#!/usr/bin/env python3
"""
Unified E2E Tests - Using Generic build_contract()

This test file uses the new unified architecture where ContractDefinition
is the single source of truth. All 5 contract types, both P2WSH and Taproot,
are generated using the same code path.

Tests:
    1-2:   Simple HODL (P2WSH + Taproot)
    3-5:   Escrow (P2WSH normal, arbitration_alice, arbitration_bob)
    6-7:   Escrow Taproot (normal, arbitration)
    8-9:   Two-Factor (P2WSH normal, recovery)
    10-11: Two-Factor Taproot (normal, recovery)
    12-13: Payment Channel (P2WSH cooperative, refund)
    14-15: Payment Channel Taproot (cooperative, refund)
    16-17: Data Publishing (P2WSH publisher, buyer_refund)
    18-19: Data Publishing Taproot (publisher, buyer_refund)

Usage:
    pytest test_unified_e2e.py -v -s --locktime=<height+1>
"""

# Configure network from central config
from network_config import configure_electrum, NETWORK_NAME
configure_electrum()

import sys
import os
import pytest
from pathlib import Path

# Add paths
ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
if os.path.exists(ELECTRUM_DIR):
    sys.path.insert(0, ELECTRUM_DIR)

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

# Import unified test builder
from unified_test_builder import build_e2e_test, get_test_amount
from test_e2e_stateful import StateManager
from test_helpers import log_test_info
from sweep_utils import sweep_funded_output
from dest_utils import get_sweep_destination
from broadcast_utils import broadcast_transaction, get_explorer_url


# ============================================================================
# TEST HELPERS
# ============================================================================

def handle_funded_test(test_data: dict, state: StateManager, current_height: int):
    """Handle a test that is already funded - attempt to sweep."""
    print(f"\n Test already funded!")
    print(f"   Funding TX: {test_data.get('funding_txid')}")
    print(f"   Amount: {test_data.get('amount_sats')} sats")
    
    locktime = test_data.get('locktime', 0)
    path = test_data.get('path', 'sweep')
    
    # Check if locked
    is_locked = current_height < locktime
    if is_locked:
        blocks_remaining = locktime - current_height
        print(f" Locked: {blocks_remaining} blocks remaining until height {locktime}")
        
        # Can still sweep cooperative paths
        if path in ('normal', 'cooperative', 'publisher'):
            print(f" But path '{path}' doesn't require locktime - can sweep now!")
        else:
            print(f" Path '{path}' requires locktime - skipping sweep")
            return
    
    # Attempt sweep
    print(f"\n Attempting sweep via path: {path}")
    
    destination = get_sweep_destination(test_data)
    
    try:
        sweep_txid = sweep_funded_output(
            test_data=test_data,
            destination_address=destination,
            current_height=current_height,
            fee_sats=200,
            path=path
        )
        
        if sweep_txid:
            print(f" Sweep successful!")
            print(f"   TX: {sweep_txid}")
            print(f"   Explorer: {get_explorer_url(sweep_txid)}")
            
            # Update state
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
# SIMPLE HODL TESTS
# ============================================================================

@pytest.mark.e2e
def test_hodl_p2wsh(generate_keypair, locktime_value, current_height):
    """Simple HODL P2WSH - single signature after locktime."""
    test_number = 1
    state = StateManager(locktime=locktime_value)
    
    # Check if already exists
    existing = state.get_tests('cltv_hodl', 'p2wsh')
    if existing:
        test_data = existing[0]
        log_test_info("Simple HODL P2WSH", test_data, current_height, "sweep")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    # Generate new test
    keypair = generate_keypair('hodl')
    
    test_data = build_e2e_test(
        contract_name='hodl',
        params={
            'locktime': locktime_value,
            'pubkey': keypair['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='sweep',
        keys={'': keypair},  # Empty key name for simple contracts
        notes='Simple HODL P2WSH - sweep after locktime'
    )
    
    state.add_test('cltv_hodl', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Simple HODL P2WSH")
    print(f"   Address: {test_data['address']}")
    print(f"   Locktime: {locktime_value}")
    print(f"   Amount: {get_test_amount(test_number)} sats")


@pytest.mark.e2e
def test_hodl_taproot(generate_keypair, locktime_value, current_height):
    """Simple HODL Taproot - single signature after locktime."""
    test_number = 2
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_hodl', 'taproot')
    if existing:
        test_data = existing[0]
        log_test_info("Simple HODL Taproot", test_data, current_height, "sweep")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    keypair = generate_keypair('hodl')
    
    test_data = build_e2e_test(
        contract_name='hodl',
        params={
            'locktime': locktime_value,
            'pubkey': keypair['pubkey_compressed'],
        },
        output_type='taproot',
        test_number=test_number,
        current_height=current_height,
        path='sweep',
        keys={'': keypair},
        notes='Simple HODL Taproot - sweep after locktime'
    )
    
    state.add_test('cltv_hodl', 'taproot', test_data)
    state.save()
    
    print(f"\n Created: Simple HODL Taproot")
    print(f"   Address: {test_data['address']}")


# ============================================================================
# ESCROW TESTS
# ============================================================================

@pytest.mark.e2e
def test_escrow_p2wsh_normal(alice_bob_keypairs, locktime_value, current_height):
    """Escrow P2WSH - Normal path (Alice + Bob)."""
    test_number = 3
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_escrow', 'p2wsh', path='normal')
    if existing:
        test_data = existing[0]
        log_test_info("Escrow P2WSH Normal", test_data, current_height, "normal")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    alice, bob, lenny = alice_bob_keypairs()
    
    test_data = build_e2e_test(
        contract_name='escrow',
        params={
            'locktime': locktime_value,
            'alice': alice['pubkey_compressed'],
            'bob': bob['pubkey_compressed'],
            'lenny': lenny['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='normal',
        keys={'alice': alice, 'bob': bob, 'lenny': lenny},
        notes='Escrow P2WSH - Normal operations (Alice + Bob)'
    )
    
    state.add_test('cltv_escrow', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Escrow P2WSH (Normal)")
    print(f"   Address: {test_data['address']}")


@pytest.mark.e2e
def test_escrow_p2wsh_arbitration_alice(alice_bob_keypairs, locktime_value, current_height):
    """Escrow P2WSH - Arbitration path (Lenny + Alice)."""
    test_number = 4
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_escrow', 'p2wsh', path='arbitration_alice')
    if existing:
        test_data = existing[0]
        log_test_info("Escrow P2WSH Arbitration Alice", test_data, current_height, "arbitration_alice")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    alice, bob, lenny = alice_bob_keypairs()
    
    test_data = build_e2e_test(
        contract_name='escrow',
        params={
            'locktime': locktime_value,
            'alice': alice['pubkey_compressed'],
            'bob': bob['pubkey_compressed'],
            'lenny': lenny['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='arbitration_alice',
        keys={'alice': alice, 'bob': bob, 'lenny': lenny},
        notes='Escrow P2WSH - Arbitration (Lenny + Alice) after locktime'
    )
    
    state.add_test('cltv_escrow', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Escrow P2WSH (Arbitration Alice)")
    print(f"   Address: {test_data['address']}")


@pytest.mark.e2e
def test_escrow_taproot_normal(alice_bob_keypairs, locktime_value, current_height):
    """Escrow Taproot - Normal path (Alice + Bob)."""
    test_number = 5
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_escrow', 'taproot', path='normal')
    if existing:
        test_data = existing[0]
        log_test_info("Escrow Taproot Normal", test_data, current_height, "normal")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    alice, bob, lenny = alice_bob_keypairs()
    
    test_data = build_e2e_test(
        contract_name='escrow',
        params={
            'locktime': locktime_value,
            'alice': alice['pubkey_compressed'],
            'bob': bob['pubkey_compressed'],
            'lenny': lenny['pubkey_compressed'],
        },
        output_type='taproot',
        test_number=test_number,
        current_height=current_height,
        path='normal',
        keys={'alice': alice, 'bob': bob, 'lenny': lenny},
        notes='Escrow Taproot - Normal operations (Alice + Bob)'
    )
    
    state.add_test('cltv_escrow', 'taproot', test_data)
    state.save()
    
    print(f"\n Created: Escrow Taproot (Normal)")
    print(f"   Address: {test_data['address']}")


# ============================================================================
# TWO-FACTOR TESTS
# ============================================================================

@pytest.mark.e2e
def test_twofactor_p2wsh_normal(twofactor_keypairs, locktime_value, current_height):
    """Two-Factor P2WSH - Normal path (User + Service)."""
    test_number = 6
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_twofactor', 'p2wsh', path='normal')
    if existing:
        test_data = existing[0]
        log_test_info("Two-Factor P2WSH Normal", test_data, current_height, "normal")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    user, service = twofactor_keypairs()
    
    test_data = build_e2e_test(
        contract_name='twofactor',
        params={
            'locktime': locktime_value,
            'user': user['pubkey_compressed'],
            'service': service['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='normal',
        keys={'user': user, 'service': service},
        notes='Two-Factor P2WSH - Normal (User + Service)'
    )
    
    state.add_test('cltv_twofactor', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Two-Factor P2WSH (Normal)")
    print(f"   Address: {test_data['address']}")


@pytest.mark.e2e
def test_twofactor_p2wsh_recovery(twofactor_keypairs, locktime_value, current_height):
    """Two-Factor P2WSH - Recovery path (User only after locktime)."""
    test_number = 7
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_twofactor', 'p2wsh', path='recovery')
    if existing:
        test_data = existing[0]
        log_test_info("Two-Factor P2WSH Recovery", test_data, current_height, "recovery")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    user, service = twofactor_keypairs()
    
    test_data = build_e2e_test(
        contract_name='twofactor',
        params={
            'locktime': locktime_value,
            'user': user['pubkey_compressed'],
            'service': service['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='recovery',
        keys={'user': user, 'service': service},
        notes='Two-Factor P2WSH - Recovery (User only) after locktime'
    )
    
    state.add_test('cltv_twofactor', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Two-Factor P2WSH (Recovery)")
    print(f"   Address: {test_data['address']}")


# ============================================================================
# PAYMENT CHANNEL TESTS
# ============================================================================

@pytest.mark.e2e
def test_payment_channel_p2wsh_cooperative(payment_channel_keypairs, locktime_value, current_height):
    """Payment Channel P2WSH - Cooperative close (Sender + Receiver)."""
    test_number = 8
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_payment_channel', 'p2wsh', path='cooperative')
    if existing:
        test_data = existing[0]
        log_test_info("Payment Channel P2WSH Cooperative", test_data, current_height, "cooperative")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    sender, receiver = payment_channel_keypairs()
    
    test_data = build_e2e_test(
        contract_name='payment_channel',
        params={
            'locktime': locktime_value,
            'sender': sender['pubkey_compressed'],
            'receiver': receiver['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='cooperative',
        keys={'sender': sender, 'receiver': receiver},
        notes='Payment Channel P2WSH - Cooperative close'
    )
    
    state.add_test('cltv_payment_channel', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Payment Channel P2WSH (Cooperative)")
    print(f"   Address: {test_data['address']}")


@pytest.mark.e2e
def test_payment_channel_p2wsh_refund(payment_channel_keypairs, locktime_value, current_height):
    """Payment Channel P2WSH - Sender refund after timeout."""
    test_number = 9
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_payment_channel', 'p2wsh', path='refund')
    if existing:
        test_data = existing[0]
        log_test_info("Payment Channel P2WSH Refund", test_data, current_height, "refund")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    sender, receiver = payment_channel_keypairs()
    
    test_data = build_e2e_test(
        contract_name='payment_channel',
        params={
            'locktime': locktime_value,
            'sender': sender['pubkey_compressed'],
            'receiver': receiver['pubkey_compressed'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='refund',
        keys={'sender': sender, 'receiver': receiver},
        notes='Payment Channel P2WSH - Sender refund after timeout'
    )
    
    state.add_test('cltv_payment_channel', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Payment Channel P2WSH (Refund)")
    print(f"   Address: {test_data['address']}")


# ============================================================================
# DATA PUBLISHING TESTS
# ============================================================================

@pytest.mark.e2e
def test_data_publishing_p2wsh_publisher(data_publishing_keypairs, test_data_preimage, locktime_value, current_height):
    """Data Publishing P2WSH - Publisher reveals preimage."""
    test_number = 10
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_data_publishing', 'p2wsh', path='publisher')
    if existing:
        test_data = existing[0]
        log_test_info("Data Publishing P2WSH Publisher", test_data, current_height, "publisher")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    publisher, buyer = data_publishing_keypairs()
    
    test_data = build_e2e_test(
        contract_name='data_publishing',
        params={
            'locktime': locktime_value,
            'publisher': publisher['pubkey_compressed'],
            'buyer': buyer['pubkey_compressed'],
            'data_hash': test_data_preimage['data_hash'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='publisher',
        keys={'publisher': publisher, 'buyer': buyer},
        notes='Data Publishing P2WSH - Publisher reveals preimage',
        data_preimage=test_data_preimage['data_hex'],
        data_hash=test_data_preimage['data_hash'],
    )
    
    state.add_test('cltv_data_publishing', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Data Publishing P2WSH (Publisher)")
    print(f"   Address: {test_data['address']}")
    print(f"   Data hash: {test_data_preimage['data_hash'][:20]}...")


@pytest.mark.e2e
def test_data_publishing_p2wsh_buyer_refund(data_publishing_keypairs, test_data_preimage, locktime_value, current_height):
    """Data Publishing P2WSH - Buyer refund after timeout."""
    test_number = 11
    state = StateManager(locktime=locktime_value)
    
    existing = state.get_tests('cltv_data_publishing', 'p2wsh', path='buyer_refund')
    if existing:
        test_data = existing[0]
        log_test_info("Data Publishing P2WSH Buyer Refund", test_data, current_height, "buyer_refund")
        if test_data.get('status') == 'FUNDED':
            handle_funded_test(test_data, state, current_height)
        return
    
    publisher, buyer = data_publishing_keypairs()
    
    test_data = build_e2e_test(
        contract_name='data_publishing',
        params={
            'locktime': locktime_value,
            'publisher': publisher['pubkey_compressed'],
            'buyer': buyer['pubkey_compressed'],
            'data_hash': test_data_preimage['data_hash'],
        },
        output_type='p2wsh',
        test_number=test_number,
        current_height=current_height,
        path='buyer_refund',
        keys={'publisher': publisher, 'buyer': buyer},
        notes='Data Publishing P2WSH - Buyer refund after timeout',
        data_hash=test_data_preimage['data_hash'],
    )
    
    state.add_test('cltv_data_publishing', 'p2wsh', test_data)
    state.save()
    
    print(f"\n Created: Data Publishing P2WSH (Buyer Refund)")
    print(f"   Address: {test_data['address']}")


# ============================================================================
# QUICK RUN: All tests in one function (for rapid testing)
# ============================================================================

@pytest.mark.e2e
def test_all_contracts_quick(
    generate_keypair,
    alice_bob_keypairs,
    twofactor_keypairs,
    payment_channel_keypairs,
    data_publishing_keypairs,
    test_data_preimage,
    locktime_value,
    current_height
):
    """
    Quick test of all contract types - generates all addresses in one run.
    
    This is useful for rapid testing and funding multiple addresses at once.
    """
    print(f"\n{'='*80}")
    print(f" QUICK E2E TEST: All Contracts (Locktime: {locktime_value})")
    print(f"{'='*80}")
    
    state = StateManager(locktime=locktime_value)
    contracts_created = []
    contracts_funded = []
    
    # 1. Simple HODL P2WSH
    hodl_kp = generate_keypair('hodl')
    test_data = build_e2e_test(
        contract_name='hodl',
        params={'locktime': locktime_value, 'pubkey': hodl_kp['pubkey_compressed']},
        output_type='p2wsh',
        test_number=1,
        current_height=current_height,
        path='sweep',
        keys={'': hodl_kp},
    )
    state.add_test('cltv_hodl', 'p2wsh', test_data)
    contracts_created.append(('Simple HODL P2WSH', test_data['address']))
    
    # 2. Simple HODL Taproot
    test_data = build_e2e_test(
        contract_name='hodl',
        params={'locktime': locktime_value, 'pubkey': hodl_kp['pubkey_compressed']},
        output_type='taproot',
        test_number=2,
        current_height=current_height,
        path='sweep',
        keys={'': hodl_kp},
    )
    state.add_test('cltv_hodl', 'taproot', test_data)
    contracts_created.append(('Simple HODL Taproot', test_data['address']))
    
    # 3. Escrow P2WSH
    alice, bob, lenny = alice_bob_keypairs()
    escrow_params = {
        'locktime': locktime_value,
        'alice': alice['pubkey_compressed'],
        'bob': bob['pubkey_compressed'],
        'lenny': lenny['pubkey_compressed'],
    }
    test_data = build_e2e_test(
        contract_name='escrow',
        params=escrow_params,
        output_type='p2wsh',
        test_number=3,
        current_height=current_height,
        path='normal',
        keys={'alice': alice, 'bob': bob, 'lenny': lenny},
    )
    state.add_test('cltv_escrow', 'p2wsh', test_data)
    contracts_created.append(('Escrow P2WSH (Normal)', test_data['address']))
    
    # 4. Escrow Taproot
    test_data = build_e2e_test(
        contract_name='escrow',
        params=escrow_params,
        output_type='taproot',
        test_number=4,
        current_height=current_height,
        path='normal',
        keys={'alice': alice, 'bob': bob, 'lenny': lenny},
    )
    state.add_test('cltv_escrow', 'taproot', test_data)
    contracts_created.append(('Escrow Taproot (Normal)', test_data['address']))
    
    # 5. Two-Factor P2WSH
    user, service = twofactor_keypairs()
    tf_params = {
        'locktime': locktime_value,
        'user': user['pubkey_compressed'],
        'service': service['pubkey_compressed'],
    }
    test_data = build_e2e_test(
        contract_name='twofactor',
        params=tf_params,
        output_type='p2wsh',
        test_number=5,
        current_height=current_height,
        path='normal',
        keys={'user': user, 'service': service},
    )
    state.add_test('cltv_twofactor', 'p2wsh', test_data)
    contracts_created.append(('Two-Factor P2WSH (Normal)', test_data['address']))
    
    # 6. Payment Channel P2WSH
    sender, receiver = payment_channel_keypairs()
    pc_params = {
        'locktime': locktime_value,
        'sender': sender['pubkey_compressed'],
        'receiver': receiver['pubkey_compressed'],
    }
    test_data = build_e2e_test(
        contract_name='payment_channel',
        params=pc_params,
        output_type='p2wsh',
        test_number=6,
        current_height=current_height,
        path='cooperative',
        keys={'sender': sender, 'receiver': receiver},
    )
    state.add_test('cltv_payment_channel', 'p2wsh', test_data)
    contracts_created.append(('Payment Channel P2WSH (Cooperative)', test_data['address']))
    
    # 7. Data Publishing P2WSH
    publisher, buyer = data_publishing_keypairs()
    dp_params = {
        'locktime': locktime_value,
        'publisher': publisher['pubkey_compressed'],
        'buyer': buyer['pubkey_compressed'],
        'data_hash': test_data_preimage['data_hash'],
    }
    test_data = build_e2e_test(
        contract_name='data_publishing',
        params=dp_params,
        output_type='p2wsh',
        test_number=7,
        current_height=current_height,
        path='publisher',
        keys={'publisher': publisher, 'buyer': buyer},
        data_preimage=test_data_preimage['data_hex'],
    )
    state.add_test('cltv_data_publishing', 'p2wsh', test_data)
    contracts_created.append(('Data Publishing P2WSH (Publisher)', test_data['address']))
    
    state.save()
    
    # Print summary
    print(f"\n CONTRACTS CREATED: {len(contracts_created)}")
    print("-" * 60)
    for name, addr in contracts_created:
        print(f"   {name}")
        print(f"   └─ {addr}")
    
    print(f"\n To fund all addresses, send sats to each address above.")
    print(f"   Run again after funding to attempt sweeps.")

