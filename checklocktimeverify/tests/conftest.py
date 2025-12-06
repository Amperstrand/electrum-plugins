"""
Pytest configuration and shared fixtures for CLTV plugin tests
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock

# NOTE: No longer mocking dns - using Electrum's venv which has dnspython installed

# Add plugin to path
PLUGIN_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

# Add Electrum to path (if available)
ELECTRUM_DIR = Path.home() / "src" / "electrum"
if ELECTRUM_DIR.exists():
    sys.path.insert(0, str(ELECTRUM_DIR))


# ============================================================================
# Test Keys (from test_keys.py)
# ============================================================================

@pytest.fixture
def test_keys():
    """Provide test keys for all script types - SAME AS PRODUCTION USES"""
    from test_keys import get_test_privkey, get_test_pubkey
    
    # Return the EXACT keys production UI uses
    # This ensures tests generate SAME addresses as UI
    return {
        'alice': {
            'privkey': get_test_privkey('alice'),
            'pubkey': get_test_pubkey('alice'),
        },
        'bob': {
            'privkey': get_test_privkey('bob'),
            'pubkey': get_test_pubkey('bob'),
        },
        'lenny': {
            'privkey': get_test_privkey('lenny'),
            'pubkey': get_test_pubkey('lenny'),
        },
        'hodl': {
            'privkey': get_test_privkey('hodl'),
            'pubkey': get_test_pubkey('hodl'),
        },
        'user': {
            'privkey': get_test_privkey('user'),
            'pubkey': get_test_pubkey('user'),
        },
        'service': {
            'privkey': get_test_privkey('service'),
            'pubkey': get_test_pubkey('service'),
        },
        'recovery': {
            'privkey': get_test_privkey('recovery'),
            'pubkey': get_test_pubkey('recovery'),
        },
        'sender': {
            'privkey': get_test_privkey('sender'),
            'pubkey': get_test_pubkey('sender'),
        },
        'receiver': {
            'privkey': get_test_privkey('receiver'),
            'pubkey': get_test_pubkey('receiver'),
        },
        'publisher': {
            'privkey': get_test_privkey('publisher'),
            'pubkey': get_test_pubkey('publisher'),
        },
        'buyer': {
            'privkey': get_test_privkey('buyer'),
            'pubkey': get_test_pubkey('buyer'),
        },
    }


# ============================================================================
# Mock Objects
# ============================================================================

@pytest.fixture
def mock_wallet():
    """Mock Electrum wallet"""
    wallet = Mock()
    wallet.has_password.return_value = False
    wallet.network = Mock()
    wallet.storage = Mock()
    wallet.storage.path = '/tmp/test_wallet'
    wallet.db = Mock()
    wallet.db.get.return_value = None
    wallet.db.put = Mock()
    return wallet


@pytest.fixture
def mock_network():
    """Mock Electrum network"""
    network = Mock()
    network.get_local_height.return_value = 1000
    return network


@pytest.fixture
def mock_config():
    """Mock Electrum config"""
    config = Mock()
    config.estimate_fee.return_value = 1000  # 1 sat/byte
    config.fee_per_kb.return_value = 1000
    config.format_amount_and_units.return_value = "0.00001 BTC"
    return config


@pytest.fixture
def mock_plugin(mock_wallet, mock_config):
    """Mock CLTV plugin"""
    plugin = Mock()
    plugin.wallet = mock_wallet
    plugin.config = mock_config
    plugin.log = Mock()
    return plugin


# ============================================================================
# Test Parameters
# ============================================================================

@pytest.fixture
def simple_cltv_params(test_keys):
    """Parameters for simple CLTV script - SAME AS UI USES"""
    return {
        'locktime': 1000,
        'pubkey': test_keys['hodl']['pubkey'],  # UI uses 'hodl' key
    }


@pytest.fixture
def escrow_params(test_keys):
    """Parameters for 3-party escrow script"""
    return {
        'locktime': 1000,
        'alice_pubkey': test_keys['alice']['pubkey'],
        'bob_pubkey': test_keys['bob']['pubkey'],
        'lenny_pubkey': test_keys['lenny']['pubkey'],
    }


@pytest.fixture
def twofactor_params(test_keys):
    """Parameters for two-factor wallet script"""
    return {
        'locktime': 1000,
        'user_pubkey': test_keys['user']['pubkey'],
        'service_pubkey': test_keys['service']['pubkey'],
        'recovery_pubkey': test_keys['recovery']['pubkey'],
    }


@pytest.fixture
def payment_channel_params(test_keys):
    """Parameters for payment channel script"""
    return {
        'locktime': 1000,
        'sender_pubkey': test_keys['sender']['pubkey'],
        'receiver_pubkey': test_keys['receiver']['pubkey'],
    }


@pytest.fixture
def data_publishing_params(test_keys):
    """Parameters for data publishing script"""
    import hashlib
    
    data = b"test data"
    data_hash = hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()
    
    return {
        'locktime': 1000,
        'publisher_pubkey': test_keys['publisher']['pubkey'],
        'buyer_pubkey': test_keys['buyer']['pubkey'],
        'data_hash': data_hash.hex(),
        'data_preimage': data.hex(),
    }


# ============================================================================
# Network Constants
# ============================================================================

@pytest.fixture
def network():
    """Default test network"""
    return 'signet'


# ============================================================================
# Test Vectors (Known Good Values)
# ============================================================================

@pytest.fixture
def known_addresses():
    """Known good addresses for validation"""
    return {
        'simple_cltv_p2wsh': {
            'address': 'tb1qwhateverknownaddress...',
            'script_hex': '...',
            'locktime': 1000,
        },
        # Add more known addresses as needed
    }


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (may require Electrum)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests (may take >1s)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on file location"""
    for item in items:
        # Auto-mark unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Auto-mark integration tests
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
