#!/usr/bin/env python3
"""
Full E2E Tests - Complete On-Chain Transaction Lifecycle

This file contains TRUE end-to-end tests that:
1. Create scripts and generate addresses
2. Fund addresses on the configured network (via Electrum wallet)
3. Record all transaction data in state
4. Verify transactions exist on blockchain
5. Sweep outputs when conditions are met

Tests are idempotent:
- If state shows "CREATED": Generate address, attempt funding
- If state shows "FUNDED": Verify on-chain, attempt sweep
- If state shows "SWEPT": Verify sweep transaction
- To rerun: Delete test_state.json

Network Configuration:
    Edit network_config.py to switch between signet and testnet4

Usage:
    pytest test_e2e_full.py -v -s                    # Run all E2E tests
    pytest test_e2e_full.py -k "simple_p2sh" -v -s   # Run specific test
"""

# Configure network from central config
from network_config import configure_electrum, NETWORK_FLAG, NETWORK_NAME
configure_electrum()

import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import pytest

# Add Electrum to path
ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
if os.path.exists(ELECTRUM_DIR):
    sys.path.insert(0, ELECTRUM_DIR)

# Add parent directory for address_helpers import
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from registry import build_script, get_builder, get_sweeper
from script_utils import script_to_p2wsh, script_to_address, ScriptFormat
from test_e2e_stateful import StateManager
from sweep_utils import sweep_funded_output, get_default_destination
from sweepers.base import LockedError, ValidationError
import subprocess
import json

# Import address_helpers for Taproot address generation
from address_helpers import create_payment_channel_address, create_data_publishing_address

# Try to import Electrum (for wallet integration - optional)
try:
    from electrum import SimpleConfig, WalletStorage, Wallet
    ELECTRUM_AVAILABLE = True
except ImportError:
    ELECTRUM_AVAILABLE = False


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Default locktime offset for tests that need to wait
# Set to 0 for immediately spendable tests, or higher for testing CLTV enforcement
DEFAULT_LOCKTIME_OFFSET = 3  # blocks in the future from current height

# Test amount pattern: Each test gets a unique amount = 1000 + test_number
# This allows easy identification of which test created which UTXO
def get_test_amount(test_number: int) -> int:
    """Calculate standardized test amount: 1000 + test_number"""
    return 1000 + test_number

# OP_RETURN configuration for sweep destinations
# Set to True to sweep to OP_RETURN instead of address (useful for testing/documentation)
# Set to False to sweep to normal address (default behavior)
USE_OP_RETURN = True

def get_op_return_label(test_number: int, variant: str = "") -> str:
    """
    Get OP_RETURN label for each test following BIP-65 format:
    "BIP65 Example #{demo_number} {path_type}"
    
    Returns hex-encoded string suitable for OP_RETURN output.
    """
    labels = {
        # P2WSH Tests (#1-10) - All BIP-65 examples
        1: "BIP65 Example #1 Freezing",            # Simple CLTV (Freezing Funds)
        2: "BIP65 Example #2 Escrow Cooperation",  # Escrow: Alice + Bob cooperation
        3: "BIP65 Example #2 Escrow Arbitration Alice",  # Escrow: Lenny + Alice after timeout
        4: "BIP65 Example #2 Escrow Arbitration Bob",    # Escrow: Lenny + Bob after timeout
        5: "BIP65 Example #3 2FA Normal",          # Two-factor: User + Service
        6: "BIP65 Example #3 2FA Recovery",        # Two-factor: User + Recovery after timeout
        7: "BIP65 Example #4 Channel Cooperative", # Payment Channel: Cooperative close
        8: "BIP65 Example #4 Channel Refund",      # Payment Channel: Refund after timeout
        9: "BIP65 Example #5 PayPub Publisher",    # Data Publishing: Publisher reveals
        10: "BIP65 Example #5 PayPub Buyer",       # Data Publishing: Buyer refund
        
        # Taproot Tests (#11-20) - Same BIP-65 examples, Taproot format
        11: "BIP65 Example #1 Freezing",           # Simple CLTV Taproot
        12: "BIP65 Example #2 Escrow Cooperation",  # Escrow: Alice + Bob cooperation
        13: "BIP65 Example #2 Escrow Arbitration Alice", # Escrow: Lenny + Alice after timeout
        14: "BIP65 Example #2 Escrow Arbitration Bob",   # Escrow: Lenny + Bob after timeout
        15: "BIP65 Example #3 2FA Normal",         # Two-factor: User + Service
        16: "BIP65 Example #3 2FA Recovery",       # Two-factor: User + Recovery after timeout
        17: "BIP65 Example #4 Channel Cooperative",# Payment Channel: Cooperative close
        18: "BIP65 Example #4 Channel Refund",     # Payment Channel: Refund after timeout
        19: "BIP65 Example #5 PayPub Publisher",   # Data Publishing: Publisher reveals
        20: "BIP65 Example #5 PayPub Buyer",       # Data Publishing: Buyer refund
    }
    label = labels.get(test_number, f"BIP65 Test #{test_number}")
    return label.encode('utf-8').hex()


# ============================================================================
# TEST LOGGING HELPERS
# ============================================================================

def log_test_info(test_name: str, test_data: Dict, current_height: int, spend_path: str = "N/A"):
    """Print comprehensive test information"""
    print(f"\n{'='*80}")
    print(f"🧪 TEST #{test_data.get('test_number', '?')}: {test_name}")
    print(f"{'='*80}")
    print(f"Status:           {test_data.get('status', 'UNKNOWN')}")
    print(f"Test Number:      {test_data.get('test_number', 'N/A')}")
    print(f"Address:          {test_data.get('address', 'N/A')}")
    print(f"Amount:           {test_data.get('amount_sats', 'Not funded')} sats")
    print(f"Lockheight:       {test_data.get('locktime', 'N/A')} (current: {current_height})")
    print(f"Script Type:      {test_data.get('script_type', 'N/A')}")
    print(f"Format:           {test_data.get('format', 'N/A')}")
    print(f"Spend Path:       {spend_path}")
    
    # Show funding transaction
    if test_data.get('funding_txid'):
        print(f"Funding TXID:     {test_data.get('funding_txid')}")
        print(f"Funding VOUT:     {test_data.get('funding_vout')}")
    
    # Show sweep transaction
    if test_data.get('sweep_txid'):
        print(f"Sweep TXID:       {test_data.get('sweep_txid')}")
    
    # Show data preimage for data publishing tests
    if 'data_publishing' in test_name.lower() and test_data.get('data_preimage'):
        print(f"Data Preimage:    {test_data.get('data_preimage')}")
    elif 'data_publishing' in test_name.lower() and test_data.get('script_params', {}).get('data_hash'):
        print(f"Data Hash:        {test_data.get('script_params', {}).get('data_hash')}")
    
    print(f"{'='*80}\n")


# ============================================================================
# BLOCKCHAIN HELPERS
# ============================================================================

def get_blockchain_height(wallet=None) -> int:
    """Get current blockchain height using Electrum wallet or fallback."""
    if wallet is not None:
        try:
            return wallet.get_local_height()
        except Exception as e:
            print(f"⚠️  Could not get height from wallet: {e}")
    
    # Fallback to subprocess for backward compatibility
    electrum_python = Path.home() / "src/electrum/venv/bin/python3"
    electrum_path = Path.home() / "src/electrum/run_electrum"
    
    try:
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "getinfo"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return info.get('blockchain_height', 100000)
    except Exception as e:
        print(f"⚠️  Could not get blockchain height: {e}")
    
    return 100000  # Default fallback


