"""
Miniscript Generation for CLTV Scripts

This module renders Miniscript strings for each CLTV `script_type` using the
**single source of truth** in `cltv_lib.contracts.CONTRACTS`.

It is purely presentational:
- symbolic: shows role names (`alice`, `bob`, `sender`, `locktime`)
- concrete: substitutes actual hex keys / hashes and numeric locktime

All semantic behaviour (actual scripts, addresses, witnesses) comes from the
miniscript compiler and `ContractDefinition.miniscript`, not from here.
"""

from typing import Dict, Any, Literal
import re

from ..contracts import CONTRACTS

Style = Literal['symbolic', 'concrete']


def _resolve_contract_name(script_type: str) -> str:
    """
    Map a script_type like 'cltv_hodl' or 'cltv_escrow_taproot'
    to the underlying contract name in CONTRACTS ('hodl', 'escrow').
    """
    name = script_type
    if name.startswith('cltv_'):
        name = name[len('cltv_'):]
    for suffix in ('_taproot', '_p2wsh', '_p2sh'):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if name not in CONTRACTS:
        raise ValueError(f"Unknown script_type for miniscript: {script_type}")
    return name


def get_miniscript(script_type: str, params: Dict[str, Any], style: Style = 'symbolic') -> str:
    """
    Render Miniscript expression for a given script type and params.
    
    This delegates to `ContractDefinition.miniscript` and then, for
    `style='concrete'`, substitutes actual parameter values (pubkeys,
    hashes, locktime) into the string.
    
    Args:
        script_type: Script type identifier (e.g., 'cltv_hodl', 'cltv_escrow')
        params: Parameter dict (pubkeys, locktime, data_hash)
        style: 'symbolic' (role names) or 'concrete' (insert hex values)
    
    Returns:
        Miniscript expression string.
    """
    contract_name = _resolve_contract_name(script_type)
    contract = CONTRACTS[contract_name]
    
    # Start from the canonical miniscript template
    ms = contract.miniscript
    
    # Always substitute locktime if available (helps docs & descriptors)
    locktime_val = params.get('locktime')
    if locktime_val is not None:
        ms = re.sub(r'\blocktime\b', str(locktime_val), ms)
    
    if style == 'symbolic':
        # Return template with optional locktime number substituted
        return ms
    
    # Concrete style: substitute keys / hashes
    concrete = ms
    
    for spec in contract.params:
        name = spec.name
        
        if spec.param_type == 'pubkey':
            # Accept both new-style ('alice') and legacy ('alice_pubkey') params
            key_hex = (
                params.get(f"{name}_pubkey")
                or params.get(f"{name}_pubkey_xonly")
                or params.get(name)
            )
            if key_hex:
                concrete = re.sub(rf'\b{name}\b', key_hex, concrete)
        
        elif spec.param_type == 'hash160':
            # Data hash parameters (e.g. data_hash)
            h = params.get(name) or params.get(f"{name}_hash")
            if h:
                concrete = re.sub(rf'\b{name}\b', h, concrete)
    
    return concrete
    
    
__all__ = ['get_miniscript']
