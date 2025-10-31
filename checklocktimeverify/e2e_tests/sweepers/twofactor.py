"""
Two-Factor Wallet Sweeper

Handles spending from two-factor wallet scripts with two paths:
1. Normal path (any time): User AND Service both sign
2. Recovery path (after timeout): User AND Recovery both sign

Supports modern Bitcoin script formats:
- P2WSH (Pay-to-Witness-Script-Hash) - SegWit v0  
- Taproot (Pay-to-Taproot) - SegWit v1

Learning points:
- 2FA security with recovery fallback
- User key always required (both paths)
- Service vs Recovery selection based on timeout
- Different witness stacks for different paths
"""

from typing import List, Dict, Any
from .base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from script_utils import get_signature_type, SignatureType


class TwoFactorSweeper(SweeperStrategy):
    """
    Sweeper for two-factor wallet scripts.
    
    Two spend paths:
    1. Normal (any time):
       - P2WSH: [user_sig, service_sig, 1, script] (witness)
       - Taproot: [user_sig, service_sig, 1, script, control] (witness)
       - OP_IF path (1 = true)
       - Requires both User and Service
    
    2. Recovery (after timeout):
       - P2WSH: [user_sig, recovery_sig, 0, script] (witness)
       - Taproot: [user_sig, recovery_sig, 0, script, control] (witness)
       - OP_ELSE path (0 = false)
       - Requires both User and Recovery
       - Must wait for locktime
    
    Args:
        use_recovery_path: bool - If True, use recovery path (after timeout)
                                  If False, use normal path (user + service)
    """
    
    SCRIPT_TYPE = "cltv_twofactor"
    
    def __init__(self, use_refund_path: bool = False, **kwargs):
        """
        Initialize sweeper with path selection.
        
        Args:
            use_refund_path: If True, use recovery path (after timeout)
                           If False, use normal path (user + service)
            **kwargs: Additional parameters (ignored for compatibility)
        """
        # Map use_refund_path to use_recovery_path for internal logic
        self.use_recovery_path = use_refund_path
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Identify which keys are needed.
        
        Normal path: user_key + service_key
        Recovery path: user_key + recovery_key
        """
        if self.use_recovery_path:
            # Recovery: user + recovery
            return ['user_key', 'recovery_key']
        else:
            # Normal: user + service
            return ['user_key', 'service_key']
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for chosen path.
        
        Normal path witness:
            [user_signature, service_signature, 1, script]
            (+control_block for Taproot)
            
        Recovery path witness:
            [user_signature, recovery_signature, 0, script]
            (+control_block for Taproot)
        
        For P2SH, this creates scriptSig content (returned as witness for consistency)
        For P2WSH/Taproot, this is actual witness
        """
        script = bytes.fromhex(output['script_hex'])
        script_type = output.get('script_type', 'cltv_twofactor')
        sig_type = get_signature_type(script_type)
        
        # User key always required
        user_key = keys.get('user_key')
        if not user_key:
            raise ValidationError("user_key not provided")
        
        if self.use_recovery_path:
            # Recovery path: user + recovery signatures
            recovery_key = keys.get('recovery_key')
            if not recovery_key:
                raise ValidationError("recovery_key not provided for recovery path")
            
            # Sign with both keys (ECDSA for P2WSH)
            user_sig = self._ecdsa_sign(user_key, sighash)
            recovery_sig = self._ecdsa_sign(recovery_key, sighash)
            
            # Witness: [user_sig, recovery_sig, 0, script]
            # Order: Stack top (consumed by final OP_CHECKSIG) = user
            #        Next (consumed by OP_CHECKSIGVERIFY) = recovery
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                user_sig,      # Stack top (final OP_CHECKSIG in ELSE branch)
                recovery_sig,  # Consumed by OP_CHECKSIGVERIFY in ELSE branch
                0,             # False - triggers ELSE branch (recovery path)
                script
            ]
        
        else:
            # Normal path: user + service signatures
            service_key = keys.get('service_key')
            if not service_key:
                raise ValidationError("service_key not provided for normal path")
            
            # Sign with both keys (ECDSA for P2WSH)
            user_sig = self._ecdsa_sign(user_key, sighash)
            service_sig = self._ecdsa_sign(service_key, sighash)
            
            # Witness: [user_sig, service_sig, 1, script]
            # Order: Stack top (consumed by final OP_CHECKSIG) = user
            #        Next (consumed by OP_CHECKSIGVERIFY) = service
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                user_sig,      # Stack top (final OP_CHECKSIG in IF branch)
                service_sig,   # Consumed by OP_CHECKSIGVERIFY in IF branch
                1,             # True - triggers IF branch (normal path)
                script
            ]
        
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
        Check if sweep is possible.
        
        Normal path: Can sweep anytime
        Recovery path: Can only sweep after locktime
        """
        locktime = output.get('script_params', {}).get('locktime')
        
        # Fallback to top-level locktime
        if locktime is None:
            locktime = output.get('locktime')
        
        if locktime is None:
            raise ValidationError("No locktime found in output")
        
        if self.use_recovery_path:
            # Recovery path: must wait for locktime
            is_unlocked = current_height >= locktime
            
            if not is_unlocked and kwargs.get('raise_if_locked', False):
                raise LockedError(
                    f"Recovery path locked. Current height: {current_height}, "
                    f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
                )
            
            return is_unlocked
        else:
            # Normal path: can sweep anytime
            return True
    
    def estimate_witness_size(self, output: Dict[str, Any]) -> int:
        """
        Estimate witness size for fee calculation.
        
        Both paths: ~180 bytes (2 sigs + script + control_block if Taproot)
        """
        from script_utils import get_witness_size_estimate
        
        script_type = output.get('script_type', 'cltv_twofactor')
        path = 'recovery' if self.use_recovery_path else 'normal'
        
        return get_witness_size_estimate(script_type, path)
    
    # Helper methods are now inherited from base class
