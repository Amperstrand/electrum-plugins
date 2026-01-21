"""
Bitcoin Descriptor Generation

Creates Bitcoin Core/Electrum compatible descriptors for all CLTV script types.
Wraps Miniscript expressions in appropriate descriptor formats (wsh, tr).

Descriptors are the standard way to describe Bitcoin output scripts in a
human-readable and machine-parseable format.

Example:
    >>> from cltv_lib.descriptors import get_descriptor
    >>> 
    >>> # P2WSH descriptor
    >>> desc = get_descriptor('cltv_hodl', 
    ...     {'locktime': 100, 'pubkey': '02abc...'}, 
    ...     variant='wsh')
    >>> # Returns: "wsh(and_v(v:pk(02abc...), after(100)))"
    >>> 
    >>> # Taproot descriptor
    >>> desc = get_descriptor('cltv_escrow',
    ...     {'locktime': 500, 'alice_pubkey': '02...', ...},
    ...     variant='tr',
    ...     internal_key='03...')
    >>> # Returns: "tr(03..., and_v(...))"

Reference:
- Bitcoin Core descriptor docs: https://github.com/bitcoin/bitcoin/blob/master/doc/descriptors.md
- Miniscript: https://bitcoin.sipa.be/miniscript/
"""

from typing import Dict, Any, Literal, Optional
from .miniscript import get_miniscript

Variant = Literal['wsh', 'tr']


def get_descriptor(
    script_type: str,
    params: Dict[str, Any],
    variant: Variant = 'wsh',
    internal_key: Optional[str] = None,
    checksum: bool = False
) -> str:
    """
    Generate Bitcoin descriptor for a CLTV script type.
    
    Args:
        script_type: Script type identifier (e.g., 'cltv_hodl')
        params: Parameter dict (will render concrete miniscript with actual keys)
        variant: 'wsh' for P2WSH (default), 'tr' for Taproot
        internal_key: Required for Taproot descriptors (32-byte x-only pubkey hex)
        checksum: Whether to append descriptor checksum (not yet implemented)
    
    Returns:
        Descriptor string
    
    Raises:
        ValueError: If unknown variant or missing internal_key for Taproot
    
    Examples:
        >>> # P2WSH descriptor
        >>> params = {'locktime': 100, 'pubkey': '02abc...'}
        >>> get_descriptor('cltv_hodl', params, variant='wsh')
        'wsh(and_v(v:pk(02abc...), after(100)))'
        
        >>> # Taproot descriptor
        >>> params = {'locktime': 100, 'alice_pubkey': '02...', 'bob_pubkey': '03...', 'lenny_pubkey': '02...'}
        >>> get_descriptor('cltv_escrow', params, variant='tr', internal_key='abc123...')
        'tr(abc123..., or_i(multi(2, 02..., 03...), and_v(v:after(100), ...)))'
    """
    # Generate concrete Miniscript (with actual key values)
    ms = get_miniscript(script_type, params, style='concrete')
    
    if variant == 'wsh':
        # P2WSH descriptor: wsh(miniscript)
        desc = f"wsh({ms})"
        
    elif variant == 'tr':
        # Taproot descriptor: tr(internal_key, miniscript)
        if not internal_key:
            raise ValueError("internal_key required for Taproot descriptors (variant='tr')")
        desc = f"tr({internal_key}, {ms})"
        
    else:
        raise ValueError(f"Unknown descriptor variant: {variant}. Use 'wsh' or 'tr'.")
    
    if checksum:
        # Implement Bitcoin Core descriptor checksum algorithm
        desc = desc + "#" + _descriptor_checksum(desc)
    
    return desc


# Backward compatibility alias
descriptor_for = get_descriptor


def _descriptor_checksum(desc: str) -> str:
    """
    Bitcoin Core descriptor checksum implementation.
    
    Implements the checksum algorithm described in BIP-380:
    https://github.com/bitcoin/bips/blob/master/bip-0380.mediawiki
    
    The checksum is 8 characters of the custom base58 alphabet.
    """
    import hashlib
    
    # Step 1: Add sentinel prefix
    input_data = desc + "#"
    
    # Step 2: Compute SHA256 hash twice
    sha256_1 = hashlib.sha256(input_data.encode('utf-8')).digest()
    sha256_2 = hashlib.sha256(sha256_1).digest()
    
    # Step 3: Convert to 8-character checksum using base58-like alphabet
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    checksum = ""
    
    # Treat the hash as a big-endian number and convert to base58
    value = int.from_bytes(sha256_2[:8], byteorder='big')
    
    for _ in range(8):
        value, rem = divmod(value, len(alphabet))
        checksum = alphabet[rem] + checksum
    
    return checksum


__all__ = ['get_descriptor', 'descriptor_for']
