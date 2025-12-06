"""
PSBT Helper for CLTV Plugin

Extends Electrum's native PSBT support with:
- BIP-371 Taproot script-path fields (TAP_SCRIPT_SIG, TAP_LEAF_SCRIPT, etc.)
- BIP-174 hash preimage fields (HASH160 for data publishing)

Uses Electrum's PartialTransaction as the base, storing extended fields
in the _unknown dict which Electrum preserves during serialization.

Reference:
- BIP-174: Partially Signed Bitcoin Transaction Format
- BIP-371: Taproot PSBT Extensions

Usage:
    >>> from cltv_lib.psbt_helper import CLTVPsbtHelper
    >>> 
    >>> # Create PSBT from unsigned tx
    >>> helper = CLTVPsbtHelper()
    >>> psbt = helper.create_psbt(unsigned_tx, inputs_data)
    >>> 
    >>> # Add Taproot script-path data
    >>> helper.add_taproot_script_path(psbt.inputs()[0], leaf_script, control_block)
    >>> 
    >>> # Add hash preimage for data publishing
    >>> helper.add_hash160_preimage(psbt.inputs()[0], hash_value, preimage)
    >>> 
    >>> # Serialize to share with hardware wallet
    >>> psbt_bytes = helper.serialize(psbt)
"""

from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

# Electrum imports
from electrum.transaction import (
    PartialTransaction, 
    PartialTxInput, 
    PartialTxOutput,
    Transaction,
    var_int,
)


# BIP-174 Hash Preimage Types (not in Electrum)
class PSBTPreimageType:
    """BIP-174 preimage field types."""
    RIPEMD160 = 0x0A
    SHA256 = 0x0B
    HASH160 = 0x0C
    HASH256 = 0x0D


# BIP-371 Taproot Script-Path Types (not in Electrum)
class PSBTTaprootType:
    """BIP-371 Taproot field types."""
    TAP_KEY_SIG = 0x13        # In Electrum (key-path)
    TAP_SCRIPT_SIG = 0x14     # NOT in Electrum (script-path)
    TAP_LEAF_SCRIPT = 0x15    # NOT in Electrum
    TAP_BIP32_DERIVATION = 0x16  # NOT in Electrum
    TAP_INTERNAL_KEY = 0x17   # NOT in Electrum
    TAP_MERKLE_ROOT = 0x18    # In Electrum


@dataclass
class TaprootLeafInfo:
    """Information about a Taproot leaf script."""
    script: bytes           # The leaf script
    leaf_version: int       # Usually TAPSCRIPT_LEAF_VERSION for Tapscript
    control_block: bytes    # Full control block


