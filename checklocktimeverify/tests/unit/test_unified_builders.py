"""
Unit tests for unified builders.

Tests that build_contract() produces correct results for all contract types.
"""

import pytest
from cltv_lib.builders.unified import build_contract
from cltv_lib.contracts import CONTRACTS

# Test keys
TEST_PUBKEY_1 = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
TEST_PUBKEY_2 = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
TEST_PUBKEY_3 = "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
TEST_LOCKTIME = 600000
TEST_DATA_HASH = "0000000000000000000000000000000000000000"


class TestBuildContractFunction:
    """Tests for build_contract() function."""
    
    def test_hodl_p2wsh(self):
        """build_contract works for hodl P2WSH."""
        result = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        
        assert 'address' in result
        assert result['address'].startswith('tb1q')
        assert 'script_hex' in result
    
    def test_hodl_taproot(self):
        """build_contract works for hodl Taproot."""
        result = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='taproot',
            network='signet'
        )
        
        assert 'address' in result
        assert result['address'].startswith('tb1p')
        assert 'output_key' in result
    
    def test_escrow_p2wsh(self):
        """build_contract works for escrow P2WSH."""
        result = build_contract(
            'escrow',
            {
                'locktime': TEST_LOCKTIME,
                'alice': TEST_PUBKEY_1,
                'bob': TEST_PUBKEY_2,
                'lenny': TEST_PUBKEY_3
            },
            output_type='p2wsh',
            network='signet'
        )
        
        assert 'address' in result
        assert 'script_hex' in result
    
    def test_escrow_taproot(self):
        """build_contract works for escrow Taproot."""
        result = build_contract(
            'escrow',
            {
                'locktime': TEST_LOCKTIME,
                'alice': TEST_PUBKEY_1,
                'bob': TEST_PUBKEY_2,
                'lenny': TEST_PUBKEY_3
            },
            output_type='taproot',
            network='signet'
        )
        
        assert 'address' in result
        assert result['address'].startswith('tb1p')
    
    def test_payment_channel_p2wsh(self):
        """build_contract works for payment_channel P2WSH."""
        result = build_contract(
            'payment_channel',
            {
                'locktime': TEST_LOCKTIME,
                'sender': TEST_PUBKEY_1,
                'receiver': TEST_PUBKEY_2
            },
            output_type='p2wsh',
            network='signet'
        )
        
        assert 'address' in result
        assert 'script_hex' in result
    
    def test_twofactor_taproot(self):
        """build_contract works for twofactor Taproot."""
        result = build_contract(
            'twofactor',
            {
                'locktime': TEST_LOCKTIME,
                'user': TEST_PUBKEY_1,
                'service': TEST_PUBKEY_2
            },
            output_type='taproot',
            network='signet'
        )
        
        assert 'address' in result
        assert result['address'].startswith('tb1p')
    
    def test_data_publishing_p2wsh(self):
        """build_contract works for data_publishing P2WSH."""
        result = build_contract(
            'data_publishing',
            {
                'locktime': TEST_LOCKTIME,
                'publisher': TEST_PUBKEY_1,
                'buyer': TEST_PUBKEY_2,
                'data_hash': TEST_DATA_HASH
            },
            output_type='p2wsh',
            network='signet'
        )
        
        assert 'address' in result
        assert 'script_hex' in result


class TestBuildContractDeterminism:
    """Test that build_contract is deterministic."""
    
    def test_p2wsh_deterministic(self):
        """P2WSH builds are deterministic."""
        params = {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1}
        
        r1 = build_contract('hodl', params, 'p2wsh', 'signet')
        r2 = build_contract('hodl', params, 'p2wsh', 'signet')
        
        assert r1['address'] == r2['address']
        assert r1['script_hex'] == r2['script_hex']
    
    def test_taproot_deterministic(self):
        """Taproot builds are deterministic."""
        params = {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1}
        
        r1 = build_contract('hodl', params, 'taproot', 'signet')
        r2 = build_contract('hodl', params, 'taproot', 'signet')
        
        assert r1['address'] == r2['address']
        assert r1['output_key'] == r2['output_key']


class TestBuildContractValidation:
    """Test that build_contract validates inputs."""
    
    def test_missing_required_param_raises(self):
        """Missing required param raises BuildError."""
        from cltv_lib.builders.base import BuildError
        
        with pytest.raises(BuildError):
            build_contract(
                'hodl',
                {'locktime': TEST_LOCKTIME},  # Missing pubkey
                output_type='p2wsh',
                network='signet'
            )
    
    def test_invalid_pubkey_raises(self):
        """Invalid pubkey raises BuildError."""
        from cltv_lib.builders.base import BuildError
        
        with pytest.raises(BuildError):
            build_contract(
                'hodl',
                {'locktime': TEST_LOCKTIME, 'pubkey': 'invalid'},
                output_type='p2wsh',
                network='signet'
            )
    
    def test_unknown_contract_raises(self):
        """Unknown contract name raises error."""
        with pytest.raises(Exception):  # Could be KeyError or BuildError
            build_contract(
                'nonexistent_contract',
                {'locktime': TEST_LOCKTIME},
                output_type='p2wsh',
                network='signet'
            )
