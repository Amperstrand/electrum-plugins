"""
Escrow Script Builder - BIP-65 Example #1

Implements BIP-65 Example #1: Escrow with Three-Party Arbitration

BIP-65 Quote:
"If Alice and Bob jointly operate a business they may want to ensure that all
funds are kept in 2-of-2 multisig transaction outputs... they appoint their
lawyer, Lenny, to act as a third-party."

Script structure (BIP-65 compliant):
    OP_IF
        <locktime> OP_CLTV OP_DROP
        <lenny_pubkey> OP_CHECKSIGVERIFY
        OP_1
    OP_ELSE
        OP_2
    OP_ENDIF
    <alice_pubkey> <bob_pubkey> OP_2 OP_CHECKMULTISIG

Spend paths:
1. Before timeout (ELSE): Alice AND Bob (2-of-2 multisig) - Normal operations
2. After timeout (IF): Lenny + (Alice OR Bob) (1-of-2 multisig) - Escrow arbitration

Learning points:
- Three-party escrow with third-party arbitrator (Lenny)
- CHECKMULTISIG with different thresholds (2-of-2 vs 1-of-2)
- Timeout prevents Lenny from stealing before expiry
- Normal business operations don't require Lenny
"""

from typing import Dict, Any
from .base import ScriptBuilder, encode_script_number, BuildError


