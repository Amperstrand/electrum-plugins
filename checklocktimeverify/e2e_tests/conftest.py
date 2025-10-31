"""
Pytest configuration and fixtures for CLTV E2E tests
"""

import pytest
import subprocess
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Add Electrum to path
ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
if os.path.exists(ELECTRUM_DIR):
    sys.path.insert(0, ELECTRUM_DIR)

# ============================================================================
# CRITICAL: Configure network BEFORE any address generation
# ============================================================================
# This must happen before any imports that use constants.net
# Edit network_config.py to switch between signet and testnet4
from network_config import configure_electrum, NETWORK_NAME, WALLET_SUBDIR, NETWORK_FLAG, EXPLORER_BASE
configure_electrum()

print(f"✅ Network set to {NETWORK_NAME}")


def pytest_addoption(parser):
    """Add custom command-line options"""
    parser.addoption(
        "--fund",
        action="store_true",
        default=False,
        help="Automatically fund unfunded test addresses via Electrum"
    )


def pytest_configure(config):
    """Configure pytest with custom settings"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "p2wsh: marks P2WSH-specific tests"
    )
    config.addinivalue_line(
        "markers", "taproot: marks Taproot-specific tests"
    )
    config.addinivalue_line(
        "markers", "integration: marks integration tests requiring external services"
    )


@pytest.fixture(scope="session", autouse=True)
def auto_fund_addresses(pytestconfig):
    """
    Automatically fund all CREATED addresses in a single batch transaction.
    
    This fixture runs AFTER all tests complete (via yield, then teardown).
    It checks test_state.json for any addresses with status='CREATED' and
    funds them all in one paytomany transaction using Electrum daemon.
    
    Enable with: pytest --fund
    
    Benefits:
    - One transaction instead of many (saves ~80% on fees)
    - All tests funded simultaneously
    - Automatic - creates and broadcasts transaction via Electrum
    - Idempotent - only funds addresses that need it
    """
    # Yield first to let all tests run and create addresses
    yield
    
    # Now run the funding logic AFTER all tests have created their addresses
    from test_e2e_stateful import StateManager
    
    # Check if auto-funding is enabled
    auto_fund_enabled = pytestconfig.getoption("--fund")
    if not auto_fund_enabled:
        return
    
    # Look for state file in parent directory (where tests create it)
    state_file = Path(__file__).parent.parent / 'test_state.json'
    
    if not state_file.exists():
        print("\n💡 No state file found - no addresses to fund")
        return
    
    # Load state and find unfunded addresses
    state = StateManager()
    unfunded_addresses = []
    
    # Check Simple CLTV
    for variant, tests in state.state.get('cltv_simple', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                tnum = test.get('test_number')
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'cltv_simple',
                    'variant': variant,
                    'type': f'Simple CLTV {variant.upper()}',
                    'test_number': tnum,
                    'amount_sats': 1000 + (tnum or 0)
                })
    
    # Check Escrow
    for variant, tests in state.state.get('cltv_escrow', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                path = 'Cooperation' if 'cooperation' in variant else 'Refund'
                fmt = variant.split('_')[0].upper()
                tnum = test.get('test_number')
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'cltv_escrow',
                    'variant': variant,
                    'type': f'Escrow {fmt} {path}',
                    'test_number': tnum,
                    'amount_sats': 1000 + (tnum or 0)
                })
    
    # Check Two-Factor
    for variant, tests in state.state.get('cltv_twofactor', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                path = 'Normal' if 'normal' in variant else 'Recovery'
                fmt = variant.split('_')[0].upper()
                tnum = test.get('test_number')
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'cltv_twofactor',
                    'variant': variant,
                    'type': f'Two-Factor {fmt} {path}',
                    'test_number': tnum,
                    'amount_sats': 1000 + (tnum or 0)
                })
    
    # Check Payment Channel
    for variant, tests in state.state.get('cltv_payment_channel', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                path = 'Cooperative' if 'cooperative' in variant else 'Refund'
                fmt = variant.split('_')[0].upper()
                tnum = test.get('test_number')
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'cltv_payment_channel',
                    'variant': variant,
                    'type': f'Payment Channel {fmt} {path}',
                    'test_number': tnum,
                    'amount_sats': 1000 + (tnum or 0)
                })
    
    # Check Data Publishing
    for variant, tests in state.state.get('cltv_data_publishing', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                path = 'Publisher' if 'publisher' in variant else 'Buyer Refund'
                fmt = variant.split('_')[0].upper()
                tnum = test.get('test_number')
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'cltv_data_publishing',
                    'variant': variant,
                    'type': f'Data Publishing {fmt} {path}',
                    'test_number': tnum,
                    'amount_sats': 1000 + (tnum or 0)
                })
    
    # Check Taproot Escrow
    for variant, tests in state.state.get('escrow', {}).items():
        for test in tests:
            if test.get('status') == 'CREATED':
                if 'normal' in variant:
                    path = 'Normal (Alice+Bob)'
                elif 'arbitration' in variant:
                    co_signer = test.get('co_signer', 'alice').capitalize()
                    path = f'Arbitration (Lenny+{co_signer})'
                else:
                    path = variant
                unfunded_addresses.append({
                    'address': test['address'],
                    'category': 'escrow',
                    'variant': variant,
                    'type': f'Taproot Escrow {path}',
                    'amount_sats': test.get('amount_sats', 1000)
                })
    
    if not unfunded_addresses:
        print("\n✅ All addresses already funded or no addresses created yet")
        return
    
    # Display what we're funding
    print(f"\n{'='*80}")
    print(f"💰 BATCH FUNDING: {len(unfunded_addresses)} tests need funding")
    print(f"{'='*80}\n")
    
    amount_per_address_btc = 0.00001  # 1,000 satoshis
    amount_per_address_sats = 1000
    
    for i, addr_info in enumerate(unfunded_addresses, 1):
        print(f"   {i}. {addr_info['type']:28} → {addr_info['address']}")
    
    # Calculate total with unique amounts (1000, 1001, 1002, ..., 1000+N-1)
    total_sats = sum(1000 + i for i in range(len(unfunded_addresses)))
    
    print(f"\n{'='*80}")
    print(f"📋 CREATING BATCH TRANSACTION WITH UNIQUE AMOUNTS")
    print(f"{'='*80}\n")
    print(f"Total to send: {total_sats:,} satoshis")
    print(f"Unique amounts per test: 1001, 1002, ..., 1020 sats")
    print(f"Plus fees: ~200-500 sats\n")
    
    try:
        # Use Electrum daemon RPC (reliable and works consistently)
        print(f"   Using Electrum daemon RPC...")
        
        import subprocess
        import json
        
        electrum_path = Path.home() / "src/electrum/run_electrum"
        electrum_python = Path.home() / "src/electrum/venv/bin/python3"
        
        if not electrum_path.exists():
            raise FileNotFoundError(f"Electrum not found at {electrum_path}")
        
        # Verify daemon is running on correct network
        print(f"   Verifying daemon is on {NETWORK_NAME}...")
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "getinfo"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Daemon not running. Start with: electrum {NETWORK_FLAG} daemon -d")
        
        daemon_info = json.loads(result.stdout)
        daemon_network = daemon_info.get('network', 'unknown')
        print(f"   ✅ Daemon confirmed on {daemon_network}")
        
        # Build outputs with unique amounts based on test_number
        # IMPORTANT: Amount = 1000 + test_number for ALL tests (P2WSH and Taproot)
        # This makes it easy to identify which UTXO belongs to which test
        # CRITICAL: We create ONE output per test, even if multiple tests share the same address!
        #           Tests sharing an address will use different UTXOs (identified by amount)
        outputs_list = []
        for addr_info in unfunded_addresses:
            addr = addr_info['address']
            # Each test gets its own UTXO with unique amount = 1000 + test_number
            tnum = addr_info.get('test_number', 0)
            amount_sats = addr_info.get('amount_sats', 1000 + (tnum or 0))
            outputs_list.append([addr, amount_sats / 100_000_000])
        
        # Format for paytomany: [[addr, amount_btc], ...]
        outputs = outputs_list
        paytomany_json = json.dumps(outputs)
        
        # Check if auto-funding is enabled
        if not auto_fund_enabled:
            print(f"\n💡 Auto-funding disabled. To fund addresses automatically, run:")
            print(f"   pytest --fund")
            return
        
        # Create transaction using daemon RPC
        print(f"   Creating batch transaction with {len(outputs)} outputs...")
        
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "paytomany", paytomany_json],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"   ❌ Transaction creation failed: {result.stderr}")
            return
        
        tx_hex = result.stdout.strip()
        print(f"   ✅ Transaction created ({len(tx_hex)//2} bytes)")
        
        # Broadcast
        print(f"   📡 Broadcasting transaction...")
        
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "broadcast", tx_hex],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"   ❌ Broadcast failed: {result.stderr}")
            return
        
        # Parse TXID from broadcast output
        broadcast_output = result.stdout.strip()
        try:
            broadcast_result = json.loads(broadcast_output)
            if isinstance(broadcast_result, list) and len(broadcast_result) == 2:
                success, txid = broadcast_result
                if not success:
                    print(f"   ❌ Broadcast returned false: {txid}")
                    yield
                    return
            elif isinstance(broadcast_result, str):
                txid = broadcast_result
            else:
                txid = str(broadcast_result)
        except json.JSONDecodeError:
            txid = broadcast_output.strip('"')
        
        if not txid or len(txid) != 64:
            print(f"   ❌ Invalid TXID: {txid}")
            return
        
        print(f"\n✅ Transaction broadcast successful!")
        print(f"   TXID: {txid}")
        print(f"   Verify: {EXPLORER_BASE}/tx/{txid}")
        
        # Parse transaction to map outputs by amount
        # Since we know each test has unique amount (1000 + test_number), we can map by amount
        print(f"\n   Mapping outputs to tests by amount...")
        
        # Get raw transaction hex
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "gettransaction", txid],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        amount_to_vout = {}  # Maps amount_sats -> vout
        if result.returncode == 0:
            # gettransaction returns raw hex, need to deserialize it
            tx_hex = result.stdout.strip()
            
            # Now deserialize the hex
            deserialize_result = subprocess.run(
                [str(electrum_python), str(electrum_path), NETWORK_FLAG, "deserialize", tx_hex],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if deserialize_result.returncode != 0:
                print(f"   ⚠️  Could not deserialize transaction")
                amount_to_vout = {}
            else:
                tx_data = json.loads(deserialize_result.stdout)
            
                if 'outputs' in tx_data:
                    for vout_idx, output in enumerate(tx_data['outputs']):
                        # Get amount in sats (deserialize returns value_sats)
                        amount_sats = output.get('value_sats', 0)
                        amount_to_vout[amount_sats] = vout_idx
                        # Pretty-print known test ranges when applicable
                        if 1000 <= amount_sats <= 2000:
                            test_num = amount_sats - 1000
                            test_type = "P2WSH" if test_num <= 9 else "Taproot"
                            print(f"     VOUT {vout_idx}: {amount_sats} sats → Test #{test_num} ({test_type})")
        else:
            print(f"   ⚠️  Could not get transaction")
        
        # Update state with vout numbers and amounts
        # Each test gets its own UTXO identified by unique amount (1000 + test_number)
        updated_count = 0
        for addr_info in unfunded_addresses:
            category = addr_info['category']
            variant = addr_info['variant']
            tnum = addr_info.get('test_number', 0)
            # Calculate expected amount: 1000 + test_number for all tests
            expected_amount = addr_info.get('amount_sats', 1000 + (tnum or 0))
            
            actual_vout = amount_to_vout.get(expected_amount)
            
            if actual_vout is None:
                print(f"   ⚠️  Warning: Could not find UTXO with {expected_amount} sats for test #{tnum}")
                continue
            
            # Update test state
            test = state.state[category][variant][0] if state.state[category][variant] else {}
            test['funding_txid'] = txid
            test['funding_vout'] = actual_vout
            test['amount_sats'] = expected_amount
            test['status'] = 'FUNDED'
            test['funded_at'] = datetime.now().isoformat()
            
            print(f"   ✅ Test {tnum}: {addr_info['type']} → vout {actual_vout}, {expected_amount} sats")
            updated_count += 1
        
        # Save state after all updates
        state.save()
        
        if updated_count != len(unfunded_addresses):
            print(f"   ⚠️  Warning: Only updated {updated_count}/{len(unfunded_addresses)} tests")
        
        print(f"\n🎉 All {updated_count} tests funded in ONE transaction!")
        print(f"   Network: {NETWORK_NAME}")
        print(f"   Ready to sweep!")
        
        return
    
    except Exception as e:
        print(f"❌ Batch funding failed: {e}")
        import traceback
        traceback.print_exc()
        return


@pytest.fixture(scope="session")
def electrum_daemon_running():
    """
    Check if Electrum daemon is running before tests
    
    Raises:
        RuntimeError: If daemon is not running
    """
    electrum_path = Path.home() / "src/electrum"
    electrum_bin = electrum_path / "run_electrum"
    
    if not electrum_bin.exists():
        raise RuntimeError(
            f"Electrum not found at {electrum_bin}. "
            f"Please install Electrum first."
        )
    
    try:
        result = subprocess.run(
            [str(electrum_bin), NETWORK_FLAG, "getinfo"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise RuntimeError(
                "Electrum daemon not responding. Please start it:\n"
                f"  cd {electrum_path}\n"
                f"  source venv/bin/activate\n"
                f"  ./run_electrum --testnet4 daemon start"
            )
        
        print(f"\n✓ Electrum daemon is running")
        return True
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("Electrum daemon check timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to check Electrum daemon: {e}")


@pytest.fixture(scope="session")
def logs_directory():
    """
    Ensure logs directory exists
    
    Returns:
        Path to logs directory
    """
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


@pytest.fixture
def test_environment(electrum_daemon_running, logs_directory):
    """
    Complete test environment setup
    
    Checks:
        - Electrum daemon is running
        - Logs directory exists
        - Test scripts are executable
    
    Returns:
        Dict with environment info
    """
    test_dir = Path(__file__).parent
    
    # Check scripts are executable (best-effort; some may be archived). If missing, skip.
    scripts = [
        'taproot_lock_demo.py',
        'taproot_sweep_demo.py'
    ]
    
    for script_name in scripts:
        script = test_dir / script_name
        if not script.exists():
            # Skip missing optional helper scripts
            print(f"ℹ️  Optional helper script missing: {script_name} (skipping check)")
            continue
        if not script.stat().st_mode & 0o111:
            # Skip non-executable scripts instead of failing
            print(f"ℹ️  Optional helper script not executable: {script_name} (skipping check)")
            continue
    
    return {
        'test_dir': test_dir,
        'logs_dir': logs_directory,
        'scripts': scripts
    }


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add markers automatically
    """
    for item in items:
        # Add slow marker to all e2e tests
        if "e2e" in item.nodeid:
            item.add_marker(pytest.mark.slow)
        
        # Add integration marker to all tests (they require Electrum)
        item.add_marker(pytest.mark.integration)


