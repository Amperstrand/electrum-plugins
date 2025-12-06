"""
Unified Test Builder - Uses generic build_contract() for E2E tests

This module provides helpers that use the new UnifiedContractBuilder
to generate addresses AND test_data in one call.

Replaces the old pattern:
    script_hex = build_script('cltv_simple_p2wsh', params)
    address = script_to_p2wsh(script_hex)
    test_data = build_test_data(...)

With:
    test_data = build_e2e_test('hodl', {...}, 'p2wsh', ...)

The ContractDefinition is now the TRUE single source of truth.
"""

import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, Literal

# Add parent directory for cltv_lib import
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from cltv_lib.builders.unified.generic import build_contract
from cltv_lib.contracts import CONTRACTS


OutputType = Literal['p2wsh', 'taproot']
Network = Literal['mainnet', 'testnet', 'signet', 'regtest']


def _get_taproot_path_mapping(contract_name: str) -> Dict[int, str]:
    """
    Get leaf_index → path_name mapping from ContractDefinition.
    
    SINGLE SOURCE OF TRUTH: Derives from SpendingPath.leaf_index in ContractDefinition.
    """
    contract = CONTRACTS.get(contract_name)
    if not contract:
        return {}
    
    return {
        path.leaf_index: path.name
        for path in contract.paths
        if path.leaf_index is not None
    }


def _map_taproot_paths(test_data: Dict[str, Any], contract_name: str, result: Dict[str, Any]) -> None:
    """
    Map leaf scripts and control blocks to path-specific names.
    
    SINGLE SOURCE OF TRUTH: Uses SpendingPath.leaf_index from ContractDefinition.
    """
    mapping = _get_taproot_path_mapping(contract_name)
    leaf_scripts = result.get('leaf_scripts', {})
    control_blocks = result.get('control_blocks', {})
    
    for leaf_idx, path_name in mapping.items():
        leaf_key = f'leaf_{leaf_idx}'
        
        if leaf_key in leaf_scripts:
            test_data[f'{path_name}_script'] = leaf_scripts[leaf_key]
        
        if leaf_key in control_blocks:
            test_data[f'{path_name}_control'] = control_blocks[leaf_key]
    
    # For single-leaf contracts, also set default script/control
    if len(mapping) == 1 and 'leaf_0' not in leaf_scripts:
        path_name = list(mapping.values())[0]
        test_data[f'{path_name}_script'] = result.get('script_hex', '')
        test_data[f'{path_name}_control'] = result.get('control_block_hex', '')


