"""
Address Factory - Unified P2SH and Taproot Address Creation

This module provides a single interface for creating both P2SH and Taproot
addresses from ScriptBuilder instances.

Key Class:
- AddressFactory: Uses ScriptBuilder + output_type to create addresses

Architecture:
  ScriptBuilder → AddressFactory → P2SH or Taproot Address
  
Benefits:
- Single point of address creation
- Taproot support added once, works for all script types
- Easy to add new address types (P2WSH, etc.)
"""

from typing import Dict, Any, Tuple
import logging
from datetime import datetime

from electrum.bitcoin import hash_160, hash_encode, hash160_to_p2sh
from electrum import constants

try:
    # Try relative import first (when used as plugin)
    from .script_builders import ScriptBuilder, ScriptInputs
    from .taproot_helpers import create_taproot_address, pubkey_to_xonly
except ImportError:
    # Fall back to absolute import (when used standalone)
    from script_builders import ScriptBuilder, ScriptInputs
    from taproot_helpers import create_taproot_address, pubkey_to_xonly

logger = logging.getLogger(__name__)


class AddressFactory:
    """
    Factory for creating P2SH or Taproot addresses from scripts.
    
    Usage:
        factory = AddressFactory()
        
        # Create P2SH address
        result = factory.create_address(
            builder=FreezingFundsBuilder(),
            common=ScriptInputs(...),
            output_type='p2sh',
            pubkey=b'...'
        )
        
        # Create Taproot address  
        result = factory.create_address(
            builder=FreezingFundsBuilder(),
            common=ScriptInputs(...),
            output_type='taproot',
            pubkey=b'...'
        )
    """
    
    def create_address(
        self,
        builder: ScriptBuilder,
        common: ScriptInputs,
        **script_inputs
    ) -> Dict[str, Any]:
        """
        Create address using the specified builder and output type.
        
        Args:
            builder: ScriptBuilder instance (FreezingFundsBuilder, etc.)
            common: Common inputs (locktime, output_type, etc.)
            **script_inputs: Type-specific inputs (pubkeys, hashes, etc.)
        
        Returns:
            Dictionary containing:
            - address: The address (P2SH or Taproot)
            - script_hex: Script in hex
            - script_hash: Hash of script (P2SH only)
            - script_type: Type identifier
            - output_type: 'p2sh' or 'taproot'
            - created: Timestamp
            - control_block: Control block hex (Taproot only)
            - internal_pubkey: Internal pubkey hex (Taproot only)
            - Plus metadata from builder.get_metadata()
        
        Raises:
            ValueError: If output_type not supported
        """
        # Validate inputs match builder's spec
        self._validate_inputs(builder, script_inputs)
        
        # Build the script
        script = builder.build_script(common, **script_inputs)
        script_hex = script.hex()
        
        logger.info(f"[FACTORY] Building {common.output_type} address for {builder.get_script_type()}")
        logger.info(f"[FACTORY] Script: {script_hex}")
        
        # Create address based on output type
        if common.output_type == 'p2sh':
            result = self._create_p2sh(script, script_hex)
        elif common.output_type == 'taproot':
            result = self._create_taproot(script, script_hex, script_inputs)
        else:
            raise ValueError(f"Unsupported output type: {common.output_type}. Use 'p2sh' or 'taproot'")
        
        # Add common metadata
        metadata = builder.get_metadata(common, **script_inputs)
        result.update(metadata)
        result['created'] = datetime.now().isoformat()
        result['output_type'] = common.output_type
        
        logger.info(f"[FACTORY] ✅ Created {common.output_type} address: {result['address']}")
        
        return result
    
    def _create_p2sh(self, script: bytes, script_hex: str) -> Dict[str, Any]:
        """
        Create P2SH address from script.
        
        P2SH Process:
        1. script_bytes → SHA256 → RIPEMD160 → script_hash (20 bytes)
        2. script_hash → base58check with prefix → P2SH address
        
        Args:
            script: Script bytes
            script_hex: Script in hex
        
        Returns:
            Dict with address, script_hex, script_hash
        """
        logger.info("[P2SH] Creating P2SH address")
        logger.info(f"[P2SH] Script bytes: {script_hex}")
        
        # Hash the script: SHA256 then RIPEMD160
        script_hash = hash_160(script)
        logger.info(f"[P2SH] Script hash (HASH160): {script_hash.hex()}")
        
        # Encode as P2SH address using proper base58 encoding
        address = hash160_to_p2sh(script_hash, net=constants.net)
        logger.info(f"[P2SH] ✅ P2SH Address: {address}")
        
        return {
            'address': address,
            'script_hex': script_hex,
            'script_hash': script_hash.hex()
        }
    
    def _create_taproot(
        self,
        script: bytes,
        script_hex: str,
        script_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create Taproot address from script.
        
        Taproot Process:
        1. Convert all pubkeys to x-only format (32 bytes)
        2. Use NUMS point as internal key (no key-path spend)
        3. Create taproot output with script as single leaf
        4. Generate control block for script-path spending
        5. Encode as bech32m address (witness v1)
        
        Args:
            script: Script bytes
            script_hex: Script in hex
            script_inputs: Dict of script inputs (may contain pubkeys to convert)
        
        Returns:
            Dict with address, script_hex, control_block, internal_pubkey, etc.
        """
        logger.info("[TAPROOT] Creating Taproot address")
        logger.info(f"[TAPROOT] Script bytes: {script_hex}")
        
        # Convert any pubkeys in inputs to x-only format
        # This ensures tapscript compatibility (BIP-340 requires x-only pubkeys)
        converted_inputs = self._convert_pubkeys_to_xonly(script_inputs)
        
        # Rebuild script with x-only pubkeys
        # Note: For Phase 1, we assume pubkeys are already in correct positions
        # TODO: For Phase 2, we might need to rebuild script with converted keys
        
        # Create taproot address using helper
        taproot_data = create_taproot_address(
            tapscript=script,
            network=constants.net
        )
        
        logger.info(f"[TAPROOT] ✅ Taproot Address: {taproot_data['address']}")
        logger.info(f"[TAPROOT] Control block: {taproot_data['control_block'][:40]}...")
        
        return {
            'address': taproot_data['address'],
            'script_hex': script_hex,
            'control_block': taproot_data['control_block'],
            'internal_pubkey': taproot_data['internal_pubkey'],
            'witness_program': taproot_data['witness_program'],
            'output_script': taproot_data['output_script']
        }
    
    def _validate_inputs(self, builder: ScriptBuilder, script_inputs: Dict) -> None:
        """
        Validate that provided inputs match builder's specification.
        
        Args:
            builder: ScriptBuilder instance
            script_inputs: Provided inputs
        
        Raises:
            ValueError: If required inputs missing or wrong type
        """
        spec = builder.get_input_spec()
        
        # Check all required inputs present
        missing = set(spec.keys()) - set(script_inputs.keys())
        if missing:
            raise ValueError(
                f"{builder.get_script_type()} requires inputs: {list(spec.keys())}, "
                f"missing: {list(missing)}"
            )
        
        # Check types (basic validation)
        for key, expected_type in spec.items():
            value = script_inputs[key]
            if not isinstance(value, expected_type):
                # Try to convert if it's hex string and we expect bytes
                if expected_type == bytes and isinstance(value, str):
                    try:
                        script_inputs[key] = bytes.fromhex(value)
                    except ValueError:
                        raise ValueError(
                            f"Input '{key}' should be {expected_type.__name__}, "
                            f"got {type(value).__name__}"
                        )
                else:
                    raise ValueError(
                        f"Input '{key}' should be {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )
    
    def _convert_pubkeys_to_xonly(self, script_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert any pubkeys in script_inputs to x-only format for Taproot.
        
        Looks for keys ending in 'pubkey' and converts them from
        33-byte compressed to 32-byte x-only format.
        
        Args:
            script_inputs: Dictionary of script inputs
        
        Returns:
            New dictionary with converted pubkeys
        """
        converted = script_inputs.copy()
        
        for key, value in script_inputs.items():
            # Look for pubkey fields
            if 'pubkey' in key.lower() and isinstance(value, bytes):
                if len(value) == 33:
                    # Compressed pubkey - convert to x-only
                    xonly = pubkey_to_xonly(value)
                    converted[key] = xonly
                    logger.info(f"[TAPROOT] Converted {key}: {value.hex()} → {xonly.hex()}")
                elif len(value) == 32:
                    # Already x-only
                    logger.info(f"[TAPROOT] {key} already x-only: {value.hex()}")
                else:
                    logger.warning(f"[TAPROOT] Unexpected pubkey length for {key}: {len(value)} bytes")
        
        return converted


# Convenience function for quick address creation
def create_cltv_address(
    script_type: str,
    locktime: int,
    locktime_type: str,
    locktime_display: str,
    output_type: str = 'p2sh',
    **script_inputs
) -> Dict[str, Any]:
    """
    Convenience function to create CLTV address.
    
    Args:
        script_type: One of: freezing_funds, escrow, twofactor, 
                     payment_channel, data_publishing
        locktime: Block height or UNIX timestamp
        locktime_type: 'block' or 'timestamp'
        locktime_display: Human-readable display string
        output_type: 'p2sh' or 'taproot'
        **script_inputs: Type-specific inputs (pubkeys, hashes, etc.)
    
    Returns:
        Address creation result dictionary
    
    Example:
        >>> result = create_cltv_address(
        ...     script_type='freezing_funds',
        ...     locktime=100,
        ...     locktime_type='block',
        ...     locktime_display='Block 100',
        ...     output_type='taproot',
        ...     pubkey=b'\\x03\\x9a\\x36...'
        ... )
        >>> print(result['address'])
        tb1p...
    """
    try:
        from .script_builders import get_builder
    except ImportError:
        from script_builders import get_builder
    
    builder = get_builder(script_type)
    common = ScriptInputs(
        locktime=locktime,
        locktime_type=locktime_type,
        locktime_display=locktime_display,
        output_type=output_type
    )
    
    factory = AddressFactory()
    return factory.create_address(builder, common, **script_inputs)


__all__ = [
    'AddressFactory',
    'create_cltv_address'
]