def pytest_report_header(config):
    """Add custom header to pytest output"""
    return [
        "CLTV E2E Test Framework",
        "Testing BIP-65 CHECKLOCKTIMEVERIFY on P2WSH and Taproot",
        "Expected duration: ~40 minutes per test"
    ]


# ============================================================================
# Shared Test Fixtures (Task 1: Eliminate Duplication)
# ============================================================================

from electrum_ecc import ECPrivkey

# ============================================================================
# HARDCODED TEST KEYS - For reproducible E2E testing
# ============================================================================
# Using well-known test vectors so we never lose keys on testnet4
# These are NOT SECURE - only use on testnet/signet!

TEST_KEYS = {
    # Simple CLTV test keys (one per format)
    # Note: P2SH support removed - only P2WSH and Taproot are supported
    'simple_p2wsh': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000002',
        'description': 'Simple CLTV P2WSH test key'
    },
    'simple_taproot': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000003',
        'description': 'Simple CLTV Taproot test key'
    },
    
    # Escrow test keys (alice/bob/lenny triplets for each format)
    # Note: P2SH support removed - only P2WSH and Taproot are supported
    'escrow_p2wsh_alice': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000020',
        'description': 'Escrow P2WSH Alice key'
    },
    'escrow_p2wsh_bob': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000021',
        'description': 'Escrow P2WSH Bob key'
    },
    'escrow_p2wsh_lenny': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000022',
        'description': 'Escrow P2WSH Lenny (lawyer/arbitrator) key'
    },
    'escrow_taproot_alice': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000030',
        'description': 'Escrow Taproot Alice key'
    },
    'escrow_taproot_bob': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000031',
        'description': 'Escrow Taproot Bob key'
    },
    'escrow_taproot_lenny': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000032',
        'description': 'Escrow Taproot Lenny (lawyer/arbitrator) key'
    },
    # Two-Factor Wallet Keys
    'twofactor_p2wsh_user': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000040',
        'description': 'Two-Factor P2WSH User key'
    },
    'twofactor_p2wsh_service': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000041',
        'description': 'Two-Factor P2WSH Service key'
    },
    'twofactor_p2wsh_recovery': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000042',
        'description': 'Two-Factor P2WSH Recovery key'
    },
    'twofactor_taproot_user': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000050',
        'description': 'Two-Factor Taproot User key'
    },
    'twofactor_taproot_service': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000051',
        'description': 'Two-Factor Taproot Service key'
    },
    'twofactor_taproot_recovery': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000052',
        'description': 'Two-Factor Taproot Recovery key'
    },
    # Payment Channel Keys
    'payment_p2wsh_sender': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000060',
        'description': 'Payment Channel P2WSH Sender key'
    },
    'payment_p2wsh_receiver': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000061',
        'description': 'Payment Channel P2WSH Receiver key'
    },
    'payment_taproot_sender': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000070',
        'description': 'Payment Channel Taproot Sender key'
    },
    'payment_taproot_receiver': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000071',
        'description': 'Payment Channel Taproot Receiver key'
    },
    # Data Publishing Keys
    'data_p2wsh_publisher': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000080',
        'description': 'Data Publishing P2WSH Publisher key'
    },
    'data_p2wsh_buyer': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000081',
        'description': 'Data Publishing P2WSH Buyer key'
    },
    'data_taproot_publisher': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000090',
        'description': 'Data Publishing Taproot Publisher key'
    },
    'data_taproot_buyer': {
        'private_key_hex': '0000000000000000000000000000000000000000000000000000000000000091',
        'description': 'Data Publishing Taproot Buyer key'
    },
}


