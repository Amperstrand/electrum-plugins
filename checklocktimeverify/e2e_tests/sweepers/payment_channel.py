"""
Payment Channel Sweeper

Handles spending from payment channel scripts with two paths:
1. Cooperative close: Sender AND Receiver both sign (2-of-2 multisig)
2. Refund: Sender only after timeout

Supports modern Bitcoin script formats:
- P2WSH (Pay-to-Witness-Script-Hash) - SegWit v0  
- Taproot (Pay-to-Taproot) - SegWit v1

Learning points:
- Multisig witness construction (OP_0 prefix required)
- Different signatures for different paths
- Cooperative close preferred (any time)
- Unilateral refund as safety valve (after timeout)
"""

from typing import List, Dict, Any
from .base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from script_utils import get_signature_type, SignatureType


class PaymentChannelSweeper(SweeperStrategy):
    """
    Sweeper for payment channel scripts.
    
    Two spend paths:
    1. Cooperative (any time):
       - P2WSH: [OP_0, sender_sig, receiver_sig, 1, script] (witness)
       - Taproot: [OP_0, sender_sig, receiver_sig, 1, script, control] (witness)
       - OP_IF path (1 = true)
       - Requires both Sender and Receiver (2-of-2 multisig)
    
    2. Refund (after timeout):
       - P2WSH: [sender_sig, 0, script] (witness)
       - Taproot: [sender_sig, 0, script, control] (witness)
       - OP_ELSE path (0 = false)
       - Requires only Sender
       - Must wait for locktime
    
    Args:
        use_refund_path: bool - If True, use refund path (sender only after timeout)
                                If False, use cooperative path (sender + receiver)
    """
    
    SCRIPT_TYPE = "cltv_payment_channel"
    
    def __init__(self, use_refund_path: bool = False):
        """
        Initialize sweeper with path selection.
        
        Args:
            use_refund_path: Use timeout refund path instead of cooperative close
        """
        self.use_refund_path = use_refund_path
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Identify which keys are needed.
        
        Cooperative path: sender_key + receiver_key
        Refund path: sender_key only
        """
        if self.use_refund_path:
            # Refund: only sender's key
            return ['sender_key']
        else:
            # Cooperative: both keys required
            return ['sender_key', 'receiver_key']
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for chosen path.
        
        Cooperative path witness:
            [OP_0, sender_signature, receiver_signature, 1, script]
            (+control_block for Taproot)
            
        Refund path witness:
            [sender_signature, 0, script]
            (+control_block for Taproot)
        
        For P2SH, this creates scriptSig content (returned as witness for consistency)
        For P2WSH/Taproot, this is actual witness
        """
        script = bytes.fromhex(output['script_hex'])
        script_type = output.get('script_type', 'cltv_payment_channel')
        sig_type = get_signature_type(script_type)
        
        if self.use_refund_path:
            # Refund path: sender signature only + 0 (OP_ELSE)
            sender_key = keys.get('sender_key')
            if not sender_key:
                raise ValidationError("sender_key not provided for refund path")
            
            # Sign with sender key (ECDSA for P2WSH)
            sender_sig = self._ecdsa_sign(sender_key, sighash)
            
            # Witness: [sender_sig, 0, script]
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                sender_sig,  # Sender's signature
                0,           # False - triggers ELSE branch (refund path)
                script
            ]
        
        else:
            # Cooperative path: 2-of-2 multisig (sender + receiver)
            sender_key = keys.get('sender_key')
            receiver_key = keys.get('receiver_key')
            
            if not sender_key:
                raise ValidationError("sender_key not provided for cooperative path")
            if not receiver_key:
                raise ValidationError("receiver_key not provided for cooperative path")
            
            # Sign with both keys (ECDSA for P2WSH)
            sender_sig = self._ecdsa_sign(sender_key, sighash)
            receiver_sig = self._ecdsa_sign(receiver_key, sighash)
            
            # Witness: [OP_0, sender_sig, receiver_sig, 1, script]
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            # OP_CHECKMULTISIG bug requires extra OP_0 at bottom of stack
            witness = [
                0,           # CHECKMULTISIG bug workaround (off-by-one)
                sender_sig,  # First signature
                receiver_sig,  # Second signature
                1,           # True - triggers IF branch (cooperative path)
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
        
        Cooperative path: Can sweep anytime
        Refund path: Can only sweep after locktime
        """
        locktime = output.get('script_params', {}).get('locktime')
        
        # Fallback to top-level locktime
        if locktime is None:
            locktime = output.get('locktime')
        
        if locktime is None:
            raise ValidationError("No locktime found in output")
        
        if self.use_refund_path:
            # Refund path: must wait for locktime
            is_unlocked = current_height >= locktime
            
            if not is_unlocked and kwargs.get('raise_if_locked', False):
                raise LockedError(
                    f"Refund path locked. Current height: {current_height}, "
                    f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
                )
            
            return is_unlocked
        else:
            # Cooperative path: can sweep anytime
            return True
    
    def estimate_witness_size(self, output: Dict[str, Any]) -> int:
        """
        Estimate witness size for fee calculation.
        
        Cooperative: ~210 bytes (OP_0 + 2 sigs + script + control_block if Taproot)
        Refund: ~140 bytes (1 sig + script + control_block if Taproot)
        """
        from script_utils import get_witness_size_estimate
        
        script_type = output.get('script_type', 'cltv_payment_channel')
        path = 'refund' if self.use_refund_path else 'cooperative'
        
        return get_witness_size_estimate(script_type, path)
    
    # Helper methods are now inherited from base class
