"""
Script Utilities - Address generation and format handling

Centralizes logic for all three Bitcoin script formats:
- P2SH (Pay-to-Script-Hash) - Legacy wrapped scripts
- P2WSH (Pay-to-Witness-Script-Hash) - Native SegWit v0
- Taproot - SegWit v1 with Schnorr

Design principles:
- DRY: Single source of truth for address generation
- Type safety: Clear format detection
- Extensible: Easy to add new formats
- Validation: Early error detection with clear messages
"""

from typing import Dict, Literal, Tuple
from enum import Enum


# ============================================================================
# Type Definitions
# ============================================================================

class ScriptFormat(str, Enum):
    """Supported Bitcoin script formats"""
    P2WSH = "p2wsh"         # Native SegWit: tb1q... addresses
    TAPROOT = "taproot"     # Taproot: tb1p... addresses


class SignatureType(Enum):
    """Bitcoin signature algorithms"""
    ECDSA = "ecdsa"         # Traditional, used in P2SH and P2WSH
    SCHNORR = "schnorr"     # BIP-340, used in Taproot


# Format characteristics
FORMAT_INFO = {
    ScriptFormat.P2WSH: {
        'prefix': 'bc1q',           # Mainnet: bc1q, Testnet: tb1q
        'pubkey_bytes': 33,         # Compressed pubkey
        'signature': SignatureType.ECDSA,
        'witness': True,            # Native witness
        'hash_func': 'sha256',      # SHA256 only
    },
    ScriptFormat.TAPROOT: {
        'prefix': 'bc1p',           # Mainnet: bc1p, Testnet: tb1p
        'pubkey_bytes': 32,         # X-only pubkey
        'signature': SignatureType.SCHNORR,
        'witness': True,            # Native witness
        'hash_func': 'sha256',      # SHA256 only
    },
}


# ============================================================================
# Validation Functions (Task 2: Input Validation)
# ============================================================================

def validate_script_type(script_type: str) -> None:
    """
    Validate script type string against known types.
    
    Args:
        script_type: Script type identifier
    
    Raises:
        ValueError: If script_type is unknown
    
    Examples:
        >>> validate_script_type("cltv_hodl_p2wsh")  # OK
        >>> validate_script_type("invalid")  # Raises ValueError
    """
    # Use registry as single source of truth for valid script types
    from cltv_lib.registry import list_scripts
    valid_types = list_scripts()
    
    if script_type not in valid_types:
        raise ValueError(
            f"Unknown script_type: '{script_type}'\n"
            f"Valid types:\n" +
            '\n'.join(f"  - {t}" for t in valid_types)
        )


def validate_locktime(locktime: int) -> None:
    """
    Validate locktime value (BIP-65 compliant).
    
    BIP-65 locktime rules:
    - Must be non-negative integer
    - Values 0-499999999: Block height
    - Values ≥500000000: Unix timestamp
    
    Args:
        locktime: Locktime value to validate
    
    Raises:
        TypeError: If locktime is not an integer
        ValueError: If locktime is out of valid range
    
    Examples:
        >>> validate_locktime(100000)  # OK - block height
        >>> validate_locktime(1700000000)  # OK - timestamp  
        >>> validate_locktime(-1)  # Raises ValueError
        >>> validate_locktime("100")  # Raises TypeError
    """
    if not isinstance(locktime, int):
        raise TypeError(
            f"Locktime must be int, got {type(locktime).__name__}: {locktime}"
        )
    
    if locktime < 0:
        raise ValueError(
            f"Locktime cannot be negative: {locktime}"
        )
    
    # BIP-65 doesn't actually have an upper limit, but we check for overflow
    if locktime > 0xFFFFFFFF:  # 32-bit unsigned max
        raise ValueError(
            f"Locktime exceeds 32-bit limit: {locktime} > {0xFFFFFFFF}"
        )


def validate_pubkey(pubkey_hex: str, expected_len: int, name: str = "pubkey") -> None:
    """
    Validate public key format and length.
    
    Args:
        pubkey_hex: Hex-encoded public key
        expected_len: Expected length in bytes (33 for compressed, 32 for x-only)
        name: Descriptive name for error messages (e.g., "alice_pubkey")
    
    Raises:
        ValueError: If pubkey is invalid hex or wrong length
    
    Examples:
        >>> validate_pubkey("02" + "00"*32, 33)  # OK - compressed
        >>> validate_pubkey("00"*32, 32)  # OK - x-only
        >>> validate_pubkey("invalid", 33)  # Raises ValueError
        >>> validate_pubkey("00"*32, 33)  # Raises ValueError (wrong length)
    """
    try:
        pubkey_bytes = bytes.fromhex(pubkey_hex)
    except ValueError as e:
        raise ValueError(
            f"Invalid hex {name}: {pubkey_hex}\n"
            f"Error: {e}"
        ) from e
    
    if len(pubkey_bytes) != expected_len:
        raise ValueError(
            f"Invalid {name} length: expected {expected_len} bytes, "
            f"got {len(pubkey_bytes)} bytes\n"
            f"Pubkey: {pubkey_hex}"
        )


