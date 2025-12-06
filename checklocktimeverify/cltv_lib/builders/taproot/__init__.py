"""
Taproot Utilities and Helpers

Provides Taproot (SegWit v1) utilities for script building and sighash computation.
Uses 32-byte x-only public keys.

For Taproot address generation, use the unified builder:
    from cltv_lib.builders.unified import build_contract
    result = build_contract('escrow', params, output_type='taproot', network='signet')

Helper modules:
- taproot_tree_builder: Bitcoin Core-aligned Taproot tree construction
- taproot_script_helpers: Script building utilities
- taproot_sighash_builder: BIP-341 sighash computation
- taproot_utils: Core utilities (tagged hash, tree hashes, etc.)
"""

from .taproot_sighash_builder import (
    compute_taproot_sighash,
    compute_taproot_sighash_simple,
    compute_bip341_sighash
)

# Import tree hash functions from taproot_utils
from .taproot_utils import compute_tapleaf_hash

# Import TaprootTreeBuilder for use by generic.py
from .taproot_tree_builder import TaprootTreeBuilder

# Import Taproot constants for external use
from .taproot_constants import (
    # Opcodes
    OP_CHECKSIGADD,
    # Witness versions
    WITNESS_V0,
    WITNESS_V1,
    OP_WITNESS_V0,
    OP_WITNESS_V1,
    # Leaf versions
    TAPSCRIPT_LEAF_VERSION,
    DEFAULT_LEAF_VERSION,
    # Push opcodes
    OP_PUSH_32,
    OP_PUSH_33,
    # Helper functions
    make_witness_v0_scriptpubkey,
    make_witness_v1_scriptpubkey,
    make_control_block_prefix,
)

__all__ = [
    'TaprootTreeBuilder',
    'compute_taproot_sighash',
    'compute_taproot_sighash_simple',
    'compute_bip341_sighash',
    'compute_tapleaf_hash',
    # Taproot constants
    'OP_CHECKSIGADD',
    'WITNESS_V0',
    'WITNESS_V1',
    'OP_WITNESS_V0',
    'OP_WITNESS_V1',
    'TAPSCRIPT_LEAF_VERSION',
    'DEFAULT_LEAF_VERSION',
    'OP_PUSH_32',
    'OP_PUSH_33',
    'make_witness_v0_scriptpubkey',
    'make_witness_v1_scriptpubkey',
    'make_control_block_prefix',
]
