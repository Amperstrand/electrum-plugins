"""
Generic Taproot Tree Builder

Mirrors Bitcoin Core's TaprootBuilder class for constructing Taproot Merkle trees.

Reference: bitcoin/src/script/signingprovider.{h,cpp}
- TaprootBuilder class (lines 49-130 in .h)
- Add(), Finalize(), Combine(), Insert() methods (lines 431-494 in .cpp)

This builder:
- Takes scripts at arbitrary depths in DFS order
- Builds Merkle tree automatically
- Computes control blocks for each leaf
- Returns complete spending data

Usage:
    builder = TaprootTreeBuilder()
    builder.add(depth=1, script_a)  # Leaf at depth 1
    builder.add(depth=1, script_b)  # Leaf at depth 1  
    output = builder.finalize(internal_key)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set
from electrum import constants
from electrum.bitcoin import hash_to_segwit_addr

# Import existing helpers
from .taproot_utils import (
    NUMS_H,
    compute_tapleaf_hash,
    compute_tapbranch_hash,
)
from .taproot_constants import (
    TAPSCRIPT_LEAF_VERSION,
    OP_WITNESS_V1,
    OP_PUSH_32,
    make_control_block_prefix,
)


@dataclass
class LeafInfo:
    """
    Metadata about a leaf in the Merkle tree.
    
    Mirrors Bitcoin Core's TaprootBuilder::LeafInfo struct.
    """
    script: bytes
    leaf_version: int
    merkle_branch: List[bytes] = field(default_factory=list)  # Bottom-to-top siblings


@dataclass
class NodeInfo:
    """
    Node in the Merkle tree.
    
    Mirrors Bitcoin Core's TaprootBuilder::NodeInfo struct.
    """
    hash: bytes  # 32-byte node hash
    leaves: List[LeafInfo] = field(default_factory=list)  # Leaves under this node


@dataclass
class TaprootSpendData:
    """
    Complete spending information for a Taproot output.
    
    Mirrors Bitcoin Core's TaprootSpendData struct.
    """
    internal_key: bytes  # 32-byte x-only
    merkle_root: bytes   # 32-byte root (or zeros if key-path only)
    scripts: Dict[Tuple[bytes, int], Set[bytes]] = field(default_factory=dict)  # (script, leaf_ver) → control_blocks


@dataclass
class TaprootOutput:
    """Complete Taproot output."""
    address: str
    output_key: bytes
    output_script: bytes  # OP_1 <32-byte output_key>
    spend_data: TaprootSpendData


class TaprootTreeBuilder:
    """
    Generic Taproot tree builder - mirrors Bitcoin Core's TaprootBuilder.
    
    Builds Taproot Merkle trees from scripts at specified depths in DFS order.
    Automatically computes control blocks and spending data.
    
    Example - 2-leaf balanced tree:
        builder = TaprootTreeBuilder()
        builder.add(depth=1, script_a)
        builder.add(depth=1, script_b)
        output = builder.finalize(internal_key)
    
    Example - 3-leaf unbalanced tree:
        builder = TaprootTreeBuilder()
        builder.add(depth=2, script_a)  # Left-left leaf
        builder.add(depth=2, script_b)  # Left-right leaf
        builder.add(depth=1, script_c)  # Right leaf
        output = builder.finalize(internal_key)
    
    Depth convention (from Bitcoin Core):
        - Root node = depth 0
        - Children = parent depth + 1
        - Leaves ≥ depth 1
    
    Reference: bitcoin/src/script/signingprovider.cpp lines 431-494
    """
    
    def __init__(self):
        """Initialize empty tree builder."""
        self.m_branch: List[Optional[NodeInfo]] = []
        self.m_valid: bool = True
        self.m_internal_key: Optional[bytes] = None
        self.m_output_key: Optional[bytes] = None
        self.m_parity: Optional[int] = None
    
    def add(
        self, 
        depth: int, 
        script: bytes, 
        leaf_version: int = TAPSCRIPT_LEAF_VERSION, 
        track: bool = True
    ) -> 'TaprootTreeBuilder':
        """
        Add leaf at specified depth (must be in DFS order).
        
        Args:
            depth: Depth in tree (root=0, leaves≥1)
            script: Script bytes
            leaf_version: Leaf version (TAPSCRIPT_LEAF_VERSION for tapscript)
            track: Whether to track leaf for control block generation
        
        Returns:
            self (for chaining)
        
        Example:
            builder.add(1, script_a).add(1, script_b)
        
        Reference: bitcoin/src/script/signingprovider.cpp lines 431-442
        """
        if not self.m_valid:
            return self
        
        # Compute leaf hash
        leaf_hash = compute_tapleaf_hash(script, leaf_version)
        
        # Create node with leaf metadata
        node = NodeInfo(
            hash=leaf_hash,
            leaves=[LeafInfo(script, leaf_version, [])] if track else []
        )
        
        # Insert at depth and propagate up
        self._insert(node, depth)
        
        return self
    
    def finalize(
        self, 
        internal_key: bytes, 
        network: str = 'signet'
    ) -> TaprootOutput:
        """
        Finalize tree and compute output key.
        
        Args:
            internal_key: 32-byte x-only internal pubkey (usually NUMS point)
            network: 'mainnet', 'testnet', 'signet', or 'regtest'
        
        Returns:
            TaprootOutput with address, output_key, and spend_data
        
        Raises:
            AssertionError: If tree is not complete
        
        Reference: bitcoin/src/script/signingprovider.cpp lines 454-465
        """
        assert self.is_complete(), "Tree is not complete - check DFS order and depths"
        
        self.m_internal_key = internal_key
        
        # Get merkle root (empty bytes if key-path only, per BIP-341)
        merkle_root = self.m_branch[0].hash if self.m_branch else b''
        
        # Tweak internal key to get output key
        self.m_output_key, self.m_parity = self._tweak_key(internal_key, merkle_root)
        
        # Build spend data
        spend_data = self._get_spend_data()
        
        # Create output script (OP_1 <32-byte output_key>)
        output_script = bytes([OP_WITNESS_V1, OP_PUSH_32]) + self.m_output_key
        
        # Create bech32m address
        address = self._to_bech32m(self.m_output_key, network)
        
        return TaprootOutput(
            address=address,
            output_key=self.m_output_key,
            output_script=output_script,
            spend_data=spend_data
        )
    
    def is_valid(self) -> bool:
        """Check if builder is in valid state."""
        return self.m_valid
    
    def is_complete(self) -> bool:
        """
        Check if tree is complete (Huffman tree or empty).
        
        A tree is complete when:
        - m_branch is empty (key-path only), OR
        - m_branch has exactly 1 entry (root node)
        
        Reference: bitcoin/src/script/signingprovider.h line 126
        """
        return self.m_valid and (
            len(self.m_branch) == 0 or 
            (len(self.m_branch) == 1 and self.m_branch[0] is not None)
        )
    
    def _insert(self, node: NodeInfo, depth: int):
        """
        Insert node at depth and propagate up.
        
        This is the core algorithm that builds the Merkle tree incrementally
        in DFS order. It maintains the m_branch invariant where m_branch[i]
        represents a complete subtree at depth i.
        
        Algorithm (mirrors Bitcoin Core exactly):
        1. Validate depth (can't insert at lower depth while deeper branch unfinished)
        2. While m_branch[depth] exists: combine and propagate up (decrement depth)
        3. Resize m_branch and place node at final depth
        
        Reference: bitcoin/src/script/signingprovider.cpp lines 382-406
        """
        if not self.m_valid:
            return
        
        # Validate depth (Bitcoin Core line 384)
        # We cannot insert a leaf at a lower depth while a deeper branch is unfinished.
        # Doing so would mean the Add() invocations do not correspond to a DFS traversal.
        if depth + 1 < len(self.m_branch):
            self.m_valid = False
            return
        
        # As long as an entry in the branch exists at the specified depth,
        # combine it and propagate up (Bitcoin Core lines 392-399)
        # The 'node' variable is overwritten here with the newly combined node.
        # 
        # CRITICAL: m_branch is maintained such that there are no trailing None entries
        # (Bitcoin Core invariant, see signingprovider.h line 100). When we're in this loop,
        # depth is always the last index in m_branch (because depth >= len(m_branch) initially,
        # and we only decrement depth after removing the last entry). So pop() removes the
        # entry at depth, matching Bitcoin Core's pop_back().
        while self.m_valid and len(self.m_branch) > depth and self.m_branch[depth] is not None:
            # Combine with existing node at this depth
            node = self._combine(node, self.m_branch[depth])
            # Remove the entry at depth (which is the last entry, so pop() works)
            # This matches Bitcoin Core's pop_back() behavior
            self.m_branch.pop()
            
            # Can't propagate further up than the root
            if depth == 0:
                self.m_valid = False
                return
            
            # Decrement depth and continue loop (will check depth-1 next iteration)
            depth -= 1
        
        # Make sure the branch is big enough to place the new node (Bitcoin Core lines 400-404)
        if self.m_valid:
            # Resize to depth+1 if needed
            while len(self.m_branch) <= depth:
                self.m_branch.append(None)
            
            # Place node at final depth (should be empty now)
            assert self.m_branch[depth] is None, f"Slot at depth {depth} should be empty"
            self.m_branch[depth] = node
    
    @staticmethod
    def _combine(left: NodeInfo, right: NodeInfo) -> NodeInfo:
        """
        Combine two child nodes into parent node.
        
        Algorithm:
        1. Compute branch hash (lexicographically sorted)
        2. Merge leaves from both children
        3. Append sibling hash to each leaf's merkle_branch
        
        The merkle_branch grows from bottom to top as we combine nodes.
        Each leaf remembers all sibling hashes on the path to the root.
        
        Reference: bitcoin/src/script/signingprovider.cpp lines ~380-395
        (Note: Exact implementation inferred from Bitcoin Core behavior)
        
        Args:
            left: Left child node
            right: Right child node
        
        Returns:
            Combined parent node
        """
        # Compute branch hash (lexicographically sorted)
        branch_hash = compute_tapbranch_hash(left.hash, right.hash)
        
        # Merge leaves from both children
        combined_leaves = []
        
        # For each leaf from left child: append right hash to its merkle_branch
        for leaf in left.leaves:
            new_leaf = LeafInfo(
                script=leaf.script,
                leaf_version=leaf.leaf_version,
                merkle_branch=leaf.merkle_branch + [right.hash]
            )
            combined_leaves.append(new_leaf)
        
        # For each leaf from right child: append left hash to its merkle_branch
        for leaf in right.leaves:
            new_leaf = LeafInfo(
                script=leaf.script,
                leaf_version=leaf.leaf_version,
                merkle_branch=leaf.merkle_branch + [left.hash]
            )
            combined_leaves.append(new_leaf)
        
        return NodeInfo(
            hash=branch_hash,
            leaves=combined_leaves
        )
    
    def _get_spend_data(self) -> TaprootSpendData:
        """
        Build TaprootSpendData with control blocks for each leaf.
        
        Reference: bitcoin/src/script/signingprovider.cpp lines 467-494
        
        Returns:
            TaprootSpendData with internal_key, merkle_root, and control blocks
        """
        assert self.is_complete()
        assert self.m_output_key is not None
        
        merkle_root = self.m_branch[0].hash if self.m_branch else b''
        
        spd = TaprootSpendData(
            internal_key=self.m_internal_key,
            merkle_root=merkle_root,
            scripts={}
        )
        
        if self.m_branch:
            # Build control block for each tracked leaf
            for leaf in self.m_branch[0].leaves:
                control_block = self._build_control_block(
                    self.m_internal_key,
                    leaf.leaf_version,
                    self.m_parity,
                    leaf.merkle_branch
                )
                
                # Add to scripts dict (key = (script, leaf_version))
                key = (leaf.script, leaf.leaf_version)
                if key not in spd.scripts:
                    spd.scripts[key] = set()
                spd.scripts[key].add(control_block)
        
        return spd
    
    @staticmethod
    def _build_control_block(
        internal_key: bytes,
        leaf_version: int,
        parity: int,
        merkle_branch: List[bytes]
    ) -> bytes:
        """
        Build control block for script-path spending.
        
        Control block structure (BIP-341):
            [0]     = leaf_version | parity
            [1..32] = internal_key
            [33+]   = merkle_branch (32 bytes per node, bottom-to-top)
        
        Args:
            internal_key: 32-byte x-only internal pubkey
            leaf_version: Leaf version (TAPSCRIPT_LEAF_VERSION for tapscript)
            parity: Parity bit of output key (0 or 1)
            merkle_branch: List of 32-byte hashes (bottom-to-top siblings)
        
        Returns:
            Control block bytes (33 + 32*len(merkle_branch) bytes)
        """
        # Byte 0: leaf_version | parity
        version_and_parity = make_control_block_prefix(leaf_version, parity)
        control_block = bytes([version_and_parity]) + internal_key
        
        # Bytes 33+: merkle_branch (already in bottom-to-top order)
        for sibling_hash in merkle_branch:
            control_block += sibling_hash
        
        return control_block
    
    @staticmethod
    def _tweak_key(internal_key: bytes, merkle_root: bytes) -> Tuple[bytes, int]:
        """
        Tweak internal key with merkle root to get output key.
        
        Q = P + int(t)*G where t = TapTweak(P, merkle_root)
        
        Uses Electrum's native taproot_tweak_pubkey for correct ECC operations.
        
        Args:
            internal_key: 32-byte x-only internal pubkey
            merkle_root: 32-byte merkle root
        
        Returns:
            (output_key, parity) where output_key is 32-byte x-only, parity is 0 or 1
        """
        from electrum.bitcoin import taproot_tweak_pubkey
        
        # Use Electrum's native implementation
        parity, output_key = taproot_tweak_pubkey(internal_key, merkle_root)
        return output_key, parity
    
    @staticmethod
    def _to_bech32m(output_key: bytes, network: str) -> str:
        """
        Convert output key to bech32m address.
        
        Args:
            output_key: 32-byte x-only output key
            network: 'mainnet', 'testnet', 'signet', or 'regtest'
        
        Returns:
            Bech32m address
        """
        # Set network for address generation
        net = constants.BitcoinMainnet
        if network in ('testnet', 'testnet4'):
            net = constants.BitcoinTestnet
        elif network == 'signet':
            net = constants.BitcoinSignet
        elif network == 'regtest':
            net = constants.BitcoinRegtest
        
        return hash_to_segwit_addr(output_key, witver=1, net=net)


if __name__ == '__main__':
    print("TaprootTreeBuilder - Bitcoin Core Compatible Implementation")
    print("=" * 70)
    
    # Test with 2-leaf balanced tree
    from .taproot_script_helpers import build_cltv_single_sig_leaf, build_2of2_leaf
    
    # Example keys
    pubkey1 = bytes.fromhex("02" + "a" * 64)[:33]  # Compressed pubkey
    pubkey2 = bytes.fromhex("02" + "b" * 64)[:33]
    
    # Convert to x-only
    pubkey1_xonly = pubkey1[1:]
    pubkey2_xonly = pubkey2[1:]
    
    # Build scripts
    script_a = build_cltv_single_sig_leaf(275948, pubkey1_xonly)
    script_b = build_2of2_leaf(pubkey1_xonly, pubkey2_xonly)
    
    # Build tree
    builder = TaprootTreeBuilder()
    builder.add(depth=1, script=script_a)
    builder.add(depth=1, script=script_b)
    
    # Finalize
    internal_key = bytes.fromhex(NUMS_H)
    output = builder.finalize(internal_key, network='signet')
    
    print(f"Address: {output.address}")
    print(f"Output key: {output.output_key.hex()}")
    print(f"Merkle root: {output.spend_data.merkle_root.hex()}")
    print(f"Scripts: {len(output.spend_data.scripts)}")
    print("\n✅ TaprootTreeBuilder test complete!")
