"""
Base Sweeper Strategy - Abstract interface for all CLTV sweepers

Each script type implements this interface to provide:
1. Required keys identification
2. Witness stack construction  
3. Sweep condition validation

Now supports Bitcoin Core's SignatureData pattern for centralized signing.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from ..signature_data import SignatureData


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
            Script type identifier (e.g., "cltv_hodl")
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
    
    # ====================================================================
    # DRY witness stack helpers (optional)
    # ====================================================================
    def _build_single_sig_witness(
        self,
        script: bytes,
        signature: bytes,
        control_block_hex: Optional[str] = None,
    ) -> List[bytes]:
        """
        Build single-signature witness stack for simple scripts.

        Returns:
            - P2WSH: [signature, script]
            - Taproot: [signature, script, control_block]
        """
        witness: List[bytes] = [signature, script]
        if control_block_hex:
            witness.append(bytes.fromhex(control_block_hex))
        return witness

    def _build_multisig_witness(
        self,
        script: bytes,
        signatures: List[bytes],
        branch_selector: int,
        *,
        add_bug_op0: bool = True,
        control_block_hex: Optional[str] = None,
    ) -> List[bytes]:
        """
        Build multisig witness stack for IF/ELSE and CHECKMULTISIG patterns.

        Args:
            script: Redeem script/tapscript bytes
            signatures: Ordered list of signatures (e.g., [sender_sig, receiver_sig])
            branch_selector: 1 for IF-branch, 0 for ELSE-branch
            add_bug_op0: Include leading OP_0 element for CHECKMULTISIG bug (P2WSH)
            control_block_hex: Optional Taproot control block (hex)

        Returns:
            List suitable for witness serialization
        """
        witness: List[bytes] = []
        if add_bug_op0:
            # Represent OP_0 as integer; serializer will encode minimally
            witness.append(0)  # CHECKMULTISIG bug workaround (P2WSH only)
        witness.extend(signatures)
        witness.append(branch_selector)  # 1 -> IF, 0 -> ELSE
        witness.append(script)
        if control_block_hex:
            witness.append(bytes.fromhex(control_block_hex))
        return witness

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
        Sign with Schnorr (for Taproot) - uses single source of truth.
        
        Args:
            private_key: ECPrivkey object, hex string, or bytes
            sighash: 32-byte sighash
        
        Returns:
            64-byte Schnorr signature
        """
        try:
            from electrum_ecc import ECPrivkey
            from .generic import _create_schnorr_signature
            
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
            
            # Use single source of truth for signature creation
            return _create_schnorr_signature(privkey, sighash)
        
        except ImportError:
            raise ValidationError("electrum_ecc not available for Schnorr signing")
    
    # ====================================================================
    # SignatureData pattern (Bitcoin Core aligned)
    # ====================================================================
    
    def create_sigdata(self, output: Dict[str, Any]) -> SignatureData:
        """
        Create a SignatureData instance for this output.
        
        Follows Bitcoin Core's pattern where SignatureData holds all
        signing-related information for an input.
        
        Args:
            output: Output data containing script info
            
        Returns:
            SignatureData instance ready for signing
        """
        sigdata = SignatureData()
        
        # Set witness script for P2WSH
        if 'script_hex' in output:
            sigdata.witness_script = bytes.fromhex(output['script_hex'])
        
        return sigdata
    
    def sign_with_sigdata(
        self,
        sigdata: SignatureData,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> SignatureData:
        """
        Sign and populate SignatureData.
        
        This method handles signing and adds signatures to the SignatureData.
        Override in subclasses for script-specific signing logic.
        
        Args:
            sigdata: SignatureData to populate
            output: Output data
            keys: Dict of {key_id: private_key_bytes}
            sighash: The sighash to sign
            **kwargs: Script-specific data
            
        Returns:
            Updated SignatureData with signatures
        """
        # Get required keys
        key_ids = self.get_required_keys(output)
        
        # Get script type
        script_type = output.get('script_type', '')
        is_taproot = 'taproot' in script_type.lower()
        
        # Sign with each required key
        for key_id in key_ids:
            key = keys.get(key_id)
            if not key:
                continue  # Key not provided
            
            # Get public key from private key
            from electrum_ecc import ECPrivkey
            if isinstance(key, str):
                key = bytes.fromhex(key)
            privkey = ECPrivkey(key)
            pubkey = privkey.get_public_key_bytes(compressed=True)
            
            if is_taproot:
                # Schnorr signature for Taproot
                sig = self._schnorr_sign(key, sighash)
                # For script-path, we need the leaf hash
                # Use xonly pubkey (drop prefix byte)
                xonly_pubkey = pubkey[1:]  # 32-byte x-only
                # Get leaf hash from output if available
                leaf_hash = kwargs.get('leaf_hash', bytes(32))
                sigdata.add_schnorr_signature(xonly_pubkey, leaf_hash, sig)
            else:
                # ECDSA signature for P2WSH
                sig = self._ecdsa_sign(key, sighash)
                sigdata.add_signature(pubkey, sig)
        
        return sigdata
    
    def build_witness_from_sigdata(
        self,
        sigdata: SignatureData,
        output: Dict[str, Any],
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack from SignatureData.
        
        Args:
            sigdata: Populated SignatureData
            output: Output data
            **kwargs: Script-specific data
            
        Returns:
            Witness stack as list of bytes
        """
        script_type = output.get('script_type', '')
        is_taproot = 'taproot' in script_type.lower()
        
        if is_taproot:
            # Taproot witness
            script = sigdata.witness_script or bytes.fromhex(output.get('script_hex', ''))
            control_block = bytes.fromhex(output.get('control_block', ''))
            return sigdata.build_taproot_witness(script, control_block)
        else:
            # P2WSH witness
            return sigdata.build_p2wsh_witness()


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
