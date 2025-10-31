#!/usr/bin/env python3
"""
Taproot Two-Factor Authentication Address Builder

Implements Two-Factor authentication using Taproot with 2 script-path leaves:
- Leaf 1: Normal operations (User + Server, both required)
- Leaf 2: Recovery (User alone after timeout)

Tree Structure:
       Root
      /    \
  Leaf1   Leaf2
(User+Server) (User+Timeout)

Reference: TAPROOT_IMPLEMENTATION_GUIDE.md Appendix B
Based on: Working patterns from taproot_tx_builder.py and escrow_taproot.py
"""

import sys
import os
from pathlib import Path

# Prefer vendored third_party helpers to avoid external dependency
_THIRD_PARTY = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../third_party'))
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)

from bip_0340_reference import point_add, point_mul, G, lift_x, int_from_bytes, bytes_from_int
from bip_350_bech32_reference import encode
import hashlib
from typing import Dict


# NUMS point - "Nothing Up My Sleeve" for internal key
NUMS_H = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"


def tagged_hash(tag: str, data: bytes) -> bytes:
    """
    BIP-340 tagged hash.
    
    TaggedHash(tag, x) = SHA256(SHA256(tag) || SHA256(tag) || x)
    """
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def varint(n: int) -> bytes:
    """Bitcoin CompactSize varint encoding."""
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b'\xfd' + n.to_bytes(2, 'little')
    elif n <= 0xffffffff:
        return b'\xfe' + n.to_bytes(4, 'little')
    else:
        return b'\xff' + n.to_bytes(8, 'little')


def encode_script_number(n: int) -> bytes:
    """
    Encode integer as minimal script number (Bitcoin consensus rules).
    
    CRITICAL: BIP-342 requires minimal encoding in Tapscript.
    """
    if n == 0:
        return b""
    
    neg = n < 0
    n = -n if neg else n
    
    # Convert to little-endian bytes
    out = bytearray()
    while n:
        out.append(n & 0xff)
        n >>= 8
    
    # Handle sign bit
    if out[-1] & 0x80:
        # MSB is set, need extra byte for sign
        out.append(0x80 if neg else 0x00)
    elif neg:
        # MSB not set, can use it for sign
        out[-1] |= 0x80
    
    return bytes(out)


def pubkey_to_xonly(pubkey_hex: str) -> bytes:
    """
    Convert 33-byte compressed pubkey to 32-byte x-only pubkey.
    
    Args:
        pubkey_hex: 33-byte compressed pubkey (02/03 prefix)
    
    Returns:
        32-byte x-only pubkey (no prefix)
    """
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    if len(pubkey_bytes) != 33:
        raise ValueError(f"Expected 33-byte compressed pubkey, got {len(pubkey_bytes)} bytes")
    
    # Remove prefix byte, keep x-coordinate
    return pubkey_bytes[1:]


def build_normal_script(user_xonly: bytes, server_xonly: bytes) -> bytes:
    """
    Build Leaf 1: Normal operations (User + Server).
    
    Script:
        <user_xonly> OP_CHECKSIGVERIFY
        <server_xonly> OP_CHECKSIG
    
    Requires signatures from both User and Server.
    No locktime check - can be spent anytime both parties agree.
    """
    script = bytearray()
    
    # User's pubkey (32 bytes)
    script.append(0x20)  # PUSH 32 bytes
    script.extend(user_xonly)
    
    # OP_CHECKSIGVERIFY (verify User's sig, fail if invalid)
    script.append(0xad)
    
    # Server's pubkey (32 bytes)  
    script.append(0x20)  # PUSH 32 bytes
    script.extend(server_xonly)
    
    # OP_CHECKSIG (check Server's sig, push result)
    script.append(0xac)
    
    return bytes(script)


def build_recovery_script(locktime: int, user_xonly: bytes) -> bytes:
    """
    Build Leaf 2: Recovery (User alone after timeout).
    
    Script:
        <locktime> OP_CLTV OP_DROP
        <user_xonly> OP_CHECKSIG
    
    Requires:
    - Locktime to have passed
    - User's signature only
    
    This is the recovery/backup path if Server becomes unavailable.
    """
    script = bytearray()
    
    # <locktime> OP_CLTV OP_DROP
    locktime_bytes = encode_script_number(locktime)
    script.append(len(locktime_bytes))
    script.extend(locktime_bytes)
    script.append(0xb1)  # OP_CLTV
    script.append(0x75)  # OP_DROP
    
    # <user_xonly> OP_CHECKSIG
    script.append(0x20)  # PUSH 32 bytes
    script.extend(user_xonly)
    script.append(0xac)  # OP_CHECKSIG
    
    return bytes(script)


