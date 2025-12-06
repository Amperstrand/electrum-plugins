"""
Centralized Taproot utilities - eliminates code duplication.

This module provides security-critical functions used across all Taproot
builders and sweepers. By centralizing these implementations:
1. Reduces attack surface (single implementation vs 11+ copies)
2. Uses Electrum builtins where available (including bip340_tagged_hash)
3. Ensures consistency across all Taproot transaction construction

Functions:
    - tagged_hash: BIP-340 tagged SHA256 hashing (via Electrum's electrum_ecc)
    - varint: Variable-length integer encoding for transactions
    - encode_script_number: Minimal ScriptNum encoding (Electrum-backed)
    - pubkey_to_xonly: Convert 33-byte compressed → 32-byte x-only
    - xonly_to_compressed: Convert 32-byte x-only → 33-byte compressed (requires parity)

Notes on pubkey formats and conversions:
    - Taproot scripts use x-only public keys (32 bytes, no 02/03 prefix)
    - P2WSH scripts use 33-byte compressed keys with 0x02/0x03 parity prefix
    - Converting compressed → x-only is lossless (drop prefix)
    - Converting x-only → compressed REQUIRES a parity bit (even=0x02, odd=0x03)
      You must know the original key's parity (e.g., from the signer) to restore
      the correct compressed form. We default to even (0x02) if parity is not provided,
      but callers SHOULD pass the actual parity when available.
"""

import sys
import os

# Import from Electrum's electrum_ecc (native BIP-340 support)
from electrum_ecc.util import bip340_tagged_hash

# Import from Electrum
from electrum.bitcoin import var_int, script_num_to_bytes
from electrum.crypto import sha256

# For ECC operations, use vendored reference implementations
# These are not exposed by electrum_ecc in a convenient way
from ...third_party import G, lift_x, point_mul, point_add

# Import constants for tree hash functions
from .taproot_constants import TAPSCRIPT_LEAF_VERSION


def tagged_hash(tag: str, data: bytes) -> bytes:
    """
    BIP-340 tagged SHA256 hashing.
    
    Uses Electrum's native bip340_tagged_hash from electrum_ecc.
    
    Args:
        tag: Tag string (e.g., "TapLeaf", "TapBranch", "TapTweak", "TapSighash")
        data: Data to hash
        
    Returns:
        32-byte tagged hash
        
    Example:
        >>> tagged_hash("TapLeaf", b"\\xc0\\x04script")
        b'...'
    """
    # Electrum's bip340_tagged_hash takes bytes tag, we convert string
    return bip340_tagged_hash(tag.encode('utf-8'), data)


def varint(n: int) -> bytes:
    """
    Variable-length integer encoding for Bitcoin transactions.
    
    Uses Electrum's built-in var_int implementation for consistency
    with transaction serialization throughout Electrum.
    
    Args:
        n: Integer to encode (0 to 2^64-1)
        
    Returns:
        Variable-length encoded bytes (1, 3, 5, or 9 bytes)
        
    Raises:
        ValueError: If n is negative or exceeds 2^64-1
    """
    return var_int(n)


def encode_script_number(n: int) -> bytes:
    """
    Encode integer as Bitcoin script number.
    
    Uses Electrum's battle-tested script_num_to_bytes implementation.
    This is the minimal encoding required by Bitcoin consensus rules.
    
    For numbers 1-16, Bitcoin requires using OP_1 through OP_16 opcodes
    instead of data pushes to comply with SCRIPT_VERIFY_MINIMALDATA (BIP 62 rule 3).
    
    Args:
        n: Integer to encode (supports positive and negative)
        
    Returns:
        Minimally-encoded script number bytes
        
    Examples:
        >>> encode_script_number(0)
        b'\\x00'  # OP_0
        >>> encode_script_number(1)
        b'\\x51'  # OP_1
        >>> encode_script_number(16)
        b'\\x60'  # OP_16
        >>> encode_script_number(17)
        b'\\x11'  # Data push of 17
    """
    from electrum.bitcoin import opcodes
    
    # For 1-16, use OP_1 through OP_16 (BIP 62 rule 3)
    # This avoids "Data push larger than necessary" error
    if 1 <= n <= 16:
        return bytes([opcodes.OP_1 + (n - 1)])  # OP_1=0x51, OP_2=0x52, ..., OP_16=0x60
    elif n == 0:
        return bytes([opcodes.OP_0])  # OP_0=0x00
    elif n == -1:
        return bytes([opcodes.OP_1NEGATE])  # OP_1NEGATE=0x4f
    else:
        return script_num_to_bytes(n)