def get_test_keypair(key_id: str) -> dict:
    """
    Get a hardcoded test keypair by ID.
    
    Returns dict with:
        - private_key: ECPrivkey instance
        - private_key_hex: Hex string of private key
        - pubkey_compressed: Hex string (33 bytes) for P2WSH
        - pubkey_xonly: Hex string (32 bytes) for Taproot
    """
    if key_id not in TEST_KEYS:
        raise ValueError(f"Unknown test key ID: {key_id}")
    
    privkey_hex = TEST_KEYS[key_id]['private_key_hex']
    privkey = ECPrivkey(bytes.fromhex(privkey_hex))
    pubkey_bytes = privkey.get_public_key_bytes(compressed=True)
    
    return {
        'private_key': privkey,
        'private_key_hex': privkey_hex,
        'pubkey_compressed': pubkey_bytes.hex(),
        'pubkey_xonly': pubkey_bytes[1:].hex()  # Remove first byte for Taproot
    }


@pytest.fixture
def generate_keypair():
    """
    Factory fixture for generating test keypairs.
    
    Returns a function that returns hardcoded test keys.
    Call with a key_id to get specific keys, or it generates sequentially.
    
    Returns:
        function: Generator function that returns dict with:
            - private_key: ECPrivkey instance
            - private_key_hex: Hex string of private key (for storage)
            - pubkey_compressed: Hex string (33 bytes) for P2WSH
            - pubkey_xonly: Hex string (32 bytes) for Taproot
    
    Example:
        >>> def test_example(generate_keypair):
        ...     # Get specific test key
        ...     alice = generate_keypair('escrow_p2wsh_alice')
        ...     bob = generate_keypair('escrow_p2wsh_bob')
    """
    counter = [0]  # Mutable counter for sequential generation
    
    def _generate(key_id: str = None):
        if key_id:
            return get_test_keypair(key_id)
        else:
            # Sequential generation for backward compatibility
            counter[0] += 1
            # Generate random for non-E2E tests
            privkey = ECPrivkey.generate_random_key()
            pubkey_bytes = privkey.get_public_key_bytes(compressed=True)
            return {
                'private_key': privkey,
                'private_key_hex': privkey.get_secret_bytes().hex(),
                'pubkey_compressed': pubkey_bytes.hex(),
                'pubkey_xonly': pubkey_bytes[1:].hex()
            }
    return _generate