def build_e2e_test(
    contract_name: str,
    params: Dict[str, Any],
    output_type: OutputType,
    test_number: int,
    current_height: int,
    path: Optional[str] = None,
    keys: Optional[Dict[str, Any]] = None,
    notes: str = '',
    network: Network = 'signet',
    amount_sats: Optional[int] = None,
    **extra_fields
) -> Dict[str, Any]:
    """
    Build complete E2E test data using UnifiedContractBuilder.
    
    This is the new single function for creating test data.
    It builds the address AND creates the test_data dict in one call.
    
    Args:
        contract_name: 'hodl', 'escrow', 'twofactor', 
                      'payment_channel', 'data_publishing'
        params: Contract params (locktime, pubkeys, etc.)
        output_type: 'p2wsh' or 'taproot'
        test_number: Unique test identifier
        current_height: Current blockchain height
        path: Spending path name (for multi-path contracts)
        keys: Dict of keypairs for the test
        notes: Human-readable description
        network: Network for address generation
        amount_sats: Funding amount (default: 1000 + test_number)
        **extra_fields: Additional test-specific fields
    
    Returns:
        Complete test_data dict ready for StateManager
    
    Example:
        >>> test_data = build_e2e_test(
        ...     contract_name='escrow',
        ...     params={
        ...         'locktime': 280000,
        ...         'alice': alice_pubkey,
        ...         'bob': bob_pubkey,
        ...         'lenny': lenny_pubkey,
        ...     },
        ...     output_type='p2wsh',
        ...     test_number=2,
        ...     current_height=279999,
        ...     path='normal',
        ...     keys={'alice': alice_kp, 'bob': bob_kp, 'lenny': lenny_kp},
        ...     notes='Escrow normal operations test'
        ... )
    """
    # Build address using generic builder
    result = build_contract(
        contract_name=contract_name,
        params=params,
        output_type=output_type,
        network=network
    )
    
    # Get contract definition for metadata
    contract = CONTRACTS.get(contract_name)
    
    # Determine script_type format using registry as single source of truth
    from cltv_lib.registry import get_script_id
    script_type = get_script_id(contract_name, output_type)
    format_str = 'TAPROOT' if output_type == 'taproot' else 'P2WSH'
    
    # Calculate amount if not provided
    if amount_sats is None:
        amount_sats = 1000 + test_number
    
    # Build test_data dict
    test_data = {
        # Metadata
        'test_number': test_number,
        'created_at': datetime.now().isoformat(),
        'status': 'CREATED',
        'notes': notes or f"{contract.name if contract else contract_name} {format_str} test",
        
        # Script info
        'locktime': params.get('locktime'),
        'script_type': script_type,
        'format': format_str,
        'output_type': output_type,
        'current_height_at_creation': current_height,
        
        # Address and script
        'address': result['address'],
        'script_hex': result.get('script_hex', ''),
        'script_params': params,
        
        # Funding (to be filled when funded)
        'funding_txid': None,
        'funding_vout': 0,
        'amount_sats': amount_sats,
        
        # Path (for multi-path contracts)
        'path': path,
    }
    
    # Add keys with proper prefixes (only store hex strings, not ECPrivkey objects)
    if keys:
        for role, keypair in keys.items():
            # Get pubkey (prefer compressed)
            pubkey = keypair.get('pubkey_compressed') or keypair.get('pubkey')
            
            # Get private key as hex string (avoid ECPrivkey object)
            privkey_hex = keypair.get('privkey_hex') or keypair.get('private_key_hex')
            if privkey_hex is None and 'private_key' in keypair:
                # If private_key is an ECPrivkey object, convert to hex
                pk = keypair['private_key']
                if hasattr(pk, 'get_secret_bytes'):
                    privkey_hex = pk.get_secret_bytes().hex()
                elif isinstance(pk, str):
                    privkey_hex = pk
            
            if role:
                # Named role: alice_pubkey, alice_private_key_hex
                test_data[f'{role}_pubkey'] = pubkey
                test_data[f'{role}_private_key_hex'] = privkey_hex
            else:
                # Empty role for simple contracts
                test_data['pubkey'] = pubkey
                test_data['private_key_hex'] = privkey_hex
    
    # Add Taproot-specific data
    if output_type == 'taproot':
        test_data['control_block'] = result.get('control_block', '')
        test_data['control_block_hex'] = result.get('control_block_hex', '')
        test_data['output_script'] = result.get('output_script', '')
        test_data['output_key'] = result.get('output_key', '')
        test_data['internal_key'] = result.get('internal_key', '')
        
        # Add leaf scripts if present
        if 'leaf_scripts' in result:
            test_data['leaf_scripts'] = result['leaf_scripts']
        if 'control_blocks' in result:
            test_data['control_blocks'] = result['control_blocks']
        
        # CRITICAL: Map leaf scripts to path-specific names for sweep_utils.py
        # Each contract has a specific mapping of leaf indices to path names
        _map_taproot_paths(test_data, contract_name, result)
    
    # Add extra fields
    test_data.update(extra_fields)
    
    return test_data


def get_contract_script_type(contract_name: str, output_type: OutputType) -> str:
    """
    Get the script_type string for a contract and output type.
    
    Args:
        contract_name: 'hodl', 'escrow', etc.
        output_type: 'p2wsh' or 'taproot'
    
    Returns:
        Script type string like 'cltv_escrow_p2wsh' or 'cltv_hodl_taproot'
    """
    if output_type == 'taproot':
        return f"cltv_{contract_name}_taproot"
    else:
        return f"cltv_{contract_name}_p2wsh"


def get_test_amount(test_number: int) -> int:
    """
    Calculate test amount based on test number.
    
    Test amounts are 1000 + test_number to easily identify which test funded what.
    """
    return 1000 + test_number


__all__ = ['build_e2e_test', 'get_contract_script_type', 'get_test_amount']

