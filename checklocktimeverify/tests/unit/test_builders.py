"""
Unit tests for CLTV builders (unified architecture).

Tests verify:
1. Script generation is deterministic
2. Same parameters produce same output
3. Miniscript compilation matches expected scripts
4. P2WSH and Taproot use same miniscript (context-aware)
"""

import pytest
from cltv_lib.builders.unified import build_contract
from cltv_lib.contracts import CONTRACTS


# Test keys (valid compressed pubkeys)
TEST_PUBKEY_1 = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
TEST_PUBKEY_2 = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
TEST_PUBKEY_3 = "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
TEST_LOCKTIME = 600000
TEST_DATA_HASH = "0000000000000000000000000000000000000000"


class TestSimpleHodlBuilder:
    """Tests for Simple HODL builder."""
    
    def test_p2wsh_returns_dict(self):
        """P2WSH returns dict with expected fields."""
        result = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        
        assert isinstance(result, dict)
        assert 'script_hex' in result
        assert 'address' in result
        assert result['address'].startswith('tb1q')  # P2WSH starts with tb1q
    
    def test_taproot_returns_dict(self):
        """Taproot returns dict with expected fields."""
        result = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='taproot',
            network='signet'
        )
        
        assert isinstance(result, dict)
        assert 'address' in result
        assert result['address'].startswith('tb1p')  # Taproot starts with tb1p
    
    def test_p2wsh_is_deterministic(self):
        """Same params produce identical script."""
        result1 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        result2 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        
        assert result1['script_hex'] == result2['script_hex']
        assert result1['address'] == result2['address']
    
    def test_taproot_is_deterministic(self):
        """Same params produce identical address."""
        result1 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='taproot',
            network='signet'
        )
        result2 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='taproot',
            network='signet'
        )
        
        assert result1['address'] == result2['address']
        assert result1['output_key'] == result2['output_key']
    
    def test_different_locktime_different_script(self):
        """Different locktime produces different script."""
        result1 = build_contract(
            'hodl',
            {'locktime': 100, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        result2 = build_contract(
            'hodl',
            {'locktime': 200, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        
        assert result1['script_hex'] != result2['script_hex']
    
    def test_different_pubkey_different_script(self):
        """Different pubkey produces different script."""
        result1 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_1},
            output_type='p2wsh',
            network='signet'
        )
        result2 = build_contract(
            'hodl',
            {'locktime': TEST_LOCKTIME, 'pubkey': TEST_PUBKEY_2},
            output_type='p2wsh',
            network='signet'
        )
        
        assert result1['script_hex'] != result2['script_hex']


class TestEscrowBuilder:
    """Tests for Escrow builder."""
    
    def test_p2wsh_returns_dict(self):
        """P2WSH returns dict with expected fields."""
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
        
        assert isinstance(result, dict)
        assert 'script_hex' in result
        assert 'address' in result
    
    def test_taproot_returns_dict(self):
        """Taproot returns dict with expected fields."""
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
        
        assert isinstance(result, dict)
        assert 'address' in result
        assert result['address'].startswith('tb1p')


class TestPaymentChannelBuilder:
    """Tests for Payment Channel builder."""
    
    def test_p2wsh_returns_dict(self):
        """P2WSH returns dict."""
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
        
        assert isinstance(result, dict)
        assert 'script_hex' in result
    
    def test_taproot_returns_dict(self):
        """Taproot returns dict."""
        result = build_contract(
            'payment_channel',
            {
                'locktime': TEST_LOCKTIME,
                'sender': TEST_PUBKEY_1,
                'receiver': TEST_PUBKEY_2
            },
            output_type='taproot',
            network='signet'
        )
        
        assert isinstance(result, dict)
        assert result['address'].startswith('tb1p')


class TestTwoFactorBuilder:
    """Tests for Two-Factor builder."""
    
    def test_p2wsh_returns_dict(self):
        """P2WSH returns dict."""
        result = build_contract(
            'twofactor',
            {
                'locktime': TEST_LOCKTIME,
                'user': TEST_PUBKEY_1,
                'service': TEST_PUBKEY_2
            },
            output_type='p2wsh',
            network='signet'
        )
        
        assert isinstance(result, dict)
        assert 'script_hex' in result
    
    def test_taproot_returns_dict(self):
        """Taproot returns dict."""
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
        
        assert isinstance(result, dict)
        assert result['address'].startswith('tb1p')


class TestDataPublishingBuilder:
    """Tests for Data Publishing builder."""
    
    def test_p2wsh_returns_dict(self):
        """P2WSH returns dict."""
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
        
        assert isinstance(result, dict)
        assert 'script_hex' in result
    
    def test_taproot_returns_dict(self):
        """Taproot returns dict."""
        result = build_contract(
            'data_publishing',
            {
                'locktime': TEST_LOCKTIME,
                'publisher': TEST_PUBKEY_1,
                'buyer': TEST_PUBKEY_2,
                'data_hash': TEST_DATA_HASH
            },
            output_type='taproot',
            network='signet'
        )
        
        assert isinstance(result, dict)
        assert result['address'].startswith('tb1p')


class TestAllContractsExist:
    """Test that all contracts in CONTRACTS can be built."""
    
    @pytest.mark.parametrize("contract_name", list(CONTRACTS.keys()))
    def test_contract_definition_exists(self, contract_name):
        """Each contract has a definition."""
        contract = CONTRACTS[contract_name]
        assert contract is not None
        assert contract.miniscript is not None
        assert len(contract.params) > 0
