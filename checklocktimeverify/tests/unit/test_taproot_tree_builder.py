"""
Unit tests for TaprootTreeBuilder

Validates against Bitcoin Core test vectors from bip341_wallet_vectors.json
to ensure our implementation matches Core exactly.

Reference: bitcoin/src/test/script_standard_tests.cpp lines 453-488
"""

import pytest
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from cltv_lib.builders.taproot.taproot_tree_builder import (
    TaprootTreeBuilder,
    TaprootOutput,
    TaprootSpendData
)


# Path to Bitcoin Core test vectors
BITCOIN_CORE_VECTORS = Path(__file__).parent.parent.parent / "bitcoin" / "src" / "test" / "data" / "bip341_wallet_vectors.json"


def parse_script_tree(node: Any, depth: int = 0) -> List[Tuple[int, bytes, int]]:
    """
    Parse Bitcoin Core scriptTree structure into DFS-ordered list of (depth, script, leaf_version).
    
    Bitcoin Core format:
    - Object: {"id": 0, "script": "hex", "leafVersion": 192} = leaf
    - Array: [left, right] = branch
    
    Returns list of (depth, script_bytes, leaf_version) in DFS order.
    
    Reference: bitcoin/src/test/script_standard_tests.cpp lines 465-478
    """
    result = []
    
    if node is None:
        return result
    
    if isinstance(node, dict):
        # Leaf node
        script_hex = node["script"]
        script_bytes = bytes.fromhex(script_hex)
        leaf_version = node.get("leafVersion", 192)
        result.append((depth, script_bytes, leaf_version))
    elif isinstance(node, list):
        # Branch node - recursively parse children
        if len(node) >= 1:
            result.extend(parse_script_tree(node[0], depth + 1))
        if len(node) >= 2:
            result.extend(parse_script_tree(node[1], depth + 1))
    
    return result


def load_test_vectors() -> List[Dict[str, Any]]:
    """Load Bitcoin Core test vectors from JSON file."""
    if not BITCOIN_CORE_VECTORS.exists():
        pytest.skip(f"Bitcoin Core test vectors not found at {BITCOIN_CORE_VECTORS}")
    
    with open(BITCOIN_CORE_VECTORS, 'r') as f:
        data = json.load(f)
    
    return data.get("scriptPubKey", [])


