#!/usr/bin/env python3
"""
Taproot Payment Channel Address Builder

Creates Taproot addresses for payment channels with two script-path leaves:
1. Cooperative close: Sender + Receiver (2-of-2, any time)
2. Refund: Sender alone (after CLTV timeout)

Uses manual BIP-341/342 construction with NUMS internal key.

Pattern:
- Cooperative leaf: <sender_xonly> CHECKSIGVERIFY <receiver_xonly> CHECKSIG
- Refund leaf: <locktime> CLTV DROP <sender_xonly> CHECKSIG

Reference: twofactor_taproot.py
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


def create_payment_channel_taproot_address(
    locktime: int,
    sender_pubkey: str,
    receiver_pubkey: str,
    network: str = 'signet'
) -> dict:
    """
    Create Taproot payment channel address with cooperative + refund paths.
    
    Args:
        locktime: Block height for refund timeout
        sender_pubkey: Sender's compressed pubkey (33 bytes hex, 02/03 prefix)
        receiver_pubkey: Receiver's compressed pubkey (33 bytes hex, 02/03 prefix)
        network: 'signet', 'testnet', 'mainnet', 'regtest'
    
    Returns:
        {
            'address': 'tb1p...',
            'output_key': hex,
            'merkle_root': hex,
            'internal_key': hex (NUMS),
            'scripts': {
                'cooperative': {
                    'script': hex,
                    'control_block': hex
                },
                'refund': {
                    'script': hex,
                    'control_block': hex
                }
            }
        }
    """
    # 1. Convert to x-only pubkeys
    sender_xonly = pubkey_to_xonly(sender_pubkey)
    receiver_xonly = pubkey_to_xonly(receiver_pubkey)
    
    # 2. Build cooperative script (sender + receiver, any time)
    # Script: <sender_xonly> CHECKSIGVERIFY <receiver_xonly> CHECKSIG
    cooperative_script = bytearray()
    cooperative_script.append(0x20)                  # Push 32 bytes
    cooperative_script.extend(sender_xonly)
    cooperative_script.append(0xad)                  # OP_CHECKSIGVERIFY
    cooperative_script.append(0x20)                  # Push 32 bytes
    cooperative_script.extend(receiver_xonly)
    cooperative_script.append(0xac)                  # OP_CHECKSIG
    cooperative_script = bytes(cooperative_script)
    
    # 3. Build refund script (sender alone after locktime)
    # Script: <locktime> CLTV DROP <sender_xonly> CHECKSIG
    locktime_bytes = encode_script_number(locktime)
    refund_script = bytearray()
    # Add explicit PUSH opcode for the locktime data
    if len(locktime_bytes) < 0x4c:
        refund_script.append(len(locktime_bytes))  # PUSH opcode
    else:
        refund_script.append(0x4c)  # OP_PUSHDATA1
        refund_script.append(len(locktime_bytes))
    refund_script.extend(locktime_bytes)
    refund_script.append(0xb1)                       # OP_CLTV
    refund_script.append(0x75)                       # OP_DROP
    refund_script.append(0x20)                       # Push 32 bytes
    refund_script.extend(sender_xonly)
    refund_script.append(0xac)                       # OP_CHECKSIG
    refund_script = bytes(refund_script)
    
    # 4. Compute TapLeaf hashes
    leaf_version = bytes([0xc0])
    tapleaf_cooperative = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(cooperative_script)) + cooperative_script
    )
    tapleaf_refund = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(refund_script)) + refund_script
    )
    
    # 5. Compute merkle root (TapBranch with lexicographic ordering)
    if tapleaf_cooperative < tapleaf_refund:
        merkle_root = tagged_hash("TapBranch", tapleaf_cooperative + tapleaf_refund)
    else:
        merkle_root = tagged_hash("TapBranch", tapleaf_refund + tapleaf_cooperative)
    
    # 6. Use NUMS internal key (script-path only)
    NUMS_HEX = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
    internal_key = bytes.fromhex(NUMS_HEX)
    
    # 7. Compute TapTweak and output key
    # Import point operations from bip_0340_reference
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
    # For cooperative path: proof = refund leaf hash
    cooperative_control = bytes([0xc0 | output_parity]) + internal_key + tapleaf_refund
    
    # For refund path: proof = cooperative leaf hash
    refund_control = bytes([0xc0 | output_parity]) + internal_key + tapleaf_cooperative
    
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
            'cooperative': {
                'script': cooperative_script.hex(),
                'control_block': cooperative_control.hex()
            },
            'refund': {
                'script': refund_script.hex(),
                'control_block': refund_control.hex()
            }
        }
    }


if __name__ == '__main__':
    print("Taproot Payment Channel Address Builder")
    print("=" * 60)
    
    # Test with known keys
    locktime = 275971
    sender_pubkey = "033f0e80e574456d8f8fa64e044b2eb72ea22eb53fe1efe3a443933aca7f8cb0e3"
    receiver_pubkey = "03a1d0fcf2ec9de675b612136e5ce70d271c21417c9d2b8aaaac138599d0717940"
    
    result = create_payment_channel_taproot_address(
        locktime=locktime,
        sender_pubkey=sender_pubkey,
        receiver_pubkey=receiver_pubkey,
        network='signet'
    )
    
    print(f"Address: {result['address']}")
    print(f"Output key: {result['output_key']}")
    print(f"Merkle root: {result['merkle_root']}")
    print(f"\nCooperative script: {result['scripts']['cooperative']['script']}")
    print(f"Cooperative control: {result['scripts']['cooperative']['control_block']}")
    print(f"\nRefund script: {result['scripts']['refund']['script']}")
    print(f"Refund control: {result['scripts']['refund']['control_block']}")
    print("\n✅ Address generation complete!")
