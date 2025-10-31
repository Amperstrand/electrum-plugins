#!/usr/bin/env python3
"""
Taproot Escrow Address Builder

Implements BIP-65 Escrow using Taproot with multiple script-path leaves.

Design: Option B - 2 Leaves with CHECKSIGADD
- Leaf 1: Normal operations (Alice + Bob)
- Leaf 2: Arbitration (Lenny + Alice OR Bob after timeout)
- Internal key: NUMS point (no key-path spending)

Tree Structure:
       Root
      /    \
  Leaf1   Leaf2
(Alice+Bob) (Lenny+1of2)

Reference: TAPROOT_ESCROW_IMPLEMENTATION_PLAN.md
"""

import sys
from pathlib import Path

# Add bitcoin-tx-tutorial to path (it's in electrum-plugins root, 3 levels up from this file)
tutorial_path = Path(__file__).parent.parent.parent.parent.parent / 'bitcoin-tx-tutorial' / 'functions'
if tutorial_path.exists():
    sys.path.insert(0, str(tutorial_path))

from bip_0340_reference import point_add, point_mul, G, lift_x
from bip_350_bech32_reference import encode
import hashlib
from typing import Dict


# NUMS point - "Nothing Up My Sleeve" for internal key
# This is the same NUMS point used in simple CLTV taproot
NUMS_H = "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"


def tagged_hash(tag: str, data: bytes) -> bytes:
    """
    BIP-340 tagged hash.
    
    TaggedHash(tag, x) = SHA256(SHA256(tag) || SHA256(tag) || x)
    """
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def ser_script(script: bytes) -> bytes:
    """Serialize script with compact size prefix."""
    n = len(script)
    if n < 0xfd:
        return bytes([n]) + script
    elif n <= 0xffff:
        return b'\xfd' + n.to_bytes(2, 'little') + script
    elif n <= 0xffffffff:
        return b'\xfe' + n.to_bytes(4, 'little') + script
    else:
        return b'\xff' + n.to_bytes(8, 'little') + script


def compact_size(n: int) -> bytes:
    """Generate compact size encoding for integers."""
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b'\xfd' + n.to_bytes(2, 'little')
    elif n <= 0xffffffff:
        return b'\xfe' + n.to_bytes(4, 'little')
    else:
        return b'\xff' + n.to_bytes(8, 'little')


def script_num_encode(n: int) -> bytes:
    """
    Encode integer as Bitcoin script number (CScriptNum).
    
    Used for locktime values in scripts.
    """
    if n == 0:
        return b''
    
    negative = n < 0
    abs_n = abs(n)
    
    # Encode as little-endian
    result = []
    while abs_n:
        result.append(abs_n & 0xff)
        abs_n >>= 8
    
    # If high bit is set, add extra byte
    if result[-1] & 0x80:
        result.append(0x80 if negative else 0x00)
    elif negative:
        result[-1] |= 0x80
    
    return bytes(result)


def build_normal_script(alice_xonly: bytes, bob_xonly: bytes) -> bytes:
    """
    Build Leaf 1: Normal operations (Alice + Bob).
    
    Script:
        <alice_xonly> OP_CHECKSIGVERIFY
        <bob_xonly> OP_CHECKSIG
    
    Requires signatures from both Alice and Bob.
    No locktime check - can be spent anytime both parties agree.
    """
    script = bytearray()
    
    # Alice's pubkey (32 bytes)
    script.append(0x20)  # PUSH 32 bytes
    script.extend(alice_xonly)
    
    # OP_CHECKSIGVERIFY (verify Alice's sig)
    script.append(0xad)
    
    # Bob's pubkey (32 bytes)  
    script.append(0x20)  # PUSH 32 bytes
    script.extend(bob_xonly)
    
    # OP_CHECKSIG (check Bob's sig, push result)
    script.append(0xac)
    
    return bytes(script)


def build_arbitration_script(
    locktime: int,
    lenny_xonly: bytes,
    alice_xonly: bytes,
    bob_xonly: bytes
) -> bytes:
    """
    Build Leaf 2: Arbitration (Lenny + Alice OR Bob after timeout).
    
    Script:
        <locktime> OP_CLTV OP_DROP
        <lenny_xonly> OP_CHECKSIGADD
        <alice_xonly> OP_CHECKSIGADD
        <bob_xonly> OP_CHECKSIGADD
        OP_2 OP_EQUAL
    
    Requires:
    - Locktime to have passed
    - Lenny's signature (always) +  at least one of Alice/Bob
    - Total of 2 valid signatures
    
    Witness stack (if Alice signs): [empty_bob, alice_sig, lenny_sig, 0, ...]
    Witness stack (if Bob signs): [bob_sig, empty_alice, lenny_sig, 0, ...]
    """
    script = bytearray()
    
    # <locktime> OP_CLTV OP_DROP
    locktime_bytes = script_num_encode(locktime)
    script.append(len(locktime_bytes))
    script.extend(locktime_bytes)
    script.append(0xb1)  # OP_CLTV
    script.append(0x75)  # OP_DROP
    
    # <lenny_xonly> OP_CHECKSIGADD (always required, adds 1)
    script.append(0x20)  # PUSH 32 bytes
    script.extend(lenny_xonly)
    script.append(0xba)  # OP_CHECKSIGADD
    
    # <alice_xonly> OP_CHECKSIGADD (optional, adds 1 if present)
    script.append(0x20)  # PUSH 32 bytes
    script.extend(alice_xonly)
    script.append(0xba)  # OP_CHECKSIGADD
    
    # <bob_xonly> OP_CHECKSIGADD (optional, adds 1 if present)
    script.append(0x20)  # PUSH 32 bytes
    script.extend(bob_xonly)
    script.append(0xba)  # OP_CHECKSIGADD
    
    # OP_2 OP_EQUAL (verify exactly 2 valid signatures)
    script.append(0x52)  # OP_2
    script.append(0x87)  # OP_EQUAL
    
    return bytes(script)


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


