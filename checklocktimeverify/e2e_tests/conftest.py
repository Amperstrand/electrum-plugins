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

# Add e2e_tests to path for network_config import
E2E_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, E2E_TESTS_DIR)

# ============================================================================
# CRITICAL: Configure network BEFORE any address generation
# ============================================================================
# This must happen before any imports that use constants.net
# Edit network_config.py to switch between signet and testnet4
from network_config import configure_electrum, NETWORK_NAME, WALLET_SUBDIR, NETWORK_FLAG, EXPLORER_BASE
configure_electrum()

print(f" Network set to {NETWORK_NAME}")


def pytest_addoption(parser):
    """Add custom command-line options"""
    parser.addoption(
        "--fund",
        action="store_true",
        default=False,
        help="Automatically fund unfunded test addresses via Electrum"
    )
    parser.addoption(
        "--locktime",
        type=int,
        default=None,
        help="Static locktime height to use for all tests (default: 1, immediately spendable)"
    )
    parser.addoption(
        "--fundsize",
        type=int,
        default=500,
        help="Base fund size in satoshis to use for tests (amount = fundsize + test_number)"
    )


def pytest_configure(config):
    """Configure pytest with custom settings"""
    # Expose fund size to test modules via environment for easy access
    try:
        fundsize = config.getoption("--fundsize")
    except Exception:
        fundsize = 500
    os.environ["E2E_FUND_BASE"] = str(fundsize)

    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "fast: marks tests as fast (quick smoke tests)"
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
    config.addinivalue_line(
        "markers", "negative: marks negative tests (expected failures)"
    )
    config.addinivalue_line(
        "markers", "edge_case: marks edge case tests (boundary conditions)"
    )


@pytest.fixture(scope="session")
def locktime_value(pytestconfig):
    """
    Get locktime from --locktime CLI option, or compute current_height + 1 as default.
    
    All tests now use current_height + 1 as the locktime, ensuring tests can run
    immediately after funding (or after waiting 1 block).
    """
    locktime = pytestconfig.getoption("--locktime")
    if locktime is None:
        # Compute current_height + 1 directly (can't use current_height fixture due to scope)
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
                current_height = info.get('blockchain_height', 100000)
                locktime = current_height + 1
                print(f"\n Locktime not specified, using: current_height + 1 = {locktime}")
            else:
                locktime = 100001  # Default fallback
                print(f"\n Locktime not specified, using default: {locktime}")
        except Exception as e:
            locktime = 100001  # Default fallback
            print(f"\n Locktime not specified, using default: {locktime} (error: {e})")
    else:
        print(f"\n Locktime set via --locktime: {locktime}")
    
    print(f"   → All tests use locktime: {locktime}")
    print(f"   → State file: test_state_{locktime}.json")
    
    return locktime

