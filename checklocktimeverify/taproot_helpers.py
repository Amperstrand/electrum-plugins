"""
Taproot Helper Functions for BIP-341/342 Support

This module provides utilities for creating Taproot addresses
from CLTV scripts.

Key Functions:
- pubkey_to_xonly(): Convert pubkeys to x-only format (32 bytes)
- create_taproot_address(): Create taproot address from script
- create_mast_tree(): Create MAST with multiple spending paths (future)

References:
- BIP-340: Schnorr Signatures for secp256k1
- BIP-341: Taproot: SegWit version 1 spending rules
- BIP-342: Validation of Taproot Scripts
"""

from typing import Dict, List, Tuple, Optional
from electrum.bitcoin import (
    taproot_output_script,
    control_block_for_taproot_script_spend,
    opcodes
)
from electrum import segwit_addr, constants
from electrum.util import bfh
import logging

logger = logging.getLogger(__name__)

# NUMS Point - "Nothing Up My Sleeve"
# This is a verifiably random point with no known discrete log
# Generated as: H = hash_to_curve("Bitcoin")
# We use this as internal key so there's NO key-path spend possible
# (only script-path spending allowed)
NUMS_POINT = bytes.fromhex(
    "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
)


def pubkey_to_xonly(pubkey_hex: str) -> bytes:
    """
    Convert compressed/uncompressed pubkey to x-only format (32 bytes).
    
    X-only pubkeys are required for Taproot scripts (BIP-340).
    They contain only the x-coordinate, with even y assumed.
    
    Args:
        pubkey_hex: Public key in hex (33 bytes compressed, 65 uncompressed, or 32 x-only)
    
    Returns:
        32-byte x-only public key
    
    Raises:
        ValueError: If pubkey has invalid length
    
    Examples:
        >>> # Compressed pubkey (33 bytes with 02/03 prefix)
        >>> xonly = pubkey_to_xonly("0339a36013301597daef41fbe593a02cc513d0b55527ec2df1050e2e8ff49c85c2")
        >>> len(xonly)
        32
        
        >>> # Uncompressed pubkey (65 bytes with 04 prefix)
        >>> xonly = pubkey_to_xonly("04" + "x"*128)  # 65 bytes total
        >>> len(xonly)
        32
    """
    pubkey_bytes = bytes.fromhex(pubkey_hex) if isinstance(pubkey_hex, str) else pubkey_hex
    
    if len(pubkey_bytes) == 33:
        # Compressed pubkey (02/03 prefix + 32 bytes)
        # Remove prefix byte, keep x-coordinate
        return pubkey_bytes[1:]
    elif len(pubkey_bytes) == 65:
        # Uncompressed pubkey (04 prefix + 32 bytes x + 32 bytes y)
        # Remove prefix and y-coordinate, keep only x
        return pubkey_bytes[1:33]
    elif len(pubkey_bytes) == 32:
        # Already x-only
        return pubkey_bytes
    else:
        raise ValueError(
            f"Invalid pubkey length: {len(pubkey_bytes)} bytes. "
            f"Expected 33 (compressed), 65 (uncompressed), or 32 (x-only)"
        )


def create_taproot_address(
    tapscript: bytes,
    network=None,
    internal_pubkey: Optional[bytes] = None
) -> Dict[str, str]:
    """
    Create taproot address from a tapscript.
    
    Uses NUMS point as internal key by default (no key-path spend).
    This ensures ONLY script-path spending is possible, making the
    script spending conditions mandatory.
    
    Args:
        tapscript: The tapscript bytes (CLTV script, escrow script, etc.)
        network: Network constants (defaults to current network)
        internal_pubkey: Optional 32-byte x-only internal pubkey
                        (defaults to NUMS point for script-only spending)
    
    Returns:
        Dictionary containing:
        - address: Bech32m taproot address (tb1p... or bc1p...)
        - tapscript: Tapscript hex
        - control_block: Control block hex (needed for spending)
        - internal_pubkey: Internal pubkey hex
        - witness_program: Witness program hex
        - leaf_version: Tapscript leaf version (0xc0)
        - output_script: Full output script hex
    
    Example:
        >>> from electrum.bitcoin import construct_script, opcodes
        >>> # Create simple CLTV script
        >>> script = construct_script([
        ...     100,  # locktime
        ...     opcodes.OP_CHECKLOCKTIMEVERIFY,
        ...     opcodes.OP_DROP,
        ...     bytes.fromhex("339a36013..."),  # x-only pubkey
        ...     opcodes.OP_CHECKSIG
        ... ])
        >>> result = create_taproot_address(script)
        >>> result['address']
        'tb1p...'  # Taproot address on signet
    """
    if network is None:
        network = constants.net
    
    if internal_pubkey is None:
        internal_pubkey = NUMS_POINT
        logger.info("[TAPROOT] Using NUMS point as internal key (script-only spending)")
    
    # Validate internal pubkey
    if not isinstance(internal_pubkey, bytes) or len(internal_pubkey) != 32:
        raise ValueError(f"Internal pubkey must be 32 bytes, got {len(internal_pubkey)}")
    
    # Build script tree with single script
    # For a single script, TapTree is just (leaf_version, script) tuple
    # For MAST (multiple scripts), it would be [left_tree, right_tree]
    leaf_version = 0xc0  # Tapscript leaf version from BIP-342
    script_tree = (leaf_version, tapscript)
    
    logger.info(f"[TAPROOT] Creating taproot output:")
    logger.info(f"  Internal pubkey: {internal_pubkey.hex()}")
    logger.info(f"  Tapscript size: {len(tapscript)} bytes")
    logger.info(f"  Leaf version: 0x{leaf_version:02x}")
    
    # Create taproot output script using Electrum's built-in function
    output_script = taproot_output_script(
        internal_pubkey, 
        script_tree=script_tree
    )
    
    logger.info(f"  Output script: {output_script.hex()}")
    
    # Get control block for script-path spending
    # This proves the script is part of the taproot tree
    leaf_script, control_block = control_block_for_taproot_script_spend(
        internal_pubkey=internal_pubkey,
        script_tree=script_tree,
        script_num=0  # First (and only) script in tree
    )
    
    logger.info(f"  Control block: {control_block.hex()}")
    logger.info(f"  Control block size: {len(control_block)} bytes")
    
    # Extract witness program (everything after OP_1 and push byte)
    # Output script format: OP_1 <32-byte-witness-program>
    witness_program = output_script[2:]
    
    if len(witness_program) != 32:
        raise ValueError(f"Invalid witness program length: {len(witness_program)}, expected 32")
    
    # Encode as bech32m address (witness version 1 = Taproot)
    address = segwit_addr.encode_segwit_address(
        network.SEGWIT_HRP,
        1,  # Witness version 1 = Taproot
        witness_program
    )
    
    logger.info(f"  ✅ Taproot address: {address}")
    
    return {
        'address': address,
        'tapscript': tapscript.hex(),
        'control_block': control_block.hex(),
        'internal_pubkey': internal_pubkey.hex(),
        'witness_program': witness_program.hex(),
        'leaf_version': leaf_version,
        'output_script': output_script.hex()
    }