def create_twofactor_taproot_address(
    locktime: int,
    user_pubkey: str,
    server_pubkey: str,
    network: str = 'signet'
) -> Dict:
    """
    Create Taproot two-factor address with 2 script-path leaves.
    
    Args:
        locktime: Block height for recovery path
        user_pubkey: User's 33-byte compressed pubkey (hex)
        server_pubkey: Server's 33-byte compressed pubkey (hex)
        network: 'mainnet', 'testnet', 'signet', 'regtest'
    
    Returns:
        {
            'address': Bech32m address,
            'output_key': Tweaked pubkey (hex),
            'output_script': ScriptPubKey (hex),
            'internal_key': NUMS point (hex),
            'merkle_root': Root hash (hex),
            'scripts': {
                'normal': {
                    'script': Script bytes (hex),
                    'leaf_hash': TapLeaf hash (hex),
                    'control_block': Control block for spending (hex)
                },
                'recovery': {
                    'script': Script bytes (hex),
                    'leaf_hash': TapLeaf hash (hex),
                    'control_block': Control block for spending (hex)
                }
            }
        }
    """
    # Step 1: Convert pubkeys to x-only
    user_xonly = pubkey_to_xonly(user_pubkey)
    server_xonly = pubkey_to_xonly(server_pubkey)
    
    # Step 2: Build script leaves
    normal_script = build_normal_script(user_xonly, server_xonly)
    recovery_script = build_recovery_script(locktime, user_xonly)
    
    # Step 3: Compute TapLeaf hashes
    # TapLeaf = tagged_hash("TapLeaf", leaf_version || compact_size(script) || script)
    # leaf_version = 0xc0 for current tapscript version
    
    leaf_version = bytes([0xc0])
    
    normal_leaf_hash = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(normal_script)) + normal_script
    )
    
    recovery_leaf_hash = tagged_hash(
        "TapLeaf",
        leaf_version + varint(len(recovery_script)) + recovery_script
    )
    
    # Step 4: Build Merkle tree (2 leaves)
    # For 2 leaves: root = TapBranch(hash1, hash2) where hashes are sorted lexicographically
    
    if normal_leaf_hash < recovery_leaf_hash:
        merkle_root = tagged_hash(
            "TapBranch",
            normal_leaf_hash + recovery_leaf_hash
        )
    else:
        merkle_root = tagged_hash(
            "TapBranch",
            recovery_leaf_hash + normal_leaf_hash
        )
    
    # Step 5: Compute internal key (NUMS point)
    internal_key_bytes = bytes.fromhex(NUMS_H)
    internal_key_point = lift_x(int.from_bytes(internal_key_bytes, 'big'))
    
    if internal_key_point is None:
        ValueError("Invalid internal key point")
    
    # Step 6: Compute TapTweak
    # t = tagged_hash("TapTweak", internal_key || merkle_root)
    tap_tweak_hash = tagged_hash(
        "TapTweak",
        internal_key_bytes + merkle_root
    )
    tap_tweak = int.from_bytes(tap_tweak_hash, 'big')
    
    # Step 7: Compute output key
    # Q = P + t*G
    tweak_point = point_mul(G, tap_tweak)
    output_point = point_add(internal_key_point, tweak_point)
    
    if output_point is None:
        raise ValueError("Failed to compute output point")
    
    # Get x-coordinate and parity
    output_x = output_point[0]
    output_parity = output_point[1] & 1
    
    output_key_bytes = bytes_from_int(output_x)
    
    # Step 8: Build control blocks
    # Control block = leaf_version_with_parity || internal_key || merkle_proof
    # For 2-leaf tree, merkle_proof is the sibling hash
    
    # Control block for normal script (sibling = recovery_leaf_hash)
    normal_control_block = bytes([0xc0 | output_parity]) + internal_key_bytes + recovery_leaf_hash
    
    # Control block for recovery script (sibling = normal_leaf_hash)
    recovery_control_block = bytes([0xc0 | output_parity]) + internal_key_bytes + normal_leaf_hash
    
    # Step 9: Generate address
    # Taproot uses witness v1 (bech32m)
    witness_program = output_key_bytes
    
    # Bech32m encoding
    if network == 'mainnet':
        hrp = 'bc'
    elif network in ['testnet', 'testnet4']:
        hrp = 'tb'
    elif network == 'signet':
        hrp = 'tb'
    elif network == 'regtest':
        hrp = 'bcrt'
    else:
        raise ValueError(f"Unknown network: {network}")
    
    # Witness version 1 for Taproot
    address = encode(hrp, 1, witness_program)
    
    # Step 10: Build output script
    # OP_1 <32-byte-output-key>
    output_script = bytes([0x51, 0x20]) + output_key_bytes
    
    return {
        'address': address,
        'output_key': output_key_bytes.hex(),
        'output_script': output_script.hex(),
        'internal_key': internal_key_bytes.hex(),
        'merkle_root': merkle_root.hex(),
        'scripts': {
            'normal': {
                'script': normal_script.hex(),
                'leaf_hash': normal_leaf_hash.hex(),
                'control_block': normal_control_block.hex()
            },
            'recovery': {
                'script': recovery_script.hex(),
                'leaf_hash': recovery_leaf_hash.hex(),
                'control_block': recovery_control_block.hex()
            }
        }
    }


if __name__ == '__main__':
    # Test with example keys
    user_pubkey = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
    server_pubkey = "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
    
    locktime = 275840
    
    result = create_twofactor_taproot_address(
        locktime=locktime,
        user_pubkey=user_pubkey,
        server_pubkey=server_pubkey,
        network='signet'
    )
    
    print("="*80)
    print("Taproot Two-Factor Address")
    print("="*80)
    print(f"\n📍 Address: {result['address']}")
    print(f"\n🔑 Keys:")
    print(f"   Internal Key (NUMS): {result['internal_key']}")
    print(f"   Output Key: {result['output_key']}")
    print(f"\n🌳 Merkle Root: {result['merkle_root']}")
    
    print(f"\n📜 Leaf 1 - Normal Operations (User + Server):")
    print(f"   Script: {result['scripts']['normal']['script']}")
    print(f"   Leaf Hash: {result['scripts']['normal']['leaf_hash']}")
    print(f"   Control Block: {result['scripts']['normal']['control_block']}")
    
    print(f"\n📜 Leaf 2 - Recovery (User alone after timeout):")
    print(f"   Script: {result['scripts']['recovery']['script']}")
    print(f"   Leaf Hash: {result['scripts']['recovery']['leaf_hash']}")
    print(f"   Control Block: {result['scripts']['recovery']['control_block']}")
    
    print(f"\n✅ Address generation complete!")
