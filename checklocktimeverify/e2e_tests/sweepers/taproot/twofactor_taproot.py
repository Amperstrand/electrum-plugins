#!/usr/bin/env python3
"""
Taproot Two-Factor Authentication Sweeper

Builds sweep transactions for Taproot Two-Factor with 2 script-path leaves.

Spend Paths:
1. Normal (Cooperative): User + Server (anytime)
2. Recovery: User alone (after locktime)

Uses BIP-341 script-path spending with Schnorr signatures.

Reference: escrow_taproot.py sweeper pattern
"""

import sys
import os
from pathlib import Path
import hashlib
import struct
from typing import Dict, List

# Prefer vendored third_party helpers to avoid external dependency
_THIRD_PARTY = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../third_party'))
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)

from bip_0340_reference import schnorr_sign, bytes_from_int


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


class TaprootTwoFactorSweeper:
    """
    Build Taproot Two-Factor sweep transactions.
    
    Handles both spend paths:
    - Normal (Cooperative): User + Server
    - Recovery: User alone after timeout
    """
    
    def __init__(
        self,
        funding_txid: str,
        funding_vout: int,
        amount_sats: int,
        script_info: Dict,
        network: str = 'signet'
    ):
        """
        Initialize sweeper with UTXO details.
        
        Args:
            funding_txid: Transaction ID of funding tx (hex)
            funding_vout: Output index
            amount_sats: Amount in satoshis
            script_info: Script info from create_twofactor_taproot_address()
            network: 'mainnet', 'testnet', 'signet', 'regtest'
        """
        self.funding_txid = funding_txid
        self.funding_vout = funding_vout
        self.amount_sats = amount_sats
        self.script_info = script_info
        self.network = network
        
        # Extract script details
        self.output_key = bytes.fromhex(script_info['output_key'])
        self.normal_script = bytes.fromhex(script_info['scripts']['normal']['script'])
        self.normal_control = bytes.fromhex(script_info['scripts']['normal']['control_block'])
        self.recovery_script = bytes.fromhex(script_info['scripts']['recovery']['script'])
        self.recovery_control = bytes.fromhex(script_info['scripts']['recovery']['control_block'])
        
        # Transaction fields
        self.version = 2
        self.nsequence = 0xfffffffe  # Enable locktime

    def _hrp(self) -> str:
        """Return correct Bech32 HRP for the configured network."""
        if self.network == 'mainnet':
            return 'bc'
        if self.network in ('testnet', 'signet'):
            return 'tb'
        if self.network == 'regtest':
            return 'bcrt'
        # Default to testnet hrp for unknown values
        return 'tb'
    
    def _build_unsigned_tx(
        self,
        dest_address: str,
        locktime: int = 0
    ) -> bytes:
        """
        Build unsigned transaction.
        
        Args:
            dest_address: Destination address (bech32/bech32m)
            locktime: Block height for CLTV (0 for cooperative path)
        
        Returns:
            Unsigned transaction bytes
        """
        from bip_350_bech32_reference import decode
        
        # Decode destination address (returns version, program)
        ver, prog = decode(self._hrp(), dest_address)
        if ver is None or prog is None:
            raise ValueError(f"Invalid destination address: {dest_address}")
        
        prog_b = bytes(prog)
        dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
        
        # Calculate fee and output amount
        FEE_SATS = 200
        output_amount = self.amount_sats - FEE_SATS
        
        if output_amount <= 0:
            raise ValueError(f"Insufficient funds: {self.amount_sats} sats, need at least {FEE_SATS} for fee")
        
        # Build transaction
        tx = bytearray()
        
        # Version (4 bytes)
        tx.extend(struct.pack("<I", self.version))
        
        # Marker and flag for segwit
        tx.append(0x00)  # Marker
        tx.append(0x01)  # Flag
        
        # Input count
        tx.extend(varint(1))
        
        # Input
        tx.extend(bytes.fromhex(self.funding_txid)[::-1])  # Reverse for little-endian
        tx.extend(struct.pack("<I", self.funding_vout))
        tx.extend(varint(0))  # Empty scriptSig (segwit)
        tx.extend(struct.pack("<I", self.nsequence))
        
        # Output count
        tx.extend(varint(1))
        
        # Output
        tx.extend(struct.pack("<Q", output_amount))
        tx.extend(varint(len(dest_script)))
        tx.extend(dest_script)
        
        # Witness placeholder (filled later)
        tx.append(0x00)  # Empty witness for now
        
        # Locktime (4 bytes)
        tx.extend(struct.pack("<I", locktime))
        
        return bytes(tx)
    
    def _compute_bip341_sighash(
        self,
        dest_address: str,
        script: bytes,
        locktime: int = 0
    ) -> bytes:
        """
        Compute BIP-341 signature hash for script-path spending.
        
        Args:
            dest_address: Destination address
            script: Tapscript to execute
            locktime: Block height for CLTV
        
        Returns:
            32-byte sighash
        """
        from bip_350_bech32_reference import decode
        
        # Decode destination address (returns version, program)
        ver, prog = decode(self._hrp(), dest_address)
        prog_b = bytes(prog)
        dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
        
        # Output amount
        FEE_SATS = 200
        output_amount = self.amount_sats - FEE_SATS
        
        # BIP-341 signature hash construction
        # See: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki#common-signature-message
        
        # epoch (1 byte)
        epoch = bytes([0x00])
        
        # hash_type (1 byte) - SIGHASH_DEFAULT = 0x00
        hash_type = bytes([0x00])
        
        # nVersion (4 bytes)
        n_version = struct.pack("<I", self.version)
        
        # nLockTime (4 bytes)
        n_locktime = struct.pack("<I", locktime)
        
        # sha_prevouts (32 bytes)
        prevouts = bytes.fromhex(self.funding_txid)[::-1] + struct.pack("<I", self.funding_vout)
        sha_prevouts = sha256(prevouts)
        
        # sha_amounts (32 bytes)
        amounts = struct.pack("<Q", self.amount_sats)
        sha_amounts = sha256(amounts)
        
        # sha_scriptpubkeys (32 bytes)
        prevout_script = bytes([0x51, 0x20]) + self.output_key
        sha_scriptpubkeys = sha256(varint(len(prevout_script)) + prevout_script)
        
        # sha_sequences (32 bytes)
        sequences = struct.pack("<I", self.nsequence)
        sha_sequences = sha256(sequences)
        
        # sha_outputs (32 bytes)
        outputs = struct.pack("<Q", output_amount) + varint(len(dest_script)) + dest_script
        sha_outputs = sha256(outputs)
        
        # spend_type (1 byte)
        # ext_flag = 1 (annex not present)
        # spend_type = (ext_flag * 2) + 0 = 2
        spend_type = bytes([0x02])
        
        # input_index (4 bytes)
        input_index = struct.pack("<I", 0)
        
        # BIP-342 script-path additions
        # tapleaf_hash (32 bytes)
        leaf_version = bytes([0xc0])
        tapleaf_hash = tagged_hash("TapLeaf", leaf_version + varint(len(script)) + script)
        
        # key_version (1 byte) - always 0 for BIP-340
        key_version = bytes([0x00])
        
        # codeseparator_pos (4 bytes) - 0xffffffff = not executed
        codeseparator_pos = bytes([0xff, 0xff, 0xff, 0xff])
        
        # Build message
        sig_msg = (
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
        
        # Hash the message with TapSighash tag
        sighash = tagged_hash("TapSighash", sig_msg)
        
        return sighash
    
    def _finalize_transaction(
        self,
        dest_address: str,
        witness_items: List[bytes],
        locktime: int = 0
    ) -> str:
        """
        Build complete transaction with witness.
        
        Args:
            dest_address: Destination address
            witness_items: List of witness stack items (bottom to top)
            locktime: Block height for CLTV
        
        Returns:
            Complete signed transaction (hex)
        """
        from bip_350_bech32_reference import decode
        
        # Decode destination address (returns version, program)
        ver, prog = decode(self._hrp(), dest_address)
        prog_b = bytes(prog)
        dest_script = bytes([0x51 if ver == 1 else 0x00, len(prog_b)]) + prog_b
        
        # Calculate output amount
        FEE_SATS = 200
        output_amount = self.amount_sats - FEE_SATS
        
        # Build transaction
        tx = bytearray()
        
        # Version
        tx.extend(struct.pack("<I", self.version))
        
        # Marker and flag
        tx.append(0x00)
        tx.append(0x01)
        
        # Inputs
        tx.extend(varint(1))
        tx.extend(bytes.fromhex(self.funding_txid)[::-1])
        tx.extend(struct.pack("<I", self.funding_vout))
        tx.extend(varint(0))  # Empty scriptSig
        tx.extend(struct.pack("<I", self.nsequence))
        
        # Outputs
        tx.extend(varint(1))
        tx.extend(struct.pack("<Q", output_amount))
        tx.extend(varint(len(dest_script)))
        tx.extend(dest_script)
        
        # Witness
        tx.extend(varint(len(witness_items)))
        for item in witness_items:
            tx.extend(varint(len(item)))
            tx.extend(item)
        
        # Locktime
        tx.extend(struct.pack("<I", locktime))
        
        return tx.hex()
    
    def sweep_cooperative(
        self,
        user_privkey_hex: str,
        server_privkey_hex: str,
        dest_address: str
    ) -> str:
        """
        Sweep using cooperative path (User + Server, no locktime).
        
        Args:
            user_privkey_hex: User's private key (32 bytes hex)
            server_privkey_hex: Server's private key (32 bytes hex)
            dest_address: Destination address
        
        Returns:
            Signed transaction hex
        """
        # Compute sighash
        sighash = self._compute_bip341_sighash(dest_address, self.normal_script, locktime=0)
        
        # Sign with both keys (BIP-340 Schnorr)
        user_privkey = bytes.fromhex(user_privkey_hex)
        server_privkey = bytes.fromhex(server_privkey_hex)
        
        user_sig = schnorr_sign(sighash, user_privkey, aux_rand=bytes(32))
        server_sig = schnorr_sign(sighash, server_privkey, aux_rand=bytes(32))
        
        # Build witness
        # Script: <user_pk> CHECKSIGVERIFY <server_pk> CHECKSIG
        # Stack consumption order:
        # - user_sig consumed by CHECKSIGVERIFY (fails if invalid, consumes sig)
        # - server_sig consumed by CHECKSIG (pushes 1 if valid)
        # Witness order (bottom to top): [user_sig, server_sig, script, control_block]
        
        # IMPORTANT: Witness items are pushed bottom-to-top. We want user_sig
        # to be on top of the stack when CHECKSIGVERIFY executes first.
        # Hence order: [server_sig, user_sig, script, control_block]
        witness_items = [
            server_sig,
            user_sig,
            self.normal_script,
            self.normal_control
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime=0)
    
    def sweep_recovery(
        self,
        user_privkey_hex: str,
        dest_address: str,
        locktime: int
    ) -> str:
        """
        Sweep using recovery path (User alone after timeout).
        
        Args:
            user_privkey_hex: User's private key (32 bytes hex)
            dest_address: Destination address
            locktime: Block height for CLTV
        
        Returns:
            Signed transaction hex
        """
        # Compute sighash (with locktime)
        sighash = self._compute_bip341_sighash(dest_address, self.recovery_script, locktime)
        
        # Sign with user key only
        user_privkey = bytes.fromhex(user_privkey_hex)
        user_sig = schnorr_sign(sighash, user_privkey, aux_rand=bytes(32))
        
        # Build witness
        # Script: <locktime> CLTV DROP <user_pk> CHECKSIG
        # Stack consumption:
        # - CLTV checks tx locktime against stack value, drops it
        # - user_sig consumed by CHECKSIG
        # Witness order: [user_sig, script, control_block]
        
        witness_items = [
            user_sig,
            self.recovery_script,
            self.recovery_control
        ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime)


if __name__ == '__main__':
    print("Taproot Two-Factor Sweeper")
    print("Use sweep_cooperative() for User + Server path")
    print("Use sweep_recovery() for User-only recovery path")
