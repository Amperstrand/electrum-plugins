"""
Descriptors Package - Miniscript and Bitcoin Descriptors

Provides first-class support for Miniscript expressions and
Bitcoin descriptors for all CLTV script types.

This module is for educational/documentation purposes and enables
transparency in how our Bitcoin Scripts map to Miniscript.

Main Functions:
- get_miniscript(): Generate Miniscript expression (symbolic or concrete)
- get_descriptor(): Generate Bitcoin descriptor (wsh or tr format)

Examples:
    >>> from cltv_lib.descriptors import get_miniscript, get_descriptor
    >>> 
    >>> # Symbolic Miniscript (educational)
    >>> ms = get_miniscript('cltv_hodl', {'locktime': 100}, 'symbolic')
    >>> print(ms)
    'and_v(v:pk(pubkey), after(100))'
    >>> 
    >>> # Concrete Miniscript (with actual keys)
    >>> params = {'locktime': 100, 'pubkey': '02abc123...'}
    >>> ms = get_miniscript('cltv_hodl', params, 'concrete')
    >>> print(ms)
    'and_v(v:pk(02abc123...), after(100))'
    >>> 
    >>> # Bitcoin descriptor
    >>> desc = get_descriptor('cltv_hodl', params, 'wsh')
    >>> print(desc)
    'wsh(and_v(v:pk(02abc123...), after(100)))'
"""

from .miniscript import get_miniscript
from .descriptors import get_descriptor

__all__ = [
    'get_miniscript',
    'get_descriptor',
]