class TestTaprootTreeBuilder:
    """Tests for TaprootTreeBuilder against Bitcoin Core vectors"""
    
    @pytest.fixture
    def test_vectors(self):
        """Load Bitcoin Core test vectors"""
        return load_test_vectors()
    
    def test_key_path_only(self, test_vectors):
        """Test key-path only (no scripts) - first vector"""
        vec = test_vectors[0]
        
        # Key-path only has scriptTree = null
        assert vec["given"]["scriptTree"] is None
        
        internal_key = bytes.fromhex(vec["given"]["internalPubkey"])
        
        builder = TaprootTreeBuilder()
        # No scripts added
        output = builder.finalize(internal_key, network='mainnet')
        
        # Verify merkle root is empty (key-path only, per BIP-341)
        assert output.spend_data.merkle_root == b''
        
        # Verify output key matches Core
        expected_output_key = bytes.fromhex(vec["intermediary"]["tweakedPubkey"])
        assert output.output_key == expected_output_key, \
            f"Output key mismatch: got {output.output_key.hex()}, expected {expected_output_key.hex()}"
        
        # Verify address matches Core
        expected_address = vec["expected"]["bip350Address"]
        assert output.address == expected_address, \
            f"Address mismatch: got {output.address}, expected {expected_address}"
        
        # Verify scriptPubKey matches Core
        expected_script_pubkey = bytes.fromhex(vec["expected"]["scriptPubKey"])
        assert output.output_script == expected_script_pubkey, \
            f"ScriptPubKey mismatch: got {output.output_script.hex()}, expected {expected_script_pubkey.hex()}"
    
    def test_single_leaf(self, test_vectors):
        """Test single-leaf tree - second vector"""
        vec = test_vectors[1]
        
        internal_key = bytes.fromhex(vec["given"]["internalPubkey"])
        script_tree = vec["given"]["scriptTree"]
        
        # Parse script tree into DFS order
        leaves = parse_script_tree(script_tree, depth=0)
        assert len(leaves) == 1
        
        depth, script, leaf_version = leaves[0]
        
        # Build tree
        builder = TaprootTreeBuilder()
        builder.add(depth=depth, script=script, leaf_version=leaf_version)
        output = builder.finalize(internal_key, network='mainnet')
        
        # Verify leaf hash matches Core
        expected_leaf_hash = bytes.fromhex(vec["intermediary"]["leafHashes"][0])
        from cltv_lib.builders.taproot.taproot_utils import compute_tapleaf_hash
        actual_leaf_hash = compute_tapleaf_hash(script, leaf_version)
        assert actual_leaf_hash == expected_leaf_hash, \
            f"Leaf hash mismatch: got {actual_leaf_hash.hex()}, expected {expected_leaf_hash.hex()}"
        
        # Verify merkle root matches Core
        expected_merkle_root = bytes.fromhex(vec["intermediary"]["merkleRoot"])
        assert output.spend_data.merkle_root == expected_merkle_root, \
            f"Merkle root mismatch: got {output.spend_data.merkle_root.hex()}, expected {expected_merkle_root.hex()}"
        
        # Verify output key matches Core
        expected_output_key = bytes.fromhex(vec["intermediary"]["tweakedPubkey"])
        assert output.output_key == expected_output_key, \
            f"Output key mismatch: got {output.output_key.hex()}, expected {expected_output_key.hex()}"
        
        # Verify address matches Core
        expected_address = vec["expected"]["bip350Address"]
        assert output.address == expected_address, \
            f"Address mismatch: got {output.address}, expected {expected_address}"
        
        # Verify control block matches Core
        expected_control_blocks = vec["expected"]["scriptPathControlBlocks"]
        assert len(expected_control_blocks) == 1
        
        # Get control block from our output (using safe .get() pattern)
        script_key = (script, leaf_version)
        our_control_blocks = output.spend_data.scripts.get(script_key, set())
        assert len(our_control_blocks) == 1, f"Control block not found for script key {script_key}"
        
        our_control_block = list(our_control_blocks)[0]
        expected_control_block = bytes.fromhex(expected_control_blocks[0])
        
        assert our_control_block == expected_control_block, \
            f"Control block mismatch:\n  got:      {our_control_block.hex()}\n  expected: {expected_control_block.hex()}"
    
    def test_two_leaf_balanced(self, test_vectors):
        """Test 2-leaf balanced tree - fourth vector"""
        vec = test_vectors[3]  # Index 3 = fourth vector (0-indexed)
        
        internal_key = bytes.fromhex(vec["given"]["internalPubkey"])
        script_tree = vec["given"]["scriptTree"]
        
        # Parse script tree into DFS order
        leaves = parse_script_tree(script_tree, depth=0)
        assert len(leaves) == 2, f"Expected 2 leaves, got {len(leaves)}"
        
        # Build tree
        builder = TaprootTreeBuilder()
        for depth, script, leaf_version in leaves:
            builder.add(depth=depth, script=script, leaf_version=leaf_version)
        
        output = builder.finalize(internal_key, network='mainnet')
        
        # Verify leaf hashes match Core
        expected_leaf_hashes = [bytes.fromhex(h) for h in vec["intermediary"]["leafHashes"]]
        from cltv_lib.builders.taproot.taproot_utils import compute_tapleaf_hash
        
        for i, (depth, script, leaf_version) in enumerate(leaves):
            actual_leaf_hash = compute_tapleaf_hash(script, leaf_version)
            assert actual_leaf_hash == expected_leaf_hashes[i], \
                f"Leaf {i} hash mismatch: got {actual_leaf_hash.hex()}, expected {expected_leaf_hashes[i].hex()}"
        
        # Verify merkle root matches Core
        expected_merkle_root = bytes.fromhex(vec["intermediary"]["merkleRoot"])
        assert output.spend_data.merkle_root == expected_merkle_root, \
            f"Merkle root mismatch: got {output.spend_data.merkle_root.hex()}, expected {expected_merkle_root.hex()}"
        
        # Verify output key matches Core
        expected_output_key = bytes.fromhex(vec["intermediary"]["tweakedPubkey"])
        assert output.output_key == expected_output_key, \
            f"Output key mismatch: got {output.output_key.hex()}, expected {expected_output_key.hex()}"
        
        # Verify address matches Core
        expected_address = vec["expected"]["bip350Address"]
        assert output.address == expected_address, \
            f"Address mismatch: got {output.address}, expected {expected_address}"
        
        # Verify control blocks match Core
        expected_control_blocks = vec["expected"]["scriptPathControlBlocks"]
        assert len(expected_control_blocks) == 2
        
        # Verify each script has a control block (using safe .get() pattern)
        for depth, script, leaf_version in leaves:
            script_key = (script, leaf_version)
            our_control_blocks = output.spend_data.scripts.get(script_key, set())
            assert len(our_control_blocks) == 1, \
                f"Control block not found for script {script.hex()[:20]}..."
            
            our_control_block = list(our_control_blocks)[0]
            
            # Find matching expected control block
            expected_control_block = None
            for expected_cb_hex in expected_control_blocks:
                expected_cb = bytes.fromhex(expected_cb_hex)
                # Control blocks should match (same internal key, same merkle branch)
                if our_control_block == expected_cb:
                    expected_control_block = expected_cb
                    break
            
            assert expected_control_block is not None, \
                f"Control block for script {script.hex()[:20]}... not found in expected list:\n" \
                f"  our:      {our_control_block.hex()}\n" \
                f"  expected: {[cb.hex() for cb in expected_control_blocks]}"
    
    def test_three_leaf_unbalanced(self, test_vectors):
        """Test 3-leaf unbalanced tree - sixth vector"""
        vec = test_vectors[5]  # Index 5 = sixth vector
        
        internal_key = bytes.fromhex(vec["given"]["internalPubkey"])
        script_tree = vec["given"]["scriptTree"]
        
        # Parse script tree into DFS order
        leaves = parse_script_tree(script_tree, depth=0)
        assert len(leaves) == 3, f"Expected 3 leaves, got {len(leaves)}"
        
        # Build tree
        builder = TaprootTreeBuilder()
        for depth, script, leaf_version in leaves:
            builder.add(depth=depth, script=script, leaf_version=leaf_version)
        
        output = builder.finalize(internal_key, network='mainnet')
        
        # Verify leaf hashes match Core
        expected_leaf_hashes = [bytes.fromhex(h) for h in vec["intermediary"]["leafHashes"]]
        from cltv_lib.builders.taproot.taproot_utils import compute_tapleaf_hash
        
        for i, (depth, script, leaf_version) in enumerate(leaves):
            actual_leaf_hash = compute_tapleaf_hash(script, leaf_version)
            assert actual_leaf_hash == expected_leaf_hashes[i], \
                f"Leaf {i} hash mismatch: got {actual_leaf_hash.hex()}, expected {expected_leaf_hashes[i].hex()}"
        
        # Verify merkle root matches Core
        expected_merkle_root = bytes.fromhex(vec["intermediary"]["merkleRoot"])
        assert output.spend_data.merkle_root == expected_merkle_root, \
            f"Merkle root mismatch: got {output.spend_data.merkle_root.hex()}, expected {expected_merkle_root.hex()}"
        
        # Verify output key matches Core
        expected_output_key = bytes.fromhex(vec["intermediary"]["tweakedPubkey"])
        assert output.output_key == expected_output_key, \
            f"Output key mismatch: got {output.output_key.hex()}, expected {expected_output_key.hex()}"
        
        # Verify address matches Core
        expected_address = vec["expected"]["bip350Address"]
        assert output.address == expected_address, \
            f"Address mismatch: got {output.address}, expected {expected_address}"
        
        # Verify control blocks match Core
        expected_control_blocks = vec["expected"]["scriptPathControlBlocks"]
        assert len(expected_control_blocks) == 3
        
        # Verify each script has a control block (using safe .get() pattern)
        for depth, script, leaf_version in leaves:
            script_key = (script, leaf_version)
            our_control_blocks = output.spend_data.scripts.get(script_key, set())
            assert len(our_control_blocks) == 1, \
                f"Control block not found for script {script.hex()[:20]}..."
            
            our_control_block = list(our_control_blocks)[0]
            
            # Find matching expected control block
            expected_control_block = None
            for expected_cb_hex in expected_control_blocks:
                expected_cb = bytes.fromhex(expected_cb_hex)
                if our_control_block == expected_cb:
                    expected_control_block = expected_cb
                    break
            
            assert expected_control_block is not None, \
                f"Control block for script {script.hex()[:20]}... not found in expected list:\n" \
                f"  our:      {our_control_block.hex()}\n" \
                f"  expected: {[cb.hex() for cb in expected_control_blocks]}"
    
    def test_all_vectors(self, test_vectors):
        """Test all scriptPubKey vectors from Bitcoin Core"""
        # Skip key-path only (tested separately)
        script_vectors = [v for v in test_vectors if v["given"]["scriptTree"] is not None]
        
        for idx, vec in enumerate(script_vectors):
            internal_key = bytes.fromhex(vec["given"]["internalPubkey"])
            script_tree = vec["given"]["scriptTree"]
            
            # Parse script tree into DFS order
            leaves = parse_script_tree(script_tree, depth=0)
            
            # Build tree
            builder = TaprootTreeBuilder()
            for depth, script, leaf_version in leaves:
                builder.add(depth=depth, script=script, leaf_version=leaf_version)
            
            output = builder.finalize(internal_key, network='mainnet')
            
            # Verify merkle root matches Core
            expected_merkle_root = bytes.fromhex(vec["intermediary"]["merkleRoot"])
            assert output.spend_data.merkle_root == expected_merkle_root, \
                f"Vector {idx}: Merkle root mismatch: got {output.spend_data.merkle_root.hex()}, expected {expected_merkle_root.hex()}"
            
            # Verify output key matches Core
            expected_output_key = bytes.fromhex(vec["intermediary"]["tweakedPubkey"])
            assert output.output_key == expected_output_key, \
                f"Vector {idx}: Output key mismatch: got {output.output_key.hex()}, expected {expected_output_key.hex()}"
            
            # Verify address matches Core
            expected_address = vec["expected"]["bip350Address"]
            assert output.address == expected_address, \
                f"Vector {idx}: Address mismatch: got {output.address}, expected {expected_address}"


