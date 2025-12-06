"""
Test Keys Module for CLTV Lib

Re-exports test keys from parent module for convenient imports.
Provides TEST_KEYS with pre-computed pubkey values for integration tests.
"""

from ..test_keys import (
    TEST_KEYS as _RAW_TEST_KEYS,
    get_test_privkey,
    get_test_pubkey,
    get_all_test_keys,  # Not get_all_test_pubkeys
)

# Build TEST_KEYS with pubkey values pre-computed for convenience
def _get_test_keys_with_pubkeys():
    """Get TEST_KEYS dict with pubkey values added."""
    result = {}
    for name, data in _RAW_TEST_KEYS.items():
        result[name] = {
            **data,
            'pubkey': get_test_pubkey(name)
        }
    return result

# Export TEST_KEYS with pubkeys included
TEST_KEYS = _get_test_keys_with_pubkeys()

# Also keep the raw version available
RAW_TEST_KEYS = _RAW_TEST_KEYS
