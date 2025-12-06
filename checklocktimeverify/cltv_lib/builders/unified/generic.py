"""
Generic Unified Contract Builder

Builds ANY contract type from its ContractDefinition.
This is the TRUE single source of truth - no more per-contract builder files.

Usage:
    from cltv_lib.builders.unified.generic import build_contract
    
    # Build any contract
    result = build_contract('escrow', {
        'locktime': 600000,
        'alice': '02abc...',
        'bob': '03def...',
        'lenny': '02ghi...',
    }, output_type='p2wsh', network='signet')
    
    # Result includes address, script_hex, etc.
"""

from typing import Dict, Any, Literal, Union, Optional

from electrum.crypto import hash_160

from ...contracts import CONTRACTS, ContractDefinition, ParamSpec
from ...contracts.definitions import get_taproot_leaves
from ...miniscript import compile_miniscript, MiniscriptContext
from ...address import generate_address
from ..taproot.taproot_utils import NUMS_H
from ..taproot.taproot_tree_builder import TaprootTreeBuilder
from ..taproot.taproot_constants import TAPSCRIPT_LEAF_VERSION
from ..base import BuildError


OutputType = Literal['p2wsh', 'taproot']
Network = Literal['mainnet', 'testnet', 'signet', 'regtest']


class UnifiedContractBuilder:
    """
    Generic builder for any contract defined in ContractDefinition.
    
    This replaces the 5 separate builder files (hodl.py, escrow.py, etc.)
    with a single generic implementation that derives everything from
    ContractDefinition metadata.
    
    The ContractDefinition is now the TRUE single source of truth.
    """
    
    VALID_NETWORKS = ['mainnet', 'testnet', 'signet', 'regtest']
    
    @classmethod
    def build(
        cls,
        contract_name: str,
        params: Dict[str, Any],
        output_type: OutputType = 'p2wsh',
        network: Network = 'signet'
    ) -> Dict[str, Any]:
        """
        Build any contract.
        
        Args:
            contract_name: One of 'hodl', 'escrow', 'twofactor', 
                          'payment_channel', 'data_publishing'
            params: Parameter values (locktime, pubkeys, etc.)
            output_type: 'p2wsh' or 'taproot'
            network: Network for address generation
        
        Returns:
            Dict with address, script_hex, and all metadata
        """
        # Get contract definition
        contract = CONTRACTS.get(contract_name)
        if not contract:
            raise BuildError(f"Unknown contract: {contract_name}. "
                           f"Available: {list(CONTRACTS.keys())}")
        
        # Validate network
        cls._validate_network(network)
        
        # Validate and normalize parameters
        validated_params = cls._validate_params(contract, params)
        
        if output_type == 'p2wsh':
            return cls._build_p2wsh(contract, validated_params, network)
        elif output_type == 'taproot':
            return cls._build_taproot(contract, validated_params, network)
        else:
            raise BuildError(f"Invalid output_type: {output_type}")
    
    @classmethod
    def build_p2wsh(
        cls,
        contract_name: str,
        params: Dict[str, Any],
        network: Network = 'signet'
    ) -> Dict[str, Any]:
        """Convenience method for P2WSH."""
        return cls.build(contract_name, params, 'p2wsh', network)
    
    @classmethod
    def build_taproot(
        cls,
        contract_name: str,
        params: Dict[str, Any],
        network: Network = 'signet'
    ) -> Dict[str, Any]:
        """Convenience method for Taproot."""
        return cls.build(contract_name, params, 'taproot', network)
    
    # ========================================================================
    # Internal Implementation
    # ========================================================================
    
    @classmethod
    def _build_p2wsh(
        cls,
        contract: ContractDefinition,
        params: Dict[str, Any],
        network: str
    ) -> Dict[str, Any]:
        """Build P2WSH address from contract definition."""
        # Map params to miniscript placeholders
        mapped_params = cls._map_params(contract, params)

        # Compile miniscript to script
        script = compile_miniscript(
            contract.miniscript,
            mapped_params,
            MiniscriptContext.P2WSH
        )

        # Generate P2WSH address
        addr_info = generate_address(script, 'p2wsh', network)

        # Build result
        # Use registry as single source of truth for script_type
        from ...registry import get_script_id
        script_type = get_script_id(contract.contract_type.value, 'p2wsh')

        result = {
            'address': addr_info['address'],
            'script': script,
            'script_hex': script.hex(),
            'witness_script_hash': addr_info.get('script_hash', ''),
            'script_type': script_type,
            'output_type': 'p2wsh',
            'witness_version': 0,
            'network': network,
        }

        # Add original params
        result.update(cls._format_params_for_storage(contract, params))

        return result
    
    @classmethod
    def _build_taproot(
        cls,
        contract: ContractDefinition,
        params: Dict[str, Any],
        network: str
    ) -> Dict[str, Any]:
        """Build Taproot address from contract definition."""
        
        # Map params to miniscript placeholders
        mapped_params = cls._map_params(contract, params)
        
        # Get leaf scripts from contract definition
        leaf_miniscripts = get_taproot_leaves(contract.contract_type.value)
        
        # Compile each leaf
        leaves = []
        for leaf_ms in leaf_miniscripts:
            script = compile_miniscript(
                leaf_ms,
                mapped_params,
                MiniscriptContext.TAPSCRIPT
            )
            leaves.append(script)
        
        # Build Taproot tree
        internal_key = bytes.fromhex(NUMS_H)
        builder = TaprootTreeBuilder()
        
        if len(leaves) == 1:
            # Single leaf: depth 0 (becomes root directly)
            builder.add(depth=0, script=leaves[0], leaf_version=TAPSCRIPT_LEAF_VERSION)
        elif len(leaves) == 2:
            # Two leaves at equal depth
            builder.add(depth=1, script=leaves[0], leaf_version=TAPSCRIPT_LEAF_VERSION)
            builder.add(depth=1, script=leaves[1], leaf_version=TAPSCRIPT_LEAF_VERSION)
        else:
            # More leaves - build balanced tree
            depth = (len(leaves) - 1).bit_length()
            for i, leaf in enumerate(leaves):
                builder.add(depth=depth, script=leaf, leaf_version=TAPSCRIPT_LEAF_VERSION)
        
        output = builder.finalize(internal_key, network=network)
        
        # Get control block for first leaf (primary spend path)
        primary_script = leaves[0]
        control_block_set = output.spend_data.scripts.get(
            (primary_script, TAPSCRIPT_LEAF_VERSION), set()
        )
        if not control_block_set:
            raise BuildError("Control block not found for primary script")
        control_block = list(control_block_set)[0]
        
        # Build result
        # Use registry as single source of truth for script_type
        from ...registry import get_script_id
        script_type = get_script_id(contract.contract_type.value, 'taproot')
        
        result = {
            'address': output.address,
            'output_script': output.output_script.hex(),
            'script_hex': primary_script.hex(),
            'control_block': control_block.hex(),
            'control_block_hex': control_block.hex(),
            'internal_key': NUMS_H,
            'output_key': output.output_key.hex(),
            'script_type': script_type,
            'output_type': 'taproot',
            'witness_version': 1,
            'network': network,
        }
        
        # Add leaf scripts for multi-path contracts
        if len(leaves) > 1:
            result['leaf_scripts'] = {
                f'leaf_{i}': leaf.hex() for i, leaf in enumerate(leaves)
            }
            
            # Add control blocks for all leaves
            result['control_blocks'] = {}
            for i, leaf in enumerate(leaves):
                cb_set = output.spend_data.scripts.get(
                    (leaf, TAPSCRIPT_LEAF_VERSION), set()
                )
                if cb_set:
                    result['control_blocks'][f'leaf_{i}'] = list(cb_set)[0].hex()
        
        # Add original params
        result.update(cls._format_params_for_storage(contract, params))
        
        return result
    
    @classmethod
    def _validate_params(
        cls,
        contract: ContractDefinition,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate parameters based on ParamSpec definitions."""
        validated = {}
        
        for spec in contract.params:
            # Get value (try both direct name and with _pubkey suffix)
            value = params.get(spec.name)
            if value is None and spec.param_type == 'pubkey':
                value = params.get(f'{spec.name}_pubkey')
            
            # Check required
            if spec.required and value is None:
                # Special case: data_hash can be derived from data_preimage
                if spec.name == 'data_hash' and 'data_preimage' in params:
                    value = cls._compute_hash160(params['data_preimage'])
                else:
                    raise BuildError(f"Missing required parameter: {spec.name}")
            
            if value is None:
                continue
            
            # Validate by type
            if spec.param_type == 'locktime':
                validated[spec.name] = cls._validate_locktime(value)
            elif spec.param_type == 'pubkey':
                validated[spec.name] = cls._validate_pubkey(value, spec.name)
            elif spec.param_type == 'hash160':
                validated[spec.name] = cls._validate_hash160(value, spec.name)
            elif spec.param_type == 'preimage':
                validated[spec.name] = cls._validate_preimage(value)
            else:
                validated[spec.name] = value
        
        return validated
    
    @classmethod
    def _map_params(
        cls,
        contract: ContractDefinition,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Map param names to miniscript placeholders.
        
        Since v12.0.0, params already use miniscript names directly (e.g., 'alice').
        This function is kept for any future param_mapping needs but is mostly a pass-through.
        """
        mapped = {}
        
        for key, value in params.items():
            # Use param_mapping if defined, otherwise pass through
            mapped_key = contract.param_mapping.get(key, key)
            mapped[mapped_key] = value
        
        return mapped
    
    @classmethod
    def _format_params_for_storage(
        cls,
        contract: ContractDefinition,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format params for return dict (uses miniscript names directly).
        
        Since v12.0.0, we use miniscript names (e.g., 'alice') not legacy
        suffixed names (e.g., 'alice_pubkey').
        """
        result = {'locktime': params.get('locktime')}
        
        for spec in contract.params:
            if spec.param_type == 'locktime':
                continue  # Already added above
            
            value = params.get(spec.name)
            if value is not None:
                # Convert bytes to hex string for JSON serialization
                if isinstance(value, bytes):
                    value = value.hex()
                result[spec.name] = value
        
        return result
    
    # ========================================================================
    # Validation Helpers
    # ========================================================================
    
    @staticmethod
    def _validate_network(network: str) -> None:
        """Validate network name."""
        valid = ['mainnet', 'testnet', 'signet', 'regtest']
        if network not in valid:
            raise BuildError(f"Invalid network: {network}. Expected one of {valid}")
    
    @staticmethod
    def _validate_locktime(value: Any) -> int:
        """Validate and normalize locktime."""
        if isinstance(value, str):
            value = int(value)
        if not isinstance(value, int):
            raise BuildError(f"locktime must be int, got {type(value).__name__}")
        if value < 0:
            raise BuildError(f"locktime must be non-negative, got {value}")
        return value
    
    @staticmethod
    def _validate_pubkey(value: Any, name: str) -> bytes:
        """Validate and normalize pubkey to bytes."""
        if isinstance(value, str):
            try:
                value = bytes.fromhex(value)
            except ValueError as e:
                raise BuildError(f"Invalid hex for {name}: {e}")
        
        if not isinstance(value, bytes):
            raise BuildError(f"{name} must be bytes or hex string")
        
        if len(value) == 33:
            # Compressed pubkey
            if value[0] not in (0x02, 0x03):
                raise BuildError(f"Invalid compressed pubkey prefix for {name}")
        elif len(value) == 32:
            # X-only pubkey (Taproot)
            pass
        else:
            raise BuildError(f"Invalid pubkey length for {name}: {len(value)}. "
                           f"Expected 32 (x-only) or 33 (compressed)")
        
        return value
    
    @staticmethod
    def _validate_hash160(value: Any, name: str) -> bytes:
        """Validate HASH160 (20 bytes)."""
        if isinstance(value, str):
            try:
                value = bytes.fromhex(value)
            except ValueError as e:
                raise BuildError(f"Invalid hex for {name}: {e}")
        
        if not isinstance(value, bytes):
            raise BuildError(f"{name} must be bytes or hex string")
        
        if len(value) != 20:
            raise BuildError(f"Invalid {name} length: {len(value)}. Expected 20 bytes (HASH160)")
        
        return value
    
    @staticmethod
    def _validate_preimage(value: Any) -> bytes:
        """Validate and normalize preimage."""
        if isinstance(value, str):
            # Could be hex or UTF-8
            if len(value) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in value):
                return bytes.fromhex(value)
            else:
                return value.encode('utf-8')
        elif isinstance(value, bytes):
            return value
        else:
            raise BuildError(f"preimage must be bytes or string, got {type(value).__name__}")
    
    @staticmethod
    def _compute_hash160(preimage: Any) -> bytes:
        """Compute HASH160 from preimage using Electrum native function."""
        if isinstance(preimage, str):
            if len(preimage) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in preimage):
                preimage = bytes.fromhex(preimage)
            else:
                preimage = preimage.encode('utf-8')
        
        # Use Electrum's native hash_160 (RIPEMD160(SHA256(x)))
        return hash_160(preimage)


# =============================================================================
# Convenience Functions
# =============================================================================

def build_contract(
    contract_name: str,
    params: Dict[str, Any],
    output_type: OutputType = 'p2wsh',
    network: Network = 'signet'
) -> Dict[str, Any]:
    """
    Build any contract address.
    
    This is the main entry point for the generic builder.
    
    Args:
        contract_name: 'hodl', 'escrow', 'twofactor', 
                      'payment_channel', 'data_publishing'
        params: Parameter values
        output_type: 'p2wsh' or 'taproot'
        network: 'mainnet', 'testnet', 'signet', 'regtest'
    
    Returns:
        Dict with address and all metadata
    
    Example:
        >>> result = build_contract('escrow', {
        ...     'locktime': 600000,
        ...     'alice': '02abc...',
        ...     'bob': '03def...',
        ...     'lenny': '02ghi...',
        ... }, output_type='taproot', network='signet')
        >>> print(result['address'])  # tb1p...
    """
    return UnifiedContractBuilder.build(contract_name, params, output_type, network)


__all__ = ['UnifiedContractBuilder', 'build_contract']