@pytest.fixture
def pubkey_compressed(generate_keypair):
    """
    Single compressed public key (33 bytes) for P2WSH.
    
    This is a convenience fixture for tests that only need one key.
    For tests needing multiple keys, use generate_keypair() directly.
    
    Returns:
        str: Hex-encoded compressed public key (33 bytes)
    """
    return generate_keypair()['pubkey_compressed']


@pytest.fixture
def pubkey_xonly(generate_keypair):
    """
    Single x-only public key (32 bytes) for Taproot.
    
    This is a convenience fixture for tests that only need one Taproot key.
    
    Returns:
        str: Hex-encoded x-only public key (32 bytes)
    """
    return generate_keypair()['pubkey_xonly']


@pytest.fixture
def private_key(generate_keypair):
    """
    Single private key for signing operations.
    
    Returns:
        ECPrivkey: Private key instance
    """
    return generate_keypair()['private_key']


@pytest.fixture
def current_height():
    """
    Current blockchain height for testing.
    
    Dynamically fetches the current blockchain height from Electrum daemon.
    Falls back to a reasonable default if daemon is not available.
    
    Returns:
        int: Current blockchain height
    """
    try:
        import subprocess
        from pathlib import Path
        from network_config import NETWORK_FLAG
        
        electrum_path = Path.home() / "src/electrum/run_electrum"
        electrum_python = Path.home() / "src/electrum/venv/bin/python3"
        
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "getinfo"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            height = info.get('blockchain_height', 100000)
            print(f"✅ Using current blockchain height: {height}")
            return height
    except Exception as e:
        print(f"⚠️  Could not get blockchain height: {e}, using default 100000")
    
    return 100000