class CLTVPsbtHelper:
    """
    Helper class for creating and handling PSBTs for CLTV plugin.
    
    Extends Electrum's PSBT support with Taproot script-path
    and hash preimage fields.
    """
    
    def __init__(self):
        """Initialize helper."""
        pass
    
    # ========================================================================
    # PSBT Creation
    # ========================================================================
    
    def create_psbt(
        self, 
        unsigned_tx: Transaction,
        *,
        strip_witness: bool = True
    ) -> PartialTransaction:
        """
        Create a PSBT from an unsigned transaction.
        
        Uses Electrum's native PartialTransaction.from_tx().
        
        Args:
            unsigned_tx: Unsigned transaction
            strip_witness: Remove witness data (default True for PSBT)
            
        Returns:
            PartialTransaction (Electrum's PSBT class)
        """
        return PartialTransaction.from_tx(unsigned_tx, strip_witness=strip_witness)
    
    def create_psbt_from_raw(self, raw_psbt: bytes) -> PartialTransaction:
        """
        Parse a raw PSBT (bytes, hex, or base64).
        
        Uses Electrum's native parser.
        
        Args:
            raw_psbt: PSBT in bytes, hex string, or base64
            
        Returns:
            PartialTransaction
        """
        return PartialTransaction.from_raw_psbt(raw_psbt)
    
    # ========================================================================
    # P2WSH Support (fully Electrum native)
    # ========================================================================
    
    def set_witness_script(self, txin: PartialTxInput, witness_script: bytes) -> None:
        """
        Set the witness script for a P2WSH input.
        
        This is fully supported by Electrum.
        
        Args:
            txin: PSBT input
            witness_script: The witness script (CLTV script)
        """
        txin.witness_script = witness_script
    
    def add_ecdsa_signature(
        self, 
        txin: PartialTxInput, 
        pubkey: bytes, 
        signature: bytes
    ) -> None:
        """
        Add an ECDSA signature to a P2WSH input.
        
        This is fully supported by Electrum.
        
        Args:
            txin: PSBT input
            pubkey: Public key (33 or 65 bytes)
            signature: DER-encoded signature with sighash byte
        """
        txin.sigs_ecdsa[pubkey] = signature
    
    # ========================================================================
    # Taproot Key-Path (Electrum native)
    # ========================================================================
    
    def set_tap_key_sig(self, txin: PartialTxInput, signature: bytes) -> None:
        """
        Set the Taproot key-path signature.
        
        This is supported by Electrum.
        
        Args:
            txin: PSBT input
            signature: 64 or 65 byte Schnorr signature
        """
        txin.tap_key_sig = signature
    
    def set_tap_merkle_root(self, txin: PartialTxInput, merkle_root: bytes) -> None:
        """
        Set the Taproot merkle root.
        
        This is supported by Electrum.
        
        Args:
            txin: PSBT input
            merkle_root: 32-byte merkle root
        """
        txin.tap_merkle_root = merkle_root
    
    # ========================================================================
    # Taproot Script-Path (custom extension for BIP-371)
    # ========================================================================
    
    def add_tap_internal_key(self, txin: PartialTxInput, internal_key: bytes) -> None:
        """
        Add Taproot internal key (BIP-371: 0x17).
        
        Not natively supported by Electrum - stored in _unknown.
        
        Args:
            txin: PSBT input
            internal_key: 32-byte x-only internal pubkey
        """
        if len(internal_key) != 32:
            raise ValueError(f"Internal key must be 32 bytes, got {len(internal_key)}")
        
        # Key format: just the type byte
        key = bytes([PSBTTaprootType.TAP_INTERNAL_KEY])
        txin._unknown[key] = internal_key
    
    def add_tap_leaf_script(
        self, 
        txin: PartialTxInput, 
        leaf_info: TaprootLeafInfo
    ) -> None:
        """
        Add a Taproot leaf script (BIP-371: 0x15).
        
        Not natively supported by Electrum - stored in _unknown.
        
        Args:
            txin: PSBT input
            leaf_info: TaprootLeafInfo with script and control block
        """
        # Key format: type + control_block
        key = bytes([PSBTTaprootType.TAP_LEAF_SCRIPT]) + leaf_info.control_block
        
        # Value format: script + leaf_version
        value = leaf_info.script + bytes([leaf_info.leaf_version])
        
        txin._unknown[key] = value
    
    def add_tap_script_sig(
        self,
        txin: PartialTxInput,
        xonly_pubkey: bytes,
        leaf_hash: bytes,
        signature: bytes
    ) -> None:
        """
        Add a Taproot script-path signature (BIP-371: 0x14).
        
        Not natively supported by Electrum - stored in _unknown.
        
        Args:
            txin: PSBT input
            xonly_pubkey: 32-byte x-only public key
            leaf_hash: 32-byte TapLeaf hash
            signature: 64 or 65 byte Schnorr signature
        """
        if len(xonly_pubkey) != 32:
            raise ValueError(f"X-only pubkey must be 32 bytes, got {len(xonly_pubkey)}")
        if len(leaf_hash) != 32:
            raise ValueError(f"Leaf hash must be 32 bytes, got {len(leaf_hash)}")
        if len(signature) not in (64, 65):
            raise ValueError(f"Signature must be 64 or 65 bytes, got {len(signature)}")
        
        # Key format: type + xonly_pubkey + leaf_hash
        key = bytes([PSBTTaprootType.TAP_SCRIPT_SIG]) + xonly_pubkey + leaf_hash
        txin._unknown[key] = signature
    
    def get_tap_internal_key(self, txin: PartialTxInput) -> Optional[bytes]:
        """Get Taproot internal key from PSBT input."""
        key = bytes([PSBTTaprootType.TAP_INTERNAL_KEY])
        return txin._unknown.get(key)
    
    def get_tap_leaf_scripts(self, txin: PartialTxInput) -> List[TaprootLeafInfo]:
        """Get all Taproot leaf scripts from PSBT input."""
        results = []
        prefix = bytes([PSBTTaprootType.TAP_LEAF_SCRIPT])
        
        for key, value in txin._unknown.items():
            if key.startswith(prefix):
                control_block = key[1:]  # Remove type byte
                script = value[:-1]      # Remove leaf version
                leaf_version = value[-1]
                results.append(TaprootLeafInfo(
                    script=script,
                    leaf_version=leaf_version,
                    control_block=control_block
                ))
        
        return results
    
    def get_tap_script_sigs(
        self, 
        txin: PartialTxInput
    ) -> Dict[Tuple[bytes, bytes], bytes]:
        """
        Get all Taproot script-path signatures.
        
        Returns:
            Dict of (xonly_pubkey, leaf_hash) -> signature
        """
        results = {}
        prefix = bytes([PSBTTaprootType.TAP_SCRIPT_SIG])
        
        for key, value in txin._unknown.items():
            if key.startswith(prefix):
                xonly_pubkey = key[1:33]
                leaf_hash = key[33:65]
                results[(xonly_pubkey, leaf_hash)] = value
        
        return results
    
    # ========================================================================
    # Hash Preimages (custom extension for BIP-174)
    # ========================================================================
    
    def add_hash160_preimage(
        self, 
        txin: PartialTxInput, 
        hash_value: bytes, 
        preimage: bytes
    ) -> None:
        """
        Add a HASH160 preimage (BIP-174: 0x0C).
        
        Used for data publishing contracts.
        Not natively supported by Electrum - stored in _unknown.
        
        Args:
            txin: PSBT input
            hash_value: 20-byte HASH160
            preimage: The preimage that hashes to hash_value
        """
        if len(hash_value) != 20:
            raise ValueError(f"HASH160 must be 20 bytes, got {len(hash_value)}")
        
        # Verify preimage is correct
        from electrum.crypto import hash_160
        if hash_160(preimage) != hash_value:
            raise ValueError("Preimage does not match hash")
        
        # Key format: type + hash_value
        key = bytes([PSBTPreimageType.HASH160]) + hash_value
        txin._unknown[key] = preimage
    
    def add_sha256_preimage(
        self, 
        txin: PartialTxInput, 
        hash_value: bytes, 
        preimage: bytes
    ) -> None:
        """
        Add a SHA256 preimage (BIP-174: 0x0B).
        
        Args:
            txin: PSBT input
            hash_value: 32-byte SHA256
            preimage: The preimage that hashes to hash_value
        """
        if len(hash_value) != 32:
            raise ValueError(f"SHA256 must be 32 bytes, got {len(hash_value)}")
        
        # Verify preimage is correct
        from electrum.crypto import sha256
        if sha256(preimage) != hash_value:
            raise ValueError("Preimage does not match hash")
        
        # Key format: type + hash_value
        key = bytes([PSBTPreimageType.SHA256]) + hash_value
        txin._unknown[key] = preimage
    
    def get_hash160_preimages(self, txin: PartialTxInput) -> Dict[bytes, bytes]:
        """
        Get all HASH160 preimages from PSBT input.
        
        Returns:
            Dict of hash_value -> preimage
        """
        results = {}
        prefix = bytes([PSBTPreimageType.HASH160])
        
        for key, value in txin._unknown.items():
            if key.startswith(prefix):
                hash_value = key[1:21]
                results[hash_value] = value
        
        return results
    
    # ========================================================================
    # Integration with SignatureData
    # ========================================================================
    
    def from_signature_data(
        self,
        txin: PartialTxInput,
        sigdata: 'SignatureData',
        is_taproot: bool = False
    ) -> None:
        """
        Populate PSBT input from SignatureData.
        
        Bridges our SignatureData pattern to PSBT format.
        
        Args:
            txin: PSBT input to populate
            sigdata: SignatureData with signatures and preimages
            is_taproot: Whether this is a Taproot input
        """
        from .signature_data import SignatureData
        
        # Set witness script
        if sigdata.witness_script:
            txin.witness_script = sigdata.witness_script
        
        if is_taproot:
            # Taproot script-path signatures
            for (xonly_pubkey, leaf_hash), sig in sigdata.taproot_script_sigs.items():
                self.add_tap_script_sig(txin, xonly_pubkey, leaf_hash, sig)
            
            # Taproot key-path signature
            if sigdata.taproot_key_path_sig:
                txin.tap_key_sig = sigdata.taproot_key_path_sig
        else:
            # ECDSA signatures for P2WSH
            for pubkey_hash, (pubkey, sig) in sigdata.signatures.items():
                txin.sigs_ecdsa[pubkey] = sig
        
        # Hash preimages
        for hash_value, preimage in sigdata.hash160_preimages.items():
            self.add_hash160_preimage(txin, hash_value, preimage)
    
    def to_signature_data(
        self,
        txin: PartialTxInput,
        is_taproot: bool = False
    ) -> 'SignatureData':
        """
        Extract SignatureData from PSBT input.
        
        Bridges PSBT format to our SignatureData pattern.
        
        Args:
            txin: PSBT input
            is_taproot: Whether this is a Taproot input
            
        Returns:
            SignatureData with extracted info
        """
        from .signature_data import SignatureData
        
        sigdata = SignatureData()
        
        # Witness script
        if txin.witness_script:
            sigdata.witness_script = txin.witness_script
        
        if is_taproot:
            # Taproot script-path signatures
            for (xonly_pubkey, leaf_hash), sig in self.get_tap_script_sigs(txin).items():
                sigdata.add_schnorr_signature(xonly_pubkey, leaf_hash, sig)
            
            # Taproot key-path signature
            if txin.tap_key_sig:
                sigdata.taproot_key_path_sig = txin.tap_key_sig
        else:
            # ECDSA signatures
            for pubkey, sig in txin.sigs_ecdsa.items():
                from electrum.crypto import hash_160
                sigdata.signatures[hash_160(pubkey)] = (pubkey, sig)
        
        # Hash preimages
        for hash_value, preimage in self.get_hash160_preimages(txin).items():
            sigdata.hash160_preimages[hash_value] = preimage
        
        return sigdata
    
    # ========================================================================
    # Serialization
    # ========================================================================
    
    def serialize(self, psbt: PartialTransaction) -> bytes:
        """
        Serialize PSBT to bytes.
        
        Uses Electrum's native serialization which preserves _unknown fields.
        
        Args:
            psbt: PartialTransaction
            
        Returns:
            PSBT bytes
        """
        return psbt.serialize_as_bytes()
    
    def serialize_base64(self, psbt: PartialTransaction) -> str:
        """
        Serialize PSBT to base64 string.
        
        Args:
            psbt: PartialTransaction
            
        Returns:
            Base64-encoded PSBT string
        """
        import base64
        return base64.b64encode(self.serialize(psbt)).decode('ascii')


__all__ = [
    'CLTVPsbtHelper',
    'PSBTPreimageType',
    'PSBTTaprootType',
    'TaprootLeafInfo',
]

