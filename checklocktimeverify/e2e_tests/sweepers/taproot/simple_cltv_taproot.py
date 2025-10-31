"""
Simple CLTV Taproot Sweeper - For Taproot time-locked outputs

Handles Taproot script-path spending with CLTV:
    <locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG

Script types:
- cltv_simple_taproot (Taproot with Schnorr) - SegWit v1
"""

from typing import List, Dict, Any
from ..base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Electrum imports
from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput
from electrum.transaction import TxOutpoint
from electrum_ecc import ECPrivkey
from electrum_ecc.util import bip340_tagged_hash
from electrum.bitcoin import construct_witness
from electrum.util import bfh


class SimpleCLTVTaprootSweeper(SweeperStrategy):
    """
    Sweeper for simple time-locked single-signature CLTV Taproot outputs.
    
    Supports Taproot script-path spending with CLTV:
    - Native Taproot CLTV (Schnorr signatures, witness)
    
    Witness structure:
    - Taproot: [signature, script, control_block]
    """
    
    SCRIPT_TYPE = "cltv_simple_taproot"
    
    def __init__(self, **kwargs):
        """
        Initialize sweeper. Accepts kwargs for compatibility with registry.
        
        Args:
            **kwargs: Ignored for simple CLTV Taproot (no path variants)
        """
        # Simple CLTV Taproot has no path variants, so we ignore all kwargs
        pass
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Simple CLTV Taproot needs exactly 1 key.
        
        Args:
            output: Must contain 'key_derivation' or default to single key
            
        Returns:
            List of required key names
        """
        return ['private_key']
    
    def validate_sweep_conditions(self, output: Dict[str, Any], current_height: int, **kwargs) -> bool:
        """
        Validate that the output can be swept.
        
        Args:
            output: Output data
            current_height: Current blockchain height
            **kwargs: Additional arguments (e.g., raise_if_locked)
            
        Returns:
            True if sweepable, False if still locked
            
        Raises:
            LockedError: If output is still time-locked
        """
        locktime = output.get('locktime')
        if locktime is None:
            raise ValidationError("Missing locktime in output data")
        
        if current_height < locktime:
            raise LockedError(
                f"Output still locked! Current height: {current_height}, "
                f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
            )
        
        return True
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, ECPrivkey],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for simple CLTV Taproot.
        
        Args:
            output: Output data with script_hex, control_block_hex
            keys: Dict of private keys
            sighash: The sighash to sign
        
        Returns:
            List of witness items: [signature, script, control_block]
        """
        # Configure Electrum for the correct network (Signet)
        from network_config import configure_electrum
        configure_electrum()
        
        # Get the key
        if 'private_key' not in keys:
            raise ValidationError("Missing private_key in keys")
        
        privkey = keys['private_key']
        
        # Get script and control block
        script_hex = output.get('script_hex')
        if not script_hex:
            raise ValidationError("Missing script_hex in output")
        
        # Use internal_key from output data if available, otherwise use control_block_hex
        internal_key_hex = output.get('internal_key')
        if internal_key_hex:
            # We have the internal key, compute control block
            script_bytes = bytes.fromhex(script_hex)
            control_block_bytes = self._compute_control_block(script_bytes, internal_key_hex)
        else:
            # Fallback to provided control_block_hex
            control_block_hex = output.get('control_block_hex')
            if not control_block_hex:
                raise ValidationError("Missing control_block_hex in output")
            script_bytes = bytes.fromhex(script_hex)
            control_block_bytes = bytes.fromhex(control_block_hex)
        
        # Sign the sighash with Schnorr
        print(f"   Signing with Schnorr...")
        sig = privkey.schnorr_sign(sighash)
        print(f"   Raw signature type: {type(sig)}")
        print(f"   Raw signature: {sig}")
        
        # Convert signature to bytes
        sig_bytes = bfh(sig.hex())
        print(f"   Converted signature: {sig_bytes.hex()[:64]}...")
        print(f"   Signature length: {len(sig_bytes)} bytes")
        
        # Return witness items as list of bytes
        witness_items = [sig_bytes, script_bytes, control_block_bytes]
        print(f"   Witness items prepared: {len(witness_items)} elements")
        
        return witness_items
    
    def _compute_control_block(self, script_bytes: bytes, internal_key_hex: str) -> bytes:
        """Compute control block for single-leaf Taproot."""
        from electrum_ecc.util import bip340_tagged_hash
        from electrum.bitcoin import var_int
        
        # Compute TapLeaf hash
        leaf_version = 0xc0
        compact_size = var_int(len(script_bytes))
        data = bytes([leaf_version]) + compact_size + script_bytes
        tapleaf_hash = bip340_tagged_hash(b"TapLeaf", data)
        
        # For now, assume parity = 0 (even)
        # In a full implementation, we'd compute the actual parity from the output key
        parity = 0
        version_and_parity = leaf_version | parity
        
        # Control block: [leaf_version | parity] || internal_key
        internal_key_bytes = bytes.fromhex(internal_key_hex)
        control_block = bytes([version_and_parity]) + internal_key_bytes
        
        return control_block