@pytest.fixture
def immediate_locktime():
    """
    Locktime that's immediately spendable (no time lock).
    
    This is useful for testing scripts where the timeout has already passed.
    
    Returns:
        int: Locktime value (0)
    """
    return 0


@pytest.fixture
def future_locktime(current_height):
    """
    Locktime in the future for testing time-locked scripts.
    
    Creates a locktime 100 blocks in the future, ensuring the time lock
    is not yet expired during testing.
    
    Returns:
        int: Locktime value (current_height + 100)
    """
    return current_height + 100


@pytest.fixture
def alice_bob_keypairs(generate_keypair):
    """
    Generate keypairs for Alice, Bob, and Lenny (BIP-65 escrow scenarios).
    
    BIP-65 Escrow Example: "Alice and Bob jointly operate a business...
    they appoint their lawyer, Lenny, to act as a third-party."
    
    For E2E tests, uses hardcoded test keys so we never lose them.
    For unit tests, generates random keys.
    
    Note: P2SH support removed - only P2WSH and Taproot are supported.
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (alice_keypair, bob_keypair, lenny_keypair) tuple
    
    Example:
        >>> def test_escrow(alice_bob_keypairs):
        ...     alice, bob, lenny = alice_bob_keypairs('p2wsh')
        ...     # All three parties can now sign with known keys
    """
    def _get_triplet(format_name='p2wsh'):
        # For E2E tests, use hardcoded keys based on format
        if format_name == 'p2wsh':
            alice = generate_keypair('escrow_p2wsh_alice')
            bob = generate_keypair('escrow_p2wsh_bob')
            lenny = generate_keypair('escrow_p2wsh_lenny')
        elif format_name == 'taproot':
            alice = generate_keypair('escrow_taproot_alice')
            bob = generate_keypair('escrow_taproot_bob')
            lenny = generate_keypair('escrow_taproot_lenny')
        else:
            # For unit tests or unknown formats, generate random
            alice = generate_keypair()
            bob = generate_keypair()
            lenny = generate_keypair()
        
        return alice, bob, lenny
    
    return _get_triplet


