#!/usr/bin/env python3
"""
UTXO Reservation System for CLTV E2E Testing

This module implements a UTXO reservation system that allows:
- Single address per example (not per path)
- Multiple UTXOs per address (one per test path)
- Clear UTXO-to-path mapping
- Efficient funding (fund once, test multiple paths)

State Structure:
{
  "cltv_escrow": {
    "script_hex": "6303aa8601b17521031be68a5a028f2601d0e80d468c344ba331d611b96c358b6032e8b4da0547fc11ad516752682103d30199d74fb5a22d47b6e054e2f378cedacffcb89904a61d75d0dbd407143e6521021697ffa6fd9de627c077e3d2fe541084ce13300b0bec1146f95ae57f0d0bd6a552ae",
    "address": "tb1qee8j0cwvh9empzhr77tal6ajujft2f2zltp43plxzee6elnk3c5szz353d",
    "funding_txid": "71d8a7129dce49e185a417e4b232d25b0b938f780f1669f9681264a7ff5730d6",
    "total_funded_sats": 2000,
    "utxo_reservations": {
      "p2wsh_normal_operations": {
        "vout": 0,
        "amount_sats": 1000,
        "status": "SWEPT",
        "sweep_txid": "201513c62a037c586045864a68afe884c902db5af5420564208c13791d3196af"
      },
      "p2wsh_arbitration": {
        "vout": 1, 
        "amount_sats": 1000,
        "status": "SWEPT",
        "sweep_txid": "cf4957d0d53344021bcb61eef0d0dddc97b411a6e3c8e19fe3cec7a216b44b8c"
      }
    }
  }
}
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pytest

# Add Electrum to path (needed for imports)
ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
if os.path.exists(ELECTRUM_DIR):
    sys.path.insert(0, ELECTRUM_DIR)

# State file location
STATE_FILE = Path(__file__).parent / "test_state_utxo.json"


class UTXOReservationManager:
    """
    Manages UTXO reservations for efficient testing.
    
    Each example gets one address with multiple UTXOs (one per test path).
    This is more realistic and efficient than creating separate addresses.
    """
    
    def __init__(self):
        self.state = self._load_state()
    
    def _empty_state(self) -> Dict:
        """Create empty state structure with UTXO reservations"""
        return {
            "cltv_hodl": {
                "script_hex": None,
                "address": None,
                "funding_txid": None,
                "total_funded_sats": 0,
                "utxo_reservations": {
                    "p2wsh": {
                        "vout": 0,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot": {
                        "vout": 1,
                        "amount_sats": 0,
                        "status": "CREATED", 
                        "sweep_txid": None
                    }
                }
            },
            "cltv_escrow": {
                "script_hex": None,
                "address": None,
                "funding_txid": None,
                "total_funded_sats": 0,
                "utxo_reservations": {
                    "p2wsh_normal_operations": {
                        "vout": 0,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "p2wsh_arbitration": {
                        "vout": 1,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_normal_operations": {
                        "vout": 2,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_arbitration": {
                        "vout": 3,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    }
                }
            },
            "cltv_twofactor": {
                "script_hex": None,
                "address": None,
                "funding_txid": None,
                "total_funded_sats": 0,
                "utxo_reservations": {
                    "p2wsh_normal": {
                        "vout": 0,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "p2wsh_recovery": {
                        "vout": 1,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_normal": {
                        "vout": 2,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_recovery": {
                        "vout": 3,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    }
                }
            },
            "cltv_payment_channel": {
                "script_hex": None,
                "address": None,
                "funding_txid": None,
                "total_funded_sats": 0,
                "utxo_reservations": {
                    "p2wsh_cooperative": {
                        "vout": 0,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "p2wsh_refund": {
                        "vout": 1,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_cooperative": {
                        "vout": 2,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_refund": {
                        "vout": 3,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    }
                }
            },
            "cltv_data_publishing": {
                "script_hex": None,
                "address": None,
                "funding_txid": None,
                "total_funded_sats": 0,
                "utxo_reservations": {
                    "p2wsh_publisher": {
                        "vout": 0,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "p2wsh_buyer_refund": {
                        "vout": 1,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_publisher": {
                        "vout": 2,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    },
                    "taproot_buyer_refund": {
                        "vout": 3,
                        "amount_sats": 0,
                        "status": "CREATED",
                        "sweep_txid": None
                    }
                }
            },
            "last_updated": None
        }
    
    def _load_state(self) -> Dict:
        """Load state from file or create new"""
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                # Ensure all required keys exist
                empty = self._empty_state()
                for example, example_data in empty.items():
                    if example == "last_updated":
                        continue
                    if example not in state:
                        state[example] = example_data
                    elif isinstance(example_data, dict):
                        # Ensure all required fields exist
                        for field in ['script_hex', 'address', 'funding_txid', 'total_funded_sats', 'utxo_reservations']:
                            if field not in state[example]:
                                state[example][field] = example_data[field]
                        # Ensure all UTXO reservations exist
                        for variant, reservation in example_data['utxo_reservations'].items():
                            if variant not in state[example]['utxo_reservations']:
                                state[example]['utxo_reservations'][variant] = reservation
                return state
        return self._empty_state()
    
    def save(self):
        """Save state to file"""
        self.state['last_updated'] = datetime.now().isoformat()
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def get_example_data(self, example: str) -> Dict:
        """Get example data including UTXO reservations"""
        return self.state.get(example, {})
    
    def get_utxo_reservation(self, example: str, variant: str) -> Dict:
        """Get UTXO reservation for a specific variant"""
        example_data = self.get_example_data(example)
        return example_data.get('utxo_reservations', {}).get(variant, {})
    
    def update_example_data(self, example: str, **kwargs):
        """Update example-level data (script, address, funding_txid, etc.)"""
        if example not in self.state:
            raise ValueError(f"Unknown example: {example}")
        
        for key, value in kwargs.items():
            if key in ['script_hex', 'address', 'funding_txid', 'total_funded_sats', 'locktime']:
                self.state[example][key] = value
            else:
                raise ValueError(f"Unknown field: {key}")
    
    def update_utxo_reservation(self, example: str, variant: str, **kwargs):
        """Update UTXO reservation for a specific variant"""
        if example not in self.state:
            raise ValueError(f"Unknown example: {example}")
        
        if variant not in self.state[example]['utxo_reservations']:
            raise ValueError(f"Unknown variant: {variant} for {example}")
        
        for key, value in kwargs.items():
            if key in ['vout', 'amount_sats', 'status', 'sweep_txid']:
                self.state[example]['utxo_reservations'][variant][key] = value
            else:
                raise ValueError(f"Unknown field: {key}")
    
    def get_funded_variants(self, example: str) -> List[str]:
        """Get list of variants that have been funded"""
        example_data = self.get_example_data(example)
        funded_variants = []
        
        for variant, reservation in example_data.get('utxo_reservations', {}).items():
            if reservation.get('status') in ['FUNDED', 'SWEPT']:
                funded_variants.append(variant)
        
        return funded_variants
    
    def get_swept_variants(self, example: str) -> List[str]:
        """Get list of variants that have been swept"""
        example_data = self.get_example_data(example)
        swept_variants = []
        
        for variant, reservation in example_data.get('utxo_reservations', {}).items():
            if reservation.get('status') == 'SWEPT':
                swept_variants.append(variant)
        
        return swept_variants
    
    def is_example_funded(self, example: str) -> bool:
        """Check if example has been funded (has funding_txid)"""
        example_data = self.get_example_data(example)
        return example_data.get('funding_txid') is not None
    
    def is_variant_swept(self, example: str, variant: str) -> bool:
        """Check if variant has been swept"""
        reservation = self.get_utxo_reservation(example, variant)
        return reservation.get('status') == 'SWEPT'
    
    def clear_all_states(self):
        """Clear all test states (for fresh start)"""
        self.state = self._empty_state()
        self.save()
        print(" Cleared all UTXO reservation states")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_utxo_manager() -> UTXOReservationManager:
    """Get UTXO reservation manager instance"""
    return UTXOReservationManager()


def clear_all_utxo_states():
    """Clear all UTXO reservation states"""
    manager = get_utxo_manager()
    manager.clear_all_states()


# ============================================================================
# TESTING UTILITIES
# ============================================================================

def test_utxo_reservation_system():
    """Test the UTXO reservation system"""
    print(" Testing UTXO Reservation System...")
    
    manager = UTXOReservationManager()
    
    # Test basic operations
    print("  Testing basic operations...")
    
    # Update example data
    manager.update_example_data('cltv_escrow', 
                               script_hex='test_script',
                               address='tb1qtest',
                               funding_txid='test_txid',
                               total_funded_sats=2000)
    
    # Update UTXO reservation
    manager.update_utxo_reservation('cltv_escrow', 'p2wsh_normal_operations',
                                   vout=0, amount_sats=1000, status='FUNDED')
    
    # Test retrieval
    example_data = manager.get_example_data('cltv_escrow')
    assert example_data['script_hex'] == 'test_script'
    assert example_data['address'] == 'tb1qtest'
    
    reservation = manager.get_utxo_reservation('cltv_escrow', 'p2wsh_normal_operations')
    assert reservation['vout'] == 0
    assert reservation['amount_sats'] == 1000
    assert reservation['status'] == 'FUNDED'
    
    # Test status checks
    assert manager.is_example_funded('cltv_escrow') == True
    assert manager.is_variant_swept('cltv_escrow', 'p2wsh_normal_operations') == False
    
    funded_variants = manager.get_funded_variants('cltv_escrow')
    assert 'p2wsh_normal_operations' in funded_variants
    
    print(" All tests passed!")
    
    # Save and reload
    manager.save()
    manager2 = UTXOReservationManager()
    assert manager2.get_example_data('cltv_escrow')['script_hex'] == 'test_script'
    
    print(" Persistence test passed!")
    print(" UTXO Reservation System working correctly!")


if __name__ == "__main__":
    test_utxo_reservation_system()
