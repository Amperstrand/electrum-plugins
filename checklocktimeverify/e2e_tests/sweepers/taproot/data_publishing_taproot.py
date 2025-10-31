#!/usr/bin/env python3
"""
Taproot Data Publishing Sweeper

Spends from Taproot data publishing contracts via two script-path options:
1. Publisher: Reveal preimage + signature (happy path)
2. Buyer Refund: Buyer alone after CLTV timeout (fallback path)

Uses BIP-341/342 manual script-path spending with Schnorr signatures.

Witness ordering:
- Publisher: [preimage, signature, script, control_block]
- Buyer refund: [signature, script, control_block]

Reference: payment_channel_taproot.py
"""

import sys
import os
import hashlib
import struct

# Prefer vendored third_party helpers to avoid external dependency
_THIRD_PARTY = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../third_party'))
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)

from bip_0340_reference import schnorr_sign, bytes_from_int


def sha256(data: bytes) -> bytes:
    """Single SHA256 hash."""
    return hashlib.sha256(data).digest()


def tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-340 tagged hash."""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


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


class TaprootDataPublishingSweeper:
    """Sweep from Taproot data publishing addresses."""
    
    def __init__(self, funding_txid, funding_vout, amount_sats, script_info, network='signet'):
        """
        Args:
            funding_txid: Funding transaction ID
            funding_vout: Output index
            amount_sats: UTXO amount in sats
            script_info: Dict with 'output_key' and 'scripts' containing publisher/buyer_refund paths
            network: 'signet', 'testnet', 'mainnet', 'regtest'
        """
        self.funding_txid = funding_txid
        self.funding_vout = funding_vout
        self.amount_sats = amount_sats
        self.script_info = script_info
        self.network = network
    
    def sweep_publisher(self, publisher_privkey_hex, preimage, dest_address, fee_sat=200):
        """
        Sweep via publisher path (reveal preimage).
        
        Args:
            publisher_privkey_hex: Publisher private key (32 bytes hex)
            preimage: Raw preimage data (bytes, NOT hex string)
            dest_address: Destination address
            fee_sat: Transaction fee in sats (default: 200)
        
        Returns:
            Transaction hex (for broadcasting)
        """
        # Get publisher script and control block
        publisher_script_hex = self.script_info['scripts']['publisher']['script']
        publisher_control_hex = self.script_info['scripts']['publisher']['control_block']
        
        # Build sighash
        sighash = self._compute_bip341_sighash(dest_address, publisher_script_hex, locktime=0, fee_sat=fee_sat)
        
        # Sign with Schnorr
        publisher_aux = hashlib.sha256(b"data_publishing_publisher").digest()
        sig_bytes = schnorr_sign(sighash, bytes.fromhex(publisher_privkey_hex), publisher_aux)
        
        # Build witness
        # Script: OP_SHA256 <hash> OP_EQUALVERIFY <publisher_xonly> OP_CHECKSIG
        # Witness order: [signature, preimage, script, control]
        # Stack after witness: [preimage, signature] (preimage on top for SHA256)
        witness_items = [
            sig_bytes,
            preimage,
            bytes.fromhex(publisher_script_hex),
            bytes.fromhex(publisher_control_hex)
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime=0, fee_sat=fee_sat)
    
    def sweep_buyer_refund(self, buyer_privkey_hex, locktime, dest_address, fee_sat=200):
        """
        Sweep via buyer refund path (after CLTV timeout).
        
        Args:
            buyer_privkey_hex: Buyer private key (32 bytes hex)
            locktime: Block height (must be >= CLTV locktime)
            dest_address: Destination address
            fee_sat: Transaction fee in sats (default: 200)
        
        Returns:
            Transaction hex (for broadcasting)
        """
        # Get buyer refund script and control block
        buyer_refund_script_hex = self.script_info['scripts']['buyer_refund']['script']
        buyer_refund_control_hex = self.script_info['scripts']['buyer_refund']['control_block']
        
        # Build sighash
        sighash = self._compute_bip341_sighash(dest_address, buyer_refund_script_hex, locktime=locktime, fee_sat=fee_sat)
        
        # Sign with Schnorr
        buyer_aux = hashlib.sha256(b"data_publishing_buyer").digest()
        sig_bytes = schnorr_sign(sighash, bytes.fromhex(buyer_privkey_hex), buyer_aux)
        
        # Build witness
        # Script: <locktime> OP_CLTV OP_DROP <buyer_xonly> OP_CHECKSIG
        # Witness: [signature, script, control]
        witness_items = [
            sig_bytes,
            bytes.fromhex(buyer_refund_script_hex),
            bytes.fromhex(buyer_refund_control_hex)
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime=locktime, fee_sat=fee_sat)
    
    def _compute_bip341_sighash(
        self,
        dest_address: str,
        script_hex: str,
        locktime: int = 0,
        fee_sat: int = 200
    ) -> bytes:
        """Compute BIP-341 sighash for script-path spending."""
        from bip_350_bech32_reference import decode
        
        script = bytes.fromhex(script_hex)
        
        # Destination can be address or OP_RETURN tuple
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
            output_amount = self.amount_sats - fee_sat
        
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
        locktime: int = 0,
        fee_sat: int = 200
    ) -> str:
        """Build final signed transaction with witness."""
        from bip_350_bech32_reference import decode
        
        # Destination can be address or OP_RETURN tuple
        if isinstance(dest_address, tuple) and dest_address[0] == 'op_return':
            data_hex = dest_address[1]
            data_bytes = bytes.fromhex(data_hex)
            dest_script = bytes([0x6a, len(data_bytes)]) + data_bytes
            output_amount = 0
        else:
            hrp = 'bc' if self.network == 'mainnet' else ('bcrt' if self.network == 'regtest' else 'tb')
            ver, prog = decode(hrp, dest_address)
            prog_b = bytes(prog)
            dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
            output_amount = self.amount_sats - fee_sat
        
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
    print("Taproot Data Publishing Sweeper")
    print("Usage: Import and use sweep_publisher() or sweep_buyer_refund() methods")
