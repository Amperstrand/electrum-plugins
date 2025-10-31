"""
Two-Factor Wallet Script Builder

Implements BIP-65 Example #3: Two-Factor Wallets

Script structure (optimized for determinism):
    OP_IF
        <user_pubkey> OP_CHECKSIGVERIFY
    OP_ELSE
        <locktime> OP_CLTV OP_DROP
    OP_ENDIF
    <service_pubkey> OP_CHECKSIG

Spend paths:
1. Normal path (before timeout): User AND Service (2-of-2 multisig)
2. Recovery path (after timeout): User AND Recovery (2-of-2 multisig after locktime)

Use case:
- User controls one key
- Service controls another key (2FA, requires user authentication)
- Recovery key activated after timeout if service unavailable

Learning points:
- 2FA protection with timeout fallback
- User always required (both paths)
- Service vs Recovery key selection based on timelock
"""

from typing import Dict, Any
from .base import ScriptBuilder, encode_script_number, BuildError


class TwoFactorBuilder(ScriptBuilder):
    """
    Builder for two-factor wallet scripts.
    
    Creates a wallet requiring user + service normally,
    or user + recovery after timeout.
    
    Parameters:
        user_pubkey: str - User's public key (hex)
        service_pubkey: str - Service's public key (hex, for normal path)
        recovery_pubkey: str - Recovery public key (hex, for timeout path)
        locktime: int - Recovery timeout (block height or timestamp)
        
    Optional (for Taproot):
        user_pubkey_xonly: str - User's x-only pubkey (32 bytes)
        service_pubkey_xonly: str - Service's x-only pubkey (32 bytes)
        recovery_pubkey_xonly: str - Recovery's x-only pubkey (32 bytes)
    
    Note: This differs slightly from BIP-65 example which shows service + user
    in IF branch. We optimize for: user always required, service vs recovery in branches.
    """
    
    SCRIPT_TYPE = "cltv_twofactor"
    
    # Opcodes
    OP_IF = 0x63
    OP_ELSE = 0x67
    OP_ENDIF = 0x68
    OP_CLTV = 0xb1
    OP_DROP = 0x75
    OP_CHECKSIG = 0xac
    OP_CHECKSIGVERIFY = 0xad
    
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build two-factor wallet script.
        
        Returns deterministic script bytes.
        """
        self.validate_params(params)
        
        locktime = params['locktime']
        
        # Support both regular and x-only pubkeys
        user_pubkey_hex = params.get('user_pubkey') or params.get('user_pubkey_xonly')
        service_pubkey_hex = params.get('service_pubkey') or params.get('service_pubkey_xonly')
        recovery_pubkey_hex = params.get('recovery_pubkey') or params.get('recovery_pubkey_xonly')
        
        user_pubkey = bytes.fromhex(user_pubkey_hex)
        service_pubkey = bytes.fromhex(service_pubkey_hex)
        recovery_pubkey = bytes.fromhex(recovery_pubkey_hex)
        
        # Build script
        script = bytearray()
        
        # OP_IF
        script.append(self.OP_IF)
        
        # Path 1: Normal (before timeout) - User + Service
        # <user_pubkey> OP_CHECKSIGVERIFY
        script.append(len(user_pubkey))
        script.extend(user_pubkey)
        script.append(self.OP_CHECKSIGVERIFY)
        
        # OP_ELSE
        script.append(self.OP_ELSE)
        
        # Path 2: Recovery (after timeout) - locktime check, then user required
        # <locktime> OP_CLTV OP_DROP
        locktime_bytes = encode_script_number(locktime)
        script.append(len(locktime_bytes))
        script.extend(locktime_bytes)
        script.append(self.OP_CLTV)
        script.append(self.OP_DROP)
        
        # User also required in recovery path
        # <user_pubkey> OP_CHECKSIGVERIFY
        script.append(len(user_pubkey))
        script.extend(user_pubkey)
        script.append(self.OP_CHECKSIGVERIFY)
        
        # OP_ENDIF
        script.append(self.OP_ENDIF)
        
        # Final check varies by path:
        # - Normal path: Service signature
        # - Recovery path: Recovery signature
        # We encode recovery pubkey here since it's the "else" final check
        # But witness will determine which is used via OP_IF value
        
        # Actually, let me reconsider the script structure...
        # The BIP-65 example shows:
        # IF
        #   2 <user> <service> 2 OP_CHECKMULTISIG
        # ELSE
        #   <locktime> OP_CLTV OP_DROP
        #   2 <user> <recovery> 2 OP_CHECKMULTISIG
        # ENDIF
        
        # But for non-multisig version (2 separate sigs), we need:
        # IF
        #   <service_pubkey> OP_CHECKSIGVERIFY <user_pubkey> OP_CHECKSIG
        # ELSE
        #   <locktime> OP_CLTV OP_DROP
        #   <recovery_pubkey> OP_CHECKSIGVERIFY <user_pubkey> OP_CHECKSIG
        # ENDIF
        
        # Let me rebuild following this pattern more closely...
        
        script = bytearray()
        
        # OP_IF
        script.append(self.OP_IF)
        
        # Path 1: Normal - Service then User
        # <service_pubkey> OP_CHECKSIGVERIFY
        script.append(len(service_pubkey))
        script.extend(service_pubkey)
        script.append(self.OP_CHECKSIGVERIFY)
        
        # <user_pubkey> OP_CHECKSIG
        script.append(len(user_pubkey))
        script.extend(user_pubkey)
        script.append(self.OP_CHECKSIG)
        
        # OP_ELSE
        script.append(self.OP_ELSE)
        
        # Path 2: Recovery - Locktime, then Recovery, then User
        # <locktime> OP_CLTV OP_DROP
        locktime_bytes = encode_script_number(locktime)
        script.append(len(locktime_bytes))
        script.extend(locktime_bytes)
        script.append(self.OP_CLTV)
        script.append(self.OP_DROP)
        
        # <recovery_pubkey> OP_CHECKSIGVERIFY
        script.append(len(recovery_pubkey))
        script.extend(recovery_pubkey)
        script.append(self.OP_CHECKSIGVERIFY)
        
        # <user_pubkey> OP_CHECKSIG
        script.append(len(user_pubkey))
        script.extend(user_pubkey)
        script.append(self.OP_CHECKSIG)
        
        # OP_ENDIF
        script.append(self.OP_ENDIF)
        
        return bytes(script)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate two-factor wallet parameters.
        """
        # Check locktime
        if 'locktime' not in params:
            raise BuildError("Missing required parameter: locktime")
        
        locktime = params['locktime']
        if not isinstance(locktime, int) or locktime < 0:
            raise BuildError(f"Invalid locktime: {locktime}")
        
        # Check User's pubkey
        user_pubkey_hex = params.get('user_pubkey') or params.get('user_pubkey_xonly')
        if not user_pubkey_hex:
            raise BuildError("Missing user_pubkey or user_pubkey_xonly")
        
        try:
            user_pubkey = bytes.fromhex(user_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid user_pubkey hex: {user_pubkey_hex}")
        
        if len(user_pubkey) not in (32, 33):
            raise BuildError(f"Invalid user_pubkey length: {len(user_pubkey)}")
        
        # Check Service's pubkey
        service_pubkey_hex = params.get('service_pubkey') or params.get('service_pubkey_xonly')
        if not service_pubkey_hex:
            raise BuildError("Missing service_pubkey or service_pubkey_xonly")
        
        try:
            service_pubkey = bytes.fromhex(service_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid service_pubkey hex: {service_pubkey_hex}")
        
        if len(service_pubkey) not in (32, 33):
            raise BuildError(f"Invalid service_pubkey length: {len(service_pubkey)}")
        
        # Check Recovery's pubkey
        recovery_pubkey_hex = params.get('recovery_pubkey') or params.get('recovery_pubkey_xonly')
        if not recovery_pubkey_hex:
            raise BuildError("Missing recovery_pubkey or recovery_pubkey_xonly")
        
        try:
            recovery_pubkey = bytes.fromhex(recovery_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid recovery_pubkey hex: {recovery_pubkey_hex}")
        
        if len(recovery_pubkey) not in (32, 33):
            raise BuildError(f"Invalid recovery_pubkey length: {len(recovery_pubkey)}")
        
        return True
    
    def parse(self, script_hex: str) -> Dict[str, Any]:
        """
        Parse two-factor wallet script back to parameters.
        
        This is the inverse of build().
        """
        script = bytes.fromhex(script_hex)
        
        if len(script) < 15:
            raise BuildError(f"Script too short: {len(script)} bytes")
        
        pos = 0
        
        # 1. Check OP_IF
        if script[pos] != self.OP_IF:
            raise BuildError(f"Expected OP_IF, got {script[pos]:02x}")
        pos += 1
        
        # 2. Read Service's pubkey (normal path)
        service_len = script[pos]
        pos += 1
        
        if service_len not in (32, 33):
            raise BuildError(f"Invalid service_pubkey length: {service_len}")
        
        service_pubkey = script[pos:pos + service_len]
        pos += service_len
        
        # 3. Check OP_CHECKSIGVERIFY
        if script[pos] != self.OP_CHECKSIGVERIFY:
            raise BuildError(f"Expected OP_CHECKSIGVERIFY, got {script[pos]:02x}")
        pos += 1
        
        # 4. Read User's pubkey (normal path)
        user_len_1 = script[pos]
        pos += 1
        
        if user_len_1 not in (32, 33):
            raise BuildError(f"Invalid user_pubkey length: {user_len_1}")
        
        user_pubkey_1 = script[pos:pos + user_len_1]
        pos += user_len_1
        
        # 5. Check OP_CHECKSIG
        if script[pos] != self.OP_CHECKSIG:
            raise BuildError(f"Expected OP_CHECKSIG, got {script[pos]:02x}")
        pos += 1
        
        # 6. Check OP_ELSE
        if script[pos] != self.OP_ELSE:
            raise BuildError(f"Expected OP_ELSE, got {script[pos]:02x}")
        pos += 1
        
        # 7. Read locktime
        locktime_len = script[pos]
        pos += 1
        
        if locktime_len > 5:
            raise BuildError(f"Invalid locktime length: {locktime_len}")
        
        locktime_bytes = script[pos:pos + locktime_len]
        pos += locktime_len
        
        from .base import decode_script_number
        locktime = decode_script_number(locktime_bytes)
        
        # 8. Check OP_CLTV OP_DROP
        if script[pos] != self.OP_CLTV:
            raise BuildError(f"Expected OP_CLTV, got {script[pos]:02x}")
        pos += 1
        
        if script[pos] != self.OP_DROP:
            raise BuildError(f"Expected OP_DROP, got {script[pos]:02x}")
        pos += 1
        
        # 9. Read Recovery's pubkey (recovery path)
        recovery_len = script[pos]
        pos += 1
        
        if recovery_len not in (32, 33):
            raise BuildError(f"Invalid recovery_pubkey length: {recovery_len}")
        
        recovery_pubkey = script[pos:pos + recovery_len]
        pos += recovery_len
        
        # 10. Check OP_CHECKSIGVERIFY
        if script[pos] != self.OP_CHECKSIGVERIFY:
            raise BuildError(f"Expected OP_CHECKSIGVERIFY, got {script[pos]:02x}")
        pos += 1
        
        # 11. Read User's pubkey (recovery path - should match normal path)
        user_len_2 = script[pos]
        pos += 1
        
        if user_len_2 not in (32, 33):
            raise BuildError(f"Invalid user_pubkey length: {user_len_2}")
        
        user_pubkey_2 = script[pos:pos + user_len_2]
        pos += user_len_2
        
        # Verify user pubkey is same in both paths
        if user_pubkey_1 != user_pubkey_2:
            raise BuildError("User pubkey mismatch between IF and ELSE branches")
        
        # 12. Check OP_CHECKSIG
        if script[pos] != self.OP_CHECKSIG:
            raise BuildError(f"Expected OP_CHECKSIG, got {script[pos]:02x}")
        pos += 1
        
        # 13. Check OP_ENDIF
        if script[pos] != self.OP_ENDIF:
            raise BuildError(f"Expected OP_ENDIF, got {script[pos]:02x}")
        pos += 1
        
        # Should be end of script
        if pos != len(script):
            raise BuildError(f"Extra data after script: {len(script) - pos} bytes")
        
        return {
            'user_pubkey': user_pubkey_1.hex(),
            'service_pubkey': service_pubkey.hex(),
            'recovery_pubkey': recovery_pubkey.hex(),
            'locktime': locktime,
        }