class EscrowTimeoutBuilder(ScriptBuilder):
    """
    Builder for BIP-65 escrow scripts with three-party arbitration.
    
    Creates a 2-of-2 multisig that becomes 1-of-2 (+ arbitrator) after timeout.
    
    Parameters:
        alice_pubkey: str - Alice's public key (hex)
        bob_pubkey: str - Bob's public key (hex)
        lenny_pubkey: str - Lenny's public key (hex) - the arbitrator
        locktime: int - Timeout for arbitration (block height or timestamp)
        
    Optional:
        alice_pubkey_xonly: str - For Taproot (32 bytes)
        bob_pubkey_xonly: str - For Taproot (32 bytes)
        lenny_pubkey_xonly: str - For Taproot (32 bytes)
    """
    
    SCRIPT_TYPE = "cltv_escrow"
    
    # Opcodes
    OP_IF = 0x63
    OP_ELSE = 0x67
    OP_ENDIF = 0x68
    OP_CLTV = 0xb1
    OP_DROP = 0x75
    OP_CHECKSIGVERIFY = 0xad
    OP_CHECKMULTISIG = 0xae
    OP_1 = 0x51
    OP_2 = 0x52
    
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build BIP-65 escrow script with CHECKMULTISIG.
        
        Returns deterministic script bytes.
        """
        self.validate_params(params)
        
        locktime = params['locktime']
        
        # Support both regular and x-only pubkeys
        alice_pubkey_hex = params.get('alice_pubkey') or params.get('alice_pubkey_xonly')
        bob_pubkey_hex = params.get('bob_pubkey') or params.get('bob_pubkey_xonly')
        lenny_pubkey_hex = params.get('lenny_pubkey') or params.get('lenny_pubkey_xonly')
        
        alice_pubkey = bytes.fromhex(alice_pubkey_hex)
        bob_pubkey = bytes.fromhex(bob_pubkey_hex)
        lenny_pubkey = bytes.fromhex(lenny_pubkey_hex)
        
        # Build script matching BIP-65 exactly
        script = bytearray()
        
        # OP_IF
        script.append(self.OP_IF)
        
        # Path 1: After timeout - Arbitration path
        # <locktime> OP_CLTV OP_DROP
        locktime_bytes = encode_script_number(locktime)
        script.append(len(locktime_bytes))
        script.extend(locktime_bytes)
        script.append(self.OP_CLTV)
        script.append(self.OP_DROP)
        
        # <lenny_pubkey> OP_CHECKSIGVERIFY
        script.append(len(lenny_pubkey))
        script.extend(lenny_pubkey)
        script.append(self.OP_CHECKSIGVERIFY)
        
        # OP_1 (threshold for 1-of-2 multisig)
        script.append(self.OP_1)
        
        # OP_ELSE
        script.append(self.OP_ELSE)
        
        # Path 2: Before timeout - Normal operations
        # OP_2 (threshold for 2-of-2 multisig)
        script.append(self.OP_2)
        
        # OP_ENDIF
        script.append(self.OP_ENDIF)
        
        # Common multisig: <alice_pubkey> <bob_pubkey> OP_2 OP_CHECKMULTISIG
        script.append(len(alice_pubkey))
        script.extend(alice_pubkey)
        script.append(len(bob_pubkey))
        script.extend(bob_pubkey)
        script.append(self.OP_2)  # 2 pubkeys total
        script.append(self.OP_CHECKMULTISIG)
        
        return bytes(script)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate escrow parameters.
        """
        # Check locktime
        if 'locktime' not in params:
            raise BuildError("Missing required parameter: locktime")
        
        locktime = params['locktime']
        if not isinstance(locktime, int) or locktime < 0:
            raise BuildError(f"Invalid locktime: {locktime}")
        
        # Check Alice's pubkey
        alice_pubkey_hex = params.get('alice_pubkey') or params.get('alice_pubkey_xonly')
        if not alice_pubkey_hex:
            raise BuildError("Missing alice_pubkey or alice_pubkey_xonly")
        
        try:
            alice_pubkey = bytes.fromhex(alice_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid alice_pubkey hex: {alice_pubkey_hex}")
        
        if len(alice_pubkey) not in (32, 33):
            raise BuildError(f"Invalid alice_pubkey length: {len(alice_pubkey)}")
        
        # Check Bob's pubkey
        bob_pubkey_hex = params.get('bob_pubkey') or params.get('bob_pubkey_xonly')
        if not bob_pubkey_hex:
            raise BuildError("Missing bob_pubkey or bob_pubkey_xonly")
        
        try:
            bob_pubkey = bytes.fromhex(bob_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid bob_pubkey hex: {bob_pubkey_hex}")
        
        if len(bob_pubkey) not in (32, 33):
            raise BuildError(f"Invalid bob_pubkey length: {len(bob_pubkey)}")
        
        # Check Lenny's pubkey (NEW - third party arbitrator)
        lenny_pubkey_hex = params.get('lenny_pubkey') or params.get('lenny_pubkey_xonly')
        if not lenny_pubkey_hex:
            raise BuildError("Missing lenny_pubkey or lenny_pubkey_xonly")
        
        try:
            lenny_pubkey = bytes.fromhex(lenny_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid lenny_pubkey hex: {lenny_pubkey_hex}")
        
        if len(lenny_pubkey) not in (32, 33):
            raise BuildError(f"Invalid lenny_pubkey length: {len(lenny_pubkey)}")
        
        return True
    
    def parse(self, script_hex: str) -> Dict[str, Any]:
        """
        Parse escrow script back to parameters.
        
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
        
        # 2. Read locktime
        locktime_len = script[pos]
        pos += 1
        
        if locktime_len > 5:
            raise BuildError(f"Invalid locktime length: {locktime_len}")
        
        locktime_bytes = script[pos:pos + locktime_len]
        pos += locktime_len
        
        from .base import decode_script_number
        locktime = decode_script_number(locktime_bytes)
        
        # 3. Check OP_CLTV OP_DROP
        if script[pos] != self.OP_CLTV:
            raise BuildError(f"Expected OP_CLTV, got {script[pos]:02x}")
        pos += 1
        
        if script[pos] != self.OP_DROP:
            raise BuildError(f"Expected OP_DROP, got {script[pos]:02x}")
        pos += 1
        
        # 4. Read Lenny's pubkey
        lenny_len = script[pos]
        pos += 1
        
        if lenny_len not in (32, 33):
            raise BuildError(f"Invalid lenny_pubkey length: {lenny_len}")
        
        lenny_pubkey = script[pos:pos + lenny_len]
        pos += lenny_len
        
        # 5. Check OP_CHECKSIGVERIFY
        if script[pos] != self.OP_CHECKSIGVERIFY:
            raise BuildError(f"Expected OP_CHECKSIGVERIFY, got {script[pos]:02x}")
        pos += 1
        
        # 6. Check OP_1
        if script[pos] != self.OP_1:
            raise BuildError(f"Expected OP_1, got {script[pos]:02x}")
        pos += 1
        
        # 7. Check OP_ELSE
        if script[pos] != self.OP_ELSE:
            raise BuildError(f"Expected OP_ELSE, got {script[pos]:02x}")
        pos += 1
        
        # 8. Check OP_2
        if script[pos] != self.OP_2:
            raise BuildError(f"Expected OP_2, got {script[pos]:02x}")
        pos += 1
        
        # 9. Check OP_ENDIF
        if script[pos] != self.OP_ENDIF:
            raise BuildError(f"Expected OP_ENDIF, got {script[pos]:02x}")
        pos += 1
        
        # 10. Read Alice's pubkey
        alice_len = script[pos]
        pos += 1
        
        if alice_len not in (32, 33):
            raise BuildError(f"Invalid alice_pubkey length: {alice_len}")
        
        alice_pubkey = script[pos:pos + alice_len]
        pos += alice_len
        
        # 11. Read Bob's pubkey
        bob_len = script[pos]
        pos += 1
        
        if bob_len not in (32, 33):
            raise BuildError(f"Invalid bob_pubkey length: {bob_len}")
        
        bob_pubkey = script[pos:pos + bob_len]
        pos += bob_len
        
        # 12. Check OP_2 (number of pubkeys)
        if script[pos] != self.OP_2:
            raise BuildError(f"Expected OP_2, got {script[pos]:02x}")
        pos += 1
        
        # 13. Check OP_CHECKMULTISIG
        if script[pos] != self.OP_CHECKMULTISIG:
            raise BuildError(f"Expected OP_CHECKMULTISIG, got {script[pos]:02x}")
        pos += 1
        
        # Should be end of script
        if pos != len(script):
            raise BuildError(f"Extra data after script: {len(script) - pos} bytes")
        
        return {
            'alice_pubkey': alice_pubkey.hex(),
            'bob_pubkey': bob_pubkey.hex(),
            'lenny_pubkey': lenny_pubkey.hex(),
            'locktime': locktime,
        }
