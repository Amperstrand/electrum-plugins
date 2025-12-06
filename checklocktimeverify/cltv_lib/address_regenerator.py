"""
Address Regenerator - Derives all address data from script_type + params

This module implements the "stateless" storage model where we only store:
- script_type: identifies contract type and address format (e.g., 'cltv_escrow_taproot')
- params: the parameters needed to rebuild (locktime, pubkeys, data_hash, etc.)

Everything else is derived on-demand using build_contract():
- P2WSH: witness_script, address
- Taproot: leaf scripts, control blocks, merkle root, address

This approach is:
1. Storage efficient (params << serialized scripts)
2. Forward compatible (can fix bugs in script generation)
3. Debuggable (can trace how address was created)
4. Consistent (same params always produce same address)
"""

from typing import Dict, Any, Optional, Tuple, List
from electrum import constants

from .contracts import CONTRACTS


def get_network() -> str:
    """Get current network from Electrum constants."""
    if constants.net.GENESIS.startswith('00000008819873'):
        return 'signet'
    elif constants.net.NET_NAME == 'mainnet':
        return 'mainnet'
    elif constants.net.NET_NAME == 'testnet':
        return 'testnet'
    else:
        return 'regtest'


def parse_script_type(script_type: str) -> Tuple[str, str]:
    """
    Parse script_type into (contract_name, output_type).
    
    Examples:
        'cltv_escrow_taproot' -> ('escrow', 'taproot')
        'cltv_hodl' -> ('hodl', 'p2wsh')
        'cltv_payment_channel_p2wsh' -> ('payment_channel', 'p2wsh')
    
    Returns:
        (contract_name, output_type) tuple
    """
    # Remove 'cltv_' prefix
    base = script_type.replace('cltv_', '')
    
    # Determine output type
    if base.endswith('_taproot'):
        output_type = 'taproot'
        contract_name = base.replace('_taproot', '')
    elif base.endswith('_p2wsh'):
        output_type = 'p2wsh'
        contract_name = base.replace('_p2wsh', '')
    else:
        # Default to P2WSH for legacy names
        output_type = 'p2wsh'
        contract_name = base
    
    # v12.0.0: No legacy mappings - use canonical names only
    return contract_name, output_type


def normalize_params(contract_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize params to match what build_contract() expects.
    
    Since storage v12.0.0, all stored params use miniscript names directly
    (e.g., 'alice' not 'alice_pubkey'), so this is mostly a no-op now.
    
    Kept for future extensibility if param normalization is ever needed.
    """
    # v12.0.0+: params already use correct names (e.g., 'alice', not 'alice_pubkey')
    # No backwards compatibility needed - old addresses were wiped on upgrade
    return dict(params)


def regenerate_address_data(script_type: str, params: Dict[str, Any], network: Optional[str] = None) -> Dict[str, Any]:
    """
    Regenerate all address data from script_type and params.
    
    This is the core function that derives everything from minimal stored data.
    Uses build_contract() from generic.py for all contract types.
    
    Args:
        script_type: Contract type identifier (e.g., 'cltv_simple_taproot', 'cltv_escrow_p2wsh')
        params: Parameters dict with locktime, pubkeys, etc.
        network: Network name (auto-detected if None)
    
    Returns:
        Complete address data dict with:
        - address: The Bitcoin address
        - script_hex: Witness script (P2WSH) or default tapscript (Taproot)
        - output_script: The scriptPubKey
        - For Taproot: control blocks, leaf scripts, etc.
        - For P2WSH: witness_script
    """
    if network is None:
        network = get_network()
    
    # Parse script_type
    contract_name, output_type = parse_script_type(script_type)
    
    # Normalize params
    normalized_params = normalize_params(contract_name, params)
    
    # Use the generic builder
    from .builders.unified.generic import build_contract
    
    result = build_contract(
        contract_name=contract_name,
        params=normalized_params,
        output_type=output_type,
        network=network
    )
    
    # Add metadata
    result['script_type'] = script_type
    result['params'] = params
    result['address_type'] = 'Taproot' if output_type == 'taproot' else 'P2WSH'
    result['output_type'] = output_type
    
    return result


# =============================================================================
# Utility Functions
# =============================================================================

def is_taproot(script_type: str) -> bool:
    """Check if script_type is a Taproot variant."""
    return 'taproot' in script_type.lower()


def is_p2wsh(script_type: str) -> bool:
    """Check if script_type is a P2WSH variant."""
    return not is_taproot(script_type)


def get_address_type_display(script_type: str) -> str:
    """Get display name for address type."""
    if is_taproot(script_type):
        return 'Taproot'
    else:
        return 'P2WSH'


def get_contract_type_display(script_type: str) -> str:
    """Get display name for contract type."""
    contract_name, _ = parse_script_type(script_type)
    
    return {
        'hodl': 'Simple CLTV',
        'escrow': 'Three-Party Escrow',
        'twofactor': 'Two-Factor Auth',
        'payment_channel': 'Payment Channel',
        'data_publishing': 'Data Publishing'
    }.get(contract_name, contract_name.replace('_', ' ').title())


def get_required_params(script_type: str) -> List[str]:
    """
    Get list of required parameter names for a script type.
    
    Returns miniscript names directly (v12.0.0 format):
    - 'alice', 'bob' (not 'alice_pubkey', 'bob_pubkey')
    - 'pubkey' (for simple contracts)
    - 'locktime'
    
    The builder accepts both formats, but storage uses miniscript names.
    """
    contract_name, _ = parse_script_type(script_type)
    
    contract = CONTRACTS.get(contract_name)
    if not contract:
        return ['locktime']
    
    required = []
    for spec in contract.params:
        if spec.required:
            # Return miniscript names directly (v12.0.0 storage format)
            required.append(spec.name)
    
    return required


def validate_params(script_type: str, params: Dict[str, Any]) -> Tuple[bool, list]:
    """
    Validate that all required params are present (v12.0.0 format only).
    
    Returns:
        (is_valid: bool, missing_params: list)
    """
    required = get_required_params(script_type)
    missing = [p for p in required if p not in params or params[p] is None]
    return (len(missing) == 0, missing)
