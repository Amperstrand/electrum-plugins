"""
Tests for CLTVPsbtHelper - PSBT support with BIP-371 extensions.
"""

import pytest
from cltv_lib.psbt_helper import (
    CLTVPsbtHelper,
    PSBTPreimageType,
    PSBTTaprootType,
    TaprootLeafInfo,
)


class TestPSBTTypeConstants:
    """Test PSBT type constant values match BIP specs."""
    
    def test_taproot_type_values(self):
        """BIP-371 Taproot PSBT field type values."""
        assert PSBTTaprootType.TAP_KEY_SIG == 0x13
        assert PSBTTaprootType.TAP_SCRIPT_SIG == 0x14
        assert PSBTTaprootType.TAP_LEAF_SCRIPT == 0x15
        assert PSBTTaprootType.TAP_BIP32_DERIVATION == 0x16
        assert PSBTTaprootType.TAP_INTERNAL_KEY == 0x17
        assert PSBTTaprootType.TAP_MERKLE_ROOT == 0x18
    
    def test_preimage_type_values(self):
        """BIP-174 preimage field type values."""
        assert PSBTPreimageType.RIPEMD160 == 0x0A
        assert PSBTPreimageType.SHA256 == 0x0B
        assert PSBTPreimageType.HASH160 == 0x0C
        assert PSBTPreimageType.HASH256 == 0x0D


class TestTaprootLeafInfo:
    """Test TaprootLeafInfo dataclass."""
    
    def test_create_leaf_info(self):
        """Create TaprootLeafInfo."""
        script = bytes.fromhex('deadbeef')
        leaf_version = 0xc0
        control_block = bytes(33)
        
        leaf_info = TaprootLeafInfo(
            script=script,
            leaf_version=leaf_version,
            control_block=control_block
        )
        
        assert leaf_info.script == script
        assert leaf_info.leaf_version == leaf_version
        assert leaf_info.control_block == control_block


class TestCLTVPsbtHelperBasic:
    """Basic CLTVPsbtHelper tests."""
    
    def test_instantiation(self):
        """Helper can be instantiated."""
        helper = CLTVPsbtHelper()
        assert helper is not None
    
    def test_has_p2wsh_methods(self):
        """Helper has P2WSH methods."""
        helper = CLTVPsbtHelper()
        assert hasattr(helper, 'set_witness_script')
        assert hasattr(helper, 'add_ecdsa_signature')
    
    def test_has_taproot_methods(self):
        """Helper has Taproot methods."""
        helper = CLTVPsbtHelper()
        assert hasattr(helper, 'add_tap_internal_key')
        assert hasattr(helper, 'add_tap_leaf_script')
        assert hasattr(helper, 'add_tap_script_sig')
        assert hasattr(helper, 'get_tap_internal_key')
        assert hasattr(helper, 'get_tap_leaf_scripts')
        assert hasattr(helper, 'get_tap_script_sigs')
    
    def test_has_preimage_methods(self):
        """Helper has preimage methods."""
        helper = CLTVPsbtHelper()
        assert hasattr(helper, 'add_hash160_preimage')
        assert hasattr(helper, 'add_sha256_preimage')
        assert hasattr(helper, 'get_hash160_preimages')
    
    def test_has_sigdata_methods(self):
        """Helper has SignatureData bridge methods."""
        helper = CLTVPsbtHelper()
        assert hasattr(helper, 'from_signature_data')
        assert hasattr(helper, 'to_signature_data')