def validate_script_hex(script_hex: str) -> None:
    """
    Validate script is valid hex using Electrum's utilities.
    
    Args:
        script_hex: Hex-encoded script
    
    Raises:
        ValueError: If script is not valid hex
    
    Examples:
        >>> validate_script_hex("6a")  # OK - OP_RETURN
        >>> validate_script_hex("invalid")  # Raises ValueError
    """
    from electrum.bitcoin import is_hex_string
    
    if not is_hex_string(script_hex):
        raise ValueError(f"Invalid hex script: {script_hex}")
    
    if len(script_hex) == 0:
        raise ValueError("Script cannot be empty")


def validate_address(address: str) -> None:
    """
    Validate Bitcoin address using Electrum's utilities.
    
    Args:
        address: Bitcoin address to validate
    
    Raises:
        ValueError: If address is invalid
    
    Examples:
        >>> validate_address("tb1q...")  # OK - valid testnet address
        >>> validate_address("invalid")  # Raises ValueError
    """
    from electrum.bitcoin import is_address
    
    if not is_address(address):
        raise ValueError(f"Invalid Bitcoin address: {address}")


# ============================================================================
# Format Detection
# ============================================================================

def detect_format(script_type: str) -> ScriptFormat:
    """
    Detect script format from type string.
    
    Args:
        script_type: String like "cltv_hodl", "cltv_taproot", "cltv_p2wsh"
    
    Returns:
        ScriptFormat enum
    
    Examples:
        >>> detect_format("cltv_simple_p2wsh")
        ScriptFormat.P2WSH
        
        >>> detect_format("cltv_taproot")
        ScriptFormat.TAPROOT
        
        >>> detect_format("cltv_escrow_timeout_p2wsh")
        ScriptFormat.P2WSH
    """
    script_type_lower = script_type.lower()
    
    if 'taproot' in script_type_lower:
        return ScriptFormat.TAPROOT
    elif 'p2wsh' in script_type_lower:
        return ScriptFormat.P2WSH
    else:
        raise ValueError(f"Cannot detect format from script_type: {script_type}. Expected '_p2wsh' or '_taproot' suffix.")


def get_signature_type(script_type: str) -> SignatureType:
    """Get signature algorithm for script type"""
    format = detect_format(script_type)
    return FORMAT_INFO[format]['signature']


def is_witness_format(script_type: str) -> bool:
    """Check if script type uses witness structure"""
    format = detect_format(script_type)
    return FORMAT_INFO[format]['witness']


def get_expected_pubkey_length(script_type: str) -> int:
    """Get expected pubkey length for script type"""
    format = detect_format(script_type)
    return FORMAT_INFO[format]['pubkey_bytes']


def script_to_address(script_hex: str, format: ScriptFormat) -> str:
    """
    Convert script to address for specified format.
    
    Args:
        script_hex: Hex-encoded script
        format: Target address format
    
    Returns:
        Bitcoin address string
    
    Examples:
        >>> script_to_address(script, ScriptFormat.P2WSH)
        'tb1q1234...'  # Testnet P2WSH
        
        >>> script_to_address(script, ScriptFormat.TAPROOT)
        'tb1p1234...'  # Testnet Taproot
    """
    if format == ScriptFormat.P2WSH:
        return script_to_p2wsh(script_hex)
    elif format == ScriptFormat.TAPROOT:
        return script_to_taproot(script_hex)
    else:
        raise ValueError(f"Unknown format: {format}")


def script_to_p2wsh(script_hex: str) -> str:
    """
    Convert script to P2WSH (native SegWit v0) address using Electrum's built-in function.
    
    Args:
        script_hex: Hex-encoded script
    
    Returns:
        P2WSH address (e.g., "tb1q..." for testnet, "bc1q..." for mainnet)
    """
    from electrum.bitcoin import script_to_p2wsh
    
    script_bytes = bytes.fromhex(script_hex)
    return script_to_p2wsh(script_bytes)


