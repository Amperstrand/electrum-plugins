"""
Data Publishing Sweeper (BIP-65 Example #5)

Handles spending from data publishing contracts with two paths:
1. Publisher path: Reveal data preimage + signature
2. Buyer refund path: After timeout, no preimage needed

Witness stack construction:
- Publisher: [signature, preimage, 1, script]
- Buyer refund: [signature, 0, script]
"""

from typing import List, Dict, Any
from .base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from script_utils import get_signature_type, SignatureType


class DataPublishingSweeper(SweeperStrategy):
    """
    Sweeper for data publishing (PayPub) scripts.
    
    Supports both publisher path (reveal preimage) and buyer refund path (timeout).
    Works with both P2WSH and Taproot formats.
    
    Witness structure:
    - Publisher path: [signature, preimage, 1, script]
    - Buyer refund path: [signature, 0, script]
    """
    
    SCRIPT_TYPE = "cltv_data_publishing"
    
    def __init__(self, use_refund_path: bool = False, data_preimage: str = None, **kwargs):
        """
        Initialize sweeper.
        
        Args:
            use_refund_path: If True, use buyer refund path; if False, use publisher path
            data_preimage: Required for publisher path (ignored for refund path)
            **kwargs: Additional parameters (ignored for compatibility)
        """
        self.use_refund_path = use_refund_path
        self.data_preimage = data_preimage
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Data publishing needs 1 key depending on path.
        
        Returns:
            ['publisher_private_key'] for publisher path
            ['buyer_private_key'] for buyer refund path
        """
        if self.use_refund_path:
            return ['buyer_private_key']
        else:
            return ['publisher_private_key']
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for data publishing.
        
        Args:
            output: Output data with script_hex, script_type, data_preimage
            keys: Dict of private keys  
            sighash: The sighash to sign
            
        Returns:
            Publisher: [signature, preimage, 1, script]
            Buyer refund: [signature, 0, script]
        """
        # Get the key for this path
        key_ids = self.get_required_keys(output)
        key = keys.get(key_ids[0])
        
        if not key:
            raise ValidationError(f"Key {key_ids[0]} not provided")
        
        # Determine signature type from script type
        script_type = output.get('script_type', 'cltv_data_publishing_p2wsh')
        sig_type = get_signature_type(script_type)
        
        # Sign (ECDSA for P2WSH)
        sig = self._ecdsa_sign(key, sighash)
        
        # Get script
        script = bytes.fromhex(output['script_hex'])
        
        # Build witness based on path
        if self.use_refund_path:
            # Buyer refund path: [signature, 0, script]
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                sig,
                0,  # False - triggers ELSE branch (buyer refund)
                script
            ]
        else:
            # Publisher path: [signature, preimage, 1, script]
            # Get the data preimage from constructor, output, or kwargs
            data_preimage = self.data_preimage or output.get('data_preimage') or kwargs.get('data_preimage')
            if not data_preimage:
                raise ValidationError("data_preimage required for publisher path")
            
            # Convert string to bytes if needed
            if isinstance(data_preimage, str):
                # Check if it's a hex string (even length, hex chars only)
                if len(data_preimage) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in data_preimage):
                    preimage_bytes = bytes.fromhex(data_preimage)
                else:
                    preimage_bytes = data_preimage.encode('utf-8')
            else:
                preimage_bytes = bytes.fromhex(data_preimage)
            
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                sig,
                preimage_bytes,
                1,  # True - triggers IF branch (publisher reveals key)
                script
            ]
        
        return witness
    
    def validate_sweep_conditions(
        self,
        output: Dict[str, Any],
        current_height: int,
        **kwargs
    ) -> bool:
        """
        Validate that sweep conditions are met.
        
        Args:
            output: Output data with locktime
            current_height: Current blockchain height
            **kwargs: Additional validation context
        
        Returns:
            True if sweep is valid, False otherwise
        """
        if self.use_refund_path:
            # Buyer refund requires locktime to pass
            locktime = output.get('locktime', 0)
            if current_height < locktime:
                raise LockedError(
                    f"Cannot spend buyer refund yet. "
                    f"Current: {current_height}, Required: {locktime}"
                )
            return True
        else:
            # Publisher can spend immediately
            return True
    
    def can_spend_now(self, output: Dict[str, Any], current_height: int) -> bool:
        """
        Check if output can be spent at current height.
        
        Args:
            output: Output with locktime
            current_height: Current block height
            
        Returns:
            Publisher path: Always true (no time lock)
            Buyer refund path: True only if current_height >= locktime
        """
        if self.use_refund_path:
            # Buyer refund requires locktime to pass
            locktime = output.get('locktime', 0)
            if current_height < locktime:
                raise LockedError(
                    f"Cannot spend buyer refund yet. "
                    f"Current: {current_height}, Required: {locktime}"
                )
            return True
        else:
            # Publisher can spend immediately
            return True


# Example usage
if __name__ == '__main__':
    """
    Demo: Witness stack construction for both paths
    """
    import hashlib
    
    # Test data
    test_data = "Secret BIP-65 data publishing example"
    data_preimage = test_data.encode('utf-8').hex()
    data_hash = hashlib.sha256(test_data.encode('utf-8')).digest().hex()
    
    print("=" * 80)
    print("Data Publishing Sweeper Demo")
    print("=" * 80)
    print(f"Test Data: {test_data}")
    print(f"Data Preimage (hex): {data_preimage}")
    print(f"Data Hash (SHA256): {data_hash}")
    print()
    print("=" * 80)
    print("Witness Stack Construction:")
    print("=" * 80)
    print("1. Publisher Path (reveal preimage):")
    print("   - use_refund_path: False")
    print("   - Witness: [sig, preimage, 1, script]")
    print("   - Can spend: Immediately")
    print()
    print("2. Buyer Refund Path (after timeout):")
    print("   - use_refund_path: True")
    print("   - Witness: [sig, 0, script]")
    print("   - Can spend: Only after locktime")
    print("=" * 80)