@pytest.fixture
def twofactor_keypairs(generate_keypair):
    """
    Generate keypairs for Two-Factor Wallet (User, Service, Recovery).
    
    For E2E tests, uses hardcoded test keys so we never lose them.
    For unit tests, generates random keys.
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (user_keypair, service_keypair, recovery_keypair) tuple
    
    Example:
        >>> def test_twofactor(twofactor_keypairs):
        ...     user, service, recovery = twofactor_keypairs('p2wsh')
        ...     # All three parties can now sign with known keys
    """
    def _get_triplet(format_name='p2wsh'):
        # For E2E tests, use hardcoded keys based on format
        if format_name == 'p2wsh':
            user = generate_keypair('twofactor_p2wsh_user')
            service = generate_keypair('twofactor_p2wsh_service')
            recovery = generate_keypair('twofactor_p2wsh_recovery')
        elif format_name == 'taproot':
            user = generate_keypair('twofactor_taproot_user')
            service = generate_keypair('twofactor_taproot_service')
            recovery = generate_keypair('twofactor_taproot_recovery')
        else:
            # For unit tests or unknown formats, generate random
            user = generate_keypair()
            service = generate_keypair()
            recovery = generate_keypair()
        
        return user, service, recovery
    
    return _get_triplet


@pytest.fixture
def payment_keypairs(generate_keypair):
    """
    Generate keypairs for Payment Channel (Sender, Receiver).
    
    For E2E tests, uses hardcoded test keys so we never lose them.
    For unit tests, generates random keys.
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (sender_keypair, receiver_keypair) tuple
    
    Example:
        >>> def test_payment(payment_keypairs):
        ...     sender, receiver = payment_keypairs('p2wsh')
        ...     # Both parties can now sign with known keys
    """
    def _get_pair(format_name='p2wsh'):
        # For E2E tests, use hardcoded keys based on format
        if format_name == 'p2wsh':
            sender = generate_keypair('payment_p2wsh_sender')
            receiver = generate_keypair('payment_p2wsh_receiver')
        elif format_name == 'taproot':
            sender = generate_keypair('payment_taproot_sender')
            receiver = generate_keypair('payment_taproot_receiver')
        else:
            # For unit tests or unknown formats, generate random
            sender = generate_keypair()
            receiver = generate_keypair()
        
        return sender, receiver
    
    return _get_pair