class TestTaprootInternalKey:
    """Test TAP_INTERNAL_KEY handling."""
    
    def test_add_internal_key_valid(self):
        """Add valid 32-byte internal key."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        internal_key = bytes(32)
        helper.add_tap_internal_key(txin, internal_key)
        
        # Should be stored in _unknown
        key = bytes([PSBTTaprootType.TAP_INTERNAL_KEY])
        assert key in txin._unknown
        assert txin._unknown[key] == internal_key
    
    def test_add_internal_key_wrong_size(self):
        """Adding wrong-size internal key raises error."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        with pytest.raises(ValueError, match="must be 32 bytes"):
            helper.add_tap_internal_key(txin, bytes(33))
    
    def test_get_internal_key(self):
        """Retrieve internal key."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        internal_key = bytes.fromhex('aa' * 32)
        helper.add_tap_internal_key(txin, internal_key)
        
        retrieved = helper.get_tap_internal_key(txin)
        assert retrieved == internal_key


class TestTaprootLeafScript:
    """Test TAP_LEAF_SCRIPT handling."""
    
    def test_add_leaf_script(self):
        """Add Taproot leaf script."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        leaf_info = TaprootLeafInfo(
            script=bytes.fromhex('deadbeef'),
            leaf_version=0xc0,
            control_block=bytes(33)
        )
        
        helper.add_tap_leaf_script(txin, leaf_info)
        
        # Should be stored in _unknown
        assert len(txin._unknown) == 1
    
    def test_get_leaf_scripts(self):
        """Retrieve leaf scripts."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        leaf_info = TaprootLeafInfo(
            script=bytes.fromhex('cafebabe'),
            leaf_version=0xc0,
            control_block=bytes(33)
        )
        
        helper.add_tap_leaf_script(txin, leaf_info)
        
        retrieved = helper.get_tap_leaf_scripts(txin)
        assert len(retrieved) == 1
        assert retrieved[0].script == leaf_info.script
        assert retrieved[0].leaf_version == leaf_info.leaf_version


class TestTaprootScriptSig:
    """Test TAP_SCRIPT_SIG handling."""
    
    def test_add_script_sig(self):
        """Add Taproot script-path signature."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        xonly_pubkey = bytes(32)
        leaf_hash = bytes.fromhex('bb' * 32)
        signature = bytes(64)
        
        helper.add_tap_script_sig(txin, xonly_pubkey, leaf_hash, signature)
        
        # Should be stored in _unknown
        assert len(txin._unknown) == 1
    
    def test_add_script_sig_wrong_sizes(self):
        """Wrong sizes raise errors."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        with pytest.raises(ValueError, match="pubkey must be 32 bytes"):
            helper.add_tap_script_sig(txin, bytes(33), bytes(32), bytes(64))
        
        with pytest.raises(ValueError, match="Leaf hash must be 32 bytes"):
            helper.add_tap_script_sig(txin, bytes(32), bytes(31), bytes(64))
        
        with pytest.raises(ValueError, match="Signature must be 64 or 65 bytes"):
            helper.add_tap_script_sig(txin, bytes(32), bytes(32), bytes(63))
    
    def test_get_script_sigs(self):
        """Retrieve script-path signatures."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        xonly_pubkey = bytes.fromhex('aa' * 32)
        leaf_hash = bytes.fromhex('bb' * 32)
        signature = bytes(64)
        
        helper.add_tap_script_sig(txin, xonly_pubkey, leaf_hash, signature)
        
        retrieved = helper.get_tap_script_sigs(txin)
        assert len(retrieved) == 1
        assert (xonly_pubkey, leaf_hash) in retrieved
        assert retrieved[(xonly_pubkey, leaf_hash)] == signature


class TestHash160Preimage:
    """Test HASH160 preimage handling."""
    
    def test_add_hash160_preimage(self):
        """Add HASH160 preimage."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        from electrum.crypto import hash_160
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        preimage = b'secret_data_for_publishing'
        hash_value = hash_160(preimage)
        
        helper.add_hash160_preimage(txin, hash_value, preimage)
        
        # Should be stored in _unknown
        assert len(txin._unknown) == 1
    
    def test_add_hash160_preimage_wrong_hash(self):
        """Wrong preimage raises error."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        # Wrong hash
        with pytest.raises(ValueError, match="does not match"):
            helper.add_hash160_preimage(txin, bytes(20), b'wrong_preimage')
    
    def test_get_hash160_preimages(self):
        """Retrieve HASH160 preimages."""
        from electrum.transaction import PartialTxInput, TxOutpoint
        from electrum.crypto import hash_160
        
        helper = CLTVPsbtHelper()
        txin = PartialTxInput(prevout=TxOutpoint.from_str('00' * 32 + ':0'))
        
        preimage = b'my_secret'
        hash_value = hash_160(preimage)
        
        helper.add_hash160_preimage(txin, hash_value, preimage)
        
        retrieved = helper.get_hash160_preimages(txin)
        assert len(retrieved) == 1
        assert hash_value in retrieved
        assert retrieved[hash_value] == preimage