def pubkey_to_xonly(pubkey_hex: str) -> bytes:
    """
    Convert compressed pubkey (33 bytes) to x-only pubkey (32 bytes).
    
    Taproot uses x-only public keys (just the x-coordinate) instead of
    compressed pubkeys. This strips the parity byte prefix.
    
    Args:
        pubkey_hex: 33-byte compressed pubkey in hex (02/03 prefix)
        
    Returns:
        32-byte x-only pubkey (no prefix)
        
    Raises:
        ValueError: If pubkey is not exactly 33 bytes
        
    Examples:
        >>> pubkey = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
        >>> xonly = pubkey_to_xonly(pubkey)
        >>> len(xonly)
        32
    """
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    if len(pubkey_bytes) != 33:
        raise ValueError(f"Expected 33-byte compressed pubkey, got {len(pubkey_bytes)} bytes")
    return pubkey_bytes[1:]  # Strip the parity byte prefix


def xonly_to_compressed(xonly_hex: str, parity: int = 0) -> bytes:
    """
    Convert x-only pubkey (32 bytes) to compressed pubkey (33 bytes).

    Important: This requires the y-parity bit of the original point.
    - parity = 0 → even y → 0x02 prefix
    - parity = 1 → odd y  → 0x03 prefix

    Args:
        xonly_hex: 32-byte x-only pubkey as hex
        parity: 0 for even (default), 1 for odd

    Returns:
        33-byte compressed public key (bytes)

    Raises:
        ValueError: If length is not 32 bytes or parity not in {0,1}
    """
    xonly = bytes.fromhex(xonly_hex)
    if len(xonly) != 32:
        raise ValueError(f"Expected 32-byte x-only pubkey, got {len(xonly)} bytes")
    if parity not in (0, 1):
        raise ValueError("parity must be 0 (even) or 1 (odd)")
    prefix = 0x02 if parity == 0 else 0x03
    return bytes([prefix]) + xonly


# ============================================================================
# Taproot Tree Hash Functions (BIP-341)
# ============================================================================

def compute_tapleaf_hash(script: bytes, leaf_version: int = TAPSCRIPT_LEAF_VERSION) -> bytes:
    """
    Compute TapLeaf hash for a script (BIP-341).
    
    TapLeaf = TaggedHash("TapLeaf", leaf_version || compact_size(script) || script)
    
    Args:
        script: Script bytes
        leaf_version: Leaf version (0xc0 for tapscript)
    
    Returns:
        32-byte tapleaf hash
    """
    return tagged_hash("TapLeaf", bytes([leaf_version]) + varint(len(script)) + script)


def compute_tapbranch_hash(left: bytes, right: bytes) -> bytes:
    """
    Compute TapBranch hash for two child nodes (BIP-341).
    
    TapBranch = TaggedHash("TapBranch", left || right)
    
    Nodes are sorted lexicographically before hashing.
    
    Args:
        left: Left child hash (32 bytes)
        right: Right child hash (32 bytes)
    
    Returns:
        32-byte branch hash
    """
    if left <= right:
        return tagged_hash("TapBranch", left + right)
    else:
        return tagged_hash("TapBranch", right + left)


# ============================================================================
# Constants
# ============================================================================

# NUMS point - "Nothing Up My Sleeve" for Taproot internal key (script-path only)
# This is a standard NUMS point used to disable key-path spending in Taproot.
# Reference: BIP-341 Section "Constructing and spending Taproot outputs"
NUMS_H = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"


# Export public API
__all__ = [
    'tagged_hash', 
    'varint', 
    'sha256', 
    'encode_script_number', 
    'pubkey_to_xonly', 
    'xonly_to_compressed',
    'compute_tapleaf_hash',
    'compute_tapbranch_hash',
    'NUMS_H', 
    'G', 
    'lift_x', 
    'point_mul', 
    'point_add'
]