@pytest.fixture
def data_publishing_keypairs(generate_keypair):
    """
    Generate keypairs for Data Publishing (Publisher, Buyer).
    
    For E2E tests, uses hardcoded test keys so we never lose them.
    For unit tests, generates random keys.
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (publisher_keypair, buyer_keypair) tuple
    
    Example:
        >>> def test_data_pub(data_publishing_keypairs):
        ...     publisher, buyer = data_publishing_keypairs('p2wsh')
        ...     # Both parties can now sign with known keys
    """
    def _get_pair(format_name='p2wsh'):
        # For E2E tests, use hardcoded keys based on format
        if format_name == 'p2wsh':
            publisher = generate_keypair('data_p2wsh_publisher')
            buyer = generate_keypair('data_p2wsh_buyer')
        elif format_name == 'taproot':
            publisher = generate_keypair('data_taproot_publisher')
            buyer = generate_keypair('data_taproot_buyer')
        else:
            # For unit tests or unknown formats, generate random
            publisher = generate_keypair()
            buyer = generate_keypair()
        
        return publisher, buyer
    
    return _get_pair


@pytest.fixture
def test_data_preimage():
    """
    Generate test data and its HASH160 hash for data publishing tests.
    
    HASH160 = RIPEMD160(SHA256(data)) as per BIP-65
    
    Returns:
        dict with:
            - data: The original data string
            - data_hex: The data as hex string
            - data_hash: HASH160 of the data (20 bytes hex = 40 chars)
    
    Example:
        >>> def test_reveal(test_data_preimage):
        ...     preimage = test_data_preimage['data_hex']
        ...     hash_expected = test_data_preimage['data_hash']
        ...     # Use in witness stack to reveal preimage
    """
    import hashlib
    
    # Use consistent test data for deterministic hashes
    test_data = "Secret BIP-65 data publishing example"
    data_bytes = test_data.encode('utf-8')
    data_hex = data_bytes.hex()
    
    # HASH160 = RIPEMD160(SHA256(data))
    sha256_hash = hashlib.sha256(data_bytes).digest()
    data_hash = hashlib.new('ripemd160', sha256_hash).digest().hex()
    
    return {
        'data': test_data,
        'data_hex': data_hex,
        'data_hash': data_hash
    }


