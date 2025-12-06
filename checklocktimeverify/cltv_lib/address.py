"""
Address Generation - P2WSH and Taproot Only

Clean API for generating addresses from CLTV scripts.
NO P2SH SUPPORT - deprecated and removed.

Supports:
- P2WSH (Pay-to-Witness-Script-Hash) - SegWit v0, witness version 0
- Taproot - SegWit v1, witness version 1

Examples:
    >>> from cltv_lib.address import generate_p2wsh_address, generate_taproot_address
    >>> from cltv_lib.builders import SimpleCLTVBuilder
    >>> 
    >>> # Generate P2WSH address
    >>> builder = SimpleCLTVBuilder()
    >>> script = builder.build({'locktime': 100, 'pubkey': '02abc...'})
    >>> addr_info = generate_p2wsh_address(script, network='signet')
    >>> print(addr_info['address'])
    'tb1q...'
    >>> 
    >>> # Generate Taproot address
    >>> from cltv_lib.builders.taproot.taproot_utils import NUMS_H
    >>> tap_info = generate_taproot_address([script], bytes.fromhex(NUMS_H), network='signet')
    >>> print(tap_info['address'])
    'tb1p...'
"""

from typing import Dict, Any, Literal
from electrum.bitcoin import sha256, hash_to_segwit_addr
from electrum import constants
from .builders.taproot.taproot_constants import (
    TAPSCRIPT_LEAF_VERSION,
    OP_WITNESS_V0,
    OP_PUSH_32,
)

Network = Literal['mainnet', 'testnet', 'testnet4', 'signet', 'regtest']


def _get_network_constant(network: Network):
    """
    Get Electrum network constant for address generation.
    
    Args:
        network: Network identifier
    
    Returns:
        Electrum network constant
    """
    networks = {
        'mainnet': constants.BitcoinMainnet,
        'testnet': constants.BitcoinTestnet,
        'testnet4': constants.BitcoinTestnet,  # Uses testnet constant
        'signet': constants.BitcoinSignet,
        'regtest': constants.BitcoinRegtest,
    }
    return networks.get(network, constants.BitcoinSignet)


def generate_p2wsh_address(script: bytes, network: Network = 'signet') -> Dict[str, Any]:
    """
    Generate P2WSH (native SegWit v0) address from script.
    
    P2WSH uses SHA256 of the script as the witness program.
    Address format: bc1q... (mainnet) or tb1q... (testnet/signet)
    
    Args:
        script: Raw script bytes (witness script)
        network: Network for address generation (default: signet)
    
    Returns:
        Dictionary with:
        - address: str - P2WSH address (bech32)
        - script_hex: str - Original script as hex
        - script_hash: str - SHA256 hash of script (hex)
        - output_script: str - Witness program (OP_0 <32-byte-hash>) as hex
        - witness_version: int - Always 0 for P2WSH
        - output_type: str - Always 'p2wsh'
    
    Example:
        >>> script = bytes.fromhex('0164b175210288ab3...')
        >>> result = generate_p2wsh_address(script, 'signet')
        >>> print(result['address'])
        'tb1q...'
        >>> print(result['script_hash'])
        'abc123...'
    """
    # Compute SHA256 hash of script (witness program)
    script_hash = sha256(script)
    
    # Get network constant
    net = _get_network_constant(network)
    
    # Generate bech32 address (witness version 0)
    address = hash_to_segwit_addr(script_hash, witver=0, net=net)
    
    # Build output script: OP_0 <32-byte-hash>
    output_script = bytes([OP_WITNESS_V0, OP_PUSH_32]) + script_hash  # OP_0, 32 bytes
    
    return {
        'address': address,
        'script_hex': script.hex(),
        'script_hash': script_hash.hex(),
        'output_script': output_script.hex(),
        'witness_version': 0,
        'output_type': 'p2wsh',
    }


