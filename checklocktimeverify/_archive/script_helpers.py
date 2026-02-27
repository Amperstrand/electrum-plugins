"""
Common Script Helper Functions

Reusable script construction utilities to reduce code duplication
across CLTV plugin modules.

These helpers encapsulate common Bitcoin script patterns for CLTV contracts.
"""

from typing import Tuple, List, Union
from electrum.bitcoin import construct_script, opcodes
from electrum.util import BitcoinException


def build_cltv_signature_path(locktime: int, pubkey: bytes) -> bytes:
    """
    Build standard CLTV signature path script.
    
    Script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG
    
    Used by:
    - Simple timelock (HODL) contracts
    - Escrow refund paths
    - Two-factor recovery paths
    - Payment channel refund paths
    
    Args:
        locktime: Locktime value (block height or timestamp)
        pubkey: 33-byte compressed public key or 32-byte x-only public key
        
    Returns:
        Script bytes
        
    Example:
        >>> script = build_cltv_signature_path(750000, pubkey_bytes)
    """
    # Ensure pubkey is bytes
    if isinstance(pubkey, str):
        from electrum.util import bfh
        pubkey = bfh(pubkey)
    
    return construct_script([
        locktime,
        opcodes.OP_CHECKLOCKTIMEVERIFY,
        opcodes.OP_DROP,
        pubkey,
        opcodes.OP_CHECKSIG
    ])


def build_2of2_signature_path(pubkey1: bytes, pubkey2: bytes) -> bytes:
    """
    Build 2-of-2 multi-signature script path.
    
    Script: <pubkey1> OP_CHECKSIGVERIFY <pubkey2> OP_CHECKSIG
    
    Used by:
    - Payment channel cooperative path
    - Two-factor normal path (user + service)
    - Escrow normal operations (Alice + Bob)
    
    Args:
        pubkey1: First public key (33-byte compressed or 32-byte x-only)
        pubkey2: Second public key (33-byte compressed or 32-byte x-only)
        
    Returns:
        Script bytes
        
    Example:
        >>> script = build_2of2_signature_path(alice_pubkey, bob_pubkey)
    """
    # Ensure pubkeys are bytes
    if isinstance(pubkey1, str):
        from electrum.util import bfh
        pubkey1 = bfh(pubkey1)
    if isinstance(pubkey2, str):
        from electrum.util import bfh
        pubkey2 = bfh(pubkey2)
    
    return construct_script([
        pubkey1,
        opcodes.OP_CHECKSIGVERIFY,
        pubkey2,
        opcodes.OP_CHECKSIG
    ])


def build_hash_locked_path(data_hash: bytes, pubkey: bytes) -> bytes:
    """
    Build hash-locked script path for data publishing.
    
    Script: OP_HASH160 <data_hash> OP_EQUALVERIFY <pubkey> OP_CHECKSIG
    
    Used by:
    - Data publishing publisher path
    - Any pay-to-hash pattern
    
    Args:
        data_hash: 20-byte HASH160 hash of the data
        pubkey: Public key (33-byte compressed or 32-byte x-only)
        
    Returns:
        Script bytes
        
    Example:
        >>> script = build_hash_locked_path(data_hash, publisher_pubkey)
    """
    # Validate inputs
    if len(data_hash) != 20:
        raise BitcoinException(f"data_hash must be 20 bytes (HASH160), got {len(data_hash)}")
    
    # Ensure pubkey is bytes
    if isinstance(pubkey, str):
        from electrum.util import bfh
        pubkey = bfh(pubkey)
    
    return construct_script([
        opcodes.OP_HASH160,
        data_hash,
        opcodes.OP_EQUALVERIFY,
        pubkey,
        opcodes.OP_CHECKSIG
    ])


def build_cltv_with_timelock(locktime: int, script: bytes) -> bytes:
    """
    Build script with wrapper for additional timelock.
    
    Script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <script>
    
    This creates a wrapper that ensures the inner script can only be
    executed after the additional timelock passes.
    
    Used by:
    - Escrow contracts with additional refund delays
    - Two-factor contracts with recovery delays
    - Payment channel refund extensions
    
    Args:
        locktime: Additional timelock value
        script: Inner script bytes that will be wrapped
        
    Returns:
        Script bytes
        
    Example:
        >>> inner_script = build_2of2_signature_path(alice_pubkey, bob_pubkey)
        >>> wrapped_script = build_cltv_with_timelock(1000, inner_script)
    """
    return construct_script([
        locktime,
        opcodes.OP_CHECKLOCKTIMEVERIFY,
        opcodes.OP_DROP,
        script
    ])


def build_minimal_sacrifice_script(locktime: int) -> bytes:
    """
    Build minimal sacrifice script for timelocked spending.
    
    Script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP OP_TRUE
    
    This creates a script where anyone can spend after the timelock,
    but only the specified timelock must pass.
    
    Args:
        locktime: Locktime value
        
    Returns:
        Script bytes
        
    Example:
        >>> script = build_minimal_sacrifice_script(750000)
    """
    return construct_script([
        locktime,
        opcodes.OP_CHECKLOCKTIMEVERIFY,
        opcodes.OP_DROP,
        opcodes.OP_TRUE
    ])


