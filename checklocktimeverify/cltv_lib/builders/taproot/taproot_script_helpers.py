"""
Taproot Script Path Helpers

Common utilities for:
1. Extracting script paths and control blocks from script_info
2. Building common Taproot script leaf patterns (DRY for builders)

Eliminates duplication across taproot builders and sweepers.
"""

from typing import Tuple


def get_script_path(script_info: dict, path_name: str) -> Tuple[str, str]:
    """
    Extract script and control block for a given script path.
    
    Args:
        script_info: Script info dict from create_*_taproot_address()
        path_name: Name of script path (e.g., 'cooperative', 'refund', 'normal')
    
    Returns:
        (script_hex, control_block_hex) tuple
    
    Example:
        >>> script_hex, control_hex = get_script_path(script_info, 'cooperative')
    """
    if 'scripts' not in script_info:
        raise ValueError("script_info missing 'scripts' key")
    
    if path_name not in script_info['scripts']:
        available = ', '.join(script_info['scripts'].keys())
        raise ValueError(f"Unknown script path '{path_name}'. Available: {available}")
    
    path_data = script_info['scripts'][path_name]
    
    if 'script' not in path_data or 'control_block' not in path_data:
        raise ValueError(f"Script path '{path_name}' missing 'script' or 'control_block'")
    
    return path_data['script'], path_data['control_block']


def get_script_path_bytes(script_info: dict, path_name: str) -> Tuple[bytes, bytes]:
    """
    Extract script and control block as bytes for a given script path.
    
    Args:
        script_info: Script info dict from create_*_taproot_address()
        path_name: Name of script path (e.g., 'cooperative', 'refund', 'normal')
    
    Returns:
        (script_bytes, control_block_bytes) tuple
    
    Example:
        >>> script, control = get_script_path_bytes(script_info, 'refund')
    """
    script_hex, control_hex = get_script_path(script_info, path_name)
    return bytes.fromhex(script_hex), bytes.fromhex(control_hex)


def get_output_key(script_info: dict) -> str:
    """
    Extract output key from script_info.
    
    Args:
        script_info: Script info dict from create_*_taproot_address()
    
    Returns:
        Output key as hex string
    """
    if 'output_key' not in script_info:
        raise ValueError("script_info missing 'output_key'")
    
    return script_info['output_key']


def get_output_key_bytes(script_info: dict) -> bytes:
    """
    Extract output key as bytes from script_info.
    
    Args:
        script_info: Script info dict from create_*_taproot_address()
    
    Returns:
        Output key as bytes
    """
    return bytes.fromhex(get_output_key(script_info))


# ============================================================================
# Common Taproot Script Leaf Patterns (DRY for Builders)
# ============================================================================

def build_cltv_single_sig_leaf(locktime: int, pubkey_xonly: bytes) -> bytes:
    """
    Build common CLTV + single signature leaf pattern.
    
    Script: <locktime> OP_CLTV OP_DROP <pubkey_xonly> OP_CHECKSIG
    
    Used by:
    - Payment channel refund path
    - Data publishing buyer refund path  
    - Two-factor recovery path
    
    Args:
        locktime: Block height or timestamp
        pubkey_xonly: 32-byte x-only public key (bytes)
    
    Returns:
        Script bytes
    
    Example:
        >>> refund_script = build_cltv_single_sig_leaf(601, sender_xonly)
    """
    from electrum.bitcoin import construct_script, opcodes
    return construct_script([
        locktime,
        opcodes.OP_CHECKLOCKTIMEVERIFY,
        opcodes.OP_DROP,
        pubkey_xonly,
        opcodes.OP_CHECKSIG
    ])


def build_2of2_leaf(pubkey1_xonly: bytes, pubkey2_xonly: bytes) -> bytes:
    """
    Build common 2-of-2 signature leaf pattern.
    
    Script: <pubkey1_xonly> OP_CHECKSIGVERIFY <pubkey2_xonly> OP_CHECKSIG
    
    Used by:
    - Payment channel cooperative path
    - Two-factor normal path
    - Escrow normal operations path
    
    Args:
        pubkey1_xonly: First 32-byte x-only public key (bytes)
        pubkey2_xonly: Second 32-byte x-only public key (bytes)
    
    Returns:
        Script bytes
    
    Example:
        >>> coop_script = build_2of2_leaf(sender_xonly, receiver_xonly)
    """
    from electrum.bitcoin import construct_script, opcodes
    return construct_script([
        pubkey1_xonly,
        opcodes.OP_CHECKSIGVERIFY,
        pubkey2_xonly,
        opcodes.OP_CHECKSIG
    ])


