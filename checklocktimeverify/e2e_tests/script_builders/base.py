"""
Base Script Builder - Common utilities for all builders

Provides base class and Electrum integration utilities.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

# Import Electrum's built-in functions for script construction
from electrum.bitcoin import construct_script, script_num_to_bytes, opcodes
from electrum.bitcoin import push_script

# Add Tapscript-specific opcodes that Electrum doesn't have yet
if not hasattr(opcodes, 'OP_CHECKSIGADD'):
    opcodes.OP_CHECKSIGADD = 0xba  # BIP-342 Tapscript opcode

# Export opcodes for use in other modules
__all__ = ['ScriptBuilder', 'BuildError', 'encode_script_number', 'decode_script_number', 'build_script_ops', 'opcodes']


def encode_script_number(n: int) -> bytes:
    """
    Encode integer as Bitcoin script number using Electrum's implementation.
    
    This uses Electrum's battle-tested script number encoding.
    
    Args:
        n: Integer to encode
    
    Returns:
        Script number bytes
    """
    return script_num_to_bytes(n)


def build_script_ops(ops_list):
    """
    Build script from operations list using Electrum's construct_script.
    
    Args:
        ops_list: List of opcodes and data to construct script from
    
    Returns:
        Script bytes
    """
    return construct_script(ops_list)


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
    Abstract base class for script builders.
    
    Each CLTV script type implements this to provide deterministic
    script generation from parameters.
    """
    
    # Script type identifier
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


class BuildError(Exception):
    """Script building error"""
    pass