def create_taproot_escrow_address(
    locktime: int,
    alice_pubkey: str,
    bob_pubkey: str,
    lenny_pubkey: str,
    network: str = 'signet'
) -> Dict:
    """
    Create Taproot escrow address with 2 script-path leaves.
    
    Args:
        locktime: Block height for arbitration path
        alice_pubkey: Alice's 33-byte compressed pubkey (hex)
        bob_pubkey: Bob's 33-byte compressed pubkey (hex)
        lenny_pubkey: Lenny's 33-byte compressed pubkey (hex)
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
                'arbitration': {
                    'script': Script bytes (hex),
                    'leaf_hash': TapLeaf hash (hex),
                    'control_block': Control block for spending (hex)
                }
            }
        }
    """
    # Step 1: Convert pubkeys to x-only
    alice_xonly = pubkey_to_xonly(alice_pubkey)
    bob_xonly = pubkey_to_xonly(bob_pubkey)
    lenny_xonly = pubkey_to_xonly(lenny_pubkey)
    
    # Step 2: Build script leaves
    normal_script = build_normal_script(alice_xonly, bob_xonly)
    arbitration_script = build_arbitration_script(locktime, lenny_xonly, alice_xonly, bob_xonly)
    
    # Step 3: Compute TapLeaf hashes
    # TapLeaf = tagged_hash("TapLeaf", leaf_version || compact_size(script) || script)
    # leaf_version = 0xc0 for current tapscript version
    
    normal_leaf_hash = tagged_hash(
        "TapLeaf",
        bytes([0xc0]) + ser_script(normal_script)
    )
    
    arbitration_leaf_hash = tagged_hash(
        "TapLeaf",
        bytes([0xc0]) + ser_script(arbitration_script)
    )
    
    # Step 4: Build Merkle tree (2 leaves)
    # For 2 leaves: root = TapBranch(hash1, hash2) where hashes are sorted lexicographically
    
    if normal_leaf_hash < arbitration_leaf_hash:
        merkle_root = tagged_hash(
            "TapBranch",
            normal_leaf_hash + arbitration_leaf_hash
        )
    else:
        merkle_root = tagged_hash(
            "TapBranch",
            arbitration_leaf_hash + normal_leaf_hash
        )
    
    # Step 5: Compute internal key (NUMS point)
    internal_key_bytes = bytes.fromhex(NUMS_H)
    internal_key_point = lift_x(int.from_bytes(internal_key_bytes, 'big'))
    
    if internal_key_point is None:
        raise ValueError("Invalid internal key point")
    
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
    
    output_key_bytes = output_x.to_bytes(32, 'big')
    
    # Step 8: Build control blocks
    # Control block = leaf_version_with_parity || internal_key || merkle_proof
    # For 2-leaf tree, merkle_proof is the sibling hash
    
    # Control block for normal script (sibling = arbitration_leaf_hash)
    normal_control_block = bytes([0xc0 | output_parity]) + internal_key_bytes + arbitration_leaf_hash
    
    # Control block for arbitration script (sibling = normal_leaf_hash)
    arbitration_control_block = bytes([0xc0 | output_parity]) + internal_key_bytes + normal_leaf_hash
    
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
            'arbitration': {
                'script': arbitration_script.hex(),
                'leaf_hash': arbitration_leaf_hash.hex(),
                'control_block': arbitration_control_block.hex()
            }
        }
    }


if __name__ == '__main__':
    # Test with example keys
    alice_pubkey = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
    bob_pubkey = "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
    lenny_pubkey = "03d30199d74fb5a22d47b6e054e2f378cedacffcb89904a61d75d0dbd407143e65"
    
    locktime = 275840
    
    result = create_taproot_escrow_address(
        locktime=locktime,
        alice_pubkey=alice_pubkey,
        bob_pubkey=bob_pubkey,
        lenny_pubkey=lenny_pubkey,
        network='signet'
    )
    
    print("="*80)
    print("Taproot Escrow Address - Option B (2 Leaves)")
    print("="*80)
    print(f"\n📍 Address: {result['address']}")
    print(f"\n🔑 Keys:")
    print(f"   Internal Key (NUMS): {result['internal_key']}")
    print(f"   Output Key: {result['output_key']}")
    print(f"\n🌳 Merkle Root: {result['merkle_root']}")
    
    print(f"\n📜 Leaf 1 - Normal Operations (Alice + Bob):")
    print(f"   Script: {result['scripts']['normal']['script']}")
    print(f"   Leaf Hash: {result['scripts']['normal']['leaf_hash']}")
    print(f"   Control Block: {result['scripts']['normal']['control_block']}")
    
    print(f"\n📜 Leaf 2 - Arbitration (Lenny + 1-of-2):")
    print(f"   Script: {result['scripts']['arbitration']['script']}")
    print(f"   Leaf Hash: {result['scripts']['arbitration']['leaf_hash']}")
    print(f"   Control Block: {result['scripts']['arbitration']['control_block']}")
    
    print(f"\n✅ Address generation complete!")