def build_data_publishing_publisher_leaf(data_hash: bytes, publisher_xonly: bytes) -> bytes:
    """
    Build Data Publishing publisher leaf (reveal preimage pattern).
    
    Script: OP_HASH160 <data_hash> OP_EQUALVERIFY <publisher_xonly> OP_CHECKSIG
    
    The publisher must reveal the preimage that hashes to data_hash.
    HASH160 = RIPEMD160(SHA256(data)) per BIP-65 spec.
    
    Used by:
    - Data Publishing publisher path (reveal + sign, anytime)
    
    Args:
        data_hash: 20-byte HASH160 of the data (RIPEMD160(SHA256(data)))
        publisher_xonly: 32-byte x-only public key of publisher
    
    Returns:
        Script bytes
    
    Example:
        >>> publisher_script = build_data_publishing_publisher_leaf(data_hash, publisher_xonly)
    
    Witness stack (for spending):
        [signature, preimage, script, control_block]
    """
    from electrum.bitcoin import construct_script, opcodes
    
    # Verify inputs are correct size
    if len(data_hash) != 20:
        raise ValueError(f"data_hash must be 20 bytes (HASH160), got {len(data_hash)}")
    if len(publisher_xonly) != 32:
        raise ValueError(f"publisher_xonly must be 32 bytes (x-only pubkey), got {len(publisher_xonly)}")
    
    return construct_script([
        opcodes.OP_HASH160,
        data_hash,
        opcodes.OP_EQUALVERIFY,
        publisher_xonly,
        opcodes.OP_CHECKSIG
    ])


def build_2of3_multisig_leaf(
    locktime: int,
    key1_xonly: bytes,
    key2_xonly: bytes, 
    key3_xonly: bytes
) -> bytes:
    """
    Build 2-of-3 threshold multisig with CLTV timelock.
    
    Script: <locktime> CLTV DROP <key1> CHECKSIG <key2> CHECKSIGADD <key3> CHECKSIGADD 2 EQUAL
    
    Standard miniscript multi_a(2, key1, key2, key3) pattern with timelock.
    First key uses CHECKSIG (initializes counter), subsequent keys use CHECKSIGADD.
    
    Used by:
    - Escrow arbitration path (Lenny + Alice OR Bob after timeout)
    
    Args:
        locktime: Block height that must be reached
        key1_xonly: First 32-byte x-only public key (arbitrator)
        key2_xonly: Second 32-byte x-only public key (party A)
        key3_xonly: Third 32-byte x-only public key (party B)
    
    Returns:
        Script bytes
    
    Witness stack (if key1 + key2 sign):
        [empty_key3, key2_sig, key1_sig, script, control_block]
    
    Witness stack (if key1 + key3 sign):
        [key3_sig, empty_key2, key1_sig, script, control_block]
    """
    from ...opcodes_ext import OP_CHECKSIGADD, build_script_with_ext_opcodes
    from electrum.bitcoin import opcodes
    
    # Verify inputs are correct size
    if len(key1_xonly) != 32:
        raise ValueError(f"key1_xonly must be 32 bytes (x-only pubkey), got {len(key1_xonly)}")
    if len(key2_xonly) != 32:
        raise ValueError(f"key2_xonly must be 32 bytes (x-only pubkey), got {len(key2_xonly)}")
    if len(key3_xonly) != 32:
        raise ValueError(f"key3_xonly must be 32 bytes (x-only pubkey), got {len(key3_xonly)}")
    
    return build_script_with_ext_opcodes([
        locktime,
        opcodes.OP_CHECKLOCKTIMEVERIFY,
        opcodes.OP_DROP,
        key1_xonly,
        opcodes.OP_CHECKSIG,  # First key: CHECKSIG (initializes counter)
        key2_xonly,
        OP_CHECKSIGADD,       # Subsequent keys: CHECKSIGADD
        key3_xonly,
        OP_CHECKSIGADD,
        opcodes.OP_2,
        opcodes.OP_EQUAL,
    ])
