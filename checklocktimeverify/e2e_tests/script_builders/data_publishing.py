"""
Data Publishing Script Builder (BIP-65 Example #5)

This implements a data publishing contract where:
- Publisher can claim by revealing data preimage + signature
- Buyer can refund after timeout if data not delivered

Script structure:
    OP_IF
        OP_SHA256 <data_hash> OP_EQUALVERIFY <publisher_pubkey> OP_CHECKSIG
    OP_ELSE
        <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <buyer_pubkey> OP_CHECKSIG
    OP_ENDIF

This is the PayPub example from BIP-65, demonstrating hash-based contract enforcement.
"""

from typing import Dict, Any
from .base import ScriptBuilder, encode_script_number, BuildError


class DataPublishingBuilder(ScriptBuilder):
    """
    Builder for data publishing (PayPub) scripts.
    
    Creates a contract where publisher reveals preimage to claim,
    or buyer refunds after timeout.
    
    Parameters:
        publisher_pubkey: str - Publisher's public key (hex)
        buyer_pubkey: str - Buyer's public key (hex, can refund after timeout)
        data_hash: str - HASH160 of the data (20 bytes hex) = RIPEMD160(SHA256(data))
        locktime: int - Refund timeout (block height or timestamp)
        
    Optional (for Taproot):
        publisher_pubkey_xonly: str - Publisher's x-only pubkey (32 bytes)
        buyer_pubkey_xonly: str - Buyer's x-only pubkey (32 bytes)
    """
    
    SCRIPT_TYPE = "cltv_data_publishing"
    
    # Opcodes
    OP_IF = 0x63
    OP_ELSE = 0x67
    OP_ENDIF = 0x68
    OP_HASH160 = 0xa9  # FIXED: BIP-65 uses HASH160, not SHA256!
    OP_EQUALVERIFY = 0x88
    OP_CLTV = 0xb1
    OP_DROP = 0x75
    OP_CHECKSIG = 0xac
    
    def build(self, params: Dict[str, Any]) -> bytes:
        """
        Build data publishing script.
        
        Returns deterministic script bytes.
        """
        self.validate_params(params)
        
        locktime = params['locktime']
        data_hash = params['data_hash']
        
        # Support both regular and x-only pubkeys
        publisher_pubkey_hex = params.get('publisher_pubkey') or params.get('publisher_pubkey_xonly')
        buyer_pubkey_hex = params.get('buyer_pubkey') or params.get('buyer_pubkey_xonly')
        
        publisher_pubkey = bytes.fromhex(publisher_pubkey_hex)
        buyer_pubkey = bytes.fromhex(buyer_pubkey_hex)
        data_hash_bytes = bytes.fromhex(data_hash)
        
        # Build script
        script = bytearray()
        
        # OP_IF
        script.append(self.OP_IF)
        
        # Path 1: Publisher reveals preimage
        # OP_HASH160 <data_hash> OP_EQUALVERIFY <publisher_pubkey> OP_CHECKSIG
        # BIP-65 line 155: HASH160 = RIPEMD160(SHA256(x))
        script.append(self.OP_HASH160)
        script.append(len(data_hash_bytes))
        script.extend(data_hash_bytes)
        script.append(self.OP_EQUALVERIFY)
        script.append(len(publisher_pubkey))
        script.extend(publisher_pubkey)
        script.append(self.OP_CHECKSIG)
        
        # OP_ELSE
        script.append(self.OP_ELSE)
        
        # Path 2: Buyer refund after timeout
        # <locktime> OP_CLTV OP_DROP <buyer_pubkey> OP_CHECKSIG
        locktime_bytes = encode_script_number(locktime)
        script.append(len(locktime_bytes))
        script.extend(locktime_bytes)
        script.append(self.OP_CLTV)
        script.append(self.OP_DROP)
        script.append(len(buyer_pubkey))
        script.extend(buyer_pubkey)
        script.append(self.OP_CHECKSIG)
        
        # OP_ENDIF
        script.append(self.OP_ENDIF)
        
        return bytes(script)
    
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate data publishing parameters.
        """
        # Check locktime
        if 'locktime' not in params:
            raise BuildError("Missing required parameter: locktime")
        
        locktime = params['locktime']
        if not isinstance(locktime, int) or locktime < 0:
            raise BuildError(f"Invalid locktime: {locktime}")
        
        # Check data_hash
        if 'data_hash' not in params:
            raise BuildError("Missing required parameter: data_hash")
        
        data_hash = params['data_hash']
        if not isinstance(data_hash, str) or len(data_hash) != 40:
            raise BuildError(f"data_hash must be 20 bytes (40 hex chars) for HASH160, got {len(data_hash)}")
        
        try:
            bytes.fromhex(data_hash)
        except ValueError:
            raise BuildError(f"Invalid data_hash hex: {data_hash}")
        
        # Check Publisher's pubkey
        publisher_pubkey_hex = params.get('publisher_pubkey') or params.get('publisher_pubkey_xonly')
        if not publisher_pubkey_hex:
            raise BuildError("Missing publisher_pubkey or publisher_pubkey_xonly")
        
        try:
            publisher_pubkey = bytes.fromhex(publisher_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid publisher_pubkey hex: {publisher_pubkey_hex}")
        
        if len(publisher_pubkey) not in (32, 33):
            raise BuildError(f"Invalid publisher_pubkey length: {len(publisher_pubkey)}")
        
        # Check Buyer's pubkey
        buyer_pubkey_hex = params.get('buyer_pubkey') or params.get('buyer_pubkey_xonly')
        if not buyer_pubkey_hex:
            raise BuildError("Missing buyer_pubkey or buyer_pubkey_xonly")
        
        try:
            buyer_pubkey = bytes.fromhex(buyer_pubkey_hex)
        except ValueError:
            raise BuildError(f"Invalid buyer_pubkey hex: {buyer_pubkey_hex}")
        
        if len(buyer_pubkey) not in (32, 33):
            raise BuildError(f"Invalid buyer_pubkey length: {len(buyer_pubkey)}")
        
        return True


# Example usage
if __name__ == '__main__':
    """
    Demo: Create a data publishing script
    """
    import hashlib
    
    # Generate test data hash using HASH160 (RIPEMD160(SHA256(x)))
    import hashlib
    test_data = "Secret BIP-65 data publishing example"
    sha256_hash = hashlib.sha256(test_data.encode('utf-8')).digest()
    data_hash = hashlib.new('ripemd160', sha256_hash).digest().hex()
    
    # Example pubkeys (compressed)
    publisher_pubkey = "02bc82dd73e5161dba0884a36f2080d682ffc274bf62fca8f9eb0aadf82a8d733c"
    buyer_pubkey = "02ee079adb1df1860074356a25aa38206a6d716b2c3e67453d287698bad7b2b2d6"
    
    builder = DataPublishingBuilder()
    
    params = {
        'locktime': 100042,
        'data_hash': data_hash,
        'publisher_pubkey': publisher_pubkey,
        'buyer_pubkey': buyer_pubkey
    }
    
    script_bytes = builder.build(params)
    script_hex = script_bytes.hex()
    
    print("=" * 80)
    print("Data Publishing (PayPub) Script")
    print("=" * 80)
    print(f"Test Data: {test_data}")
    print(f"Data Hash (HASH160): {data_hash}")
    print(f"Locktime: {params['locktime']}")
    print(f"\nScript Hex: {script_hex[:80]}...")
    print(f"Script Length: {len(script_bytes)} bytes")
    print("\n" + "=" * 80)
    print("Spending Paths:")
    print("=" * 80)
    print("1. Publisher Claims (reveal preimage):")
    print("   - Witness: [publisher_sig, data_preimage, 1, script]")
    print("   - Script checks: HASH160(preimage) == data_hash [RIPEMD160(SHA256(preimage))]")
    print("   - Then verifies publisher signature")
    print()
    print("2. Buyer Refund (after timeout):")
    print(f"   - Requires block height >= {params['locktime']}")
    print("   - Witness: [buyer_sig, 0, script]")
    print("   - Takes ELSE branch (no preimage needed)")
    print("=" * 80)
