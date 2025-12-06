"""
Miniscript Registry - Compatibility Shim for cltv_lib

This module provides backward-compatible APIs for E2E tests while importing
from the new cltv_lib.descriptors module.

MIGRATION STATUS (Phase 2):
- ✅ All functions now delegate to cltv_lib.descriptors
- ✅ Tests use production library code
- ✅ Backward compatibility maintained

After all tests verified, this shim can be removed and tests updated to
import directly from cltv_lib.descriptors.

Usage:
    from miniscript_registry import miniscript_for, descriptor_for
    
    ms = miniscript_for('cltv_hodl', params, 'symbolic')
    desc = descriptor_for('cltv_hodl', params, 'wsh')
"""

import sys
import os

# Add parent directory to import cltv_lib
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# Import from production library (single source of truth)
from cltv_lib.descriptors import get_miniscript, get_descriptor

# ============================================================================
# Compatibility Wrappers
# ============================================================================

def miniscript_for(script_type: str, params: dict, style: str = 'symbolic') -> str:
    """
    Render Miniscript expression for a given script type and params.
    
    Wrapper for cltv_lib.descriptors.get_miniscript().
    
    Args:
        script_type: Builder's SCRIPT_TYPE (e.g., 'cltv_hodl')
        params: Parameter dict (pubkeys, locktime, data_hash)
        style: 'symbolic' (role names) or 'concrete' (insert hex)
    
    Returns:
        Miniscript expression string
    
    Examples:
        >>> miniscript_for('cltv_hodl', {'locktime': 100}, 'symbolic')
        'and_v(v:pk(pubkey), after(100))'
        
        >>> miniscript_for('cltv_hodl', {'locktime': 100, 'pubkey': '02...'}, 'concrete')
        'and_v(v:pk(02...), after(100))'
    """
    return get_miniscript(script_type, params, style)


def descriptor_for(script_type: str, params: dict, variant: str = 'wsh') -> str:
    """
    Render a Bitcoin Core/Electrum descriptor string for the given script type.
    
    Wrapper for cltv_lib.descriptors.get_descriptor().
    
    Args:
        script_type: Builder SCRIPT_TYPE (e.g., 'cltv_hodl')
        params: Parameter dict (will render concrete miniscript)
        variant: 'wsh' for P2WSH (default), 'tr' for Taproot
    
    Returns:
        Descriptor string
    
    Examples:
        >>> descriptor_for('cltv_hodl', {'locktime': 100, 'pubkey': '02...'}, 'wsh')
        'wsh(and_v(v:pk(02...), after(100)))'
    """
    return get_descriptor(script_type, params, variant)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'miniscript_for',
    'descriptor_for',
    'get_miniscript',
    'get_descriptor',
]
