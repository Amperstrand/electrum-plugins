#!/usr/bin/env python3
"""
Taproot Data Publishing Address Builder

Creates Taproot addresses for data publishing contracts with two script-path leaves:
1. Publisher path: Reveal preimage + signature (any time)
2. Buyer refund path: Buyer alone (after CLTV timeout)

Uses manual BIP-341/342 construction with NUMS internal key.

Pattern:
- Publisher leaf: OP_HASH160 <hash> OP_EQUALVERIFY <publisher_xonly> OP_CHECKSIG
- Buyer refund leaf: <locktime> OP_CLTV OP_DROP <buyer_xonly> OP_CHECKSIG

Reference: payment_channel_taproot.py
Note: Uses HASH160 to match BIP-65 specification exactly (RIPEMD160(SHA256(data)))
"""

import sys
import os
from pathlib import Path
import hashlib
import struct

# Prefer vendored third_party helpers to avoid external dependency
_THIRD_PARTY = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../third_party'))
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)

from bip_350_bech32_reference import encode as bech32m_encode


def tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-340 tagged hash."""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def sha256(data: bytes) -> bytes:
    """Single SHA256 hash."""
    return hashlib.sha256(data).digest()


def varint(n: int) -> bytes:
    """Encode variable-length integer (CompactSize)."""
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return bytes([0xfd]) + struct.pack("<H", n)
    elif n <= 0xffffffff:
        return bytes([0xfe]) + struct.pack("<I", n)
    else:
        return bytes([0xff]) + struct.pack("<Q", n)


def encode_script_number(n: int) -> bytes:
    """Encode integer as minimal script number (Bitcoin consensus rules)."""
    if n == 0:
        return b""
    neg = n < 0
    n = -n if neg else n
    out = bytearray()
    while n:
        out.append(n & 0xff)
        n >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return bytes(out)


def pubkey_to_xonly(pubkey_hex: str) -> bytes:
    """Convert compressed pubkey (33 bytes) to x-only (32 bytes)."""
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    if len(pubkey_bytes) != 33:
        raise ValueError(f"Expected 33-byte compressed pubkey, got {len(pubkey_bytes)}")
    return pubkey_bytes[1:]  # Strip 02/03 prefix


def create_data_publishing_taproot_address(
    locktime: int,
    data_hash: bytes,  # 20-byte HASH160 of the data (RIPEMD160(SHA256(data)))
    publisher_pubkey: str,
    buyer_pubkey: str,
    network: str = 'signet'
) -> dict:
    """
    Create Taproot data publishing address with publisher + buyer refund paths.
    
    Args:
        locktime: Block height for buyer refund timeout
        data_hash: 20-byte HASH160 of the data (bytes, not hex) = RIPEMD160(SHA256(data))
        publisher_pubkey: Publisher's compressed pubkey (33 bytes hex, 02/03 prefix)
        buyer_pubkey: Buyer's compressed pubkey (33 bytes hex, 02/03 prefix)
        network: 'signet', 'testnet', 'mainnet', 'regtest'
    
    Returns:
        {
            'address': 'tb1p...',
            'output_key': hex,
            'merkle_root': hex,
            'internal_key': hex (NUMS),
            'scripts': {
                'publisher': {
                    'script': hex,
                    'control_block': hex
                },
                'buyer_refund': {
                    'script': hex,
                    'control_block': hex
                }
            }
        }
    """
    # 1. Convert to x-only pubkeys
    publisher_xonly = pubkey_to_xonly(publisher_pubkey)
    buyer_xonly = pubkey_to_xonly(buyer_pubkey)
    
    # 2. Build publisher script (reveal preimage, any time)
    # Script: OP_HASH160 <data_hash> OP_EQUALVERIFY <publisher_xonly> OP_CHECKSIG
    # Stack execution:
    # Initial: [preimage, sig] (from witness)
    # HASH160: [sig, HASH160(preimage)]  (HASH160 = RIPEMD160(SHA256(x)))
    # <data_hash>: [sig, HASH160(preimage), data_hash]
    # EQUALVERIFY: [sig] (pops both, fails if not equal)
    # <publisher_xonly>: [sig, publisher_xonly]
    # CHECKSIG: [1]
    publisher_script = bytearray()
    publisher_script.append(0xa9)                    # OP_HASH160
    publisher_script.append(0x14)                    # Push 20 bytes
    publisher_script.extend(data_hash)               # Expected hash
    publisher_script.append(0x88)                    # OP_EQUALVERIFY
    publisher_script.append(0x20)                    # Push 32 bytes
    publisher_script.extend(publisher_xonly)         # Publisher x-only pubkey
    publisher_script.append(0xac)                    # OP_CHECKSIG
    publisher_script = bytes(publisher_script)
    
    # 3. Build buyer refund script (buyer alone after locktime)
    # Script: <locktime> OP_CLTV OP_DROP <buyer_xonly> OP_CHECKSIG
    # Identical to Payment Channel refund pattern
    locktime_bytes = encode_script_number(locktime)
    buyer_refund_script = bytearray()
    # Add explicit PUSH opcode for the locktime data
    if len(locktime_bytes) < 0x4c:
        buyer_refund_script.append(len(locktime_bytes))  # PUSH opcode
    else:
        buyer_refund_script.append(0x4c)  # OP_PUSHDATA1
        buyer_refund_script.append(len(locktime_bytes))
    buyer_refund_script.extend(locktime_bytes)
    buyer_refund_script.append(0xb1)                 # OP_CLTV
    buyer_refund_script.append(0x75)                 # OP_DROP
    buyer_refund_script.append(0x20)                 # Push 32 bytes
    buyer_refund_script.extend(buyer_xonly)          # Buyer x-only pubkey
    buyer_refund_script.append(0xac)                 # OP_CHECKSIG
    buyer_refund_script = bytes(buyer_refund_script)
    
    # 4. Compute TapLeaf hashes
    leaf_version = bytes([0xc0])
    tapleaf_publisher = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(publisher_script)) + publisher_script
    )
    tapleaf_buyer_refund = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(buyer_refund_script)) + buyer_refund_script
    )
    
    # 5. Compute merkle root (TapBranch with lexicographic ordering)
    if tapleaf_publisher < tapleaf_buyer_refund:
        merkle_root = tagged_hash("TapBranch", tapleaf_publisher + tapleaf_buyer_refund)
    else:
        merkle_root = tagged_hash("TapBranch", tapleaf_buyer_refund + tapleaf_publisher)
    
    # 6. Use NUMS internal key (script-path only)
    NUMS_HEX = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
    internal_key = bytes.fromhex(NUMS_HEX)
    
    # 7. Compute TapTweak and output key
    from bip_0340_reference import int_from_bytes, bytes_from_int, lift_x, point_add, point_mul, G
    
    taptweak_hash = tagged_hash("TapTweak", internal_key + merkle_root)
    taptweak_int = int_from_bytes(taptweak_hash)
    
    internal_point = lift_x(int_from_bytes(internal_key))
    if internal_point is None:
        raise ValueError("Failed to lift internal key")
    
    # Compute t*G
    tweak_point = point_mul(G, taptweak_int)
    
    # Q = P + t*G
    output_point = point_add(internal_point, tweak_point)
    if output_point is None:
        raise ValueError("Failed to compute output point")
    
    # 8. Extract x-only output key and parity
    output_key = bytes_from_int(output_point[0])
    output_parity = output_point[1] & 1
    
    # 9. Build control blocks (with Merkle proof = sibling hash)
    # For publisher path: proof = buyer refund leaf hash
    publisher_control = bytes([0xc0 | output_parity]) + internal_key + tapleaf_buyer_refund
    
    # For buyer refund path: proof = publisher leaf hash
    buyer_refund_control = bytes([0xc0 | output_parity]) + internal_key + tapleaf_publisher
    
    # 10. Create bech32m address
    hrp = 'bc' if network == 'mainnet' else ('bcrt' if network == 'regtest' else 'tb')
    address = bech32m_encode(hrp, 1, list(output_key))
    if address is None:
        raise ValueError("Failed to encode bech32m address")
    
    return {
        'address': address,
        'output_key': output_key.hex(),
        'merkle_root': merkle_root.hex(),
        'internal_key': internal_key.hex(),
        'scripts': {
            'publisher': {
                'script': publisher_script.hex(),
                'control_block': publisher_control.hex()
            },
            'buyer_refund': {
                'script': buyer_refund_script.hex(),
                'control_block': buyer_refund_control.hex()
            }
        }
    }


if __name__ == '__main__':
    print("Taproot Data Publishing Address Builder")
    print("=" * 60)
    
    # Test with known keys
    locktime = 275971
    publisher_pubkey = "033f0e80e574456d8f8fa64e044b2eb72ea22eb53fe1efe3a443933aca7f8cb0e3"
    buyer_pubkey = "03a1d0fcf2ec9de675b612136e5ce70d271c21417c9d2b8aaaac138599d0717940"
    
    # Test data and hash (HASH160 = RIPEMD160(SHA256(data)) to match BIP-65)
    test_data = b"Secret BIP-65 data publishing example"
    sha256_hash = hashlib.sha256(test_data).digest()
    data_hash = hashlib.new('ripemd160', sha256_hash).digest()
    
    result = create_data_publishing_taproot_address(
        locktime=locktime,
        data_hash=data_hash,
        publisher_pubkey=publisher_pubkey,
        buyer_pubkey=buyer_pubkey,
        network='signet'
    )
    
    print(f"Address: {result['address']}")
    print(f"Output key: {result['output_key']}")
    print(f"Merkle root: {result['merkle_root']}")
    print(f"Data hash: {data_hash.hex()}")
    print(f"\nPublisher script: {result['scripts']['publisher']['script']}")
    print(f"Publisher control: {result['scripts']['publisher']['control_block']}")
    print(f"\nBuyer refund script: {result['scripts']['buyer_refund']['script']}")
    print(f"Buyer refund control: {result['scripts']['buyer_refund']['control_block']}")
    print("\n✅ Address generation complete!")
