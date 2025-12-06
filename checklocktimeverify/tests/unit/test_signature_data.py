"""
Tests for SignatureData - Bitcoin Core aligned signing data pattern.
"""

import pytest
from cltv_lib.signature_data import SignatureData


class TestSignatureDataBasic:
    """Basic SignatureData functionality tests."""
    
    def test_create_empty_sigdata(self):
        """Create empty SignatureData."""
        sigdata = SignatureData()
        assert sigdata.complete == False
        assert sigdata.witness == True  # Always True for our plugin
        assert sigdata.witness_script is None
        assert len(sigdata.signatures) == 0
        assert len(sigdata.taproot_script_sigs) == 0
        assert len(sigdata.hash160_preimages) == 0
    
    def test_mark_complete(self):
        """Test marking as complete."""
        sigdata = SignatureData()
        assert not sigdata.is_complete()
        sigdata.mark_complete()
        assert sigdata.is_complete()


class TestSignatureDataSignatures:
    """Signature handling tests."""
    
    def test_add_ecdsa_signature(self):
        """Add ECDSA signature for P2WSH."""
        sigdata = SignatureData()
        
        # Test pubkey and signature (mock data)
        pubkey = bytes.fromhex('02' + '11' * 32)  # 33-byte compressed
        signature = bytes.fromhex('3044' + '00' * 68)  # DER signature
        
        sigdata.add_signature(pubkey, signature)
        
        assert len(sigdata.signatures) == 1
        # Get by pubkey hash
        from electrum.crypto import hash_160
        pubkey_hash = hash_160(pubkey)
        assert pubkey_hash in sigdata.signatures
        assert sigdata.signatures[pubkey_hash] == (pubkey, signature)
    
    def test_add_schnorr_signature(self):
        """Add Schnorr signature for Taproot."""
        sigdata = SignatureData()
        
        # Test x-only pubkey and signature
        xonly_pubkey = bytes(32)  # 32-byte x-only
        leaf_hash = bytes.fromhex('aa' * 32)
        signature = bytes(64)  # 64-byte Schnorr
        
        sigdata.add_schnorr_signature(xonly_pubkey, leaf_hash, signature)
        
        assert len(sigdata.taproot_script_sigs) == 1
        assert (xonly_pubkey, leaf_hash) in sigdata.taproot_script_sigs
        assert sigdata.taproot_script_sigs[(xonly_pubkey, leaf_hash)] == signature


class TestSignatureDataPreimages:
    """Preimage handling tests (for hash-locked contracts)."""
    
    def test_add_hash160_preimage(self):
        """Add HASH160 preimage for data publishing."""
        sigdata = SignatureData()
        
        hash_value = bytes.fromhex('bb' * 20)
        preimage = b'secret_data'
        
        sigdata.add_preimage(hash_value, preimage, 'hash160')
        
        assert len(sigdata.hash160_preimages) == 1
        assert sigdata.get_preimage(hash_value, 'hash160') == preimage
    
    def test_add_sha256_preimage(self):
        """Add SHA256 preimage."""
        sigdata = SignatureData()
        
        hash_value = bytes.fromhex('cc' * 32)
        preimage = b'another_secret'
        
        sigdata.add_preimage(hash_value, preimage, 'sha256')
        
        assert len(sigdata.sha256_preimages) == 1
        assert sigdata.get_preimage(hash_value, 'sha256') == preimage
    
    def test_invalid_hash_type_raises_error(self):
        """Invalid hash type raises ValueError."""
        sigdata = SignatureData()
        
        with pytest.raises(ValueError, match="Unknown hash type"):
            sigdata.add_preimage(bytes(20), b'data', 'invalid_type')


class TestSignatureDataMerge:
    """Merge functionality tests."""
    
    def test_merge_signatures(self):
        """Merge signatures from two SignatureData instances."""
        sigdata1 = SignatureData()
        sigdata2 = SignatureData()
        
        # Add different signatures to each
        pubkey1 = bytes.fromhex('02' + '11' * 32)
        sig1 = bytes(70)
        sigdata1.add_signature(pubkey1, sig1)
        
        pubkey2 = bytes.fromhex('02' + '22' * 32)
        sig2 = bytes(71)
        sigdata2.add_signature(pubkey2, sig2)
        
        # Merge
        sigdata1.merge(sigdata2)
        
        assert len(sigdata1.signatures) == 2
    
    def test_merge_preimages(self):
        """Merge preimages from two SignatureData instances."""
        sigdata1 = SignatureData()
        sigdata2 = SignatureData()
        
        sigdata1.add_preimage(bytes.fromhex('aa' * 20), b'preimage1', 'hash160')
        sigdata2.add_preimage(bytes.fromhex('bb' * 20), b'preimage2', 'hash160')
        
        sigdata1.merge(sigdata2)
        
        assert len(sigdata1.hash160_preimages) == 2
    
    def test_merge_marks_complete(self):
        """Merging complete sigdata marks result complete."""
        sigdata1 = SignatureData()
        sigdata2 = SignatureData()
        sigdata2.mark_complete()
        
        assert not sigdata1.is_complete()
        sigdata1.merge(sigdata2)
        assert sigdata1.is_complete()


class TestSignatureDataWitnessBuilding:
    """Witness stack building tests."""
    
    def test_build_p2wsh_witness(self):
        """Build P2WSH witness stack."""
        sigdata = SignatureData()
        sigdata.witness_script = bytes.fromhex('deadbeef')
        
        # Add a signature
        pubkey = bytes.fromhex('02' + '11' * 32)
        signature = bytes.fromhex('3044' + '00' * 68)
        sigdata.add_signature(pubkey, signature)
        
        witness = sigdata.build_p2wsh_witness()
        
        # Should have: [signature, witness_script]
        assert len(witness) == 2
        assert witness[0] == signature
        assert witness[1] == sigdata.witness_script
    
    def test_build_p2wsh_witness_with_preimage(self):
        """Build P2WSH witness with preimage."""
        sigdata = SignatureData()
        sigdata.witness_script = bytes.fromhex('deadbeef')
        
        # Add signature
        pubkey = bytes.fromhex('02' + '11' * 32)
        signature = bytes(70)
        sigdata.add_signature(pubkey, signature)
        
        # Add preimage
        sigdata.add_preimage(bytes.fromhex('aa' * 20), b'preimage', 'hash160')
        
        witness = sigdata.build_p2wsh_witness()
        
        # Should have: [signature, preimage, witness_script]
        assert len(witness) == 3
        assert witness[1] == b'preimage'
    
    def test_build_taproot_witness(self):
        """Build Taproot script-path witness."""
        sigdata = SignatureData()
        
        # Add Schnorr signature
        xonly = bytes(32)
        leaf_hash = bytes.fromhex('aa' * 32)
        sig = bytes(64)
        sigdata.add_schnorr_signature(xonly, leaf_hash, sig)
        
        script = bytes.fromhex('cafebabe')
        control_block = bytes(33)
        
        witness = sigdata.build_taproot_witness(script, control_block)
        
        # Should have: [signature, script, control_block]
        assert len(witness) == 3
        assert witness[0] == sig
        assert witness[1] == script
        assert witness[2] == control_block

