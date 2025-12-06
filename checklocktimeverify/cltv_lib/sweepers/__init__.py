"""
CLTV Script Sweepers - Generic Sweeper for ALL contract types

The GenericSweeper handles witness generation for any contract/path combination.
It derives everything from ContractDefinition, just like build_contract().

No per-contract sweeper classes needed!

Usage:
    from cltv_lib.sweepers import GenericSweeper, sweep_output
    
    # Using GenericSweeper class
    sweeper = GenericSweeper('cltv_escrow_taproot', path='normal')
    witness = sweeper.build_witness(output_data, keys, sighash)
    
    # Using convenience function
    witness = sweep_output(
        script_type='cltv_payment_channel_p2wsh',
        params={'locktime': 280500, 'sender_pubkey': ..., 'receiver_pubkey': ...},
        path='cooperative',
        keys={'sender_key': privkey1, 'receiver_key': privkey2},
        sighash=sighash_bytes
    )
"""

# Base classes
from .base import SweeperStrategy, SweepError

# Generic Sweeper - handles ALL contract types
from .generic import (
    GenericSweeper,
    sweep_output,
    get_required_keys,
    validate_sweep_conditions,
    build_witness,
    normalize_key,
    LockedError,
    ValidationError,
)

__all__ = [
    # Base classes
    'SweeperStrategy',
    'SweepError',
    
    # Generic Sweeper (the only sweeper - handles all contract types)
    'GenericSweeper',
    'sweep_output',
    'get_required_keys',
    'validate_sweep_conditions',
    'build_witness',
    'normalize_key',
    'LockedError',
    'ValidationError',
]