def create_mast_tree(
    scripts: List[bytes],
    network=None,
    internal_pubkey: Optional[bytes] = None
) -> Dict:
    """
    Create MAST (Merkle Alternative Script Tree) with multiple scripts.
    
    MAST allows multiple spending conditions where only the used path
    is revealed on-chain. Unused paths remain private.
    
    This is useful for:
    - Escrow: immediate 2-of-2 OR timeout + arbiter
    - Two-factor: user+2FA OR user+recovery after timeout
    - Payment channels: receiver OR sender refund
    
    Args:
        scripts: List of script bytes (2 or more spending paths)
        network: Network constants
        internal_pubkey: Optional internal pubkey (defaults to NUMS)
    
    Returns:
        Dictionary with address and control blocks for each path
    
    TODO: Implement MAST support
    This requires building a merkle tree and generating control blocks
    for each spending path. For now, we use single-script taproot.
    
    Example future usage:
        >>> # Escrow with two paths
        >>> path1 = construct_script([...])  # Immediate 2-of-2
        >>> path2 = construct_script([...])  # Timeout + arbiter
        >>> result = create_mast_tree([path1, path2])
        >>> # result['control_blocks'] has one for each path
    """
    if len(scripts) < 2:
        raise ValueError("MAST requires at least 2 scripts. Use create_taproot_address() for single script.")
    
    # TODO: Implement MAST
    # For Phase 1, we only support single-script taproot
    # MAST will be added in Phase 2 for complex examples
    raise NotImplementedError(
        "MAST (multiple script paths) not yet implemented. "
        "Currently only single-script taproot is supported. "
        "Coming in Phase 2!"
    )


def validate_taproot_address(address: str, network=None) -> bool:
    """
    Validate a taproot address format.
    
    Args:
        address: Address to validate
        network: Network constants
    
    Returns:
        True if valid taproot address, False otherwise
    """
    if network is None:
        network = constants.net
    
    try:
        witver, witprog = segwit_addr.decode_segwit_address(network.SEGWIT_HRP, address)
        # Taproot is witness version 1 with 32-byte program
        return witver == 1 and len(witprog) == 32
    except Exception:
        return False


def extract_tapscript_from_witness(witness: List[bytes]) -> Tuple[bytes, bytes, bytes]:
    """
    Extract tapscript and control block from spending witness.
    
    Taproot script-path witness format:
    - witness[0]: Signature(s) and other stack elements
    - witness[-2]: The tapscript being executed
    - witness[-1]: Control block proving script is in tree
    
    Args:
        witness: List of witness stack elements
    
    Returns:
        Tuple of (stack_elements, tapscript, control_block)
    
    Example:
        >>> witness = [sig, tapscript, control_block]
        >>> stack, script, cb = extract_tapscript_from_witness(witness)
    """
    if len(witness) < 2:
        raise ValueError("Taproot witness must have at least 2 elements (script + control block)")
    
    control_block = witness[-1]
    tapscript = witness[-2]
    stack_elements = witness[:-2] if len(witness) > 2 else []
    
    return (stack_elements, tapscript, control_block)


# Export key functions
__all__ = [
    'NUMS_POINT',
    'pubkey_to_xonly',
    'create_taproot_address',
    'create_mast_tree',
    'validate_taproot_address',
    'extract_tapscript_from_witness'
]
