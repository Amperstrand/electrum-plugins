"""
Base Script Builder - Common utilities for all builders

Provides base class and Electrum integration utilities for P2WSH and Taproot.
P2SH support has been REMOVED - deprecated and not supported.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

# Import Electrum's built-in functions for script construction
from electrum.bitcoin import construct_script, opcodes
from electrum.bitcoin import push_script
# Use electrum_ecc package for EC validation (consistent with test fixtures)
from electrum_ecc import ECPubkey

# Import from centralized utilities (from parent package)
from ..opcodes_ext import OP_CHECKSIGADD, build_script_with_ext_opcodes
from .taproot.taproot_utils import encode_script_number

# Export opcodes for use in other modules
__all__ = [
    'ScriptBuilder', 'BuildError', 
    'encode_script_number', 'decode_script_number', 
    'construct_script', 'build_script_with_ext_opcodes',
    'opcodes', 'OP_CHECKSIGADD'
]


def decode_script_number(data: bytes, max_size: int = 5) -> int:
    """
    Decode Bitcoin script number to integer.
    
    Args:
        data: Script number bytes
        max_size: Maximum size in bytes (default 5)
    
    Returns:
        Decoded integer
    
    Raises:
        ValueError: If data too long or invalid
    """
    if len(data) == 0:
        return 0
    
    if len(data) > max_size:
        raise ValueError(f"Script number too long: {len(data)} > {max_size}")
    
    # Extract sign
    negative = data[-1] & 0x80
    
    # Remove sign bit from last byte
    last_byte = data[-1] & 0x7f
    
    # Decode little-endian
    result = 0
    for i in range(len(data) - 1):
        result |= data[i] << (8 * i)
    result |= last_byte << (8 * (len(data) - 1))
    
    return -result if negative else result


class ScriptBuilder(ABC):
    """
    Abstract base class for CLTV script builders.
    
    Each CLTV script type implements this to provide deterministic
    script generation from parameters.
    
    Supports P2WSH and Taproot only. P2SH has been removed (deprecated).
    """
    
    # Script type identifier (must be set by subclass)
    SCRIPT_TYPE: str = "unknown"
    
    @abstractmethod
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build script from parameters (deterministic!).
        
        Args:
            params: Script-specific parameters
        
        Returns:
            Script bytes
        
        Must be deterministic: same params → same script
        """
        pass
    
    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate parameters before building.
        
        Args:
            params: Parameters to validate
        
        Returns:
            True if valid
        
        Raises:
            ValueError: If invalid parameters with explanation
        """
        pass
    
    def get_script_type(self) -> str:
        """Get script type identifier"""
        return self.SCRIPT_TYPE
    
    # ========================================================================
    # DRY Helper Methods - Reduce duplication across builders
    # ========================================================================
    
    def get_pubkey(self, params: Dict[str, Any], key_name: str) -> bytes:
        """
        Extract and validate pubkey from params.
        Handles both regular pubkey and xonly variants.
        
        Args:
            params: Parameter dict
            key_name: Base key name (e.g., 'sender', 'alice', 'user')
        
        Returns:
            Pubkey bytes (32 or 33 bytes)
        
        Raises:
            BuildError: If key missing or invalid
        
        Examples:
            get_pubkey(params, 'sender')  # Looks for sender_pubkey or sender_pubkey_xonly
            get_pubkey(params, 'alice')   # Looks for alice_pubkey or alice_pubkey_xonly
        """
        # Try both regular and x-only variants
        pubkey_hex = params.get(f'{key_name}_pubkey') or params.get(f'{key_name}_pubkey_xonly')

        if not pubkey_hex:
            raise BuildError(f"Missing {key_name}_pubkey or {key_name}_pubkey_xonly")

        # Validate format and convert from hex → bytes
        return self.validate_pubkey(pubkey_hex, field_name=f"{key_name}_pubkey")

    def validate_pubkey(self, pubkey_hex: str, field_name: str = "pubkey", allow_formats=("compressed", "xonly")) -> bytes:
        """
        Validate a public key hex string.

        - Accepts 33-byte compressed pubkeys (02/03 prefix) and/or 32-byte x-only keys
        - For compressed pubkeys, additionally verifies curve validity using Electrum's ECPubkey

        Args:
            pubkey_hex: Hex-encoded public key
            field_name: Used in error messages for clarity
            allow_formats: Tuple of allowed formats: "compressed", "xonly"

        Returns:
            The pubkey bytes as provided (32 or 33 bytes)

        Raises:
            BuildError: If invalid hex, wrong length/prefix, or disallowed format
        """
        # Basic hex → bytes validation
        try:
            pubkey = bytes.fromhex(pubkey_hex)
        except Exception:
            raise BuildError(f"Invalid {field_name} hex")

        length = len(pubkey)
        if length == 33:
            if "compressed" not in allow_formats:
                raise BuildError(f"{field_name}: compressed format not allowed here")
            prefix = pubkey[0]
            if prefix not in (0x02, 0x03):
                raise BuildError(f"{field_name}: invalid compressed prefix 0x{prefix:02x}")
            # Deep validation using Electrum's ECPubkey (catches invalid curve points)
            try:
                _ = ECPubkey(pubkey)
            except Exception as e:
                raise BuildError(f"{field_name}: invalid compressed pubkey: {e}")
        elif length == 32:
            if "xonly" not in allow_formats:
                raise BuildError(f"{field_name}: x-only format not allowed here")
            # Cannot fully validate x-only without parity; length check is all we can do here
        else:
            allowed_desc = ", ".join(sorted(set(["33-byte compressed" if f=="compressed" else "32-byte x-only" for f in allow_formats])))
            raise BuildError(f"{field_name}: invalid length {length} bytes (allowed: {allowed_desc})")

        return pubkey
    
    def validate_locktime(self, locktime: int) -> None:
        """
        Validate locktime parameter.
        
        Args:
            locktime: Block height or timestamp
        
        Raises:
            BuildError: If locktime invalid
        """
        if not isinstance(locktime, int):
            raise BuildError(f"locktime must be int, got {type(locktime)}")
        
        if locktime < 0:
            raise BuildError(f"locktime must be non-negative, got {locktime}")
        
        # Validate range (block height vs timestamp)
        # Values >= 500000000 are treated as Unix timestamps
        if locktime >= 500_000_000:
            # Timestamp (Unix epoch)
            if locktime > 2_000_000_000:
                raise BuildError(f"Invalid timestamp locktime: {locktime}")
        else:
            # Block height
            if locktime > 10_000_000:
                raise BuildError(f"Invalid block height locktime: {locktime}")
    
    def require_param(self, params: Dict[str, Any], param_name: str) -> Any:
        """
        Get required parameter or raise BuildError.
        
        Args:
            params: Parameter dict
            param_name: Parameter name
        
        Returns:
            Parameter value
        
        Raises:
            BuildError: If parameter missing
        """
        if param_name not in params:
            raise BuildError(f"Missing required parameter: {param_name}")
        return params[param_name]

    # ====================================================================
    # Miniscript rendering (educational transparency)
    # ====================================================================
    def miniscript(self, params: Dict[str, Any], style: str = 'symbolic') -> str:
        """
        Return the Miniscript expression corresponding to this builder
        and the given params. This does not compile Miniscript; it only
        renders an educational mapping string.
        
        Args:
            params: Parameters used by the builder
            style: 'symbolic' (role names) or 'concrete' (insert hex values)
        
        Returns:
            Miniscript expression string
        """
        try:
            # Import from descriptors module
            from ..descriptors.miniscript import get_miniscript
            return get_miniscript(self.get_script_type(), params, style)
        except Exception as e:
            return f"<miniscript unavailable: {e}>"


class BuildError(Exception):
    """Script building error"""
    pass