def build_conditional_script(
    if_script: bytes,
    else_script: bytes,
    opcode_sequence: Tuple[str, str, str] = ('OP_IF', 'OP_ELSE', 'OP_ENDIF')
) -> bytes:
    """
    Build conditional script with IF/ELSE/ENDIF structure.
    
    Script: OP_IF <if_script> OP_ELSE <else_script> OP_ENDIF
    
    Used by:
    - Data publishing (publisher vs buyer paths)
    - Any conditional spending logic
    
    Args:
        if_script: Script for the IF branch
        else_script: Script for the ELSE branch  
        opcode_sequence: Tuple of opcodes for IF/ELSE/ENDIF
        
    Returns:
        Script bytes
        
    Example:
        >>> publisher_path = build_hash_locked_path(data_hash, publisher_pubkey)
        >>> buyer_path = build_cltv_signature_path(locktime, buyer_pubkey)
        >>> script = build_conditional_script(publisher_path, buyer_path)
    """
    if_script_bytes = if_script if isinstance(if_script, bytes) else bytes.fromhex(if_script)
    else_script_bytes = else_script if isinstance(else_script, bytes) else bytes.fromhex(else_script)
    
    # Map opcode strings to actual opcodes
    op_map = {
        'OP_IF': opcodes.OP_IF,
        'OP_ELSE': opcodes.OP_ELSE,
        'OP_ENDIF': opcodes.OP_ENDIF,
        'OP_NOTIF': opcodes.OP_NOTIF,
    }
    
    op_if = op_map.get(opcode_sequence[0], opcodes.OP_IF)
    op_else = op_map.get(opcode_sequence[1], opcodes.OP_ELSE)
    op_endif = op_map.get(opcode_sequence[2], opcodes.OP_ENDIF)
    
    return construct_script([
        op_if,
        if_script_bytes,
        op_else,
        else_script_bytes,
        op_endif
    ])


def validate_pubkey_format(pubkey: Union[str, bytes]) -> bytes:
    """
    Validate and normalize public key format.
    
    Accepts both hex strings and bytes. Returns normalized bytes.
    
    Args:
        pubkey: Public key as hex string or bytes
        
    Returns:
        Normalized public key bytes
        
    Raises:
        BitcoinException: If pubkey format is invalid
    """
    if isinstance(pubkey, bytes):
        return pubkey
    
    if isinstance(pubkey, str):
        from electrum.util import bfh, is_hex_str
        if not is_hex_str(pubkey):
            raise BitcoinException(f"Invalid hex pubkey: {pubkey}")
        
        pubkey_bytes = bfh(pubkey)
        
        # Check length - accept both compressed (33 bytes) and x-only (32 bytes)
        if len(pubkey_bytes) not in (32, 33):
            raise BitcoinException(f"Invalid pubkey length: {len(pubkey_bytes)} bytes. Expected 32 (x-only) or 33 (compressed)")
        
        return pubkey_bytes
    
    raise BitcoinException(f"Invalid pubkey type: {type(pubkey)}. Expected str or bytes")


def get_script_size_estimate(script_items: List[Union[int, bytes, str]]) -> int:
    """
    Estimate script size in bytes.
    
    Args:
        script_items: List of script items (integers, bytes, or hex strings)
        
    Returns:
        Estimated script size in bytes
        
    Example:
        >>> items = [750000, 'OP_CHECKLOCKTIMEVERIFY', 'OP_DROP', pubkey_bytes, 'OP_CHECKSIG']
        >>> size = get_script_size_estimate(items)
    """
    total_size = 0
    
    for item in script_items:
        if isinstance(item, int):
            # Integers use 1-9 bytes depending on value
            if item == 0:
                total_size += 1
            elif 1 <= item <= 16:
                total_size += 1  # OP_1 through OP_16
            elif item <= 0x4b:
                total_size += 1
            elif item <= 0xff:
                total_size += 2
            elif item <= 0xffff:
                total_size += 3
            elif item <= 0xffffff:
                total_size += 4
            elif item <= 0xffffffff:
                total_size += 5
            else:
                total_size += 9  # Large numbers use minimal encoding
                
        elif isinstance(item, (bytes, str)):
            if isinstance(item, str):
                from electrum.util import bfh
                item_bytes = bfh(item)
            else:
                item_bytes = item
            
            # Data push: 1 byte for push opcode + data length + data
            if len(item_bytes) < 76:
                total_size += 1 + len(item_bytes)
            elif len(item_bytes) < 256:
                total_size += 2 + len(item_bytes)
            elif len(item_bytes) < 65536:
                total_size += 3 + len(item_bytes)
            else:
                total_size += 5 + len(item_bytes)
                
        else:
            # Handle opcodes (assumed to be handled by caller as integers)
            total_size += 1
    
    return total_size