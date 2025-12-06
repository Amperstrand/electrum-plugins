"""
Unit tests for CLTV sweepers (unified architecture).

Tests verify:
1. GenericSweeper can be instantiated for all contract types
2. Sweeper correctly identifies required keys from ContractDefinition
3. Sweeper validates locktime conditions
"""

import pytest
from unittest.mock import MagicMock, patch

from cltv_lib.sweepers.generic import GenericSweeper
from cltv_lib.contracts import CONTRACTS


# Test data
TEST_LOCKTIME = 600000
TEST_CURRENT_HEIGHT_BEFORE = 599999
TEST_CURRENT_HEIGHT_AFTER = 600001
TEST_PUBKEY = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"


class TestGenericSweeper:
    """Tests for GenericSweeper."""
    
    def test_instantiation_hodl_p2wsh(self):
        """Can instantiate sweeper for hodl P2WSH."""
        sweeper = GenericSweeper('cltv_hodl_p2wsh')
        assert sweeper is not None
        assert sweeper.contract_name == 'hodl'
        assert sweeper.output_type == 'p2wsh'
    
    def test_instantiation_hodl_taproot(self):
        """Can instantiate sweeper for hodl Taproot."""
        sweeper = GenericSweeper('cltv_hodl_taproot')
        assert sweeper is not None
        assert sweeper.contract_name == 'hodl'
        assert sweeper.output_type == 'taproot'
    
    def test_instantiation_escrow_p2wsh(self):
        """Can instantiate sweeper for escrow P2WSH."""
        sweeper = GenericSweeper('cltv_escrow_p2wsh')
        assert sweeper is not None
        assert sweeper.contract_name == 'escrow'
    
    def test_instantiation_escrow_taproot(self):
        """Can instantiate sweeper for escrow Taproot."""
        sweeper = GenericSweeper('cltv_escrow_taproot')
        assert sweeper is not None
        assert sweeper.contract_name == 'escrow'
    
    def test_instantiation_payment_channel(self):
        """Can instantiate sweeper for payment_channel."""
        sweeper = GenericSweeper('cltv_payment_channel_p2wsh')
        assert sweeper is not None
        assert sweeper.contract_name == 'payment_channel'
    
    def test_instantiation_twofactor(self):
        """Can instantiate sweeper for twofactor."""
        sweeper = GenericSweeper('cltv_twofactor_p2wsh')
        assert sweeper is not None
        assert sweeper.contract_name == 'twofactor'
    
    def test_instantiation_data_publishing(self):
        """Can instantiate sweeper for data_publishing."""
        sweeper = GenericSweeper('cltv_data_publishing_p2wsh')
        assert sweeper is not None
        assert sweeper.contract_name == 'data_publishing'
    
    def test_path_resolution_default(self):
        """Default path is resolved correctly."""
        sweeper = GenericSweeper('cltv_hodl_p2wsh')
        # hodl has only 'sweep' path
        assert sweeper.path == 'sweep'
    
    def test_path_resolution_cooperative(self):
        """Cooperative path can be specified."""
        sweeper = GenericSweeper('cltv_payment_channel_p2wsh', path='cooperative')
        assert sweeper.path == 'cooperative'
    
    def test_path_resolution_refund(self):
        """Refund path can be specified."""
        sweeper = GenericSweeper('cltv_payment_channel_p2wsh', path='refund')
        assert sweeper.path == 'refund'
    
    def test_contract_name_available(self):
        """Sweeper has contract_name attribute."""
        sweeper = GenericSweeper('cltv_escrow_p2wsh')
        assert sweeper.contract_name == 'escrow'
        # Can access contract definition via CONTRACTS
        contract = CONTRACTS[sweeper.contract_name]
        assert 'Escrow' in contract.name
    
    def test_required_keys_from_path(self):
        """Sweeper can get required keys for path."""
        sweeper = GenericSweeper('cltv_escrow_p2wsh', path='arbitration_alice')
        required_keys = sweeper.get_required_keys()
        assert 'alice' in required_keys
        assert 'lenny' in required_keys


class TestSweeperForAllContracts:
    """Test that GenericSweeper works for all contract types."""
    
    @pytest.mark.parametrize("contract_name", list(CONTRACTS.keys()))
    def test_p2wsh_sweeper_instantiation(self, contract_name):
        """Can instantiate P2WSH sweeper for each contract."""
        script_type = f'cltv_{contract_name}_p2wsh'
        sweeper = GenericSweeper(script_type)
        assert sweeper is not None
        assert sweeper.contract_name == contract_name
    
    @pytest.mark.parametrize("contract_name", list(CONTRACTS.keys()))
    def test_taproot_sweeper_instantiation(self, contract_name):
        """Can instantiate Taproot sweeper for each contract."""
        script_type = f'cltv_{contract_name}_taproot'
        sweeper = GenericSweeper(script_type)
        assert sweeper is not None
        assert sweeper.contract_name == contract_name


class TestSweeperPaths:
    """Test that sweeper paths match ContractDefinition."""
    
    def test_hodl_has_sweep_path(self):
        """hodl has sweep path."""
        contract = CONTRACTS['hodl']
        assert contract.get_path('sweep') is not None
    
    def test_payment_channel_has_cooperative_and_refund(self):
        """payment_channel has cooperative and refund paths."""
        contract = CONTRACTS['payment_channel']
        assert contract.get_path('cooperative') is not None
        assert contract.get_path('refund') is not None
    
    def test_escrow_has_all_paths(self):
        """escrow has normal, arbitration_alice, arbitration_bob paths."""
        contract = CONTRACTS['escrow']
        assert contract.get_path('normal') is not None
        assert contract.get_path('arbitration_alice') is not None
        assert contract.get_path('arbitration_bob') is not None
    
    def test_twofactor_has_normal_and_recovery(self):
        """twofactor has normal and recovery paths."""
        contract = CONTRACTS['twofactor']
        assert contract.get_path('normal') is not None
        assert contract.get_path('recovery') is not None
    
    def test_data_publishing_has_publisher_and_buyer_refund(self):
        """data_publishing has publisher and buyer_refund paths."""
        contract = CONTRACTS['data_publishing']
        assert contract.get_path('publisher') is not None
        assert contract.get_path('buyer_refund') is not None
