"""
Sweepers Module - Polymorphic Sweep Logic for CLTV Scripts

This module provides script-type-specific sweep logic using the Strategy Pattern.
Each script type (simple CLTV, multisig, HTLC) implements the SweeperStrategy interface.

Usage:
    from sweepers import SimpleCLTVSweeper, EscrowTimeoutSweeper
    # Or use the unified registry:
    from registry import get_sweeper
    
    sweeper = get_sweeper("cltv_simple_hodl")
    required_keys = sweeper.get_required_keys(output)
    witness = sweeper.build_witness(output, keys, sighash)
"""

from .base import SweeperStrategy
from .simple_cltv import SimpleCLTVSweeper
from .escrow_timeout import EscrowTimeoutSweeper

__all__ = [
    'SweeperStrategy',
    'SimpleCLTVSweeper',
    'EscrowTimeoutSweeper',
]