# Legacy function for backward compatibility
def sweep_simple_cltv_taproot(txid, vout, amount_sats, script_hex, control_block_hex, 
                             locktime, private_key_hex, dest_address, current_height,
                             fee_sats=200):
    """
    Legacy function for backward compatibility.
    
    This function is deprecated. Use SimpleCLTVTaprootSweeper class instead.
    """
    # Configure Electrum for the correct network (Signet)
    from network_config import configure_electrum
    configure_electrum()
    
    # Validate locktime
    if current_height < locktime:
        raise ValueError(
            f"Output still locked! Current height: {current_height}, "
            f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
        )
    
    print(f"Building Taproot sweep transaction...")
    print(f"Input: {txid}:{vout} ({amount_sats} sats)")
    print(f"Locktime: {locktime}")
    print(f"Fee: {fee_sats} sats")
    
    # Parse inputs
    script_bytes = bytes.fromhex(script_hex)
    control_block = bytes.fromhex(control_block_hex)
    privkey = ECPrivkey(bytes.fromhex(private_key_hex))
    
    # Debug: Verify private key and public key
    pubkey = privkey.get_public_key_bytes(compressed=True)
    print(f"Private key: {private_key_hex}")
    print(f"Public key: {pubkey.hex()}")
    print(f"Public key length: {len(pubkey)} bytes")
    
    # Extract expected pubkey from script (x-only format)
    # Script format: OP_PUSH4 <locktime> OP_CLTV OP_DROP OP_PUSH32 <pubkey> OP_CHECKSIG
    # Example: 0493350400 b1 75 20 f9308a... ac
    # Skip: OP_PUSH4 (04) + locktime (4 bytes) + OP_CLTV (b1) + OP_DROP (75) + OP_PUSH32 (20)
    # That's 1 + 4 + 1 + 1 + 1 = 8 bytes = 16 hex chars before pubkey
    expected_pubkey_hex = script_hex[16:80]  # Skip 16 hex chars, take next 64 hex chars (32 bytes)
    print(f"Expected pubkey in script: {expected_pubkey_hex}")
    
    # Get x-only pubkey (remove 0x02/0x03 prefix)
    our_pubkey_xonly = pubkey[1:].hex()
    print(f"Our pubkey x-only: {our_pubkey_xonly}")
    
    if our_pubkey_xonly != expected_pubkey_hex:
        raise ValueError(f"Public key mismatch! Expected: {expected_pubkey_hex}, Got: {our_pubkey_xonly}")
    
    print(f"✅ Public key matches script")
    
    # Create transaction
    txin = PartialTxInput(
        prevout=TxOutpoint(txid=bytes.fromhex(txid), out_idx=vout),
        script_sig=None,
        nsequence=0xfffffffe  # Enable locktime
    )
    
    # Set input amount (required for segwit sighash)
    txin.value_sats = lambda: amount_sats
    
    # Create output
    txout = PartialTxOutput.from_address_and_value(dest_address, amount_sats - fee_sats)
    
    # Create transaction
    tx = PartialTransaction.from_io([txin], [txout])
    tx.version = 2
    tx.locktime = locktime
    
    # Compute Taproot sighash
    print(f"Computing Taproot sighash...")
    
    def compute_tapleaf_hash(script_bytes: bytes) -> bytes:
        """Compute TapLeaf hash according to BIP341."""
        # TapLeaf hash = TaggedHash("TapLeaf", leaf_version || compact_size(script) || script)
        leaf_version = bytes([0xc0])  # Tapscript leaf version
        
        # CompactSize encoding for script length
        script_len = len(script_bytes)
        if script_len < 0xfd:
            compact_size = bytes([script_len])
        elif script_len <= 0xffff:
            compact_size = bytes([0xfd]) + script_len.to_bytes(2, 'little')
        elif script_len <= 0xffffffff:
            compact_size = bytes([0xfe]) + script_len.to_bytes(4, 'little')
        else:
            compact_size = bytes([0xff]) + script_len.to_bytes(8, 'little')
        
        # TapLeaf hash
        tapleaf_hash = bip340_tagged_hash(b"TapLeaf", leaf_version + compact_size + script_bytes)
        print(f"Tapleaf hash (CORRECTED): {tapleaf_hash.hex()}")
        return tapleaf_hash
    
    def taproot_sighash(tx, input_index, script, control_block, leaf_version=0xc0):
        """Compute BIP341 Taproot sighash for script-path spending."""
        import struct
        import hashlib
        
        def sha256(data):
            return hashlib.sha256(data).digest()
        
        print(f"Computing correct BIP341 Taproot sighash...")
        
        # Compute TapLeaf hash
        leaf_hash = compute_tapleaf_hash(script)
        print(f"TapLeaf hash (corrected): {leaf_hash.hex()}")
        
        print(f"Computing manual BIP341 sighash...")
        
        # Build preimage according to BIP341 §5.3 CORRECT field order (Bitcoin Core validated)
        epoch = bytes([0])  # epoch (always 0)
        hash_type = bytes([0])  # SIGHASH_DEFAULT
        tx_version = struct.pack("<I", tx.version)
        tx_locktime = struct.pack("<I", tx.locktime)
        
        # prevouts - CRITICAL FIX: TXID must be little-endian for BIP341
        # Bitcoin TXIDs are displayed big-endian but must be reversed for sighash
        if isinstance(txin.prevout.txid, str):
            txid_bytes = bytes.fromhex(txin.prevout.txid)[::-1]  # Reverse to little-endian
        else:
            txid_bytes = txin.prevout.txid[::-1]  # Already bytes, just reverse
        prevouts_hash = sha256(sha256(txid_bytes + struct.pack("<I", txin.prevout.out_idx)))
        
        # amounts
        amounts_hash = sha256(sha256(struct.pack("<Q", amount_sats)))
        
        # scriptPubKeys - use the actual output scriptPubKey
        from electrum.bitcoin import address_to_script, var_int
        scriptpubkey = address_to_script(dest_address)
        scriptpubkeys_hash = sha256(sha256(var_int(len(scriptpubkey)) + scriptpubkey))
        
        # sequences
        sequences_hash = sha256(sha256(struct.pack("<I", 0xfffffffe)))
        
        # outputs - manually serialize the output with CompactSize varint
        output_serialized = struct.pack("<Q", txout.value) + var_int(len(txout.scriptpubkey)) + txout.scriptpubkey
        outputs_hash = sha256(sha256(output_serialized))
        
        # Build preimage according to BIP341 §5.3
        pre_hash = bytearray()
        pre_hash.extend(bytes([0]))                     # epoch
        pre_hash.extend(bytes([0]))                     # hash_type
        pre_hash.extend(struct.pack("<I", tx.version))  # tx_version (CORRECT POSITION - after hash_type)
        pre_hash.extend(struct.pack("<I", tx.locktime)) # tx_locktime (CORRECT POSITION - after tx_version)
        pre_hash.extend(prevouts_hash)
        pre_hash.extend(amounts_hash)
        pre_hash.extend(scriptpubkeys_hash)
        pre_hash.extend(sequences_hash)
        pre_hash.extend(outputs_hash)
        pre_hash.extend(bytes([0x02]))                  # spend_type (script-path) ✅ FIXED
        pre_hash.extend(struct.pack("<I", 0))           # input_index
        pre_hash.extend(leaf_hash)
        pre_hash.extend(bytes([0x00]))                  # key_version ✅ FIXED
        pre_hash.extend(struct.pack("<I", 0xffffffff))  # code_separator_pos
        
        print(f"   Preimage length: {len(pre_hash)} bytes")
        
        # Compute sighash for taproot
        msg_hash = bip340_tagged_hash(b"TapSighash", pre_hash)
        print(f"   BIP341 sighash: {msg_hash.hex()[:64]}...")
        
        return msg_hash
    
    # Compute sighash
    sighash = taproot_sighash(tx, 0, script_bytes, control_block)
    
    # Sign the sighash
    print(f"Signing with Schnorr...")
    sig = privkey.schnorr_sign(sighash)
    print(f"Raw signature type: {type(sig)}")
    print(f"Raw signature: {sig}")
    
    # Convert signature like working example (bfh(sig.hex()))
    sig_bytes = bfh(sig.hex())
    print(f"Converted signature: {sig_bytes.hex()[:64]}...")
    print(f"Signature length: {len(sig_bytes)} bytes")
    
    # Build witness stack for Taproot script-path spend
    # Witness: [signature, script, control_block]
    print(f"Building Taproot witness...")
    print(f"- Signature: {len(sig_bytes)} bytes")
    print(f"- Script: {len(script_bytes)} bytes")
    print(f"- Control block: {len(control_block)} bytes")
    
    # Use Electrum's construct_witness function
    from electrum.bitcoin import construct_witness
    witness_items = [sig_bytes, script_bytes, control_block]
    constructed_witness = construct_witness(witness_items)
    
    print(f"Witness items prepared: {len(witness_items)} elements")
    print(f"Constructed witness: {len(constructed_witness)} bytes")
    
    # Add witness to the transaction input
    txin.witness = constructed_witness
    txin.script_sig = b''  # Empty scriptSig for Taproot
    
    # Serialize transaction (with witness included)
    try:
        # Use serialize_to_network to get raw transaction format
        tx_hex = tx.serialize_to_network()
        print(f"✅ Serialized transaction to network format")
        
        # Fix nLockTime
        try:
            tx_bytes = bytes.fromhex(tx_hex)
            correct_locktime_bytes = locktime.to_bytes(4, 'little')
            tx_bytes_fixed = tx_bytes[:-4] + correct_locktime_bytes
            tx_hex = tx_bytes_fixed.hex()
            print(f"✅ Fixed nLockTime: {locktime}")
        except Exception as e:
            print(f"⚠️  Failed to fix nLockTime: {e}")
            # Continue with original tx_hex
    except Exception as e:
        print(f"❌ Serialization failed: {e}")
        raise ValueError(f"Failed to serialize transaction: {e}")
    
    print(f"✅ Transaction built: {len(tx_hex)//2} bytes")
    return tx_hex


if __name__ == '__main__':
    print("Simple CLTV Taproot Sweeper")
    print("This module is used by the test framework.")