@pytest.fixture(scope="session", autouse=True)
def auto_fund_addresses(pytestconfig):
    """
    Automatically fund all CREATED addresses in a single batch transaction.
    
    This fixture runs AFTER all tests complete (via yield, then teardown).
    It checks test_state_{locktime}.json for any addresses with status='CREATED' and
    funds them all in one paytomany transaction using Electrum daemon.
    
    Enable with: pytest --fund
    
    Benefits:
    - One transaction instead of many (saves ~80% on fees)
    - All tests funded simultaneously
    - Automatic - creates and broadcasts transaction via Electrum
    - Idempotent - only funds addresses that need it
    - GENERIC: Works with ANY category structure (no hardcoded categories)
    """
    # Yield first to let all tests run and create addresses
    yield
    
    # Now run the funding logic AFTER all tests have created their addresses
    from test_e2e_stateful import StateManager
    
    # Check if auto-funding is enabled
    auto_fund_enabled = pytestconfig.getoption("--fund")
    if not auto_fund_enabled:
        return
    
    # Get locktime from CLI option
    locktime = pytestconfig.getoption("--locktime")
    if locktime is None:
        print("\n Cannot auto-fund: --locktime not specified")
        return
    
    state = StateManager(locktime=locktime)
    unfunded_addresses = []
    
    # GENERIC: Iterate over ALL categories in state that start with 'cltv_'
    # This works with the new parametrized tests without hardcoding category names
    for category, variants in state.state.items():
        if not category.startswith('cltv_') or not isinstance(variants, dict):
            continue
        
        for variant, tests in variants.items():
            if not isinstance(tests, list):
                continue
            
            for test in tests:
                if test.get('status') == 'CREATED' and not test.get('funding_txid'):
                    # Extract test info
                    tnum = test.get('test_number', 0)
                    path = test.get('path', 'sweep')
                    amount_sats = test.get('amount_sats', 1000 + tnum)
                    
                    # Create display name from category and path
                    contract_name = category.replace('cltv_', '').replace('_', ' ').title()
                    type_str = f"{contract_name} {variant.upper()} ({path})"
                    
                    unfunded_addresses.append({
                        'address': test['address'],
                        'category': category,
                        'variant': variant,
                        'type': type_str,
                        'test_number': tnum,
                        'amount_sats': amount_sats,
                        'path': path,
                    })
    
    if not unfunded_addresses:
        print("\n All addresses already funded or no addresses created yet")
        return
    
    # Sort by test number for consistent ordering
    unfunded_addresses.sort(key=lambda x: x.get('test_number', 0))
    
    # Display what we're funding
    print(f"\n{'='*80}")
    print(f" BATCH FUNDING: {len(unfunded_addresses)} tests need funding")
    print(f"{'='*80}\n")
    
    for i, addr_info in enumerate(unfunded_addresses, 1):
        print(f"  #{addr_info['test_number']:2d}. {addr_info['type']:40}")
        print(f"       {addr_info['address']}")
        print(f"       Amount: {addr_info['amount_sats']} sats")
    
    total_sats = sum(addr['amount_sats'] for addr in unfunded_addresses)
    
    print(f"\n{'='*80}")
    print(f" FUNDING SUMMARY")
    print(f"{'='*80}")
    print(f"   Tests to fund: {len(unfunded_addresses)}")
    print(f"   Total amount: {total_sats:,} satoshis ({total_sats / 100_000_000:.8f} BTC)")
    print(f"   Plus fees: ~200-500 sats\n")
    
    try:
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
        print(f" Daemon confirmed on {daemon_info.get('network', 'unknown')}")
        
        # Build outputs: each test gets unique address + unique amount
        outputs_list = []
        for addr_info in unfunded_addresses:
            addr = addr_info['address']
            amount_btc = addr_info['amount_sats'] / 100_000_000
            outputs_list.append([addr, amount_btc])
        
        paytomany_json = json.dumps(outputs_list)
        
        # Create transaction
        print(f"   Creating batch transaction with {len(outputs_list)} outputs...")
        
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "paytomany", paytomany_json],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f" Transaction creation failed: {result.stderr}")
            return
        
        tx_hex = result.stdout.strip()
        print(f" Transaction created ({len(tx_hex)//2} bytes)")
        
        # Broadcast
        print(f" Broadcasting transaction...")
        
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "broadcast", tx_hex],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f" Broadcast failed: {result.stderr}")
            return
        
        # Parse TXID
        broadcast_output = result.stdout.strip()
        try:
            broadcast_result = json.loads(broadcast_output)
            if isinstance(broadcast_result, list) and len(broadcast_result) == 2:
                success, txid = broadcast_result
                if not success:
                    print(f" Broadcast returned false: {txid}")
                    return
            elif isinstance(broadcast_result, str):
                txid = broadcast_result
            else:
                txid = str(broadcast_result)
        except json.JSONDecodeError:
            txid = broadcast_output.strip('"')
        
        if not txid or len(txid) != 64:
            print(f" Invalid TXID: {txid}")
            return
        
        print(f"\n Transaction broadcast successful!")
        print(f"   TXID: {txid}")
        print(f"   Verify: {EXPLORER_BASE}/tx/{txid}")
        
        # Map outputs to vout indices using UTXO offset (vout index)
        # CRITICAL: paytomany preserves output order, so vout index = position in outputs_list
        # This is more reliable than amount matching (which fails if amounts aren't unique)
        print(f"\n   Mapping outputs to tests (using UTXO offset)...")
        
        # Build address+amount -> vout mapping from the original outputs_list order
        # This is the most reliable method since paytomany preserves order
        addr_amount_to_vout = {}
        for vout_idx, addr_info in enumerate(unfunded_addresses):
            addr = addr_info['address']
            amount = addr_info['amount_sats']
            addr_amount_to_vout[(addr, amount)] = vout_idx
        
        # Verify mapping by deserializing transaction (optional verification)
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "gettransaction", txid],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        verification_failed = []
        if result.returncode == 0:
            tx_hex = result.stdout.strip()
            
            deserialize_result = subprocess.run(
                [str(electrum_python), str(electrum_path), NETWORK_FLAG, "deserialize", tx_hex],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if deserialize_result.returncode == 0:
                tx_data = json.loads(deserialize_result.stdout)
                if 'outputs' in tx_data:
                    # Verify each output matches our expected mapping
                    for vout_idx, output in enumerate(tx_data['outputs']):
                        output_addr = output.get('address', '')
                        output_amount = output.get('value_sats', 0)
                        
                        # Find which test this should belong to
                        expected_test = None
                        for addr_info in unfunded_addresses:
                            if addr_info['address'] == output_addr and addr_info['amount_sats'] == output_amount:
                                expected_test = addr_info
                                break
                        
                        if expected_test and vout_idx != addr_amount_to_vout.get((output_addr, output_amount)):
                            verification_failed.append((vout_idx, output_addr, output_amount))
        
        if verification_failed:
            print(f" WARNING: {len(verification_failed)} outputs don't match expected order")
        
        # Update state with funding info using UTXO offset (vout index)
        updated_count = 0
        for addr_info in unfunded_addresses:
            category = addr_info['category']
            variant = addr_info['variant']
            tnum = addr_info['test_number']
            addr = addr_info['address']
            expected_amount = addr_info['amount_sats']
            
            # Get vout index from our mapping (UTXO offset)
            actual_vout = addr_amount_to_vout.get((addr, expected_amount))
            
            if actual_vout is None:
                print(f" Test #{tnum}: Could not find vout for {addr[:20]}... ({expected_amount} sats)")
                continue
            
            # Find and update the test in state
            tests = state.state.get(category, {}).get(variant, [])
            for test in tests:
                if test.get('test_number') == tnum:
                    # Verify address matches (safety check)
                    if test.get('address') != addr:
                        print(f" Test #{tnum}: Address mismatch! Expected {addr}, got {test.get('address')}")
                    
                    test['funding_txid'] = txid
                    test['funding_vout'] = actual_vout
                    test['status'] = 'FUNDED'
                    test['funded_at'] = datetime.now().isoformat()
                    updated_count += 1
                    print(f" Test #{tnum}: vout={actual_vout} (UTXO offset), {expected_amount} sats, {addr[:20]}...")
                    break
        
        state.save()
        
        print(f"\n {updated_count}/{len(unfunded_addresses)} tests funded!")
        print(f"   Network: {NETWORK_NAME}")
        print(f"   Run tests again to sweep after locktime passes")
        
        return
    
    except Exception as e:
        print(f" Batch funding failed: {e}")
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
        
        print(f"\n Electrum daemon is running")
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
            print(f" Optional helper script missing: {script_name} (skipping check)")
            continue
        if not script.stat().st_mode & 0o111:
            # Skip non-executable scripts instead of failing
            print(f" Optional helper script not executable: {script_name} (skipping check)")
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

# ============================================================================
# TEST KEYS - Import from central test_keys.py
# ============================================================================
# All tests now use the same keys as the UI dialogs
# This ensures consistency and simplifies the codebase

# Add parent dir to path for test_keys import
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from test_keys import get_test_keypair as _central_get_keypair, get_test_pubkey, get_test_privkey, TEST_KEYS as CENTRAL_TEST_KEYS

# Map old format-specific key IDs to central key names
# This provides backward compatibility while using central keys
KEY_ID_MAP = {
    # Simple CLTV - uses 'hodl' key for all formats
    'simple_p2wsh': 'hodl',
    'simple_taproot': 'hodl',
    
    # Escrow - uses alice/bob/lenny for all formats
    'escrow_p2wsh_alice': 'alice',
    'escrow_p2wsh_bob': 'bob',
    'escrow_p2wsh_lenny': 'lenny',
    'escrow_taproot_alice': 'alice',
    'escrow_taproot_bob': 'bob',
    'escrow_taproot_lenny': 'lenny',
    
    # Two-Factor - uses user/service/recovery for all formats
    'twofactor_p2wsh_user': 'user',
    'twofactor_p2wsh_service': 'service',
    'twofactor_p2wsh_recovery': 'recovery',
    'twofactor_taproot_user': 'user',
    'twofactor_taproot_service': 'service',
    'twofactor_taproot_recovery': 'recovery',
    
    # Payment Channel - uses sender/receiver for all formats
    'payment_p2wsh_sender': 'sender',
    'payment_p2wsh_receiver': 'receiver',
    'payment_taproot_sender': 'sender',
    'payment_taproot_receiver': 'receiver',
    
    # Data Publishing - uses publisher/buyer for all formats
    'data_p2wsh_publisher': 'publisher',
    'data_p2wsh_buyer': 'buyer',
    'data_taproot_publisher': 'publisher',
    'data_taproot_buyer': 'buyer',
}


def get_test_keypair(key_id: str) -> dict:
    """
    Get a test keypair by ID.
    
    Uses central test_keys.py for all keys.
    Supports both old format-specific IDs and new central names.
    
    Returns dict with:
        - private_key: ECPrivkey instance
        - private_key_hex: Hex string of private key
        - pubkey_compressed: Hex string (33 bytes) for P2WSH
        - pubkey_xonly: Hex string (32 bytes) for Taproot
    """
    # Map old key IDs to central key names
    central_key_name = KEY_ID_MAP.get(key_id, key_id)
    
    # Get keypair from central test_keys.py
    keypair = _central_get_keypair(central_key_name)
    
    # Convert to expected format
    pubkey_bytes = keypair['privkey'].get_public_key_bytes(compressed=True)
    
    return {
        'private_key': keypair['privkey'],
        'private_key_hex': keypair['privkey_hex'],
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
            print(f" Using current blockchain height: {height}")
            return height
    except Exception as e:
        print(f" Could not get blockchain height: {e}, using default 100000")
    
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
    
    Now uses central test_keys.py - same keys for all formats!
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (alice_keypair, bob_keypair, lenny_keypair) tuple
    
    Example:
        >>> def test_escrow(alice_bob_keypairs):
        ...     alice, bob, lenny = alice_bob_keypairs('p2wsh')
        ...     # All three parties can now sign with known keys
    """
    def _get_triplet(format_name='p2wsh'):
        # Same keys for all formats - uses central test_keys.py
        alice = generate_keypair('alice')
        bob = generate_keypair('bob')
        lenny = generate_keypair('lenny')
        return alice, bob, lenny
    
    return _get_triplet


@pytest.fixture
def twofactor_keypairs(generate_keypair):
    """
    Generate keypairs for Two-Factor Wallet (User, Service).
    
    Now uses central test_keys.py - same keys for all formats!
    Note: Recovery key is same as User in unified design.
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (user_keypair, service_keypair) tuple
    
    Example:
        >>> def test_twofactor(twofactor_keypairs):
        ...     user, service = twofactor_keypairs('p2wsh')
        ...     # Both parties can now sign
    """
    def _get_pair(format_name='p2wsh'):
        # Same keys for all formats - uses central test_keys.py
        user = generate_keypair('user')
        service = generate_keypair('service')
        return user, service
    
    return _get_pair


@pytest.fixture
def payment_keypairs(generate_keypair):
    """
    Generate keypairs for Payment Channel (Sender, Receiver).
    
    Now uses central test_keys.py - same keys for all formats!
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (sender_keypair, receiver_keypair) tuple
    
    Example:
        >>> def test_payment(payment_keypairs):
        ...     sender, receiver = payment_keypairs('p2wsh')
        ...     # Both parties can now sign with known keys
    """
    def _get_pair(format_name='p2wsh'):
        # Same keys for all formats - uses central test_keys.py
        sender = generate_keypair('sender')
        receiver = generate_keypair('receiver')
        return sender, receiver
    
    return _get_pair


@pytest.fixture
def data_publishing_keypairs(generate_keypair):
    """
    Generate keypairs for Data Publishing (Publisher, Buyer).
    
    Now uses central test_keys.py - same keys for all formats!
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns (publisher_keypair, buyer_keypair) tuple
    
    Example:
        >>> def test_data_pub(data_publishing_keypairs):
        ...     publisher, buyer = data_publishing_keypairs('p2wsh')
        ...     # Both parties can now sign with known keys
    """
    def _get_pair(format_name='p2wsh'):
        # Same keys for all formats - uses central test_keys.py
        publisher = generate_keypair('publisher')
        buyer = generate_keypair('buyer')
        return publisher, buyer
    
    return _get_pair


@pytest.fixture
def multisig_keypairs(generate_keypair):
    """
    Generate 5 keypairs for Decaying Multisig contracts.
    
    Decaying multisig contracts have different spending rules based on time:
    - Normal: 3-of-5 members
    - After 60 months: 2-of-5 members  
    - After 66 months: 1-of-5 members
    
    Returns:
        function: Function that takes format ('p2wsh', 'taproot')
                  and returns 5-tuple of keypairs for members
    
    Example:
        >>> def test_multisig(multisig_keypairs):
        ...     m1, m2, m3, m4, m5 = multisig_keypairs('p2wsh')
        ...     # All 5 members can now sign
    """
    def _get_quintet(format_name='p2wsh'):
        # Same keys for all formats - uses central test_keys.py
        member1 = generate_keypair('member1')
        member2 = generate_keypair('member2')
        member3 = generate_keypair('member3')
        member4 = generate_keypair('member4')
        member5 = generate_keypair('member5')
        return member1, member2, member3, member4, member5
    
    return _get_quintet


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


# ============================================================================
# TEST PERFORMANCE TRACKING
# ============================================================================

@pytest.fixture(autouse=True)
def track_test_performance(request):
    """
    Track and report test execution time.
    
    Automatically runs for every test. Logs timing information and warns
    about slow tests (> 30 seconds).
    """
    import time
    
    test_name = request.node.name
    start_time = time.time()
    
    yield
    
    duration = time.time() - start_time
    
    # Categorize test speed
    if duration < 5:
        speed_emoji = ""
        speed_label = "fast"
    elif duration < 15:
        speed_emoji = ""
        speed_label = "normal"
    elif duration < 30:
        speed_emoji = ""
        speed_label = "slow"
    else:
        speed_emoji = ""
        speed_label = "very slow"
    
    # Log timing (only for verbose mode)
    if request.config.getoption("-v"):
        print(f"\n{speed_emoji} {test_name}: {duration:.2f}s ({speed_label})")
    
    # Warn about very slow tests
    if duration > 30:
        import warnings
        warnings.warn(
            f"Slow test detected: {test_name} took {duration:.2f}s",
            UserWarning
        )