def script_to_taproot(script_hex: str) -> str:
    """
    Convert script to Taproot (SegWit v1) address.
    
    For CLTV/escrow scripts, this parses the script to extract the locktime
    and pubkey, then uses the taproot module's create_taproot_cltv_output()
    function which handles:
    - NUMS internal key (no key-path spending)
    - Script tree construction
    - Control block generation
    - Taproot address encoding
    
    Args:
        script_hex: Hex-encoded CLTV or escrow script
    
    Returns:
        Taproot address (e.g., "tb1p..." for testnet, "bc1p..." for mainnet)
    
    Raises:
        ValueError: If script format is not recognized or cannot be parsed
    """
    from electrum.bitcoin import opcodes
    import sys
    import os
    
    # Add parent directory to path to import taproot module
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    from taproot import create_taproot_cltv_output
    
    # Parse script to extract locktime and pubkey
    script_bytes = bytes.fromhex(script_hex)
    
    # Try to extract locktime and pubkey from script
    # Format: <locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG (simple)
    # Or: OP_IF <pubkey1> OP_CHECKSIG OP_ELSE <timeout> OP_CLTV ... (escrow)
    
    try:
        idx = 0
        locktime = None
        pubkey_hex = None
        
        # Check if it's an escrow script (starts with OP_IF)
        if script_bytes[0] == opcodes.OP_IF:
            # BIP-65 Escrow script structure:
            # OP_IF <locktime> OP_CLTV OP_DROP <lenny_pubkey> OP_CHECKSIGVERIFY OP_1 OP_ELSE OP_2 OP_ENDIF <alice> <bob> OP_2 OP_CHECKMULTISIG
            # Locktime is in IF branch (right after OP_IF)
            idx = 1
            push_len = script_bytes[idx]
            if push_len <= 75:  # Direct push
                locktime_bytes = script_bytes[idx+1:idx+1+push_len]
                locktime = int.from_bytes(locktime_bytes, 'little')
                idx = idx + 1 + push_len
            
            # Skip OP_CLTV and OP_DROP
            if idx < len(script_bytes) and script_bytes[idx] == opcodes.OP_CHECKLOCKTIMEVERIFY:
                idx += 1
            if idx < len(script_bytes) and script_bytes[idx] == opcodes.OP_DROP:
                idx += 1
            
            # Extract Lenny's pubkey (the arbitrator - after OP_DROP, before OP_CHECKSIGVERIFY)
            if idx < len(script_bytes):
                push_len = script_bytes[idx]
                if push_len == 32:  # x-only pubkey
                    pubkey_hex = script_bytes[idx+1:idx+1+32].hex()
                    # Convert x-only to compressed for create_taproot_cltv_output
                    pubkey_hex = '02' + pubkey_hex  # Add prefix
                elif push_len == 33:  # compressed pubkey
                    pubkey_hex = script_bytes[idx+1:idx+1+33].hex()
        else:
            # Simple CLTV script
            # Extract locktime (first few bytes)
            push_len = script_bytes[0]
            if push_len <= 75:  # Direct push opcode
                locktime_bytes = script_bytes[1:1+push_len]
                locktime = int.from_bytes(locktime_bytes, 'little')
                idx = 1 + push_len
            
            # Skip OP_CLTV and OP_DROP
            if script_bytes[idx] == opcodes.OP_CHECKLOCKTIMEVERIFY:
                idx += 1
            if script_bytes[idx] == opcodes.OP_DROP:
                idx += 1
            
            # Extract pubkey
            push_len = script_bytes[idx]
            if push_len == 32:  # x-only pubkey
                pubkey_hex = script_bytes[idx+1:idx+1+32].hex()
                # Convert x-only to compressed for create_taproot_cltv_output
                pubkey_hex = '02' + pubkey_hex  # Add prefix
            elif push_len == 33:  # compressed pubkey  
                pubkey_hex = script_bytes[idx+1:idx+1+33].hex()
        
        if locktime is None or pubkey_hex is None:
            raise ValueError(f"Could not extract locktime or pubkey from script: {script_hex}")
        
        # Use the existing taproot module function
        result = create_taproot_cltv_output(locktime, pubkey_hex)
        
        if result.get('error'):
            raise ValueError(f"Taproot address generation failed: {result['error']}")
        
        return result['address']
        
    except Exception as e:
        raise ValueError(
            f"Failed to generate Taproot address from script. "
            f"Script may not be a recognized CLTV/escrow format. Error: {e}"
        )