class TestTaprootTreeBuilderBasic:
    """Basic functionality tests for TaprootTreeBuilder"""
    
    def test_empty_tree(self):
        """Test key-path only (empty tree)"""
        from cltv_lib.builders.taproot.taproot_utils import NUMS_H
        
        internal_key = bytes.fromhex(NUMS_H)
        builder = TaprootTreeBuilder()
        
        assert builder.is_valid()
        assert builder.is_complete()  # Empty tree (m_branch=[]) is complete per Bitcoin Core
        
        output = builder.finalize(internal_key, network='signet')
        
        assert output.spend_data.merkle_root == b''  # Key-path only uses empty merkle root
        assert len(output.spend_data.scripts) == 0
        assert output.address.startswith('tb1p')  # Signet bech32m
    
    def test_single_leaf_basic(self):
        """Test basic single-leaf tree"""
        from cltv_lib.builders.taproot.taproot_utils import NUMS_H
        
        internal_key = bytes.fromhex(NUMS_H)
        script = bytes([0x51])  # OP_1
        
        builder = TaprootTreeBuilder()
        builder.add(depth=0, script=script)  # Single leaf at root depth
        
        assert builder.is_valid()
        assert builder.is_complete()  # Single leaf at root makes tree complete
        
        output = builder.finalize(internal_key, network='signet')
        
        assert output.spend_data.merkle_root != bytes(32)
        assert len(output.spend_data.scripts) == 1
        assert (script, 0xc0) in output.spend_data.scripts
        assert output.address.startswith('tb1p')
    
    def test_two_leaf_basic(self):
        """Test basic 2-leaf balanced tree"""
        from cltv_lib.builders.taproot.taproot_utils import NUMS_H
        
        internal_key = bytes.fromhex(NUMS_H)
        script_a = bytes([0x51])  # OP_1
        script_b = bytes([0x52])  # OP_2
        
        builder = TaprootTreeBuilder()
        builder.add(depth=1, script=script_a)
        builder.add(depth=1, script=script_b)
        
        assert builder.is_valid()
        assert builder.is_complete()
        
        output = builder.finalize(internal_key, network='signet')
        
        assert output.spend_data.merkle_root != bytes(32)
        assert len(output.spend_data.scripts) == 2
        assert (script_a, 0xc0) in output.spend_data.scripts
        assert (script_b, 0xc0) in output.spend_data.scripts
        assert output.address.startswith('tb1p')
        
        # Verify both control blocks have merkle branches (using safe .get() pattern)
        for script_key in output.spend_data.scripts:
            control_blocks = output.spend_data.scripts.get(script_key, set())
            assert len(control_blocks) == 1, f"Control block not found for key {script_key}"
            control_block = list(control_blocks)[0]
            # Control block should be 33 (version+key) + 32 (merkle branch) = 65 bytes
            assert len(control_block) == 65

