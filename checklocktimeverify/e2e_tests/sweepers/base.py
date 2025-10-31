"""
Base Sweeper Strategy - Abstract interface for all CLTV sweepers

Each script type implements this interface to provide:
1. Required keys identification
2. Witness stack construction  
3. Sweep condition validation
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class SweeperStrategy(ABC):
    """
    Abstract base class for script-specific sweep logic.
    
    Each CLTV script type (simple, multisig, HTLC, etc.) implements this
    interface to encapsulate its specific sweep requirements.
    """
    
    @abstractmethod
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Identify which keys are needed to sweep this output.
        
        Args:
            output: CLTV output data containing script_params
        
        Returns:
            List of key identifiers (derivation paths or key IDs)
            
        Examples:
            Simple CLTV: ["m/84'/1'/0'/0/5"]
            Multisig 2-of-3: ["m/48'/1'/0'/2'/0/0", "m/48'/1'/1'/2'/0/0"]
            HTLC hash path: [] (no keys needed!)
        """
        pass
    
    @abstractmethod
    def build_witness(
        self, 
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for this script type.
        
        Args:
            output: CLTV output data
            keys: Dict of {key_id: private_key_bytes}
            sighash: The sighash to sign
            **kwargs: Script-specific data (preimage, etc.)
        
        Returns:
            List of witness stack items (bottom to top)
            
        Examples:
            Simple P2SH: [signature, script]
            Multisig P2SH: [OP_0, sig1, sig2, script]
            Taproot: [signature, script, control_block]
            HTLC hash: [preimage, script]
        """
        pass
    
    @abstractmethod
    def validate_sweep_conditions(
        self,
        output: Dict[str, Any],
        current_height: int,
        **kwargs
    ) -> bool:
        """
        Check if sweep is possible under current conditions.
        
        Args:
            output: CLTV output data
            current_height: Current blockchain height
            **kwargs: Additional validation context
        
        Returns:
            True if sweep is valid, False otherwise
            
        Examples:
            CLTV: current_height >= locktime
            HTLC hash path: preimage is available
            HTLC refund: current_height >= locktime
        """
        pass
    
    def get_script_type(self) -> str:
        """
        Get the script type this sweeper handles.
        
        Returns:
            Script type identifier (e.g., "cltv_simple_hodl")
        """
        return getattr(self, 'SCRIPT_TYPE', 'unknown')
    
    def estimate_witness_size(self, output: Dict[str, Any]) -> int:
        """
        Estimate witness size for fee calculation.
        
        Args:
            output: CLTV output data
        
        Returns:
            Estimated witness size in bytes
        """
        # Default implementation - override for accuracy
        # Simple CLTV: ~107 bytes (sig + script)
        # Multisig: ~(70 * m + script_size) bytes
        return 150  # Conservative default
    
    # DRY signing methods - shared by all sweepers
    def _ecdsa_sign(self, private_key, sighash: bytes) -> bytes:
        """
        Sign with ECDSA (for P2WSH).
        
        Args:
            private_key: ECPrivkey object, hex string, or bytes
            sighash: 32-byte sighash
        
        Returns:
            DER-encoded signature with SIGHASH_ALL appended
        """
        try:
            from electrum_ecc import ECPrivkey, ecdsa_der_sig_from_ecdsa_sig64
            
            # Handle different private key types
            if isinstance(private_key, str):
                # Hex string - convert to bytes
                private_key = bytes.fromhex(private_key)
                privkey = ECPrivkey(private_key)
            elif hasattr(private_key, 'get_secret_bytes'):
                # Already an ECPrivkey object
                privkey = private_key
            else:
                # Assume it's bytes
                privkey = ECPrivkey(private_key)
            
            sig_compact = privkey.ecdsa_sign(sighash)
            sig_der = ecdsa_der_sig_from_ecdsa_sig64(sig_compact)
            
            return sig_der + b'\x01'  # SIGHASH_ALL
        
        except ImportError:
            raise ValidationError("electrum_ecc not available for ECDSA signing")
    
    def _schnorr_sign(self, private_key, sighash: bytes) -> bytes:
        """
        Sign with Schnorr (for Taproot).
        
        Args:
            private_key: ECPrivkey object, hex string, or bytes
            sighash: 32-byte sighash
        
        Returns:
            64-byte Schnorr signature
        """
        try:
            from electrum_ecc import ECPrivkey
            
            # Handle different private key types
            if isinstance(private_key, str):
                # Hex string - convert to bytes
                private_key = bytes.fromhex(private_key)
                privkey = ECPrivkey(private_key)
            elif hasattr(private_key, 'get_secret_bytes'):
                # Already an ECPrivkey object
                privkey = private_key
            else:
                # Assume it's bytes
                privkey = ECPrivkey(private_key)
            
            sig = privkey.schnorr_sign(sighash, aux_rand32=None)
            
            return sig  # Schnorr signatures are exactly 64 bytes, no hash type
        
        except ImportError:
            raise ValidationError("electrum_ecc not available for Schnorr signing")


class SweepError(Exception):
    """Base exception for sweep errors"""
    pass


class InsufficientKeysError(SweepError):
    """Not enough keys available to sweep"""
    pass


class LockedError(SweepError):
    """Output is still locked (timelock not reached)"""
    pass


class ValidationError(SweepError):
    """Sweep validation failed"""
    pass