def get_witness_size_estimate(script_type: str, path: str = None) -> int:
    """
    Estimate witness size for fee calculation.
    
    Args:
        script_type: Script type identifier
        path: Optional spending path (for multi-path scripts)
    
    Returns:
        Estimated witness size in bytes
    
    Size breakdown:
    - P2WSH: [sig, script] → ~140 bytes (single-sig) or ~180 (2-sig)
    - Taproot: [sig, script, control] → ~170 (single-sig) or ~210 (2-sig)
    """
    format = detect_format(script_type)
    
    # Estimate based on script complexity
    # Simple scripts: 1 signature
    # Escrow: 1 or 2 signatures depending on path
    
    if 'escrow' in script_type.lower():
        # Escrow can be 1-sig (refund) or 2-sig (cooperation)
        if path == 'refund' or path == 'timeout':
            sigs = 1
        else:
            sigs = 2
    else:
        sigs = 1
    
    # Base sizes
    if format == ScriptFormat.P2WSH:
        # P2WSH: [sig1, sig2, ..., script]
        return 140 + (sigs - 1) * 40  # ~140 for 1-sig, ~180 for 2-sig
    
    elif format == ScriptFormat.TAPROOT:
        # Taproot: [sig1, sig2, ..., script, control_block]
        return 170 + (sigs - 1) * 40  # ~170 for 1-sig, ~210 for 2-sig
    
    return 150  # Fallback


def normalize_script_type(base_type: str, format: ScriptFormat) -> str:
    """
    Generate normalized script type string.
    
    Args:
        base_type: Base script type (e.g., "cltv_hodl", "cltv_escrow_timeout")
        format: Target format
    
    Returns:
        Normalized type string
    
    Examples:
        >>> normalize_script_type("cltv_hodl", ScriptFormat.P2SH)
        'cltv_hodl'
        
        >>> normalize_script_type("cltv_hodl", ScriptFormat.P2WSH)
        'cltv_hodl_p2wsh'
        
        >>> normalize_script_type("cltv_hodl", ScriptFormat.TAPROOT)
        'cltv_taproot'
    """
    # Remove existing format suffixes
    base = base_type.replace('_p2wsh', '').replace('_taproot', '')
    
    if format == ScriptFormat.P2SH:
        return base
    elif format == ScriptFormat.P2WSH:
        return f"{base}_p2wsh"
    elif format == ScriptFormat.TAPROOT:
        # Special case: taproot uses different naming convention
        if 'hodl' in base:
            return 'cltv_taproot'
        else:
            return f"{base}_taproot"
    
    return base


# Pubkey conversion utilities

def compressed_to_xonly(compressed_pubkey_hex: str) -> str:
    """
    Convert compressed pubkey (33 bytes) to x-only (32 bytes) for Taproot.
    
    Args:
        compressed_pubkey_hex: 33-byte compressed pubkey (02/03 prefix)
    
    Returns:
        32-byte x-only pubkey (no prefix)
    
    Example:
        >>> compressed_to_xonly("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
        '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
    """
    pubkey_bytes = bytes.fromhex(compressed_pubkey_hex)
    
    if len(pubkey_bytes) != 33:
        raise ValueError(f"Expected 33-byte compressed pubkey, got {len(pubkey_bytes)}")
    
    if pubkey_bytes[0] not in (0x02, 0x03):
        raise ValueError(f"Invalid compressed pubkey prefix: {pubkey_bytes[0]:02x}")
    
    # Remove prefix byte
    return pubkey_bytes[1:].hex()


def ensure_correct_pubkey_format(pubkey_hex: str, format: ScriptFormat) -> str:
    """
    Ensure pubkey is in correct format for script type.
    
    Args:
        pubkey_hex: Public key hex
        format: Target format
    
    Returns:
        Pubkey in correct format
    """
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    
    if format in (ScriptFormat.P2SH, ScriptFormat.P2WSH):
        # Need 33-byte compressed
        if len(pubkey_bytes) == 32:
            raise ValueError(
                f"{format.value} requires 33-byte compressed pubkey, got 32-byte x-only. "
                f"Cannot convert x-only back to compressed."
            )
        return pubkey_hex
    
    elif format == ScriptFormat.TAPROOT:
        # Need 32-byte x-only
        if len(pubkey_bytes) == 33:
            return compressed_to_xonly(pubkey_hex)
        return pubkey_hex
    
    return pubkey_hex