def handle_funded_test(test_data: Dict, state: StateManager, **sweep_kwargs) -> bool:
    """
    Common handler for tests in FUNDED state - attempts sweep.
    
    Returns:
        True if sweep successful or still locked, False if error
    """
    print(f"💰 Address funded, attempting sweep...")
    print(f"   Address: {test_data.get('address')}")
    print(f"   Amount: {test_data.get('amount_sats')} sats")
    
    # Get current height and attempt sweep
    # Try to get wallet for better height accuracy
    wallet = get_electrum_wallet()
    current_block_height = get_blockchain_height(wallet)
    print(f"   Current height: {current_block_height}")
    print(f"   Locktime: {test_data.get('locktime')}")
    
    try:
        # Determine destination based on USE_OP_RETURN flag
        if USE_OP_RETURN:
            test_number = test_data.get('test_number', 0)
            op_return_hex = get_op_return_label(test_number)
            destination = ('op_return', op_return_hex)
            # Decode for display
            op_return_text = bytes.fromhex(op_return_hex).decode('utf-8')
            print(f"   Destination: OP_RETURN [{op_return_text}]")
        else:
            destination = get_default_destination()
            print(f"   Destination: {destination}")
        
        sweep_txid = sweep_funded_output(
            test_data=test_data,
            destination_address=destination,
            current_height=current_block_height,
            fee_sats=200,
            **sweep_kwargs
        )
        
        # Update state
        test_data['sweep_txid'] = sweep_txid
        test_data['status'] = 'SWEPT'
        test_data['swept_at'] = datetime.now().isoformat()
        state.save()
        
        print(f"\n✅ SWEEP SUCCESSFUL!")
        print(f"   Sweep TXID: {sweep_txid}")
        print(f"   Verify: https://mempool.space/testnet4/tx/{sweep_txid}")
        return True
        
    except LockedError as e:
        print(f"\n🔒 Still locked: {e}")
        print(f"   Wait for height {test_data.get('locktime')} before sweeping")
        return True  # Not an error, just locked
    except Exception as e:
        print(f"\n❌ Sweep failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# WALLET HELPERS
# ============================================================================

def get_electrum_wallet(wallet_path: str = None) -> Optional[object]:
    """
    Get Electrum wallet for funding transactions.
    
    Returns None if wallet not available or not found.
    """
    if not ELECTRUM_AVAILABLE:
        return None
    
    if wallet_path is None:
        # Try default testnet wallet location
        wallet_path = os.path.expanduser("~/.electrum/testnet/wallets/default_wallet")
    
    if not os.path.exists(wallet_path):
        return None
    
    try:
        config = SimpleConfig()
        config.set_key('testnet', True)
        storage = WalletStorage(wallet_path)
        wallet = Wallet(storage, config=config)
        return wallet
    except Exception as e:
        print(f"⚠️  Could not load wallet: {e}")
        return None


def get_sweep_destination(wallet=None) -> Optional[str]:
    """
    Get next available receiving address from Electrum wallet for sweep destination.
    
    This gets a regular wallet address (P2WPKH, P2PKH, etc.) for receiving
    the swept funds. The sweep doesn't need to create another P2SH/script address.
    
    Returns:
        Bitcoin address string, or None if wallet not available
    """
    if wallet is None:
        # Return a default testnet address for testing
        return "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
    
    try:
        # Get next unused receiving address from wallet
        address = wallet.get_receiving_address()
        if address:
            print(f"   📬 Sweep destination from wallet: {address}")
            return address
        else:
            # Fallback to default
            return "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
    except Exception as e:
        print(f"   ⚠️  Could not get wallet address: {e}")
        return "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"


def fund_address(address: str, amount_sats: int, wallet=None) -> Optional[str]:
    """
    Fund an address with testnet coins using Electrum wallet methods.
    
    Returns:
        Transaction ID if successful, None otherwise
    """
    # Input validation
    if not address or not isinstance(address, str):
        raise ValueError("Address must be a non-empty string")
    
    if not isinstance(amount_sats, int) or amount_sats <= 0:
        raise ValueError("Amount must be a positive integer")
    
    if wallet is None:
        print(f"   💡 Manual funding required:")
        print(f"      Address: {address}")
        print(f"      Amount: {amount_sats} satoshis")
        return None
    
    try:
        print(f"   🚀 Attempting to fund {address} with {amount_sats} sats...")
        
        # Use Electrum's transaction building
        from electrum.transaction import PartialTxOutput
        
        # Create output
        output = PartialTxOutput(
            scriptpubkey=wallet.address_to_script(address),
            value=amount_sats
        )
        
        # Get UTXOs and create transaction
        coins = wallet.get_spendable_coins()
        if not coins:
            print(f"   ❌ No spendable coins available")
            return None
        
        tx = wallet.make_unsigned_transaction(coins=coins, outputs=[output], fee=500)
        wallet.sign_transaction(tx)
        
        # Broadcast transaction
        if hasattr(wallet, 'network') and wallet.network:
            result = wallet.network.broadcast_transaction(tx)
            if result:
                print(f"   ✅ Transaction broadcast: {tx.txid()}")
                return tx.txid()
        else:
            print(f"   ⚠️  No network available for broadcasting")
            return None
            
    except Exception as e:
        print(f"   ❌ Funding failed: {e}")
        import traceback
        print(f"   Debug info: {traceback.format_exc()}")
        return None


# ============================================================================
# SIMPLE CLTV E2E TESTS
# ============================================================================



@pytest.mark.e2e
def test_simple_cltv_p2wsh_full_e2e(generate_keypair, current_height):
    """Full E2E: Simple CLTV P2WSH"""
    # Test #1: Amount will be 1001 sats
    test_number = 1
    
    state = StateManager()
    variant = 'p2wsh'
    
    existing_tests = state.get_tests('cltv_simple', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        
        log_test_info("Simple CLTV P2WSH", test_data, current_height, "Normal (single signature)")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state)
        elif status == 'SWEPT':
            print(f"✅ Already swept!")
            print(f"   Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    print(f"\n{'='*80}")
    print(f"🧪 NEW E2E TEST: Simple CLTV P2WSH")
    print(f"{'='*80}")
    
    keypair = generate_keypair('simple_p2wsh')
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {'locktime': locktime, 'pubkey': keypair['pubkey_compressed']}
    script_hex = build_script('cltv_simple_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    print(f"   Using hardcoded test key (simple_p2wsh)")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': locktime,
        'script_type': 'cltv_simple_p2wsh',
        'script_params': {'locktime': locktime, 'pubkey': keypair['pubkey_compressed']},
        'current_height_at_creation': current_height,
        'script_hex': script_hex,
        'pubkey': keypair['pubkey_compressed'],
        'private_key_hex': keypair['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH CLTV test. Awaiting manual funding'
    }
    
    state.add_test('cltv_simple', variant, test_data)
    state.save()
    
    # Verbose logging
    print(f"\n✅ TEST CREATED: Simple CLTV P2WSH")
    print(f"   Address: {address}")
    print(f"   Locktime: {locktime} (current height: {current_height})")
    print(f"   Script Type: {test_data['script_type']}")
    print(f"   Format: {test_data['format']}")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund via wallet API")


# ============================================================================
# ESCROW E2E TESTS
# ============================================================================




@pytest.mark.e2e  
def test_escrow_p2wsh_normal_operations_full_e2e(alice_bob_keypairs, current_height):
    """
    Full E2E: Escrow P2WSH - Normal Operations
    
    BIP-65 Escrow: Alice and Bob operate a business with 2-of-2 multisig.
    Normal path: Both Alice AND Bob sign (anytime, no timeout required).
    """
    # Test #2: Amount will be 1002 sats
    test_number = 2
    
    state = StateManager()
    variant = 'p2wsh_normal_operations'
    
    existing_tests = state.get_tests('cltv_escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_arbitration_path=False)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    # Use test_number suffix to create unique keys per test
    alice, bob, lenny = alice_bob_keypairs('p2wsh')
    print(f'   Using hardcoded test keys')
    
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'alice_pubkey': alice['pubkey_compressed'],
        'bob_pubkey': bob['pubkey_compressed'],
        'lenny_pubkey': lenny['pubkey_compressed']  # NEW: Third party arbitrator
    }
    
    script_hex = build_script('cltv_escrow_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_escrow_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'normal_operations',  # Updated terminology
        'script_hex': script_hex,
        'alice_pubkey': alice['pubkey_compressed'],
        'alice_private_key_repr': str(alice['private_key']),
        'alice_private_key_hex': alice['private_key_hex'],
        'bob_pubkey': bob['pubkey_compressed'],
        'bob_private_key_repr': str(bob['private_key']),
        'bob_private_key_hex': bob['private_key_hex'],
        'lenny_pubkey': lenny['pubkey_compressed'],  # NEW
        'lenny_private_key_repr': str(lenny['private_key']),  # NEW
        'lenny_private_key_hex': lenny['private_key_hex'],  # NEW
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH escrow normal operations (Alice+Bob 2-of-2 multisig)'
    }
    
    state.add_test('cltv_escrow', variant, test_data)
    state.save()
    print(f"✅ P2WSH Escrow Normal Operations - Address: {address}")


@pytest.mark.e2e
def test_escrow_p2wsh_arbitration_full_e2e(alice_bob_keypairs, current_height):
    """
    Full E2E: Escrow P2WSH - Arbitration
    
    BIP-65 Escrow: If Alice or Bob is "hit by a bus", Lenny (lawyer) can
    arbitrate after timeout. Requires Lenny + one of (Alice OR Bob).
    """
    # Test #3: Amount will be 1003 sats
    test_number = 3
    
    state = StateManager()
    variant = 'p2wsh_arbitration'
    
    existing_tests = state.get_tests('cltv_escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_arbitration_path=True, arbitration_co_signer='alice')
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    alice, bob, lenny = alice_bob_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (escrow_p2wsh_alice, bob, lenny)")
    
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'alice_pubkey': alice['pubkey_compressed'],
        'bob_pubkey': bob['pubkey_compressed'],
        'lenny_pubkey': lenny['pubkey_compressed']  # NEW: Third party arbitrator
    }
    
    script_hex = build_script('cltv_escrow_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_escrow_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'arbitration',  # Updated terminology
        'script_hex': script_hex,
        'alice_pubkey': alice['pubkey_compressed'],
        'alice_private_key_repr': str(alice['private_key']),
        'alice_private_key_hex': alice['private_key_hex'],
        'bob_pubkey': bob['pubkey_compressed'],
        'bob_private_key_repr': str(bob['private_key']),
        'bob_private_key_hex': bob['private_key_hex'],
        'lenny_pubkey': lenny['pubkey_compressed'],  # NEW
        'lenny_private_key_repr': str(lenny['private_key']),  # NEW
        'lenny_private_key_hex': lenny['private_key_hex'],  # NEW
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH escrow arbitration (Lenny+Alice 1-of-2 multisig after timeout)'
    }
    
    state.add_test('cltv_escrow', variant, test_data)
    state.save()
    print(f"✅ P2WSH Escrow Arbitration - Address: {address}")


@pytest.mark.e2e
def test_escrow_p2wsh_arbitration_bob_full_e2e(alice_bob_keypairs, current_height):
    """
    Full E2E: Escrow P2WSH - Arbitration (Bob Path)
    
    BIP-65 Escrow: If Alice is "hit by a bus", Lenny (lawyer) can
    arbitrate after timeout with Bob. Requires Lenny + Bob signatures.
    This is the second arbitration path (Bob instead of Alice).
    """
    # Test #4: Amount will be 1004 sats
    test_number = 4
    
    state = StateManager()
    variant = 'p2wsh_arbitration_bob'
    
    existing_tests = state.get_tests('cltv_escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_arbitration_path=True, arbitration_co_signer='bob')
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    alice, bob, lenny = alice_bob_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (escrow_p2wsh_alice, bob, lenny)")
    
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'alice_pubkey': alice['pubkey_compressed'],
        'bob_pubkey': bob['pubkey_compressed'],
        'lenny_pubkey': lenny['pubkey_compressed']
    }
    
    script_hex = build_script('cltv_escrow_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_escrow_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'arbitration_bob',
        'script_hex': script_hex,
        'alice_pubkey': alice['pubkey_compressed'],
        'alice_private_key_repr': str(alice['private_key']),
        'alice_private_key_hex': alice['private_key_hex'],
        'bob_pubkey': bob['pubkey_compressed'],
        'bob_private_key_repr': str(bob['private_key']),
        'bob_private_key_hex': bob['private_key_hex'],
        'lenny_pubkey': lenny['pubkey_compressed'],
        'lenny_private_key_repr': str(lenny['private_key']),
        'lenny_private_key_hex': lenny['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH escrow arbitration (Lenny+Bob 1-of-2 multisig after timeout)'
    }
    
    state.add_test('cltv_escrow', variant, test_data)
    state.save()
    print(f"✅ P2WSH Escrow Arbitration (Bob) - Address: {address}")


# ============================================================================
# TWO-FACTOR WALLET E2E TESTS
# ============================================================================


@pytest.mark.e2e
def test_twofactor_p2wsh_normal_full_e2e(twofactor_keypairs, current_height):
    """Full E2E: Two-Factor Wallet P2WSH - Normal Path"""
    # Test #5: Amount will be 1005 sats
    test_number = 5
    
    state = StateManager()
    variant = 'p2wsh_normal'
    
    existing_tests = state.get_tests('cltv_twofactor', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_recovery_path=False)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    user, service, recovery = twofactor_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (twofactor_p2wsh_user, service, recovery)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'user_pubkey': user['pubkey_compressed'],
        'service_pubkey': service['pubkey_compressed'],
        'recovery_pubkey': recovery['pubkey_compressed']
    }
    
    script_hex = build_script('cltv_twofactor_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_twofactor_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'normal',
        'script_hex': script_hex,
        'user_pubkey': user['pubkey_compressed'],
        'user_private_key_hex': user['private_key_hex'],
        'service_pubkey': service['pubkey_compressed'],
        'service_private_key_hex': service['private_key_hex'],
        'recovery_pubkey': recovery['pubkey_compressed'],
        'recovery_private_key_hex': recovery['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH two-factor normal path (user+service)'
    }
    
    state.add_test('cltv_twofactor', variant, test_data)
    state.save()
    print(f"✅ P2WSH Two-Factor Normal - Address: {address}")


@pytest.mark.e2e
def test_twofactor_p2wsh_recovery_full_e2e(twofactor_keypairs, current_height):
    """Full E2E: Two-Factor Wallet P2WSH - Recovery Path"""
    # Test #6: Amount will be 1006 sats
    test_number = 6
    
    state = StateManager()
    variant = 'p2wsh_recovery'
    
    existing_tests = state.get_tests('cltv_twofactor', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_recovery_path=True)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    user, service, recovery = twofactor_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (twofactor_p2wsh_user, service, recovery)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'user_pubkey': user['pubkey_compressed'],
        'service_pubkey': service['pubkey_compressed'],
        'recovery_pubkey': recovery['pubkey_compressed']
    }
    
    script_hex = build_script('cltv_twofactor_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_twofactor_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'recovery',
        'script_hex': script_hex,
        'user_pubkey': user['pubkey_compressed'],
        'user_private_key_hex': user['private_key_hex'],
        'service_pubkey': service['pubkey_compressed'],
        'service_private_key_hex': service['private_key_hex'],
        'recovery_pubkey': recovery['pubkey_compressed'],
        'recovery_private_key_hex': recovery['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH two-factor recovery path (user+recovery after timeout)'
    }
    
    state.add_test('cltv_twofactor', variant, test_data)
    state.save()
    print(f"✅ P2WSH Two-Factor Recovery - Address: {address}")


# ============================================================================
# PAYMENT CHANNEL E2E TESTS
# ============================================================================


@pytest.mark.e2e
def test_payment_channel_p2wsh_cooperative_full_e2e(payment_keypairs, current_height):
    """Full E2E: Payment Channel P2WSH - Cooperative Close"""
    # Test #7: Amount will be 1007 sats
    test_number = 7
    
    state = StateManager()
    variant = 'p2wsh_cooperative'
    
    existing_tests = state.get_tests('cltv_payment_channel', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_refund_path=False)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    sender, receiver = payment_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (payment_p2wsh_sender, receiver)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'sender_pubkey': sender['pubkey_compressed'],  # Use compressed for P2WSH
        'receiver_pubkey': receiver['pubkey_compressed']  # Use compressed for P2WSH
    }
    
    script_hex = build_script('cltv_payment_channel_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_payment_channel_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'cooperative',
        'script_hex': script_hex,
        'sender_pubkey': sender['pubkey_compressed'],
        'sender_private_key_hex': sender['private_key_hex'],
        'receiver_pubkey': receiver['pubkey_compressed'],
        'receiver_private_key_hex': receiver['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH payment channel cooperative close (sender+receiver multisig)'
    }
    
    state.add_test('cltv_payment_channel', variant, test_data)
    state.save()
    print(f"✅ P2WSH Payment Channel Cooperative - Address: {address}")


@pytest.mark.e2e
def test_payment_channel_p2wsh_refund_full_e2e(payment_keypairs, current_height):
    """Full E2E: Payment Channel P2WSH - Refund Path"""
    # Test #8: Amount will be 1008 sats
    test_number = 8
    
    state = StateManager()
    variant = 'p2wsh_refund'
    
    existing_tests = state.get_tests('cltv_payment_channel', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_refund_path=True)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    sender, receiver = payment_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (payment_p2wsh_sender, receiver)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    params = {
        'locktime': timeout,
        'sender_pubkey': sender['pubkey_compressed'],  # Use compressed for P2WSH
        'receiver_pubkey': receiver['pubkey_compressed']  # Use compressed for P2WSH
    }
    
    script_hex = build_script('cltv_payment_channel_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_payment_channel_p2wsh',
        'script_params': params,
        'current_height_at_creation': current_height,
        'path': 'refund',
        'script_hex': script_hex,
        'sender_pubkey': sender['pubkey_compressed'],
        'sender_private_key_hex': sender['private_key_hex'],
        'receiver_pubkey': receiver['pubkey_compressed'],
        'receiver_private_key_hex': receiver['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'P2WSH payment channel refund (sender only after timeout)'
    }
    
    state.add_test('cltv_payment_channel', variant, test_data)
    state.save()
    print(f"✅ P2WSH Payment Channel Refund - Address: {address}")


@pytest.mark.e2e
def test_payment_channel_taproot_cooperative_full_e2e(payment_keypairs, current_height):
    """
    TEST #16: Taproot Payment Channel - Cooperative Path (Sender + Receiver)
    
    Amount: 1016 sats (1000 + 16)
    Path: Cooperative (any time)
    Keys: Sender + Receiver
    """
    from script_builders.taproot.payment_channel_taproot import create_payment_channel_taproot_address
    from sweepers.taproot.payment_channel_taproot import TaprootPaymentChannelSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 17
    variant = 'taproot_cooperative'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_payment_channel', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Payment Channel Taproot Cooperative (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Payment Channel Taproot Cooperative (Test #{test_number})")
            print(f"{'='*80}")
            try:
                # Extract keys
                sender_privkey = test_data['sender_private_key']
                receiver_privkey = test_data['receiver_private_key']

                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']

                # Script info in sweeper-friendly structure
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'cooperative': {
                            'script': test_data['cooperative_script'],
                            'control_block': test_data['cooperative_control']
                        },
                        'refund': {
                            'script': test_data['refund_script'],
                            'control_block': test_data['refund_control']
                        }
                    }
                }

                # Destination (address or OP_RETURN)
                if USE_OP_RETURN:
                    op_return_hex = get_op_return_label(test_number)
                    dest_address = ('op_return', op_return_hex)
                    print(f"   Destination: OP_RETURN [{bytes.fromhex(op_return_hex).decode('utf-8')}]")
                else:
                    dest_address = get_default_destination()

                # Build sweeper
                sweeper = TaprootPaymentChannelSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )

                # Build sweep transaction
                print(f"   Building sweep transaction (Cooperative path: Sender + Receiver)...")
                sweep_tx_hex = sweeper.sweep_cooperative(sender_privkey, receiver_privkey, dest_address)
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")

                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")

                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()

                    print(f"\n{'='*80}")
                    print(f"✅ TEST #{test_number} COMPLETE: Payment Channel Taproot Cooperative")
                    print(f"{'='*80}")
                else:
                    print(f"❌ Broadcast failed: {result.stderr}")
                    raise Exception(f"Broadcast failed: {result.stderr}")

            except Exception as e:
                print(f"❌ Sweep failed: {e}")
                import traceback
                traceback.print_exc()
                raise
        
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        
        return
    
    # CREATE NEW TEST
    print(f"\n{'='*80}")
    print(f"🆕 CREATING NEW TEST: Payment Channel Taproot Cooperative (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keys
    sender, receiver = payment_keypairs('taproot')
    print(f"   Sender pubkey: {sender['pubkey_compressed']}")
    print(f"   Receiver pubkey: {receiver['pubkey_compressed']}")
    
    # Use current height as locktime (won't be enforced in cooperative path)
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    
    # Build Taproot address
    print(f"   Building Taproot payment channel address (locktime={locktime})...")
    result = create_payment_channel_taproot_address(
        locktime=locktime,
        sender_pubkey=sender['pubkey_compressed'],
        receiver_pubkey=receiver['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    amount_sats = get_test_amount(test_number)
    
    print(f"   Address: {address}")
    print(f"   Amount: {amount_sats} sats")
    print(f"   Output key: {result['output_key']}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': locktime,
        'current_height_at_creation': current_height,
        'path': 'cooperative',
        'sender_pubkey': sender['pubkey_compressed'],
        'sender_private_key': sender['private_key_hex'],
        'receiver_pubkey': receiver['pubkey_compressed'],
        'receiver_private_key': receiver['private_key_hex'],
        'address': address,
        'output_key': result['output_key'],
        'cooperative_script': result['scripts']['cooperative']['script'],
        'cooperative_control': result['scripts']['cooperative']['control_block'],
        'refund_script': result['scripts']['refund']['script'],
        'refund_control': result['scripts']['refund']['control_block'],
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': amount_sats,
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot payment channel cooperative close (sender+receiver 2-of-2)'
    }
    
    state.add_test('cltv_payment_channel', variant, test_data)
    state.save()
    
    print(f"\n{'='*80}")
    print(f"✅ TEST #{test_number} CREATED: Payment Channel Taproot Cooperative")
    print(f"{'='*80}")
    print(f"   Fund this address: {address}")
    print(f"   Amount: {amount_sats} sats")


@pytest.mark.e2e
def test_payment_channel_taproot_refund_full_e2e(payment_keypairs, current_height):
    """
    TEST #17: Taproot Payment Channel - Refund Path (Sender alone after timeout)
    
    Amount: 1017 sats (1000 + 17)
    Path: Refund (sender after CLTV)
    Keys: Sender only
    """
    from script_builders.taproot.payment_channel_taproot import create_payment_channel_taproot_address
    from sweepers.taproot.payment_channel_taproot import TaprootPaymentChannelSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 18
    variant = 'taproot_refund'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_payment_channel', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Payment Channel Taproot Refund (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        print(f"   Locktime: {test_data.get('locktime')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Payment Channel Taproot Refund (Test #{test_number})")
            print(f"{'='*80}")
            
            # Check if locktime has passed
            if current_height < test_data['locktime']:
                print(f"🔒 LOCKED: Current height {current_height} < locktime {test_data['locktime']}")
                print(f"   Wait for {test_data['locktime'] - current_height} more blocks")
                return
            
            try:
                # Extract keys
                sender_privkey = test_data['sender_private_key']

                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']
                locktime = test_data['locktime']

                # Script info in sweeper-friendly structure
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'cooperative': {
                            'script': test_data['cooperative_script'],
                            'control_block': test_data['cooperative_control']
                        },
                        'refund': {
                            'script': test_data['refund_script'],
                            'control_block': test_data['refund_control']
                        }
                    }
                }

                # Destination (address or OP_RETURN)
                if USE_OP_RETURN:
                    op_return_hex = get_op_return_label(test_number)
                    dest_address = ('op_return', op_return_hex)
                    print(f"   Destination: OP_RETURN [{bytes.fromhex(op_return_hex).decode('utf-8')}]")
                else:
                    dest_address = get_default_destination()

                # Build sweeper
                sweeper = TaprootPaymentChannelSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )

                # Build sweep transaction
                print(f"   Building sweep transaction (Refund path: Sender only)...")
                sweep_tx_hex = sweeper.sweep_refund(sender_privkey, dest_address, locktime)
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")

                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")

                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()

                    print(f"\n{'='*80}")
                    print(f"✅ TEST #{test_number} COMPLETE: Payment Channel Taproot Refund")
                    print(f"{'='*80}")
                else:
                    print(f"❌ Broadcast failed: {result.stderr}")
                    raise Exception(f"Broadcast failed: {result.stderr}")

            except Exception as e:
                print(f"❌ Sweep failed: {e}")
                import traceback
                traceback.print_exc()
                raise
        
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        
        return
    
    # CREATE NEW TEST
    print(f"\n{'='*80}")
    print(f"🆕 CREATING NEW TEST: Payment Channel Taproot Refund (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keys
    sender, receiver = payment_keypairs('taproot')
    print(f"   Sender pubkey: {sender['pubkey_compressed']}")
    print(f"   Receiver pubkey: {receiver['pubkey_compressed']}")
    
    # Use current height + DEFAULT_LOCKTIME_OFFSET as locktime
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    
    # Build Taproot address (same as cooperative, different path will be used)
    print(f"   Building Taproot payment channel address (locktime={locktime})...")
    result = create_payment_channel_taproot_address(
        locktime=locktime,
        sender_pubkey=sender['pubkey_compressed'],
        receiver_pubkey=receiver['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    amount_sats = get_test_amount(test_number)
    
    print(f"   Address: {address}")
    print(f"   Amount: {amount_sats} sats")
    print(f"   Output key: {result['output_key']}")
    print(f"   Locktime: {locktime}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': locktime,
        'current_height_at_creation': current_height,
        'path': 'refund',
        'sender_pubkey': sender['pubkey_compressed'],
        'sender_private_key': sender['private_key_hex'],
        'receiver_pubkey': receiver['pubkey_compressed'],
        'receiver_private_key': receiver['private_key_hex'],
        'address': address,
        'output_key': result['output_key'],
        'cooperative_script': result['scripts']['cooperative']['script'],
        'cooperative_control': result['scripts']['cooperative']['control_block'],
        'refund_script': result['scripts']['refund']['script'],
        'refund_control': result['scripts']['refund']['control_block'],
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': amount_sats,
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot payment channel refund (sender only after timeout)'
    }
    
    state.add_test('cltv_payment_channel', variant, test_data)
    state.save()
    
    print(f"\n{'='*80}")
    print(f"✅ TEST #{test_number} CREATED: Payment Channel Taproot Refund")
    print(f"{'='*80}")
    print(f"   Fund this address: {address}")
    print(f"   Amount: {amount_sats} sats")


# ============================================================================
# DATA PUBLISHING (PAYPUB) TESTS - BIP-65 Example #5
# ============================================================================

def test_data_publishing_taproot_publisher_full_e2e(data_publishing_keypairs, test_data_preimage_taproot, current_height):
    """
    TEST #18: Taproot Data Publishing - Publisher Path (Reveal Preimage)
    
    Amount: 1018 sats (1000 + 18)
    Path: Publisher (reveal preimage, any time)
    Keys: Publisher only
    """
    from script_builders.taproot.data_publishing_taproot import create_data_publishing_taproot_address
    from sweepers.taproot.data_publishing_taproot import TaprootDataPublishingSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 19
    variant = 'taproot_publisher'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_data_publishing', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Data Publishing Taproot Publisher (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Data Publishing Taproot Publisher (Test #{test_number})")
            print(f"{'='*80}")
            
            try:
                # Extract keys and data
                publisher_privkey = test_data['publisher_private_key']
                preimage = bytes.fromhex(test_data['data_preimage'])
                
                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount']
                
                # Script info in sweeper-friendly structure
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'publisher': {
                            'script': test_data['publisher_script'],
                            'control_block': test_data['publisher_control_block']
                        },
                        'buyer_refund': {
                            'script': test_data['buyer_refund_script'],
                            'control_block': test_data['buyer_refund_control_block']
                        }
                    }
                }
                
                # Destination (address or OP_RETURN)
                if USE_OP_RETURN:
                    op_return_hex = get_op_return_label(test_number)
                    dest_address = ('op_return', op_return_hex)
                    print(f"   Destination: OP_RETURN [{bytes.fromhex(op_return_hex).decode('utf-8')}]")
                else:
                    dest_address = get_default_destination()
                
                print(f"   Funding UTXO: {funding_txid}:{funding_vout} ({amount_sats} sats)")
                print(f"   Destination: {dest_address}")
                print(f"   Preimage: {preimage.hex()[:32]}... ({len(preimage)} bytes)")
                
                # Build sweeper
                sweeper = TaprootDataPublishingSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )
                
                # Build sweep transaction
                print(f"   Building sweep transaction (Publisher path: Reveal preimage)...")
                sweep_tx_hex = sweeper.sweep_publisher(publisher_privkey, preimage, dest_address)
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   TX hex (first 100 chars): {sweep_tx_hex[:100]}")
                print(f"   TX hex (last 100 chars): {sweep_tx_hex[-100:]}")
                print(f"   Broadcasting...")
                
                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                else:
                    raise Exception(f"Broadcast failed: {result.stderr}")
                
                print(f"\n{'='*80}")
                print(f"✅ SWEEP SUCCESSFUL: Data Publishing Taproot Publisher")
                print(f"{'='*80}")
                print(f"   Sweep TX: {sweep_txid}")
                print(f"   Spent: {amount_sats} sats → {amount_sats - 200} sats (fee: 200 sats)")
                
                # Update state
                test_data['sweep_txid'] = sweep_txid
                test_data['status'] = 'SWEPT'
                test_data['swept_at'] = datetime.now().isoformat()
                state.save()
                
                return
                
            except Exception as e:
                print(f"\n❌ SWEEP FAILED: {e}")
                import traceback
                traceback.print_exc()
                return
        
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
            return
        else:
            print(f"⚠️  Test exists but not funded. Status: {status}")
            return
    
    # ========== CREATE NEW TEST ==========
    
    print(f"\n{'='*80}")
    print(f"🆕 CREATING NEW TEST: Data Publishing Taproot Publisher (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keys
    publisher, buyer = data_publishing_keypairs('taproot')
    print(f"   Using hardcoded test keys (data_taproot_publisher, buyer)")
    
    # Get test data
    data_hash_bytes = test_data_preimage_taproot['data_hash_bytes']
    data_bytes = test_data_preimage_taproot['data_bytes']
    print(f"   Test data: \"{test_data_preimage_taproot['data']}\"")
    print(f"   SHA256: {data_hash_bytes.hex()}")
    
    # Build address
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    result = create_data_publishing_taproot_address(
        locktime=locktime,
        data_hash=data_hash_bytes,
        publisher_pubkey=publisher['pubkey_compressed'],
        buyer_pubkey=buyer['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    amount_sats = get_test_amount(test_number)
    
    print(f"\n{'='*80}")
    print(f"📍 ADDRESS GENERATED: Data Publishing Taproot Publisher")
    print(f"{'='*80}")
    print(f"   Address: {address}")
    print(f"   Amount: {amount_sats} sats")
    print(f"   Locktime: {locktime}")
    print(f"   Output key: {result['output_key']}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'address': address,
        'amount': amount_sats,
        'locktime': locktime,
        'publisher_pubkey': publisher['pubkey_compressed'],
        'publisher_private_key': publisher['private_key_hex'],
        'buyer_pubkey': buyer['pubkey_compressed'],
        'buyer_private_key': buyer['private_key_hex'],
        'data_preimage': data_bytes.hex(),
        'data_hash': data_hash_bytes.hex(),
        'publisher_script': result['scripts']['publisher']['script'],
        'publisher_control_block': result['scripts']['publisher']['control_block'],
        'buyer_refund_script': result['scripts']['buyer_refund']['script'],
        'buyer_refund_control_block': result['scripts']['buyer_refund']['control_block'],
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'status': 'CREATED',
        'created_at': datetime.now().isoformat(),
        'funding_txid': None,
        'funding_vout': None,
        'sweep_txid': None,
        'notes': 'Taproot data publishing publisher path (reveal preimage, any time)'
    }
    
    state.add_test('cltv_data_publishing', variant, test_data)
    state.save()
    
    print(f"\n{'='*80}")
    print(f"✅ TEST #{test_number} CREATED: Data Publishing Taproot Publisher")
    print(f"{'='*80}")
    print(f"   Fund this address: {address}")
    print(f"   Amount: {amount_sats} sats")


def test_data_publishing_taproot_buyer_refund_full_e2e(data_publishing_keypairs, test_data_preimage_taproot, current_height):
    """
    TEST #19: Taproot Data Publishing - Buyer Refund Path (Timeout Fallback)
    
    Amount: 1019 sats (1000 + 19)
    Path: Buyer refund (buyer alone after CLTV)
    Keys: Buyer only
    """
    from script_builders.taproot.data_publishing_taproot import create_data_publishing_taproot_address
    from sweepers.taproot.data_publishing_taproot import TaprootDataPublishingSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 20
    variant = 'taproot_buyer_refund'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_data_publishing', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Data Publishing Taproot Buyer Refund (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        print(f"   Locktime: {test_data.get('locktime')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Data Publishing Taproot Buyer Refund (Test #{test_number})")
            print(f"{'='*80}")
            
            # Check if locktime has passed
            if current_height < test_data['locktime']:
                print(f"🔒 LOCKED: Current height {current_height} < locktime {test_data['locktime']}")
                print(f"   Wait for {test_data['locktime'] - current_height} more blocks")
                return
            
            try:
                # Extract keys
                buyer_privkey = test_data['buyer_private_key']
                
                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount']
                
                # Script info in sweeper-friendly structure
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'publisher': {
                            'script': test_data['publisher_script'],
                            'control_block': test_data['publisher_control_block']
                        },
                        'buyer_refund': {
                            'script': test_data['buyer_refund_script'],
                            'control_block': test_data['buyer_refund_control_block']
                        }
                    }
                }
                locktime = test_data['locktime']
                
                # Destination (address or OP_RETURN)
                if USE_OP_RETURN:
                    op_return_hex = get_op_return_label(test_number)
                    dest_address = ('op_return', op_return_hex)
                    print(f"   Destination: OP_RETURN [{bytes.fromhex(op_return_hex).decode('utf-8')}]")
                else:
                    dest_address = get_default_destination()
                
                print(f"   Funding UTXO: {funding_txid}:{funding_vout} ({amount_sats} sats)")
                print(f"   Destination: {dest_address}")
                print(f"   Locktime: {locktime} (current: {current_height})")
                
                # Build sweeper
                sweeper = TaprootDataPublishingSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )
                
                # Build sweep transaction
                print(f"   Building sweep transaction (Buyer refund path: Buyer after CLTV)...")
                sweep_tx_hex = sweeper.sweep_buyer_refund(buyer_privkey, locktime, dest_address)
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")
                
                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                else:
                    raise Exception(f"Broadcast failed: {result.stderr}")
                
                print(f"\n{'='*80}")
                print(f"✅ SWEEP SUCCESSFUL: Data Publishing Taproot Buyer Refund")
                print(f"{'='*80}")
                print(f"   Sweep TX: {sweep_txid}")
                print(f"   Spent: {amount_sats} sats → {amount_sats - 200} sats (fee: 200 sats)")
                
                # Update state
                test_data['sweep_txid'] = sweep_txid
                test_data['status'] = 'SWEPT'
                test_data['swept_at'] = datetime.now().isoformat()
                state.save()
                
                return
                
            except Exception as e:
                print(f"\n❌ SWEEP FAILED: {e}")
                import traceback
                traceback.print_exc()
                return
        
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
            return
        else:
            print(f"⚠️  Test exists but not funded. Status: {status}")
            return
    
    # ========== CREATE NEW TEST ==========
    
    print(f"\n{'='*80}")
    print(f"🆕 CREATING NEW TEST: Data Publishing Taproot Buyer Refund (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keys
    publisher, buyer = data_publishing_keypairs('taproot')
    print(f"   Using hardcoded test keys (publisher, data_taproot_buyer)")
    
    # Get test data
    data_hash_bytes = test_data_preimage_taproot['data_hash_bytes']
    data_bytes = test_data_preimage_taproot['data_bytes']
    print(f"   Test data: \"{test_data_preimage_taproot['data']}\"")
    print(f"   SHA256: {data_hash_bytes.hex()}")
    
    # Build address
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    result = create_data_publishing_taproot_address(
        locktime=locktime,
        data_hash=data_hash_bytes,
        publisher_pubkey=publisher['pubkey_compressed'],
        buyer_pubkey=buyer['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    amount_sats = get_test_amount(test_number)
    
    print(f"\n{'='*80}")
    print(f"📍 ADDRESS GENERATED: Data Publishing Taproot Buyer Refund")
    print(f"{'='*80}")
    print(f"   Address: {address}")
    print(f"   Amount: {amount_sats} sats")
    print(f"   Locktime: {locktime}")
    print(f"   Output key: {result['output_key']}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'address': address,
        'amount': amount_sats,
        'locktime': locktime,
        'publisher_pubkey': publisher['pubkey_compressed'],
        'publisher_private_key': publisher['private_key_hex'],
        'buyer_pubkey': buyer['pubkey_compressed'],
        'buyer_private_key': buyer['private_key_hex'],
        'data_preimage': data_bytes.hex(),
        'data_hash': data_hash_bytes.hex(),
        'publisher_script': result['scripts']['publisher']['script'],
        'publisher_control_block': result['scripts']['publisher']['control_block'],
        'buyer_refund_script': result['scripts']['buyer_refund']['script'],
        'buyer_refund_control_block': result['scripts']['buyer_refund']['control_block'],
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'status': 'CREATED',
        'created_at': datetime.now().isoformat(),
        'funding_txid': None,
        'funding_vout': None,
        'sweep_txid': None,
        'notes': 'Taproot data publishing buyer refund (buyer alone after timeout)'
    }
    
    state.add_test('cltv_data_publishing', variant, test_data)
    state.save()
    
    print(f"\n{'='*80}")
    print(f"✅ TEST #{test_number} CREATED: Data Publishing Taproot Buyer Refund")
    print(f"{'='*80}")
    print(f"   Fund this address: {address}")
    print(f"   Amount: {amount_sats} sats")


def test_data_publishing_p2wsh_publisher_full_e2e(data_publishing_keypairs, test_data_preimage, current_height):
    """Full E2E: Data Publishing P2WSH - Publisher Path (Reveal Preimage)"""
    # Test #9: Amount will be 1009 sats
    test_number = 9
    
    state = StateManager()
    variant = 'p2wsh_publisher'
    
    existing_tests = state.get_tests('cltv_data_publishing', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_refund_path=False, data_preimage=test_data_preimage['data_hex'])
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    publisher, buyer = data_publishing_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (data_p2wsh_publisher, buyer)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    
    # Use test data fixture
    data_hash = test_data_preimage['data_hash']
    data_hex = test_data_preimage['data_hex']
    
    # Build the script using registry
    params = {
        'locktime': timeout,
        'data_hash': data_hash,
        'publisher_pubkey': publisher['pubkey_compressed'],  # Use compressed for P2WSH
        'buyer_pubkey': buyer['pubkey_compressed']  # Use compressed for P2WSH
    }
    
    script_hex = build_script('cltv_data_publishing_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_data_publishing_p2wsh',
        'script_params': {
            'locktime': timeout,
            'data_hash': data_hash,
            'publisher_pubkey': publisher['pubkey_compressed'],
            'buyer_pubkey': buyer['pubkey_compressed']
        },
        'current_height_at_creation': current_height,
        'path': 'publisher',
        'script_hex': script_hex,
        'data_hash': data_hash,
        'data_preimage': data_hex,
        'publisher_pubkey': publisher['pubkey_compressed'],
        'publisher_private_key_hex': publisher['private_key_hex'],
        'buyer_pubkey': buyer['pubkey_compressed'],
        'buyer_private_key_hex': buyer['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Publisher reveals preimage to claim funds'
    }
    
    state.add_test('cltv_data_publishing', variant, test_data)
    state.save()
    print(f"✅ P2WSH Data Publishing Publisher - Address: {address}")


def test_data_publishing_p2wsh_buyer_refund_full_e2e(data_publishing_keypairs, test_data_preimage, current_height):
    """Full E2E: Data Publishing P2WSH - Buyer Refund Path (After Timeout)"""
    # Test #10: Amount will be 1010 sats
    test_number = 10
    
    state = StateManager()
    variant = 'p2wsh_buyer_refund'
    
    existing_tests = state.get_tests('cltv_data_publishing', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        print(f"\n✅ Test exists - Status: {status}, Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            handle_funded_test(test_data, state, use_refund_path=True)
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    publisher, buyer = data_publishing_keypairs('p2wsh')
    print(f"   Using hardcoded test keys (data_p2wsh_publisher, buyer)")
    timeout = current_height + DEFAULT_LOCKTIME_OFFSET
    
    # Use test data fixture
    data_hash = test_data_preimage['data_hash']
    data_hex = test_data_preimage['data_hex']
    
    # Build the script using registry (same as publisher test, different spending path)
    params = {
        'locktime': timeout,
        'data_hash': data_hash,
        'publisher_pubkey': publisher['pubkey_compressed'],  # Use compressed for P2WSH
        'buyer_pubkey': buyer['pubkey_compressed']  # Use compressed for P2WSH
    }
    
    script_hex = build_script('cltv_data_publishing_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    
    print(f"✅ Generated P2WSH address: {address}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': timeout,
        'script_type': 'cltv_data_publishing_p2wsh',
        'script_params': {
            'locktime': timeout,
            'data_hash': data_hash,
            'publisher_pubkey': publisher['pubkey_compressed'],
            'buyer_pubkey': buyer['pubkey_compressed']
        },
        'current_height_at_creation': current_height,
        'path': 'buyer_refund',
        'script_hex': script_hex,
        'data_hash': data_hash,
        'data_preimage': data_hex,
        'publisher_pubkey': publisher['pubkey_compressed'],
        'publisher_private_key_hex': publisher['private_key_hex'],
        'buyer_pubkey': buyer['pubkey_compressed'],
        'buyer_private_key_hex': buyer['private_key_hex'],
        'format': 'P2WSH',
        'address': address,
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Buyer refunds after timeout (data not delivered)'
    }
    
    state.add_test('cltv_data_publishing', variant, test_data)
    state.save()
    print(f"✅ P2WSH Data Publishing Buyer Refund - Address: {address}")


def test_simple_cltv_taproot_full_e2e(generate_keypair, current_height):
    """
    Full E2E: Simple CLTV Taproot - WORKING IMPLEMENTATION
    
    Test #11: 1011 sats
    Locks coins until a future block height using Taproot script-path spending.
    Uses working taproot_tx_builder.py with manual BIP-341 sighash (no Electrum bugs)
    """
    from taproot_tx_builder import create_taproot_cltv_address, build_taproot_sweep_tx
    from pathlib import Path
    
    state = StateManager()
    variant = 'taproot'
    test_number = 11
    
    existing_tests = state.get_tests('cltv_simple', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status')
        log_test_info("Simple CLTV Taproot", test_data, current_height, "Normal (single sig)")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Simple CLTV Taproot (Test #{test_number})")
            print(f"{'='*80}")
            
            try:
                # IMPORTANT: For FUNDED UTXOs we must use the exact artifacts used to create the address.
                # Recompute legacy artifacts using the original tutorial-based implementation to match funding.
                import sys as _sys, os as _os
                LEGACY_PATH = _os.path.join(_os.path.dirname(__file__), 'archive', 'old_taproot_code')
                if LEGACY_PATH not in _sys.path:
                    _sys.path.insert(0, LEGACY_PATH)
                from taproot_tx_builder import create_taproot_cltv_address as legacy_create_addr, build_taproot_sweep_tx

                legacy = legacy_create_addr(
                    locktime=test_data['locktime'],
                    pubkey_hex=test_data['pubkey'],
                    network='signet' if NETWORK_NAME == 'Signet' else 'testnet'
                )
                # Restore state to legacy artifacts to match the funded witness program
                restored_fields = []
                for k in ('script_hex', 'control_block', 'output_script', 'output_key', 'internal_key'):
                    if test_data.get(k) != legacy.get(k):
                        test_data[k] = legacy.get(k)
                        restored_fields.append(k)
                if restored_fields:
                    print(f"   🔄 Restored funded artifacts: {', '.join(restored_fields)}")
                    state.save()

                # Define Electrum paths (needed for getaddressinfo and broadcast)
                electrum_python = Path.home() / "src/electrum/venv/bin/python3"
                electrum_path = Path.home() / "src/electrum/run_electrum"
                
                # Get destination scriptPubKey
                # Determine destination based on USE_OP_RETURN flag
                if USE_OP_RETURN:
                    # Get test-specific OP_RETURN label
                    test_number = test_data.get('test_number', 0)
                    op_return_hex = get_op_return_label(test_number)
                    destination = ('op_return', op_return_hex)
                    print(f"   Destination: OP_RETURN [{bytes.fromhex(op_return_hex).decode('utf-8')}]")
                    # Build OP_RETURN scriptPubKey directly: OP_RETURN <data>
                    data_bytes = bytes.fromhex(op_return_hex)
                    data_len = len(data_bytes)
                    if data_len <= 75:
                        push_op = bytes([data_len])
                    elif data_len < 256:
                        push_op = bytes([0x4c, data_len])  # OP_PUSHDATA1
                    elif data_len < 65536:
                        push_op = bytes([0x4d]) + data_len.to_bytes(2, 'little')  # OP_PUSHDATA2
                    else:
                        raise ValueError("OP_RETURN data too large")
                    dest_scriptpubkey = (bytes([0x6a]) + push_op + data_bytes).hex()
                else:
                    destination = get_default_destination()
                    print(f"   Destination: {destination}")
                    # Query Electrum for scriptPubKey of the destination address
                    result = subprocess.run(
                        [str(electrum_python), str(electrum_path), NETWORK_FLAG, "getaddressinfo", destination],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        try:
                            addr_info = json.loads(result.stdout.strip())
                            dest_scriptpubkey = addr_info.get('scriptPubKey')
                            if not dest_scriptpubkey:
                                dest_scriptpubkey = "001408c2277a065015c74f6c6593ced9d3f36880ee6d"
                        except Exception:
                            dest_scriptpubkey = "001408c2277a065015c74f6c6593ced9d3f36880ee6d"
                    else:
                        dest_scriptpubkey = "001408c2277a065015c74f6c6593ced9d3f36880ee6d"
                
                # Build sweep transaction using WORKING taproot_tx_builder (manual BIP-341)
                tx_hex, sighash, signature = build_taproot_sweep_tx(
                    txid=test_data['funding_txid'],
                    vout=test_data['funding_vout'],
                    amount=test_data['amount_sats'],
                    scriptpubkey=test_data['output_script'],
                    script=test_data['script_hex'],
                    control_block=test_data['control_block'],
                    privkey_hex=test_data['private_key_hex'],
                    dest_scriptpubkey=dest_scriptpubkey,
                    locktime=test_data['locktime'],
                    fee=200
                )
                
                print(f"   Broadcasting transaction...")
                print(f"   Transaction hex: {tx_hex[:100]}...")
                
                result = subprocess.run(
                    [str(electrum_python), str(electrum_path), NETWORK_FLAG, "broadcast", tx_hex],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    broadcast_output = result.stdout.strip()
                    try:
                        broadcast_result = json.loads(broadcast_output)
                        if isinstance(broadcast_result, list) and len(broadcast_result) == 2:
                            success, txid = broadcast_result
                            if not success:
                                raise Exception(f"Broadcast returned false: {txid}")
                            sweep_txid = txid
                        elif isinstance(broadcast_result, str):
                            sweep_txid = broadcast_result
                        else:
                            sweep_txid = str(broadcast_result)
                    except json.JSONDecodeError:
                        sweep_txid = broadcast_output.strip('"')
                    
                    if not sweep_txid or len(sweep_txid) != 64:
                        raise Exception(f"Invalid TXID from broadcast: {sweep_txid}")
                    
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                    
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TX: {sweep_txid}")
                    print(f"   Sighash: {sighash.hex()}")
                    print(f"   Verify: https://mempool.space/signet/tx/{sweep_txid}")
                else:
                    error_msg = result.stderr or result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                import traceback
                traceback.print_exc()
                
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    # CREATE NEW TEST
    print(f"\n{'='*80}")
    print(f"🧪 NEW E2E TEST: Simple CLTV Taproot (Test #{test_number})")
    print(f"{'='*80}")
    
    keypair = generate_keypair('simple_taproot')
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    
    # Use taproot_tx_builder to create address (manual BIP-341, no Electrum)
    address_result = create_taproot_cltv_address(
        locktime=locktime,
        pubkey_hex=keypair['pubkey_compressed'],
        network='signet' if NETWORK_NAME == 'Signet' else 'testnet'
    )
    
    print(f"✅ Generated Taproot address: {address_result['address']}")
    print(f"   Using hardcoded test key (simple_taproot)")
    print(f"   Internal key (NUMS): {address_result['internal_key']}")
    print(f"   Output key: {address_result['output_key']}")
    
    test_data = {
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'locktime': locktime,
        'script_type': 'cltv_simple_taproot',
        'current_height_at_creation': current_height,
        'script_hex': address_result['script_hex'],
        'pubkey': keypair['pubkey_compressed'],
        'private_key_hex': keypair['private_key_hex'],
        'format': 'TAPROOT',
        'address': address_result['address'],
        'output_script': address_result['output_script'],
        'control_block': address_result['control_block'],
        'internal_key': address_result['internal_key'],
        'output_key': address_result['output_key'],
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': get_test_amount(test_number),
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot CLTV test using manual BIP-341 (no Electrum bugs)'
    }
    
    state.add_test('cltv_simple', variant, test_data)
    state.save()
    
    print(f"\n✅ TEST CREATED: Simple CLTV Taproot")
    print(f"   Address: {address_result['address']}")
    print(f"   Locktime: {locktime} (current height: {current_height})")
    print(f"   Script Type: {test_data['script_type']}")
    print(f"   Format: TAPROOT")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund via wallet API")


@pytest.mark.e2e
def test_escrow_taproot_normal_operations_full_e2e(generate_keypair, current_height):
    """
    TEST #11: Taproot Escrow - Normal Operations Path (Alice + Bob)
    
    Tests the normal cooperation path where Alice and Bob both agree.
    Uses 2-leaf Merkle tree with CHECKSIGADD for arbitration path.
    """
    from script_builders.taproot.escrow_taproot import create_taproot_escrow_address
    from sweepers.taproot.escrow_taproot import TaprootEscrowSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 12
    variant = 'taproot_normal'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Escrow Taproot Normal (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Escrow Taproot Normal (Test #{test_number})")
            print(f"{'='*80}")
            
            try:
                # Extract keys
                alice_privkey = test_data['alice_private_key']
                bob_privkey = test_data['bob_private_key']
                
                # Get funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']
                
                # Get script info
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'normal': {
                            'script': test_data['normal_script'],
                            'control_block': test_data['normal_control']
                        },
                        'arbitration': {
                            'script': test_data['arbitration_script'],
                            'control_block': test_data['arbitration_control']
                        }
                    }
                }
                
                # Build sweeper
                sweeper = TaprootEscrowSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )
                
                # Destination address
                dest_address = "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
                
                # Build sweep transaction
                print(f"   Building sweep transaction (Normal path: Alice + Bob)...")
                sweep_tx_hex = sweeper.sweep_normal(alice_privkey, bob_privkey, dest_address)
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")
                
                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")
                    
                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                raise
                
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    # Create new test
    print(f"\n{'='*80}")
    print(f"🧪 NEW E2E TEST: Escrow Taproot Normal (Test #{test_number})")
    print(f"{'='*80}")
    
    # Generate keypairs for Alice, Bob, and Lenny
    alice_keypair = generate_keypair('escrow_taproot_alice')
    bob_keypair = generate_keypair('escrow_taproot_bob')
    lenny_keypair = generate_keypair('escrow_taproot_lenny')
    
    alice_pubkey = alice_keypair['pubkey_compressed']
    bob_pubkey = bob_keypair['pubkey_compressed']
    lenny_pubkey = lenny_keypair['pubkey_compressed']
    
    print(f"   Alice: {alice_pubkey[:16]}...")
    print(f"   Bob: {bob_pubkey[:16]}...")
    print(f"   Lenny: {lenny_pubkey[:16]}...")
    
    # Build Taproot escrow address
    locktime = current_height  # Already unlocked for testing
    result = create_taproot_escrow_address(
        locktime=locktime,
        alice_pubkey=alice_pubkey,
        bob_pubkey=bob_pubkey,
        lenny_pubkey=lenny_pubkey,
        network='signet'
    )
    
    print(f"✅ Generated Taproot Escrow address: {result['address']}")
    print(f"   Locktime: {locktime} (current height: {current_height})")
    print(f"   Format: Taproot (bech32m)")
    print(f"   Merkle Root: {result['merkle_root'][:16]}...")
    
    # Save to state
    test_data = {
        'test_number': test_number,
        'address': result['address'],
        'locktime': locktime,
        'alice_pubkey': alice_pubkey,
        'alice_private_key': alice_keypair['private_key_hex'],
        'bob_pubkey': bob_pubkey,
        'bob_private_key': bob_keypair['private_key_hex'],
        'lenny_pubkey': lenny_pubkey,
        'lenny_private_key': lenny_keypair['private_key_hex'],
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'normal_script': result['scripts']['normal']['script'],
        'normal_control': result['scripts']['normal']['control_block'],
        'arbitration_script': result['scripts']['arbitration']['script'],
        'arbitration_control': result['scripts']['arbitration']['control_block'],
        'script_type': 'escrow',
        'format': 'TAPROOT',
        'amount_sats': get_test_amount(test_number),
        'funding_txid': None,
        'funding_vout': 0,
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot escrow - normal path (Alice + Bob)'
    }
    
    state.add_test('escrow', variant, test_data)
    state.save()
    
    print(f"✅ TEST CREATED: Escrow Taproot Normal")
    print(f"   Address: {result['address']}")
    print(f"   Amount: 1011 sats (1100 + {test_number})")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund")


@pytest.mark.e2e
def test_escrow_taproot_arbitration_full_e2e(generate_keypair, current_height):
    """
    TEST #12: Taproot Escrow - Arbitration Path (Lenny + Alice/Bob)
    
    Tests the arbitration path where Lenny mediates with either Alice or Bob.
    Uses CHECKSIGADD to accept either Alice OR Bob as second signer.
    """
    from script_builders.taproot.escrow_taproot import create_taproot_escrow_address
    from sweepers.taproot.escrow_taproot import TaprootEscrowSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 13
    variant = 'taproot_arbitration'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Escrow Taproot Arbitration (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Escrow Taproot Arbitration (Test #{test_number})")
            print(f"{'='*80}")
            
            try:
                # Extract keys (use Lenny + Alice for this test)
                lenny_privkey = test_data['lenny_private_key']
                alice_privkey = test_data['alice_private_key']
                locktime = test_data['locktime']
                
                # Get funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']
                
                # Get script info
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'normal': {
                            'script': test_data['normal_script'],
                            'control_block': test_data['normal_control']
                        },
                        'arbitration': {
                            'script': test_data['arbitration_script'],
                            'control_block': test_data['arbitration_control']
                        }
                    }
                }
                
                # Build sweeper
                sweeper = TaprootEscrowSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )
                
                # Destination address
                dest_address = "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
                
                # Build sweep transaction
                print(f"   Building sweep transaction (Arbitration path: Lenny + Alice)...")
                sweep_tx_hex = sweeper.sweep_arbitration(
                    lenny_privkey,
                    alice_privkey,
                    dest_address,
                    locktime,
                    use_alice=True
                )
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")
                
                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")
                    
                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                raise
                
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    # Create new test
    print(f"\n{'='*80}")
    print(f"🧪 NEW E2E TEST: Escrow Taproot Arbitration (Test #{test_number})")
    print(f"{'='*80}")
    
    # Generate keypairs for Alice, Bob, and Lenny (reuse same keys as normal path)
    alice_keypair = generate_keypair('escrow_taproot_alice')
    bob_keypair = generate_keypair('escrow_taproot_bob')
    lenny_keypair = generate_keypair('escrow_taproot_lenny')
    
    alice_pubkey = alice_keypair['pubkey_compressed']
    bob_pubkey = bob_keypair['pubkey_compressed']
    lenny_pubkey = lenny_keypair['pubkey_compressed']
    
    print(f"   Alice: {alice_pubkey[:16]}...")
    print(f"   Bob: {bob_pubkey[:16]}...")
    print(f"   Lenny: {lenny_pubkey[:16]}...")
    
    # Build Taproot escrow address
    locktime = current_height  # Already unlocked for testing
    result = create_taproot_escrow_address(
        locktime=locktime,
        alice_pubkey=alice_pubkey,
        bob_pubkey=bob_pubkey,
        lenny_pubkey=lenny_pubkey,
        network='signet'
    )
    
    print(f"✅ Generated Taproot Escrow address: {result['address']}")
    print(f"   Locktime: {locktime} (current height: {current_height})")
    print(f"   Format: Taproot (bech32m)")
    print(f"   Merkle Root: {result['merkle_root'][:16]}...")
    
    # Save to state
    test_data = {
        'test_number': test_number,
        'address': result['address'],
        'locktime': locktime,
        'alice_pubkey': alice_pubkey,
        'alice_private_key': alice_keypair['private_key_hex'],
        'bob_pubkey': bob_pubkey,
        'bob_private_key': bob_keypair['private_key_hex'],
        'lenny_pubkey': lenny_pubkey,
        'lenny_private_key': lenny_keypair['private_key_hex'],
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'normal_script': result['scripts']['normal']['script'],
        'normal_control': result['scripts']['normal']['control_block'],
        'arbitration_script': result['scripts']['arbitration']['script'],
        'arbitration_control': result['scripts']['arbitration']['control_block'],
        'script_type': 'escrow',
        'format': 'TAPROOT',
        'amount_sats': get_test_amount(test_number),
        'funding_txid': None,
        'funding_vout': 0,
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot escrow - arbitration path (Lenny + Alice/Bob)'
    }
    
    state.add_test('escrow', variant, test_data)
    state.save()
    
    print(f"✅ TEST CREATED: Escrow Taproot Arbitration")
    print(f"   Address: {result['address']}")
    print(f"   Amount: 1012 sats (1100 + {test_number})")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund")


def test_escrow_taproot_arbitration_bob_full_e2e(generate_keypair, current_height):
    """
    TEST #13: Taproot Escrow - Arbitration Path (Lenny + Bob)
    
    Tests the arbitration path where Lenny mediates with Bob (instead of Alice).
    Uses same escrow address as test #12 but different spend path.
    """
    from script_builders.taproot.escrow_taproot import create_taproot_escrow_address
    from sweepers.taproot.escrow_taproot import TaprootEscrowSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 14
    variant = 'taproot_arbitration_bob'  # Different variant for Bob co-signer
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('escrow', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Escrow Taproot Arbitration Bob (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Escrow Taproot Arbitration Bob (Test #{test_number})")
            print(f"{'='*80}")
            
            try:
                # Extract keys (use Lenny + Bob for this test)
                lenny_privkey = test_data['lenny_private_key']
                bob_privkey = test_data['bob_private_key']
                locktime = test_data['locktime']
                
                # Get funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']
                
                # Get script info
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'normal': {
                            'script': test_data['normal_script'],
                            'control_block': test_data['normal_control']
                        },
                        'arbitration': {
                            'script': test_data['arbitration_script'],
                            'control_block': test_data['arbitration_control']
                        }
                    }
                }
                
                # Build sweeper
                sweeper = TaprootEscrowSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )
                
                # Destination address
                dest_address = "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
                
                # Build sweep transaction
                print(f"   Building sweep transaction (Arbitration path: Lenny + Bob)...")
                sweep_tx_hex = sweeper.sweep_arbitration(
                    lenny_privkey,
                    bob_privkey,
                    dest_address,
                    locktime,
                    use_alice=False  # Use Bob instead
                )
                
                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")
                
                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")
                    
                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                raise
                
        elif status == 'SWEPT':
            print(f"✅ Already swept! Sweep TX: {test_data.get('sweep_txid')}")
        return
    
    # Create new test (same address as test #12, but different funding UTXO)
    print(f"\n{'='*80}")
    print(f"🧪 NEW E2E TEST: Escrow Taproot Arbitration Bob (Test #{test_number})")
    print(f"{'='*80}")
    
    # Generate keypairs for Alice, Bob, and Lenny (reuse same keys as other escrow tests)
    alice_keypair = generate_keypair('escrow_taproot_alice')
    bob_keypair = generate_keypair('escrow_taproot_bob')
    lenny_keypair = generate_keypair('escrow_taproot_lenny')
    
    alice_pubkey = alice_keypair['pubkey_compressed']
    bob_pubkey = bob_keypair['pubkey_compressed']
    lenny_pubkey = lenny_keypair['pubkey_compressed']
    
    print(f"   Alice: {alice_pubkey[:16]}...")
    print(f"   Bob: {bob_pubkey[:16]}...")
    print(f"   Lenny: {lenny_pubkey[:16]}...")
    
    # Build Taproot escrow address (same as test #11 and #12)
    locktime = current_height + DEFAULT_LOCKTIME_OFFSET
    result = create_taproot_escrow_address(
        locktime=locktime,
        alice_pubkey=alice_pubkey,
        bob_pubkey=bob_pubkey,
        lenny_pubkey=lenny_pubkey,
        network='signet'
    )
    
    print(f"✅ Generated Taproot Escrow address: {result['address']}")
    print(f"   Locktime: {locktime} (current height: {current_height})")
    print(f"   Format: Taproot (bech32m)")
    print(f"   Merkle Root: {result['merkle_root'][:16]}...")
    print(f"   Same address as tests #11 and #12 (different spend paths)")
    
    # Save to state
    test_data = {
        'test_number': test_number,
        'address': result['address'],
        'locktime': locktime,
        'alice_pubkey': alice_pubkey,
        'alice_private_key': alice_keypair['private_key_hex'],
        'bob_pubkey': bob_pubkey,
        'bob_private_key': bob_keypair['private_key_hex'],
        'lenny_pubkey': lenny_pubkey,
        'lenny_private_key': lenny_keypair['private_key_hex'],
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'normal_script': result['scripts']['normal']['script'],
        'normal_control': result['scripts']['normal']['control_block'],
        'arbitration_script': result['scripts']['arbitration']['script'],
        'arbitration_control': result['scripts']['arbitration']['control_block'],
        'script_type': 'escrow',
        'format': 'TAPROOT',
        'amount_sats': get_test_amount(test_number),
        'funding_txid': None,
        'funding_vout': 0,
        'status': 'CREATED',
        'sweep_txid': None,
        'notes': 'Taproot escrow - arbitration path (Lenny + Bob)',
        'co_signer': 'bob'
    }
    
    state.add_test('escrow', variant, test_data)
    state.save()
    
    print(f"✅ TEST CREATED: Escrow Taproot Arbitration Bob")
    print(f"   Address: {result['address']}")
    print(f"   Amount: {test_data['amount_sats']} sats")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund")


# ============================================================================
# Two-Factor Wallet - Taproot Tests (#14, #15)
# ============================================================================

@pytest.mark.e2e
def test_twofactor_taproot_cooperative_full_e2e(twofactor_keypairs, current_height):
    """
    TEST #14: Taproot Two-Factor - Cooperative Path (User + Service)
    
    Amount: 1014 sats (1000 + 14)
    Path: Cooperative (any time)
    Keys: User + Service
    
    NOTE: Currently uses Electrum-based builder which has BIP-341 bugs.
    Needs rewrite similar to test #10 using taproot_tx_builder.py pattern.
    """
    from script_builders.taproot.twofactor_taproot import create_twofactor_taproot_address
    from sweepers.taproot.twofactor_taproot import TaprootTwoFactorSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 15
    variant = 'taproot_cooperative'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_twofactor', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Two-Factor Taproot Cooperative (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Two-Factor Taproot Cooperative (Test #{test_number})")
            print(f"{'='*80}")
            try:
                # Extract keys
                user_privkey = test_data['user_private_key']
                service_privkey = test_data['service_private_key']

                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']

                # Script info in sweeper-friendly structure
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'normal': {
                            'script': test_data['normal_script'],
                            'control_block': test_data['normal_control']
                        },
                        'recovery': {
                            'script': test_data['recovery_script'],
                            'control_block': test_data['recovery_control']
                        }
                    }
                }

                # Build sweeper
                sweeper = TaprootTwoFactorSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )

                # Destination address
                dest_address = get_default_destination()

                # Build sweep transaction
                print(f"   Building sweep transaction (Cooperative path: User + Service)...")
                sweep_tx_hex = sweeper.sweep_cooperative(user_privkey, service_privkey, dest_address)

                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")

                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")

                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                raise
        
        elif status == 'SWEPT':
            print(f"✅ Already swept!")
            print(f"   Sweep TXID: {test_data.get('sweep_txid')}")
        
        return
    
    # Create new test
    print(f"\n{'='*80}")
    print(f"🔨 CREATING NEW TEST: Two-Factor Taproot Cooperative (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keypairs
    user, service, recovery = twofactor_keypairs('taproot')
    
    # Build Taproot two-factor scripts (manual BIP-341)
    result = create_twofactor_taproot_address(
        locktime=current_height,
        user_pubkey=user['pubkey_compressed'],
        server_pubkey=service['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    print(f"   Address: {address}")
    print(f"   Locktime: {current_height}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'script_type': 'cltv_twofactor_taproot',
        'address': address,
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'normal_script': result['scripts']['normal']['script'],
        'normal_control': result['scripts']['normal']['control_block'],
        'recovery_script': result['scripts']['recovery']['script'],
        'recovery_control': result['scripts']['recovery']['control_block'],
        'locktime': current_height,
        'user_pubkey': user['pubkey_compressed'],
        'service_pubkey': service['pubkey_compressed'],
        'recovery_pubkey': recovery['pubkey_compressed'],
        'user_private_key': user['private_key_hex'],
        'service_private_key': service['private_key_hex'],
        'recovery_private_key': recovery['private_key_hex'],
        'format': 'TAPROOT',
        'status': 'CREATED',
        'created_at': datetime.now().isoformat(),
        'amount_sats': get_test_amount(test_number),
        'notes': 'Taproot two-factor - cooperative path (User + Service)'
    }
    
    state.add_test('cltv_twofactor', variant, test_data)
    state.save()
    
    print(f"\n✅ TEST #{test_number} CREATED")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund")


@pytest.mark.e2e
def test_twofactor_taproot_recovery_full_e2e(twofactor_keypairs, current_height):
    """
    TEST #15: Taproot Two-Factor - Recovery Path (User + Recovery after timeout)
    
    Amount: 1015 sats (1000 + 15)
    Path: Recovery (after timeout)
    Keys: User + Recovery
    
    Uses same address as test #14 but spends via recovery path.
    """
    from script_builders.taproot.twofactor_taproot import create_twofactor_taproot_address
    from sweepers.taproot.twofactor_taproot import TaprootTwoFactorSweeper
    import subprocess
    import os
    from datetime import datetime
    
    state = StateManager()
    test_number = 16
    variant = 'taproot_recovery'
    
    print(f"\n📊 Current blockchain height: {current_height}")
    
    # Check if test already exists
    existing_tests = state.get_tests('cltv_twofactor', variant)
    if existing_tests:
        test_data = existing_tests[0]
        status = test_data.get('status', 'UNKNOWN')
        
        print(f"\n{'='*80}")
        print(f"🔍 EXISTING TEST FOUND: Two-Factor Taproot Recovery (Test #{test_number})")
        print(f"{'='*80}")
        print(f"   Status: {status}")
        print(f"   Address: {test_data.get('address')}")
        
        if status == 'FUNDED':
            print(f"\n{'='*80}")
            print(f"💰 SWEEPING FUNDED TEST: Two-Factor Taproot Recovery (Test #{test_number})")
            print(f"{'='*80}")
            try:
                # Extract keys
                user_privkey = test_data['user_private_key']
                locktime = test_data['locktime']

                # Funding details
                funding_txid = test_data['funding_txid']
                funding_vout = test_data['funding_vout']
                amount_sats = test_data['amount_sats']

                # Script info
                script_info = {
                    'output_key': test_data['output_key'],
                    'scripts': {
                        'normal': {
                            'script': test_data['normal_script'],
                            'control_block': test_data['normal_control']
                        },
                        'recovery': {
                            'script': test_data['recovery_script'],
                            'control_block': test_data['recovery_control']
                        }
                    }
                }

                # Build sweeper
                sweeper = TaprootTwoFactorSweeper(
                    funding_txid=funding_txid,
                    funding_vout=funding_vout,
                    amount_sats=amount_sats,
                    script_info=script_info,
                    network='signet'
                )

                # Destination address
                dest_address = get_default_destination()

                # Build sweep transaction (recovery path)
                print(f"   Building sweep transaction (Recovery path: User only, locktime {locktime})...")
                sweep_tx_hex = sweeper.sweep_recovery(user_privkey, dest_address, locktime)

                print(f"   Sweep TX size: {len(sweep_tx_hex)//2} bytes")
                print(f"   Broadcasting...")

                # Broadcast using Electrum
                electrum_python = os.path.expanduser("~/src/electrum/venv/bin/python3")
                electrum_path = os.path.expanduser("~/src/electrum/run_electrum")
                result = subprocess.run(
                    [electrum_python, electrum_path, '--signet', 'broadcast', sweep_tx_hex],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    sweep_txid = result.stdout.strip()
                    print(f"✅ Sweep successful!")
                    print(f"   Sweep TXID: {sweep_txid}")
                    print(f"   View: https://mempool.space/signet/tx/{sweep_txid}")

                    # Update state
                    test_data['sweep_txid'] = sweep_txid
                    test_data['status'] = 'SWEPT'
                    test_data['swept_at'] = datetime.now().isoformat()
                    state.save()
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    print(f"❌ Broadcast failed: {error_msg}")
                    raise Exception(error_msg)
            except Exception as e:
                print(f"❌ Sweep error: {e}")
                raise
        
        elif status == 'SWEPT':
            print(f"✅ Already swept!")
            print(f"   Sweep TXID: {test_data.get('sweep_txid')}")
        
        return
    
    # Create new test
    print(f"\n{'='*80}")
    print(f"🔨 CREATING NEW TEST: Two-Factor Taproot Recovery (Test #{test_number})")
    print(f"{'='*80}")
    
    # Get keypairs (same as cooperative test)
    user, service, recovery = twofactor_keypairs('taproot')
    
    # Build Taproot two-factor scripts (manual BIP-341)
    result = create_twofactor_taproot_address(
        locktime=current_height,
        user_pubkey=user['pubkey_compressed'],
        server_pubkey=service['pubkey_compressed'],
        network='signet'
    )
    
    address = result['address']
    print(f"   Address: {address}")
    print(f"   Locktime: {current_height}")
    
    # Save test data
    test_data = {
        'test_number': test_number,
        'script_type': 'cltv_twofactor_taproot',
        'address': address,
        'output_key': result['output_key'],
        'merkle_root': result['merkle_root'],
        'internal_key': result['internal_key'],
        'normal_script': result['scripts']['normal']['script'],
        'normal_control': result['scripts']['normal']['control_block'],
        'recovery_script': result['scripts']['recovery']['script'],
        'recovery_control': result['scripts']['recovery']['control_block'],
        'locktime': current_height,
        'user_pubkey': user['pubkey_compressed'],
        'service_pubkey': service['pubkey_compressed'],
        'recovery_pubkey': recovery['pubkey_compressed'],
        'user_private_key': user['private_key_hex'],
        'service_private_key': service['private_key_hex'],
        'recovery_private_key': recovery['private_key_hex'],
        'format': 'TAPROOT',
        'status': 'CREATED',
        'created_at': datetime.now().isoformat(),
        'amount_sats': get_test_amount(test_number),
        'notes': 'Taproot two-factor - recovery path (User only after CLTV)'
    }
    
    state.add_test('cltv_twofactor', variant, test_data)
    state.save()
    
    print(f"\n✅ TEST #{test_number} CREATED")
    print(f"   Status: CREATED (awaiting funding)")
    print(f"   Run with --fund flag to automatically fund")


if __name__ == "__main__":
    print(__doc__)