def generate_taproot_address(
    scripts: list[bytes],
    internal_key: bytes,
    network: Network = 'signet',
    leaf_version: int = TAPSCRIPT_LEAF_VERSION
) -> Dict[str, Any]:
    """
    Generate Taproot (SegWit v1) address from script(s).
    
    For CLTV scripts, this typically uses a single script path with a NUMS
    (Nothing-Up-My-Sleeve) internal key to disable key-path spending.
    
    Uses TaprootTreeBuilder (Bitcoin Core compatible) for address generation.
    
    Args:
        scripts: List of script bytes (usually 1 script for CLTV)
        internal_key: 32-byte x-only internal public key (usually NUMS point)
        network: Network for address generation (default: signet)
        leaf_version: Tapscript leaf version (default: TAPSCRIPT_LEAF_VERSION)
    
    Returns:
        Dictionary with:
        - address: str - Taproot address (bech32m)
        - output_script: str - Witness program (OP_1 <32-byte-key>) as hex
        - control_blocks: list[str] - Control blocks for each script path
        - merkle_root: str - Merkle root of script tree
        - output_key: str - Tweaked output key (x-only)
        - witness_version: int - Always 1 for Taproot
        - output_type: str - Always 'taproot'
    
    Example:
        >>> from cltv_lib.builders.taproot.taproot_utils import NUMS_H
        >>> script = bytes.fromhex('0164b175...')
        >>> result = generate_taproot_address([script], bytes.fromhex(NUMS_H), 'signet')
        >>> print(result['address'])
        'tb1p...'
    
    Note:
        For full Taproot functionality, use TaprootTreeBuilder directly.
        This is a simplified wrapper for common CLTV use cases.
    """
    from .builders.taproot.taproot_tree_builder import TaprootTreeBuilder
    
    # Build Taproot address using TaprootTreeBuilder (Bitcoin Core compatible)
    builder = TaprootTreeBuilder()
    
    # Add scripts at appropriate depths
    # Single script: depth 0 (becomes root directly)
    # Multiple scripts: depth 1 (balanced tree)
    if len(scripts) == 1:
        builder.add(depth=0, script=scripts[0], leaf_version=leaf_version)
    else:
        for script in scripts:
            builder.add(depth=1, script=script, leaf_version=leaf_version)
    
    # Finalize and get output
    output = builder.finalize(internal_key, network=network)
    
    # Extract control blocks in order matching input scripts
    control_blocks = []
    for script in scripts:
        control_block_set = output.spend_data.scripts.get((script, leaf_version), set())
        if control_block_set:
            control_blocks.append(list(control_block_set)[0].hex())
        else:
            control_blocks.append('')  # Should not happen with valid inputs
    
    return {
        'address': output.address,
        'output_script': output.output_script.hex(),
        'control_blocks': control_blocks,
        'merkle_root': output.spend_data.merkle_root.hex() if output.spend_data.merkle_root else '',
        'output_key': output.output_key.hex(),
        'witness_version': 1,
        'output_type': 'taproot',
    }


# Convenience function for simple use cases
def generate_address(
    script: bytes,
    output_type: Literal['p2wsh', 'taproot'],
    network: Network = 'signet',
    internal_key: bytes = None
) -> Dict[str, Any]:
    """
    Generate address from script (convenience wrapper).
    
    Args:
        script: Raw script bytes
        output_type: 'p2wsh' or 'taproot'
        network: Network for address generation
        internal_key: Required for Taproot (32-byte x-only key)
    
    Returns:
        Address info dictionary (format depends on output_type)
    
    Raises:
        ValueError: If P2SH requested (not supported) or missing internal_key for Taproot
    
    Examples:
        >>> # P2WSH
        >>> info = generate_address(script, 'p2wsh', 'signet')
        >>> 
        >>> # Taproot
        >>> from cltv_lib.builders.taproot.taproot_utils import NUMS_H
        >>> info = generate_address(script, 'taproot', 'signet', internal_key=bytes.fromhex(NUMS_H))
    """
    if output_type == 'p2wsh':
        return generate_p2wsh_address(script, network)
    
    elif output_type == 'taproot':
        if internal_key is None:
            raise ValueError(
                "internal_key required for Taproot addresses. "
                "Use NUMS_H from taproot_utils for standard CLTV scripts."
            )
        return generate_taproot_address([script], internal_key, network)
    
    else:
        raise ValueError(
            f"Unsupported output type: {output_type}. "
            "Only 'p2wsh' and 'taproot' are supported. "
            "P2SH is deprecated and removed."
        )


__all__ = [
    'generate_address',
    'generate_p2wsh_address',
    'generate_taproot_address',
]