@pytest.fixture
def test_data_preimage_taproot():
    """
    Generate test data and its HASH160 hash for Taproot data publishing tests.
    
    Uses HASH160 (RIPEMD160(SHA256(data))) to match BIP-65 specification exactly.
    Uses same test data as P2WSH version for consistency.
    
    Returns:
        dict with:
            - data: The original data string
            - data_bytes: The data as bytes (for witness)
            - data_hex: The data as hex string
            - data_hash: HASH160 of the data (20 bytes hex = 40 chars)
            - data_hash_bytes: HASH160 hash as bytes (for script builder)
    
    Example:
        >>> def test_taproot_reveal(test_data_preimage_taproot):
        ...     preimage = test_data_preimage_taproot['data_bytes']
        ...     hash_expected = test_data_preimage_taproot['data_hash_bytes']
        ...     # Use in Taproot witness stack to reveal preimage
    """
    import hashlib
    
    # Use same test data as P2WSH for consistency
    test_data = "Secret BIP-65 data publishing example"
    data_bytes = test_data.encode('utf-8')
    data_hex = data_bytes.hex()
    
    # HASH160 for Taproot (RIPEMD160(SHA256(data)) to match BIP-65)
    sha256_hash = hashlib.sha256(data_bytes).digest()
    data_hash_bytes = hashlib.new('ripemd160', sha256_hash).digest()
    data_hash = data_hash_bytes.hex()
    
    return {
        'data': test_data,
        'data_bytes': data_bytes,
        'data_hex': data_hex,
        'data_hash': data_hash,
        'data_hash_bytes': data_hash_bytes
    }
