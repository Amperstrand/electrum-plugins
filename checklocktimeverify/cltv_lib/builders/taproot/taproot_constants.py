"""
Taproot Constants

Centralized definitions for Taproot-specific opcodes, versions, and magic values.
These are not yet available in Electrum's opcodes module.

This module re-exports constants from opcodes_ext and adds helper functions.

References:
- BIP-340: Schnorr Signatures
- BIP-341: Taproot
- BIP-342: Tapscript
"""

# Import base constants from the dependency-free module
from ...opcodes_ext import (
    # Opcodes
    OP_CHECKSIGADD,
    # Witness versions
    WITNESS_V0,
    WITNESS_V1,
    OP_WITNESS_V0,
    OP_WITNESS_V1,
    # Leaf versions
    TAPSCRIPT_LEAF_VERSION,
    DEFAULT_LEAF_VERSION,
    # Push opcodes
    OP_PUSH_20,
    OP_PUSH_32,
    OP_PUSH_33,
)


# =============================================================================
# Helper Functions
# =============================================================================

def make_witness_v0_scriptpubkey(program: bytes) -> bytes:
    """
    Create P2WPKH or P2WSH scriptPubKey.
    
    Args:
        program: 20-byte (P2WPKH) or 32-byte (P2WSH) witness program
    
    Returns:
        scriptPubKey: OP_0 <len> <program>
    """
    return bytes([OP_WITNESS_V0, len(program)]) + program


def make_witness_v1_scriptpubkey(output_key: bytes) -> bytes:
    """
    Create P2TR (Taproot) scriptPubKey.
    
    Args:
        output_key: 32-byte x-only tweaked output key
    
    Returns:
        scriptPubKey: OP_1 0x20 <output_key>
    
    Example:
        >>> output_key = bytes.fromhex("a0...")
        >>> spk = make_witness_v1_scriptpubkey(output_key)
        >>> spk.hex()
        '5120a0...'
    """
    if len(output_key) != 32:
        raise ValueError(f"Output key must be 32 bytes, got {len(output_key)}")
    return bytes([OP_WITNESS_V1, OP_PUSH_32]) + output_key


def make_control_block_prefix(leaf_version: int, parity: int) -> int:
    """
    Create the first byte of a control block.
    
    Args:
        leaf_version: Leaf version (e.g., TAPSCRIPT_LEAF_VERSION for Tapscript)
        parity: Parity bit of output key (0 or 1)
    
    Returns:
        Single byte: leaf_version | parity
    
    Example:
        >>> make_control_block_prefix(TAPSCRIPT_LEAF_VERSION, 1)
        0xc1
    """
    return leaf_version | parity


# =============================================================================
# Validation
# =============================================================================

def is_valid_leaf_version(version: int) -> bool:
    """
    Check if a leaf version is valid per BIP-341.
    
    Valid leaf versions have the lowest bit unset (0) to allow
    for parity encoding in control blocks.
    """
    return (version & 0x01) == 0


def is_tapscript_version(version: int) -> bool:
    """Check if this is the standard Tapscript version."""
    return version == TAPSCRIPT_LEAF_VERSION


# =============================================================================
# Exported Names
# =============================================================================

__all__ = [
    # Opcodes (from opcodes_ext)
    'OP_CHECKSIGADD',
    
    # Witness versions (from opcodes_ext)
    'WITNESS_V0',
    'WITNESS_V1', 
    'OP_WITNESS_V0',
    'OP_WITNESS_V1',
    
    # Leaf versions (from opcodes_ext)
    'TAPSCRIPT_LEAF_VERSION',
    'DEFAULT_LEAF_VERSION',
    
    # Push opcodes (from opcodes_ext)
    'OP_PUSH_20',
    'OP_PUSH_32',
    'OP_PUSH_33',
    
    # Helper functions
    'make_witness_v0_scriptpubkey',
    'make_witness_v1_scriptpubkey',
    'make_control_block_prefix',
    
    # Validation
    'is_valid_leaf_version',
    'is_tapscript_version',
]
