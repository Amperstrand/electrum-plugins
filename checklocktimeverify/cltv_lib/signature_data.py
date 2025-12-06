"""
SignatureData - Centralized signing data structure.

Mirrors Bitcoin Core's SignatureData struct from sign.h.
Centralizes all signing-related data for a transaction input.

This pattern enables:
1. Cleaner sweeper code (pass one struct instead of many params)
2. Support for partial signing (PSBT-style)
3. Standardized preimage handling for hash-locked contracts
4. Taproot script-path signing with proper control blocks

Reference: bitcoin/src/script/sign.h lines 77-110

Usage:
    >>> sigdata = SignatureData()
    >>> sigdata.witness_script = cltv_script
    >>> sigdata.add_signature(pubkey, signature)
    >>> sigdata.add_preimage(hash160_value, preimage_bytes)
    >>> if sigdata.is_complete():
    ...     witness = sigdata.build_witness()
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from .builders.taproot.taproot_tree_builder import TaprootSpendData


@dataclass
class SignatureData:
    """
    Signing data for a single transaction input.
    
    Mirrors Bitcoin Core's SignatureData struct.
    Used across all sweepers for consistent signing.
    
    Attributes:
        complete: Whether the input is fully signed
        witness: Whether this is a witness input (always True for us)
        witness_script: The witness script (for P2WSH)
        script_witness: The witness stack (list of witness items)
        
        # Taproot-specific
        tr_spenddata: Taproot spending data (control blocks, scripts)
        taproot_key_path_sig: Schnorr signature for key-path spending
        taproot_script_sigs: Map of (xonly_pubkey, leaf_hash) → signature
        
        # Signatures (for non-Taproot)
        signatures: Map of pubkey → (pubkey, signature)
        
        # Preimages for hash-locked contracts (HTLC, data publishing)
        hash160_preimages: Map of HASH160 → preimage
        sha256_preimages: Map of SHA256 → preimage
        ripemd160_preimages: Map of RIPEMD160 → preimage
        hash256_preimages: Map of HASH256 → preimage
    """
    
    # Completion status
    complete: bool = False
    witness: bool = True  # Always True for our plugin (no legacy support)
    
    # Scripts
    witness_script: Optional[bytes] = None  # For P2WSH
    script_witness: List[bytes] = field(default_factory=list)  # Witness stack
    
    # Taproot-specific
    tr_spenddata: Optional[TaprootSpendData] = None
    taproot_key_path_sig: Optional[bytes] = None  # 64-byte Schnorr sig
    taproot_script_sigs: Dict[Tuple[bytes, bytes], bytes] = field(default_factory=dict)
    # Key: (32-byte xonly pubkey, 32-byte leaf_hash), Value: 64-byte Schnorr sig
    
    # Signatures for P2WSH (non-Taproot)
    signatures: Dict[bytes, Tuple[bytes, bytes]] = field(default_factory=dict)
    # Key: pubkey_hash (20 bytes), Value: (pubkey, DER signature)
    
    # Preimages for hash-locked contracts
    hash160_preimages: Dict[bytes, bytes] = field(default_factory=dict)
    sha256_preimages: Dict[bytes, bytes] = field(default_factory=dict)
    ripemd160_preimages: Dict[bytes, bytes] = field(default_factory=dict)
    hash256_preimages: Dict[bytes, bytes] = field(default_factory=dict)
    
    def add_signature(self, pubkey: bytes, signature: bytes) -> None:
        """
        Add a signature for a public key (P2WSH).
        
        Args:
            pubkey: Public key (33 bytes compressed)
            signature: DER-encoded ECDSA signature
        """
        from electrum.crypto import hash_160
        pubkey_hash = hash_160(pubkey)
        self.signatures[pubkey_hash] = (pubkey, signature)
    
    def add_schnorr_signature(
        self, 
        xonly_pubkey: bytes, 
        leaf_hash: bytes, 
        signature: bytes
    ) -> None:
        """
        Add a Schnorr signature for Taproot script-path spending.
        
        Args:
            xonly_pubkey: 32-byte x-only public key
            leaf_hash: 32-byte TapLeaf hash
            signature: 64-byte Schnorr signature
        """
        self.taproot_script_sigs[(xonly_pubkey, leaf_hash)] = signature
    
    def add_preimage(self, hash_value: bytes, preimage: bytes, hash_type: str = 'hash160') -> None:
        """
        Add a preimage for hash-locked contracts.
        
        Args:
            hash_value: The hash that the preimage reveals
            preimage: The preimage data
            hash_type: Type of hash ('hash160', 'sha256', 'ripemd160', 'hash256')
        """
        preimage_maps = {
            'hash160': self.hash160_preimages,
            'sha256': self.sha256_preimages,
            'ripemd160': self.ripemd160_preimages,
            'hash256': self.hash256_preimages,
        }
        if hash_type not in preimage_maps:
            raise ValueError(f"Unknown hash type: {hash_type}")
        preimage_maps[hash_type][hash_value] = preimage
    
    def get_preimage(self, hash_value: bytes, hash_type: str = 'hash160') -> Optional[bytes]:
        """
        Get a preimage for a hash value.
        
        Args:
            hash_value: The hash to look up
            hash_type: Type of hash ('hash160', 'sha256', 'ripemd160', 'hash256')
            
        Returns:
            The preimage if found, None otherwise
        """
        preimage_maps = {
            'hash160': self.hash160_preimages,
            'sha256': self.sha256_preimages,
            'ripemd160': self.ripemd160_preimages,
            'hash256': self.hash256_preimages,
        }
        if hash_type not in preimage_maps:
            raise ValueError(f"Unknown hash type: {hash_type}")
        return preimage_maps[hash_type].get(hash_value)
    
    def is_complete(self) -> bool:
        """Check if signing is complete."""
        return self.complete
    
    def mark_complete(self) -> None:
        """Mark signing as complete."""
        self.complete = True
    
    def build_p2wsh_witness(self) -> List[bytes]:
        """
        Build witness stack for P2WSH spending.
        
        The witness stack for P2WSH is:
        [signature(s)...] [preimage(s)...] [witness_script]
        
        Returns:
            List of witness stack items
        """
        witness = list(self.script_witness)  # Start with any pre-set items
        
        # Add signatures in order
        for pubkey_hash, (pubkey, sig) in self.signatures.items():
            witness.append(sig)
        
        # Add preimages (for data publishing, etc.)
        for preimage in self.hash160_preimages.values():
            witness.append(preimage)
        
        # Add witness script at the end
        if self.witness_script:
            witness.append(self.witness_script)
        
        return witness
    
    def build_taproot_witness(self, script: bytes, control_block: bytes) -> List[bytes]:
        """
        Build witness stack for Taproot script-path spending.
        
        The witness stack for Taproot script-path is:
        [signature(s)...] [preimage(s)...] [script] [control_block]
        
        Args:
            script: The Tapscript being executed
            control_block: Control block for this script path
            
        Returns:
            List of witness stack items
        """
        witness = list(self.script_witness)  # Start with any pre-set items
        
        # Add Schnorr signatures
        for (xonly_pubkey, leaf_hash), sig in self.taproot_script_sigs.items():
            witness.append(sig)
        
        # Add preimages (for data publishing, etc.)
        for preimage in self.hash160_preimages.values():
            witness.append(preimage)
        
        # Add script and control block at the end
        witness.append(script)
        witness.append(control_block)
        
        return witness
    
    def merge(self, other: 'SignatureData') -> None:
        """
        Merge another SignatureData into this one.
        
        Used for combining partial signatures (PSBT-style).
        
        Args:
            other: SignatureData to merge in
        """
        # Merge signatures
        self.signatures.update(other.signatures)
        self.taproot_script_sigs.update(other.taproot_script_sigs)
        
        # Merge preimages
        self.hash160_preimages.update(other.hash160_preimages)
        self.sha256_preimages.update(other.sha256_preimages)
        self.ripemd160_preimages.update(other.ripemd160_preimages)
        self.hash256_preimages.update(other.hash256_preimages)
        
        # Take Taproot spending data if we don't have it
        if other.tr_spenddata and not self.tr_spenddata:
            self.tr_spenddata = other.tr_spenddata
        
        # Take key path sig if we don't have it
        if other.taproot_key_path_sig and not self.taproot_key_path_sig:
            self.taproot_key_path_sig = other.taproot_key_path_sig
        
        # Take witness script if we don't have it
        if other.witness_script and not self.witness_script:
            self.witness_script = other.witness_script
        
        # Complete if either is complete
        if other.complete:
            self.complete = True


__all__ = ['SignatureData']

