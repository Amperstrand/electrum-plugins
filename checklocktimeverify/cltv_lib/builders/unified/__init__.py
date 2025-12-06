"""
Unified CLTV Builders

The generic builder can build ANY contract from ContractDefinition.
This is the ONLY builder needed - individual contract builders have been archived.

Usage:
    from cltv_lib.builders.unified import build_contract
    
    # Build any contract type
    result = build_contract('escrow', {
        'locktime': 600000,
        'alice': '02abc...',
        'bob': '03def...',
        'lenny': '02ghi...',
    }, output_type='taproot', network='signet')
    
    # Or use P2WSH
    result = build_contract('hodl', {
        'locktime': 600000,
        'pubkey': '02abc...',
    }, output_type='p2wsh', network='signet')
    
    # Contract types: hodl, escrow, twofactor, payment_channel, data_publishing
"""

# Generic builder - the only builder needed
from .generic import UnifiedContractBuilder, build_contract

__all__ = [
    'UnifiedContractBuilder',
    'build_contract',
]
