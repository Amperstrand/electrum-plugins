"""
Simple CLTV Builder - Single-sig time-locked scripts

Builds: <locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG

Supports:
- P2WSH variant (33-byte compressed pubkey)
- Taproot variant (32-byte x-only pubkey)
"""

from typing import Dict, Any
from .base import ScriptBuilder, build_script_ops, BuildError, opcodes


class SimpleCLTVBuilder(ScriptBuilder):
    """
    Builder for simple time-locked single-signature CLTV scripts.
    
    Script structure:
        <locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG
    
    Parameters:
        locktime: int - Block height or timestamp
        pubkey: str - Hex-encoded public key (33 bytes for P2WSH, 32 for Taproot)
        
    Optional:
        pubkey_xonly: str - For Taproot (alias for pubkey)
    """
    
    SCRIPT_TYPE = "cltv_simple_hodl"
    
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build simple CLTV script using Electrum's construct_script.
        
        Args:
            params: Must contain 'locktime' and 'pubkey' (or 'pubkey_xonly')
        
        Returns:
            Script bytes (deterministic)
        """
        # Validate first
        self.validate_params(params)
        
        locktime = params['locktime']
        
        # Support both 'pubkey' and 'pubkey_xonly' keys
        pubkey_hex = params.get('pubkey') or params.get('pubkey_xonly')
        pubkey = bytes.fromhex(pubkey_hex)
        
        # Build script using Electrum's construct_script
        return build_script_ops([
            locktime,                                    # Push locktime
            opcodes.OP_CHECKLOCKTIMEVERIFY,              # OP_CLTV
            opcodes.OP_DROP,                             # OP_DROP
            pubkey,                                      # Push pubkey
            opcodes.OP_CHECKSIG                          # OP_CHECKSIG
        ])
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate simple CLTV parameters.
        
        Checks:
        - locktime is present and valid
        - pubkey is present and correct length
        """
        # Check locktime
        if 'locktime' not in params:
            raise BuildError("Missing required parameter: locktime")
        
        locktime = params['locktime']
        if not isinstance(locktime, int):
            raise BuildError(f"locktime must be int, got {type(locktime)}")
        
        if locktime < 0:
            raise BuildError(f"locktime must be non-negative, got {locktime}")
        
        # Validate locktime type (block height vs timestamp)
        if locktime >= 500_000_000:
            # Timestamp (Unix epoch)
            if locktime < 500_000_000 or locktime > 2_000_000_000:
                raise BuildError(f"Invalid timestamp locktime: {locktime}")
        else:
            # Block height
            if locktime > 10_000_000:
                raise BuildError(f"Invalid block height locktime: {locktime}")
        
        # Check pubkey
        pubkey_hex = params.get('pubkey') or params.get('pubkey_xonly')
        if not pubkey_hex:
            raise BuildError("Missing required parameter: pubkey or pubkey_xonly")
        
        try:
            pubkey = bytes.fromhex(pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid pubkey hex: {pubkey_hex}")
        
        # Check pubkey length
        if len(pubkey) not in (32, 33):
            raise BuildError(
                f"Invalid pubkey length: {len(pubkey)} bytes. "
                f"Expected 32 (x-only/Taproot) or 33 (compressed/P2WSH)"
            )
        
        # If 33 bytes, verify it's compressed
        if len(pubkey) == 33:
            if pubkey[0] not in (0x02, 0x03):
                raise BuildError(
                    f"Invalid compressed pubkey prefix: {pubkey[0]:02x}. "
                    f"Expected 0x02 or 0x03"
                )
        
        return True
    
    def parse(self, script_hex: str) -> Dict[str, Any]:
        """
        Parse script back to parameters (inverse of build).
        
        Args:
            script_hex: Hex-encoded script
        
        Returns:
            Parameters dict with locktime and pubkey
        
        Raises:
            BuildError: If script doesn't match expected format
        """
        script = bytes.fromhex(script_hex)
        
        if len(script) < 6:
            raise BuildError(f"Script too short: {len(script)} bytes")
        
        pos = 0
        
        # 1. Read locktime
        locktime_len = script[pos]
        pos += 1
        
        if locktime_len > 5:
            raise BuildError(f"Invalid locktime length: {locktime_len}")
        
        locktime_bytes = script[pos:pos + locktime_len]
        pos += locktime_len
        
        from .base import decode_script_number
        locktime = decode_script_number(locktime_bytes)
        
        # 2. Check OP_CLTV OP_DROP
        if pos + 2 > len(script):
            raise BuildError("Script truncated after locktime")
        
        if script[pos] != self.OP_CLTV:
            raise BuildError(f"Expected OP_CLTV (0xb1), got {script[pos]:02x}")
        pos += 1
        
        if script[pos] != self.OP_DROP:
            raise BuildError(f"Expected OP_DROP (0x75), got {script[pos]:02x}")
        pos += 1
        
        # 3. Read pubkey
        if pos >= len(script):
            raise BuildError("Script truncated after OP_DROP")
        
        pubkey_len = script[pos]
        pos += 1
        
        if pubkey_len not in (32, 33):
            raise BuildError(f"Invalid pubkey length: {pubkey_len}")
        
        if pos + pubkey_len > len(script):
            raise BuildError("Script truncated in pubkey")
        
        pubkey = script[pos:pos + pubkey_len]
        pos += pubkey_len
        
        # 4. Check OP_CHECKSIG
        if pos >= len(script):
            raise BuildError("Script truncated after pubkey")
        
        if script[pos] != self.OP_CHECKSIG:
            raise BuildError(f"Expected OP_CHECKSIG (0xac), got {script[pos]:02x}")
        pos += 1
        
        # Should be end of script
        if pos != len(script):
            raise BuildError(f"Extra data after script: {len(script) - pos} bytes")
        
        return {
            'locktime': locktime,
            'pubkey': pubkey.hex(),
        }
