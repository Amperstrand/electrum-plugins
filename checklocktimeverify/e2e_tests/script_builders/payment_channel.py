"""
Payment Channel Script Builder

Implements BIP-65 Example #4: Payment Channels

Script structure:
    OP_IF
        2 <sender_pubkey> <receiver_pubkey> 2 OP_CHECKMULTISIG
    OP_ELSE
        <locktime> OP_CLTV OP_DROP
        <sender_pubkey> OP_CHECKSIG
    OP_ENDIF

Spend paths:
1. Cooperative close: Sender AND Receiver (2-of-2 multisig)
2. Refund: Sender only (after timeout)

Use case:
- Sender deposits funds into channel
- Both parties can cooperate to close at any time (adjust balances)
- If receiver disappears, sender can reclaim after timeout

Learning points:
- Channel setup with refund protection
- Cooperative spending preferred (lower fees, privacy)
- Unilateral exit via timeout (safety valve)
"""

from typing import Dict, Any
from .base import ScriptBuilder, encode_script_number, BuildError


class PaymentChannelBuilder(ScriptBuilder):
    """
    Builder for payment channel scripts.
    
    Creates a 2-of-2 cooperative channel with sender refund after timeout.
    
    Parameters:
        sender_pubkey: str - Sender's public key (hex, can refund after timeout)
        receiver_pubkey: str - Receiver's public key (hex)
        locktime: int - Refund timeout (block height or timestamp)
        
    Optional (for Taproot):
        sender_pubkey_xonly: str - Sender's x-only pubkey (32 bytes)
        receiver_pubkey_xonly: str - Receiver's x-only pubkey (32 bytes)
    """
    
    SCRIPT_TYPE = "cltv_payment_channel"
    
    # Opcodes
    OP_IF = 0x63
    OP_ELSE = 0x67
    OP_ENDIF = 0x68
    OP_CLTV = 0xb1
    OP_DROP = 0x75
    OP_CHECKSIG = 0xac
    OP_CHECKMULTISIG = 0xae
    
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build payment channel script.
        
        Returns deterministic script bytes.
        """
        self.validate_params(params)
        
        locktime = params['locktime']
        
        # Support both regular and x-only pubkeys
        sender_pubkey_hex = params.get('sender_pubkey') or params.get('sender_pubkey_xonly')
        receiver_pubkey_hex = params.get('receiver_pubkey') or params.get('receiver_pubkey_xonly')
        
        sender_pubkey = bytes.fromhex(sender_pubkey_hex)
        receiver_pubkey = bytes.fromhex(receiver_pubkey_hex)
        
        # Build script
        script = bytearray()
        
        # OP_IF
        script.append(self.OP_IF)
        
        # Path 1: Cooperative close - 2-of-2 multisig (sender + receiver)
        # 2 <sender_pubkey> <receiver_pubkey> 2 OP_CHECKMULTISIG
        script.append(0x52)  # OP_2
        script.append(len(sender_pubkey))
        script.extend(sender_pubkey)
        script.append(len(receiver_pubkey))
        script.extend(receiver_pubkey)
        script.append(0x52)  # OP_2
        script.append(self.OP_CHECKMULTISIG)
        
        # OP_ELSE
        script.append(self.OP_ELSE)
        
        # Path 2: Refund - Sender only after timeout
        # <locktime> OP_CLTV OP_DROP
        locktime_bytes = encode_script_number(locktime)
        script.append(len(locktime_bytes))
        script.extend(locktime_bytes)
        script.append(self.OP_CLTV)
        script.append(self.OP_DROP)
        
        # <sender_pubkey> OP_CHECKSIG
        script.append(len(sender_pubkey))
        script.extend(sender_pubkey)
        script.append(self.OP_CHECKSIG)
        
        # OP_ENDIF
        script.append(self.OP_ENDIF)
        
        return bytes(script)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate payment channel parameters.
        """
        # Check locktime
        if 'locktime' not in params:
            raise BuildError("Missing required parameter: locktime")
        
        locktime = params['locktime']
        if not isinstance(locktime, int) or locktime < 0:
            raise BuildError(f"Invalid locktime: {locktime}")
        
        # Check Sender's pubkey
        sender_pubkey_hex = params.get('sender_pubkey') or params.get('sender_pubkey_xonly')
        if not sender_pubkey_hex:
            raise BuildError("Missing sender_pubkey or sender_pubkey_xonly")
        
        try:
            sender_pubkey = bytes.fromhex(sender_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid sender_pubkey hex: {sender_pubkey_hex}")
        
        if len(sender_pubkey) not in (32, 33):
            raise BuildError(f"Invalid sender_pubkey length: {len(sender_pubkey)}")
        
        # Check Receiver's pubkey
        receiver_pubkey_hex = params.get('receiver_pubkey') or params.get('receiver_pubkey_xonly')
        if not receiver_pubkey_hex:
            raise BuildError("Missing receiver_pubkey or receiver_pubkey_xonly")
        
        try:
            receiver_pubkey = bytes.fromhex(receiver_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid receiver_pubkey hex: {receiver_pubkey_hex}")
        
        if len(receiver_pubkey) not in (32, 33):
            raise BuildError(f"Invalid receiver_pubkey length: {len(receiver_pubkey)}")
        
        return True
    
    def parse(self, script_hex: str) -> Dict[str, Any]:
        """
        Parse payment channel script back to parameters.
        
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
        
        # 2. Check OP_2
        if script[pos] != 0x52:
            raise BuildError(f"Expected OP_2, got {script[pos]:02x}")
        pos += 1
        
        # 3. Read Sender's pubkey
        sender_len = script[pos]
        pos += 1
        
        if sender_len not in (32, 33):
            raise BuildError(f"Invalid sender_pubkey length: {sender_len}")
        
        sender_pubkey = script[pos:pos + sender_len]
        pos += sender_len
        
        # 4. Read Receiver's pubkey
        receiver_len = script[pos]
        pos += 1
        
        if receiver_len not in (32, 33):
            raise BuildError(f"Invalid receiver_pubkey length: {receiver_len}")
        
        receiver_pubkey = script[pos:pos + receiver_len]
        pos += receiver_len
        
        # 5. Check OP_2
        if script[pos] != 0x52:
            raise BuildError(f"Expected OP_2, got {script[pos]:02x}")
        pos += 1
        
        # 6. Check OP_CHECKMULTISIG
        if script[pos] != self.OP_CHECKMULTISIG:
            raise BuildError(f"Expected OP_CHECKMULTISIG, got {script[pos]:02x}")
        pos += 1
        
        # 7. Check OP_ELSE
        if script[pos] != self.OP_ELSE:
            raise BuildError(f"Expected OP_ELSE, got {script[pos]:02x}")
        pos += 1
        
        # 8. Read locktime
        locktime_len = script[pos]
        pos += 1
        
        if locktime_len > 5:
            raise BuildError(f"Invalid locktime length: {locktime_len}")
        
        locktime_bytes = script[pos:pos + locktime_len]
        pos += locktime_len
        
        from .base import decode_script_number
        locktime = decode_script_number(locktime_bytes)
        
        # 9. Check OP_CLTV OP_DROP
        if script[pos] != self.OP_CLTV:
            raise BuildError(f"Expected OP_CLTV, got {script[pos]:02x}")
        pos += 1
        
        if script[pos] != self.OP_DROP:
            raise BuildError(f"Expected OP_DROP, got {script[pos]:02x}")
        pos += 1
        
        # 10. Read Sender's pubkey (refund path - should match cooperative path)
        sender_len_2 = script[pos]
        pos += 1
        
        if sender_len_2 not in (32, 33):
            raise BuildError(f"Invalid sender_pubkey length: {sender_len_2}")
        
        sender_pubkey_2 = script[pos:pos + sender_len_2]
        pos += sender_len_2
        
        # Verify sender pubkey is same in both paths
        if sender_pubkey != sender_pubkey_2:
            raise BuildError("Sender pubkey mismatch between IF and ELSE branches")
        
        # 11. Check OP_CHECKSIG
        if script[pos] != self.OP_CHECKSIG:
            raise BuildError(f"Expected OP_CHECKSIG, got {script[pos]:02x}")
        pos += 1
        
        # 12. Check OP_ENDIF
        if script[pos] != self.OP_ENDIF:
            raise BuildError(f"Expected OP_ENDIF, got {script[pos]:02x}")
        pos += 1
        
        # Should be end of script
        if pos != len(script):
            raise BuildError(f"Extra data after script: {len(script) - pos} bytes")
        
        return {
            'sender_pubkey': sender_pubkey.hex(),
            'receiver_pubkey': receiver_pubkey.hex(),
            'locktime': locktime,
        }
