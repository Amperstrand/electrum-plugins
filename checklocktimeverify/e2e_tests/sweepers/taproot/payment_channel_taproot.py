#!/usr/bin/env python3
"""
Taproot Payment Channel Sweeper

Sweeps payment channel Taproot UTXOs using either:
1. Cooperative path: sender + receiver signatures (2-of-2)
2. Refund path: sender signature after CLTV timeout

Manual BIP-341/342 implementation.

Reference: twofactor_taproot.py
"""

import sys
import os
from typing import Optional

# Prefer vendored third_party helpers to avoid external dependency
_THIRD_PARTY = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../third_party'))
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)

from bip_350_bech32_reference import decode as bech32_decode
from bip_0340_reference import schnorr_sign, int_from_bytes
import hashlib
import struct


def tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-340 tagged hash."""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def sha256(data: bytes) -> bytes:
    """Single SHA256 hash."""
    return hashlib.sha256(data).digest()


def varint(n: int) -> bytes:
    """Encode variable-length integer (CompactSize)."""
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return bytes([0xfd]) + struct.pack("<H", n)
    elif n <= 0xffffffff:
        return bytes([0xfe]) + struct.pack("<I", n)
    else:
        return bytes([0xff]) + struct.pack("<Q", n)


class TaprootPaymentChannelSweeper:
    """Sweep payment channel Taproot UTXOs."""
    
    def __init__(self, funding_txid: str, funding_vout: int, amount_sats: int, 
                 script_info: dict, network: str = 'signet'):
        """
        Args:
            funding_txid: Funding transaction ID
            funding_vout: Funding output index
            amount_sats: Funding amount in satoshis
            script_info: Script information dict containing scripts and control blocks
            network: 'signet', 'testnet', 'mainnet', 'regtest'
        """
        self.funding_txid = funding_txid
        self.funding_vout = funding_vout
        self.amount_sats = amount_sats
        self.script_info = script_info
        self.network = network
    
    def sweep_cooperative(
        self,
        sender_privkey_hex: str,
        receiver_privkey_hex: str,
        dest_address: str
    ) -> str:
        """
        Sweep using cooperative path (Sender + Receiver, any time).
        
        Args:
            sender_privkey_hex: Sender's private key (32 bytes hex)
            receiver_privkey_hex: Receiver's private key (32 bytes hex)
            dest_address: Destination address
        
        Returns:
            Signed transaction hex
        """
        # Get cooperative script and control block
        cooperative_script_hex = self.script_info['scripts']['cooperative']['script']
        cooperative_control_hex = self.script_info['scripts']['cooperative']['control_block']
        
        # Build sighash
        sighash = self._compute_bip341_sighash(dest_address, cooperative_script_hex, locktime=0)
        
        # Sign with both keys
        sender_aux = hashlib.sha256(b"payment_channel_sender").digest()
        receiver_aux = hashlib.sha256(b"payment_channel_receiver").digest()
        
        sender_sig = schnorr_sign(sighash, bytes.fromhex(sender_privkey_hex), sender_aux)
        receiver_sig = schnorr_sign(sighash, bytes.fromhex(receiver_privkey_hex), receiver_aux)
        
        # Build witness
        # Script: <sender_xonly> CHECKSIGVERIFY <receiver_xonly> CHECKSIG
        # Witness order: [receiver_sig, sender_sig, script, control]
        witness_items = [
            receiver_sig,
            sender_sig,
            bytes.fromhex(cooperative_script_hex),
            bytes.fromhex(cooperative_control_hex)
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime=0)
    
    def sweep_refund(
        self,
        sender_privkey_hex: str,
        dest_address: str,
        locktime: int
    ) -> str:
        """
        Sweep using refund path (Sender alone after locktime).
        
        Args:
            sender_privkey_hex: Sender's private key (32 bytes hex)
            dest_address: Destination address
            locktime: Absolute locktime (block height)
        
        Returns:
            Signed transaction hex
        """
        # Get refund script and control block
        refund_script_hex = self.script_info['scripts']['refund']['script']
        refund_control_hex = self.script_info['scripts']['refund']['control_block']
        
        # Build sighash
        sighash = self._compute_bip341_sighash(dest_address, refund_script_hex, locktime=locktime)
        
        # Sign with sender key
        sender_aux = hashlib.sha256(b"payment_channel_refund").digest()
        sender_sig = schnorr_sign(sighash, bytes.fromhex(sender_privkey_hex), sender_aux)
        
        # Build witness
        # Script: <locktime> CLTV DROP <sender_xonly> CHECKSIG
        # Witness: [sender_sig, script, control]
        witness_items = [
            sender_sig,
            bytes.fromhex(refund_script_hex),
            bytes.fromhex(refund_control_hex)
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime=locktime)
    
    def _compute_bip341_sighash(
        self,
        dest_address: str,
        script_hex: str,
        locktime: int = 0
    ) -> bytes:
        """Compute BIP-341 sighash for script-path spending."""
        import hashlib
        import struct
        from bip_350_bech32_reference import decode
        
        script = bytes.fromhex(script_hex)
        
        # Decode destination (address or OP_RETURN tuple)
        if isinstance(dest_address, tuple) and dest_address[0] == 'op_return':
            data_hex = dest_address[1]
            data_bytes = bytes.fromhex(data_hex)
            dest_script = bytes([0x6a, len(data_bytes)]) + data_bytes  # OP_RETURN <push>
            output_amount = 0
        else:
            hrp = 'bc' if self.network == 'mainnet' else ('bcrt' if self.network == 'regtest' else 'tb')
            ver, prog = decode(hrp, dest_address)
            prog_b = bytes(prog)
            dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
            # Output amount for address case
            FEE_SATS = 200
            output_amount = self.amount_sats - FEE_SATS
        
        # For OP_RETURN, output_amount already set to 0 above
        
        # BIP-341 sighash components
        epoch = bytes([0x00])
        hash_type = bytes([0x00])
        n_version = struct.pack("<I", 2)
        n_locktime = struct.pack("<I", locktime)
        
        # Prevouts
        prevouts = bytes.fromhex(self.funding_txid)[::-1] + struct.pack("<I", self.funding_vout)
        sha_prevouts = sha256(prevouts)
        
        # Amounts
        amounts = struct.pack("<Q", self.amount_sats)
        sha_amounts = sha256(amounts)
        
        # Script pubkeys
        output_key = bytes.fromhex(self.script_info['output_key'])
        prevout_script = bytes([0x51, 0x20]) + output_key
        sha_scriptpubkeys = sha256(varint(len(prevout_script)) + prevout_script)
        
        # Sequences
        nsequence = 0xfffffffe if locktime > 0 else 0xffffffff
        sequences = struct.pack("<I", nsequence)
        sha_sequences = sha256(sequences)
        
        # Outputs
        outputs = struct.pack("<Q", output_amount) + varint(len(dest_script)) + dest_script
        sha_outputs = sha256(outputs)
        
        # Spend type
        spend_type = bytes([0x02])
        
        # Input index
        input_index = struct.pack("<I", 0)
        
        # Tapleaf hash
        leaf_version = bytes([0xc0])
        tapleaf_hash = tagged_hash("TapLeaf", leaf_version + varint(len(script)) + script)
        
        # Key version and codeseparator
        key_version = bytes([0x00])
        codeseparator_pos = struct.pack("<I", 0xffffffff)
        
        # Build sighash preimage
        preimage = (
            epoch +
            hash_type +
            n_version +
            n_locktime +
            sha_prevouts +
            sha_amounts +
            sha_scriptpubkeys +
            sha_sequences +
            sha_outputs +
            spend_type +
            input_index +
            tapleaf_hash +
            key_version +
            codeseparator_pos
        )
        
        # Hash with TapSighash tag
        return tagged_hash("TapSighash", preimage)
    
    def _finalize_transaction(
        self,
        dest_address: str,
        witness_items: list,
        locktime: int = 0
    ) -> str:
        """Build final signed transaction with witness."""
        import struct
        from bip_350_bech32_reference import decode
        
        # Decode destination (address or OP_RETURN)
        if isinstance(dest_address, tuple) and dest_address[0] == 'op_return':
            data_hex = dest_address[1]
            data_bytes = bytes.fromhex(data_hex)
            dest_script = bytes([0x6a, len(data_bytes)]) + data_bytes  # OP_RETURN <push>
            output_amount = 0
        else:
            hrp = 'bc' if self.network == 'mainnet' else ('bcrt' if self.network == 'regtest' else 'tb')
            ver, prog = decode(hrp, dest_address)
            prog_b = bytes(prog)
            dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
            # Output amount for address case
            FEE_SATS = 200
            output_amount = self.amount_sats - FEE_SATS
        
        # Build transaction
        tx = bytearray()
        
        # Version
        tx.extend(struct.pack("<I", 2))
        
        # Marker and flag
        tx.append(0x00)
        tx.append(0x01)
        
        # Inputs
        tx.append(0x01)  # 1 input
        tx.extend(bytes.fromhex(self.funding_txid)[::-1])
        tx.extend(struct.pack("<I", self.funding_vout))
        tx.append(0x00)  # Empty scriptSig
        nsequence = 0xfffffffe if locktime > 0 else 0xffffffff
        tx.extend(struct.pack("<I", nsequence))
        
        # Outputs
        tx.append(0x01)  # 1 output
        tx.extend(struct.pack("<Q", output_amount))
        tx.append(len(dest_script))
        tx.extend(dest_script)
        
        # Witness
        tx.append(len(witness_items))
        for item in witness_items:
            if isinstance(item, bytes):
                item_bytes = item
            else:
                item_bytes = bytes.fromhex(item) if isinstance(item, str) else item
            
            if len(item_bytes) < 0xfd:
                tx.append(len(item_bytes))
            else:
                tx.append(0xfd)
                tx.extend(struct.pack("<H", len(item_bytes)))
            tx.extend(item_bytes)
        
        # Locktime
        tx.extend(struct.pack("<I", locktime))
        
        return tx.hex()


if __name__ == '__main__':
    print("Taproot Payment Channel Sweeper")
    print("=" * 60)
    print("This module requires an Electrum RPC client to function.")
    print("Import TaprootPaymentChannelSweeper and use sweep_cooperative() or sweep_refund().")
    print("✅ Module loaded successfully!")
