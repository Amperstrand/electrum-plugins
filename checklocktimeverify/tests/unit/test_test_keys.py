"""
Unit tests for test keys (test_keys.py)

Tests hardcoded test key management
"""

import pytest


class TestTestKeys:
    """Tests for test key management"""
    
    def test_get_test_privkey_alice(self):
        """Test getting alice's private key"""
        from test_keys import get_test_privkey
        
        privkey = get_test_privkey('alice')
        
        assert privkey is not None
        # Should be ECPrivkey instance with get_public_key method
        assert hasattr(privkey, 'get_public_key_bytes')
    
    def test_get_test_pubkey_alice(self):
        """Test getting alice's public key"""
        from test_keys import get_test_pubkey
        
        pubkey = get_test_pubkey('alice', compressed=True)
        
        assert pubkey is not None
        assert isinstance(pubkey, str)
        # Compressed pubkey is 66 hex chars (33 bytes)
        assert len(pubkey) == 66
        # Should start with 02 or 03
        assert pubkey.startswith('02') or pubkey.startswith('03')
    
    def test_get_test_pubkey_uncompressed(self):
        """Test getting uncompressed public key"""
        from test_keys import get_test_pubkey
        
        pubkey = get_test_pubkey('alice', compressed=False)
        
        assert pubkey is not None
        assert isinstance(pubkey, str)
        # Uncompressed pubkey is 130 hex chars (65 bytes)
        assert len(pubkey) == 130
        # Should start with 04
        assert pubkey.startswith('04')
    
    def test_get_test_keypair(self):
        """Test getting keypair"""
        from test_keys import get_test_keypair
        
        keypair = get_test_keypair('alice')
        
        assert keypair is not None
        assert isinstance(keypair, dict)
        assert 'privkey' in keypair
        assert 'pubkey' in keypair
        assert keypair['privkey'] is not None
        assert keypair['pubkey'] is not None
        assert isinstance(keypair['pubkey'], str)
    
    def test_all_test_keys_available(self):
        """Test that all expected test keys are available"""
        from test_keys import get_test_privkey
        
        expected_keys = [
            'alice', 'bob', 'lenny',  # Escrow
            'user', 'service', 'recovery',  # Two-factor
            'sender', 'receiver',  # Payment channel
            'publisher', 'buyer',  # Data publishing
        ]
        
        for key_name in expected_keys:
            privkey = get_test_privkey(key_name)
            assert privkey is not None, f"Key {key_name} not found"
    
    def test_get_all_test_keys(self):
        """Test getting all test keys at once"""
        from test_keys import get_all_test_keys
        
        all_keys = get_all_test_keys()
        
        assert all_keys is not None
        assert isinstance(all_keys, dict)
        assert len(all_keys) >= 10  # At least 10 test keys
    
    def test_different_keys_have_different_pubkeys(self):
        """Test that different key names produce different pubkeys"""
        from test_keys import get_test_pubkey
        
        alice_pubkey = get_test_pubkey('alice')
        bob_pubkey = get_test_pubkey('bob')
        
        assert alice_pubkey != bob_pubkey
    
    def test_same_key_always_produces_same_pubkey(self):
        """Test deterministic key generation"""
        from test_keys import get_test_pubkey
        
        pubkey1 = get_test_pubkey('alice')
        pubkey2 = get_test_pubkey('alice')
        
        assert pubkey1 == pubkey2
    
    def test_invalid_key_name_raises_error(self):
        """Test that invalid key name raises error"""
        from test_keys import get_test_privkey
        
        with pytest.raises(ValueError):
            get_test_privkey('invalid_key_name')
    
    @pytest.mark.parametrize("key_name", [
        'alice', 'bob', 'lenny',
        'user', 'service', 'recovery',
        'sender', 'receiver',
        'publisher', 'buyer',
    ])
    def test_each_key_has_valid_format(self, key_name):
        """Parametrized test: Each key has valid format"""
        from test_keys import get_test_pubkey
        
        pubkey = get_test_pubkey(key_name, compressed=True)
        
        # Valid compressed pubkey
        assert len(pubkey) == 66
        assert pubkey.startswith('02') or pubkey.startswith('03')
        
        # Valid hex
        try:
            bytes.fromhex(pubkey)
        except ValueError:
            pytest.fail(f"Invalid hex for {key_name}")
