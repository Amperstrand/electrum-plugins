"""
Unified Contract Definitions

This module provides a single source of truth for all CLTV contract types.
Each contract is defined once using Miniscript and can generate both
P2WSH and Taproot scripts.

Usage:
    from cltv_lib.contracts import CONTRACTS, build_contract_script
    
    # Get contract definition
    contract = CONTRACTS['hodl']
    
    # Build P2WSH script
    p2wsh_script = build_contract_script(
        'hodl',
        {'locktime': 100, 'pubkey': pubkey_bytes},
        context='p2wsh'
    )
    
    # Build Taproot script (same parameters!)
    taproot_script = build_contract_script(
        'hodl',
        {'locktime': 100, 'pubkey': pubkey_bytes},
        context='tapscript'
    )
"""

from .definitions import (
    ContractDefinition,
    ContractType,
    ParamSpec,
    SpendingPath,
    KeyRole,
    CONTRACTS,
    build_contract_script,
    get_contract_miniscript,
    get_taproot_leaves,
)

__all__ = [
    'ContractDefinition',
    'ContractType',
    'ParamSpec',
    'SpendingPath',
    'KeyRole',
    'CONTRACTS',
    'build_contract_script',
    'get_contract_miniscript',
    'get_taproot_leaves',
]

