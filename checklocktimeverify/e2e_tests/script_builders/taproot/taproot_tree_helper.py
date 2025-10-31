"""
Taproot Tree Helper

Common utilities for building Taproot Taptrees with multiple script leaves.

Implements:
- TapLeaf hash computation (BIP-341)
- Merkle tree construction
- Control block generation for each leaf
- Address generation (bech32m)

Used by all Taproot script builders that need multiple script paths.
"""

from typing import List, Tuple, Dict, Any
import hashlib


def varint(n: int) -> bytes:
    """
    Encode variable-length integer (CompactSize).
    
    Bitcoin uses this encoding for all length fields.
    """
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return bytes([0xfd]) + n.to_bytes(2, 'little')
    elif n <= 0xffffffff:
        return bytes([0xfe]) + n.to_bytes(4, 'little')
    else:
        return bytes([0xff]) + n.to_bytes(8, 'little')


def tagged_hash(tag: str, msg: bytes) -> bytes:
    """
    BIP-340 tagged hash.
    
    TaggedHash(tag, msg) = SHA256(SHA256(tag) || SHA256(tag) || msg)
    """
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()


def compute_tapleaf_hash(script: bytes, leaf_version: int = 0xc0) -> bytes:
    """
    Compute TapLeaf hash for a script (BIP-341).
    
    TapLeaf = TaggedHash("TapLeaf", leaf_version || compact_size(script) || script)
    
    Args:
        script: Script bytes
        leaf_version: Leaf version (0xc0 for tapscript)
    
    Returns:
        32-byte tapleaf hash
    """
    return tagged_hash("TapLeaf", bytes([leaf_version]) + varint(len(script)) + script)


def compute_tapbranch_hash(left: bytes, right: bytes) -> bytes:
    """
    Compute TapBranch hash for two child nodes (BIP-341).
    
    TapBranch = TaggedHash("TapBranch", left || right)
    
    Nodes are sorted lexicographically before hashing.
    
    Args:
        left: Left child hash (32 bytes)
        right: Right child hash (32 bytes)
    
    Returns:
        32-byte branch hash
    """
    if left <= right:
        return tagged_hash("TapBranch", left + right)
    else:
        return tagged_hash("TapBranch", right + left)


def build_merkle_tree(leaf_hashes: List[bytes]) -> Tuple[bytes, List[List[bytes]]]:
    """
    Build Merkle tree from leaf hashes.
    
    For a 2-leaf tree:
        root = TapBranch(leaf1, leaf2)
    
    For more leaves, builds a balanced binary tree.
    
    Args:
        leaf_hashes: List of 32-byte leaf hashes
    
    Returns:
        (merkle_root, proof_paths) where proof_paths[i] is the Merkle proof for leaf i
    """
    if len(leaf_hashes) == 0:
        raise ValueError("No leaves provided")
    
    if len(leaf_hashes) == 1:
        # Single leaf: merkle root = leaf hash
        return leaf_hashes[0], [[]]
    
    # Build tree bottom-up
    levels = [leaf_hashes]
    
    while len(levels[-1]) > 1:
        current_level = levels[-1]
        next_level = []
        
        for i in range(0, len(current_level), 2):
            if i + 1 < len(current_level):
                # Pair of nodes
                branch_hash = compute_tapbranch_hash(current_level[i], current_level[i + 1])
                next_level.append(branch_hash)
            else:
                # Odd node, propagate to next level
                next_level.append(current_level[i])
        
        levels.append(next_level)
    
    merkle_root = levels[-1][0]
    
    # Build proof paths for each leaf
    proof_paths = []
    for leaf_idx in range(len(leaf_hashes)):
        proof = []
        idx = leaf_idx
        
        for level in levels[:-1]:
            # Find sibling at this level
            if idx % 2 == 0:
                # Left child, sibling is on right
                if idx + 1 < len(level):
                    sibling = level[idx + 1]
                    proof.append(sibling)
            else:
                # Right child, sibling is on left
                sibling = level[idx - 1]
                proof.append(sibling)
            
            idx //= 2
        
        proof_paths.append(proof)
    
    return merkle_root, proof_paths


def compute_taptweak(internal_key: bytes, merkle_root: bytes) -> bytes:
    """
    Compute TapTweak for internal key and merkle root (BIP-341).
    
    t = TaggedHash("TapTweak", internal_key || merkle_root)
    
    Args:
        internal_key: 32-byte x-only internal pubkey
        merkle_root: 32-byte merkle root
    
    Returns:
        32-byte tweak
    """
    return tagged_hash("TapTweak", internal_key + merkle_root)


