"""
CLTV Script Builders - Unified Architecture

All contract building now uses the generic build_contract() function.
Individual builder classes have been archived.

Usage:
    from cltv_lib.builders.unified import build_contract
    
    # Build any contract
    result = build_contract('escrow', {
        'locktime': 600000,
        'alice': '02abc...',
        'bob': '03def...',
        'lenny': '02ghi...',
    }, output_type='taproot', network='signet')
    
    # Contract types: hodl, escrow, twofactor, payment_channel, data_publishing
    # Output types: p2wsh, taproot
"""

from .base import ScriptBuilder, BuildError

# Import the unified generic builder
from .unified import UnifiedContractBuilder, build_contract

__all__ = [
    # Base classes
    'ScriptBuilder',
    'BuildError',
    
    # Unified builder (the only builder needed)
    'UnifiedContractBuilder',
    'build_contract',
]
