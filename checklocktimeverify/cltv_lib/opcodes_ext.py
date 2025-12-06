"""
Extended Opcodes and Constants

Taproot-specific opcodes and constants not yet in Electrum's opcodes module.
This module has MINIMAL dependencies to avoid circular imports.

These can be imported from anywhere in the codebase without causing import loops.

References:
- BIP-340: Schnorr Signatures
- BIP-341: Taproot
- BIP-342: Tapscript
"""

from typing import List, Any, Union

# =============================================================================
# Tapscript Opcodes (BIP-342)
# =============================================================================

# OP_CHECKSIGADD (0xba) - Tapscript-only opcode for multi-signature
# Pops: sig, n, pubkey
# Pushes: n+1 if sig valid, n if sig empty, fails otherwise
OP_CHECKSIGADD = 0xba

# =============================================================================
# Witness Versions (BIP-141, BIP-341)
# =============================================================================

# Witness version 0 (P2WPKH, P2WSH)
WITNESS_V0 = 0x00

# Witness version 1 (P2TR - Taproot)
WITNESS_V1 = 0x01

# OP_0 for witness v0 scriptPubKey (same value as WITNESS_V0)
OP_WITNESS_V0 = 0x00

# OP_1 for witness v1 scriptPubKey (Taproot)
OP_WITNESS_V1 = 0x51

# =============================================================================
# Taproot Leaf Versions (BIP-341)
# =============================================================================

# Tapscript leaf version (BIP-342)
# This indicates the script should be interpreted as Tapscript
TAPSCRIPT_LEAF_VERSION = 0xc0

# Default leaf version (alias for clarity)
DEFAULT_LEAF_VERSION = TAPSCRIPT_LEAF_VERSION

# =============================================================================
# Script Construction Constants
# =============================================================================

# Push opcode for 20 bytes (OP_PUSHBYTES_20)
OP_PUSH_20 = 0x14

# Push opcode for 32 bytes (OP_PUSHBYTES_32)
OP_PUSH_32 = 0x20

# Push opcode for 33 bytes (OP_PUSHBYTES_33)
OP_PUSH_33 = 0x21

# =============================================================================
# Exported Names
# =============================================================================

def build_script_with_ext_opcodes(ops: List[Union[bytes, int, Any]]) -> bytes:
    """
    Build Bitcoin script supporting both Electrum and Taproot-extended opcodes.
    
    This is a high-level script builder that handles:
    - Electrum opcodes (e.g., opcodes.OP_DROP, opcodes.OP_CHECKSIG)
    - Extended opcodes (e.g., OP_CHECKSIGADD)
    - Integers → MINIMALDATA encoding (OP_0 to OP_16, or proper push)
    - Bytes → automatic data push with correct length prefix
    
    Args:
        ops: List of script elements, can be:
            - int: Will be encoded as MINIMALDATA (OP_0-OP_16 or pushed)
            - bytes: Will be pushed with proper length prefix
            - Electrum opcode (IntEnum): Used as-is
    
    Returns:
        Complete script as bytes
    
    Example:
        from electrum.bitcoin import opcodes
        from cltv_lib.opcodes_ext import OP_CHECKSIGADD, build_script_with_ext_opcodes
        
        script = build_script_with_ext_opcodes([
            100,                            # locktime (MINIMALDATA)
            opcodes.OP_CHECKLOCKTIMEVERIFY,
            opcodes.OP_DROP,
            pubkey_32_bytes,                # x-only pubkey
            OP_CHECKSIGADD,
        ])
    """
    # Import here to avoid circular imports
    from electrum.bitcoin import add_number_to_script
    
    result = bytearray()
    
    for op in ops:
        if isinstance(op, int) and 0 <= op <= 0xff and op not in (OP_CHECKSIGADD,):
            # Electrum opcode or small integer
            # For small integers (0-16), use add_number_to_script for MINIMALDATA
            if 0 <= op <= 16:
                result.extend(add_number_to_script(op))
            elif op >= 0x01 and op <= 0xff:
                # Likely an opcode value - use directly
                result.append(op)
            else:
                result.extend(add_number_to_script(op))
        elif isinstance(op, int):
            # Could be OP_CHECKSIGADD or a larger number
            if op == OP_CHECKSIGADD:
                result.append(OP_CHECKSIGADD)
            else:
                result.extend(add_number_to_script(op))
        elif isinstance(op, bytes):
            # Data push - add proper length prefix
            if len(op) <= 75:
                result.append(len(op))
            elif len(op) <= 255:
                result.append(0x4c)  # OP_PUSHDATA1
                result.append(len(op))
            elif len(op) <= 65535:
                result.append(0x4d)  # OP_PUSHDATA2
                result.extend(len(op).to_bytes(2, 'little'))
            else:
                result.append(0x4e)  # OP_PUSHDATA4
                result.extend(len(op).to_bytes(4, 'little'))
            result.extend(op)
        elif hasattr(op, '__int__'):
            # Electrum opcode (IntEnum)
            result.append(int(op))
        else:
            raise TypeError(f"Unsupported script element type: {type(op)}")
    
    return bytes(result)


__all__ = [
    # Opcodes
    'OP_CHECKSIGADD',
    
    # Witness versions
    'WITNESS_V0',
    'WITNESS_V1', 
    'OP_WITNESS_V0',
    'OP_WITNESS_V1',
    
    # Leaf versions
    'TAPSCRIPT_LEAF_VERSION',
    'DEFAULT_LEAF_VERSION',
    
    # Push opcodes
    'OP_PUSH_20',
    'OP_PUSH_32',
    'OP_PUSH_33',
    
    # Builder functions
    'build_script_with_ext_opcodes',
]