def tweak_internal_key(internal_key: bytes, merkle_root: bytes) -> Tuple[bytes, int]:
    """
    Tweak internal key with merkle root to get output key (BIP-341).
    
    Q = P + int(t)*G where t = TapTweak(P, merkle_root)
    
    Args:
        internal_key: 32-byte x-only internal pubkey
        merkle_root: 32-byte merkle root
    
    Returns:
        (output_key, parity) where output_key is 32-byte x-only, parity is 0 or 1
    """
    from electrum_ecc import ECPubkey, ECPrivkey
    
    # Compute tweak
    tweak_hash = compute_taptweak(internal_key, merkle_root)
    tweak_int = int.from_bytes(tweak_hash, 'big')
    
    # Create internal pubkey point from x-only coordinate
    # For NUMS point, we know it's the generator G with specific x,y
    if internal_key.hex() == "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0":
        # This is the NUMS point (secp256k1 generator x-coordinate)
        internal_pub = ECPubkey.from_x_and_y(
            0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798,
            0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8
        )
    else:
        # Generic x-only pubkey (assume even y)
        raise NotImplementedError("Only NUMS internal key is currently supported")
    
    # Q = P + int(t)*G
    tweak_privkey = ECPrivkey.from_secret_scalar(tweak_int)
    tweak_point = ECPubkey(tweak_privkey.get_public_key_bytes(compressed=False))
    tweaked_pub = internal_pub + tweak_point
    
    # Extract x-only output key and parity
    output_key = tweaked_pub.x().to_bytes(32, 'big')
    parity = 0 if (tweaked_pub.y() % 2 == 0) else 1
    
    return output_key, parity


def build_control_block(
    internal_key: bytes,
    leaf_version: int,
    parity: int,
    merkle_proof: List[bytes]
) -> bytes:
    """
    Build control block for script-path spending (BIP-341).
    
    Control block = [version_and_parity] || [internal_key] || [merkle_proof...]
    
    Args:
        internal_key: 32-byte x-only internal pubkey
        leaf_version: Leaf version (0xc0 for tapscript)
        parity: Parity bit of output key (0 or 1)
        merkle_proof: List of 32-byte hashes (siblings up the tree)
    
    Returns:
        Control block bytes (33 + 32*len(merkle_proof) bytes)
    """
    version_and_parity = leaf_version | parity
    control_block = bytes([version_and_parity]) + internal_key
    
    for proof_hash in merkle_proof:
        control_block += proof_hash
    
    return control_block


def build_taproot_address(
    scripts: List[bytes],
    internal_key: bytes,
    leaf_version: int = 0xc0
) -> Dict[str, Any]:
    """
    Build Taproot address from scripts and internal key.
    
    Args:
        scripts: List of script bytes (one per leaf)
        internal_key: 32-byte x-only internal pubkey (usually NUMS)
        leaf_version: Leaf version (0xc0 for tapscript)
    
    Returns:
        dict with:
            - address: bech32m address
            - output_script: witness program (OP_1 <32-byte output key>)
            - control_blocks: list of control blocks (one per script)
            - merkle_root: 32-byte merkle root
            - output_key: 32-byte x-only output key
    """
    # Compute leaf hashes
    leaf_hashes = [compute_tapleaf_hash(script, leaf_version) for script in scripts]
    
    # Build merkle tree
    merkle_root, proof_paths = build_merkle_tree(leaf_hashes)
    
    # Tweak internal key
    output_key, parity = tweak_internal_key(internal_key, merkle_root)
    
    # Build control blocks for each script
    control_blocks = []
    for proof in proof_paths:
        control_block = build_control_block(internal_key, leaf_version, parity, proof)
        control_blocks.append(control_block.hex())
    
    # Create output script (witness v1 = OP_1 <32-byte output key>)
    output_script = bytes([0x51, 0x20]) + output_key
    
    # Create bech32m address
    from electrum.bitcoin import hash_to_segwit_addr
    address = hash_to_segwit_addr(output_key, witver=1)
    
    return {
        'address': address,
        'output_script': output_script.hex(),
        'control_blocks': control_blocks,
        'merkle_root': merkle_root.hex(),
        'output_key': output_key.hex(),
    }

