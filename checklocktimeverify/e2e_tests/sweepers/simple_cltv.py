"""
Simple CLTV Sweeper - For single-sig time-locked outputs

Handles both modern Bitcoin script formats of:
    <locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG

Script types:
- cltv_simple_p2wsh (P2WSH with ECDSA) - SegWit v0
- cltv_simple_taproot (Taproot with Schnorr) - SegWit v1
"""

from typing import List, Dict, Any
from .base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from script_utils import get_signature_type, SignatureType


class SimpleCLTVSweeper(SweeperStrategy):
    """
    Sweeper for simple time-locked single-signature CLTV outputs.
    
    Supports modern Bitcoin script formats:
    - P2WSH native SegWit CLTV (ECDSA signatures, witness)
    - Native Taproot CLTV (Schnorr signatures, witness)
    
    Witness structure:
    - P2WSH: [signature, script]
    - Taproot: [signature, script, control_block]
    """
    
    SCRIPT_TYPE = "cltv_simple_hodl"
    
    def __init__(self, **kwargs):
        """
        Initialize sweeper. Accepts kwargs for compatibility with registry.
        
        Args:
            **kwargs: Ignored for simple CLTV (no path variants)
        """
        # Simple CLTV has no path variants, so we ignore all kwargs
        pass
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Simple CLTV needs exactly 1 key.
        
        Args:
            output: Must contain 'key_derivation' or default to single key
        
        Returns:
            List with one key identifier
        """
        # Check for key derivation path
        key_deriv = output.get('key_derivation')
        if key_deriv:
            return [key_deriv]
        
        # Fallback: use private_key field directly (for tests)
        if 'private_key' in output:
            return ['private_key']
        
        # Default to 'private_key' for testing
        return ['private_key']
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for simple CLTV.
        
        Args:
            output: Output data with script_hex, script_type
            keys: Dict of private keys
            sighash: The sighash to sign
        
        Returns:
            P2SH: No witness (empty list, uses scriptSig instead)
            P2WSH: [signature, script]
            Taproot: [signature, script, control_block]
        """
        # Get the key
        key_ids = self.get_required_keys(output)
        key = keys.get(key_ids[0])
        
        if not key:
            raise ValidationError(f"Key {key_ids[0]} not provided")
        
        # Determine signature type from script type
        script_type = output.get('script_type', 'cltv_simple_hodl')
        
        # Sign with ECDSA for P2WSH (Taproot uses separate taproot_tx_builder.py)
        sig = self._ecdsa_sign(key, sighash)
        
        # Get script
        script = bytes.fromhex(output['script_hex'])
        
        # Build witness based on format
        if 'p2wsh' not in script_type.lower() and 'taproot' not in script_type.lower():
            raise ValidationError(f"Unknown script format: {script_type}. Expected p2wsh or taproot.")
        
        # P2WSH or Taproot - use witness
        witness = [sig, script]
        
        # Add control block for Taproot
        if 'taproot' in script_type.lower():
            control_block = output.get('control_block')
            if not control_block:
                raise ValidationError("Taproot output missing control_block")
            witness.append(bytes.fromhex(control_block))
        
        return witness
    
    def validate_sweep_conditions(
        self,
        output: Dict[str, Any],
        current_height: int,
        **kwargs
    ) -> bool:
        """
        Check if output is unlocked (past locktime).
        
        Args:
            output: Must contain script_params['locktime']
            current_height: Current blockchain height
        
        Returns:
            True if unlocked, False if still locked
        
        Raises:
            LockedError: If explicitly checking and still locked
        """
        locktime = output.get('script_params', {}).get('locktime')
        
        # Fallback to top-level locktime (legacy test format)
        if locktime is None:
            locktime = output.get('locktime')
        
        if locktime is None:
            raise ValidationError("No locktime found in output")
        
        is_unlocked = current_height >= locktime
        
        # If caller wants exception on locked
        if not is_unlocked and kwargs.get('raise_if_locked', False):
            raise LockedError(
                f"Output still locked. Current height: {current_height}, "
                f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
            )
        
        return is_unlocked
    
    def estimate_witness_size(self, output: Dict[str, Any]) -> int:
        """
        Estimate witness size for fee calculation.
        
        P2SH: ~0 bytes (uses scriptSig instead)
        P2WSH: ~107 bytes (64-byte sig + 3 bytes overhead + 40-byte script)
        Taproot: ~140 bytes (64-byte sig + 40-byte script + 33-byte control block)
        """
        from script_utils import get_witness_size_estimate
        
        script_type = output.get('script_type', 'cltv_simple_hodl')
        return get_witness_size_estimate(script_type)
    
    # Helper methods are now inherited from base class
