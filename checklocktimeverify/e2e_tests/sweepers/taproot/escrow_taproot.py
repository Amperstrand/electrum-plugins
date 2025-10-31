#!/usr/bin/env python3
"""
Taproot Escrow Transaction Sweeper

Builds sweep transactions for Taproot escrow with 2 script-path leaves.

Spend Paths:
1. Normal: Alice + Bob cooperation (anytime)
2. Arbitration: Lenny + (Alice OR Bob) after locktime

Uses BIP-341 script-path spending with Schnorr signatures.

Reference: taproot_escrow_builder.py, taproot_tx_builder.py
"""

import sys
from pathlib import Path
import hashlib
import struct
from typing import Dict, Optional

# Add bitcoin-tx-tutorial to path
tutorial_path = Path(__file__).parent.parent.parent / 'bitcoin-tx-tutorial' / 'functions'
if tutorial_path.exists():
    sys.path.insert(0, str(tutorial_path))

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


class TaprootEscrowSweeper:
    """
    Build Taproot escrow sweep transactions.
    
    Handles both spend paths:
    - Normal: Alice + Bob
    - Arbitration: Lenny + Alice/Bob
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
            script_info: Script info from taproot_escrow_builder.create_taproot_escrow_address()
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
        self.arbitration_script = bytes.fromhex(script_info['scripts']['arbitration']['script'])
        self.arbitration_control = bytes.fromhex(script_info['scripts']['arbitration']['control_block'])
        
        # Transaction fields (match working taproot_tx_builder.py)
        self.version = 2
        self.nsequence = 0xfffffffe  # Enable locktime
    
    def _build_unsigned_tx(
        self,
        dest_address: str,
        locktime: int = 0
    ) -> bytes:
        """
        Build unsigned transaction.
        
        Args:
            dest_address: Destination address (bech32/bech32m)
            locktime: nLockTime value (0 for normal path, block height for arbitration)
        
        Returns:
            Unsigned transaction bytes
        """
        # Parse destination address to get scriptPubKey
        # For now, assume P2WPKH destination (tb1q...)
        if dest_address.startswith('tb1q') or dest_address.startswith('bc1q'):
            # P2WPKH: OP_0 <20-byte-hash>
            # Decode bech32
            from bip_350_bech32_reference import decode
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            if witver != 0 or len(witprog) != 20:
                raise ValueError("Expected P2WPKH destination address")
            dest_script = bytes([0x00, 0x14]) + bytes(witprog)
        elif dest_address.startswith('tb1p') or dest_address.startswith('bc1p'):
            # P2TR: OP_1 <32-byte-pubkey>
            from bip_350_bech32_reference import decode
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            if witver != 1 or len(witprog) != 32:
                raise ValueError("Expected P2TR destination address")
            dest_script = bytes([0x51, 0x20]) + bytes(witprog)
        else:
            raise ValueError(f"Unsupported destination address format: {dest_address}")
        
        # Calculate fee (simple: 200 sats)
        fee_sats = 200
        output_amount = self.amount_sats - fee_sats
        
        if output_amount <= 0:
            raise ValueError(f"Insufficient funds: {self.amount_sats} sats - {fee_sats} fee")
        
        # Build transaction
        tx = bytearray()
        
        # Version (4 bytes, little-endian)
        tx.extend((2).to_bytes(4, 'little'))
        
        # Marker and flag for SegWit
        tx.append(0x00)  # Marker
        tx.append(0x01)  # Flag
        
        # Input count (1)
        tx.append(0x01)
        
        # Input
        # - Previous outpoint (txid + vout)
        tx.extend(bytes.fromhex(self.funding_txid)[::-1])  # Reverse for little-endian
        tx.extend(self.funding_vout.to_bytes(4, 'little'))
        
        # - ScriptSig (empty for SegWit)
        tx.append(0x00)
        
        # - Sequence (0xfffffffe for locktime, 0xffffffff otherwise)
        if locktime > 0:
            tx.extend((0xfffffffe).to_bytes(4, 'little'))
        else:
            tx.extend((0xffffffff).to_bytes(4, 'little'))
        
        # Output count (1)
        tx.append(0x01)
        
        # Output
        # - Amount (8 bytes, little-endian)
        tx.extend(output_amount.to_bytes(8, 'little'))
        
        # - ScriptPubKey
        tx.append(len(dest_script))
        tx.extend(dest_script)
        
        # Witness placeholder (will be filled later)
        # For now, empty witness
        tx.append(0x00)
        
        # Locktime (4 bytes)
        tx.extend(locktime.to_bytes(4, 'little'))
        
        return bytes(tx)
    
    def _compute_bip341_sighash(
        self,
        dest_address: str,
        script: bytes,
        locktime: int = 0
    ) -> bytes:
        """
        Compute BIP-341 sighash for script-path spending.
        
        BIP-341 sighash is different from BIP-143:
        - Uses single SHA256 (not double)
        - Different commitment structure
        - Includes taproot-specific fields
        
        Args:
            dest_address: Destination address
            script: Script being executed (tapleaf script)
            locktime: nLockTime value
        
        Returns:
            32-byte sighash for signing
        """
        # Parse destination to get output scriptPubKey and amount
        from bip_350_bech32_reference import decode
        
        if dest_address.startswith('tb1q') or dest_address.startswith('bc1q'):
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            dest_script = bytes([0x00, 0x14]) + bytes(witprog)
        elif dest_address.startswith('tb1p') or dest_address.startswith('bc1p'):
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            dest_script = bytes([0x51, 0x20]) + bytes(witprog)
        else:
            raise ValueError(f"Unsupported address: {dest_address}")
        
        fee_sats = 200
        output_amount = self.amount_sats - fee_sats
        
        # BIP-341 sighash computation (matching working taproot_tx_builder.py)
        # Reference: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki#common-signature-message
        
        # Basic fields
        epoch = bytes([0])
        hash_type = bytes([0])  # SIGHASH_DEFAULT
        tx_version = struct.pack("<I", self.version)
        tx_locktime = struct.pack("<I", locktime)
        
        # sha_prevouts (txid in little-endian + vout)
        txid_bytes = bytes.fromhex(self.funding_txid)[::-1]  # Reverse for little-endian
        prevout = txid_bytes + struct.pack("<I", self.funding_vout)
        sha_prevouts = sha256(prevout)
        
        # sha_amounts
        sha_amounts = sha256(struct.pack("<Q", self.amount_sats))
        
        # sha_scriptpubkeys (input scriptPubKey with varint length)
        # CRITICAL: Must use varint(), not bytes([len()])
        input_spk = bytes([0x51, 0x20]) + self.output_key  # Taproot output
        sha_scriptpubkeys = sha256(varint(len(input_spk)) + input_spk)
        
        # sha_sequences (use self.nsequence for locktime support)
        nsequence = self.nsequence if locktime > 0 else 0xffffffff
        sha_sequences = sha256(struct.pack("<I", nsequence))
        
        # sha_outputs
        output_data = struct.pack("<Q", output_amount) + varint(len(dest_script)) + dest_script
        sha_outputs = sha256(output_data)
        
        # spend_type = 2 (script-path spend, no annex)
        spend_type = bytes([0x02])
        
        # input_index = 0 (only one input)
        input_index = struct.pack("<I", 0)
        
        # TapLeaf hash (use varint for script length)
        leaf_version = bytes([0xc0])
        tapleaf_hash = tagged_hash("TapLeaf", leaf_version + varint(len(script)) + script)
        
        # key_version = 0 (for BIP-342)
        key_version = bytes([0x00])
        
        # codeseparator_pos = 0xffffffff (no OP_CODESEPARATOR)
        codeseparator_pos = struct.pack("<I", 0xffffffff)
        
        # Build preimage (matching working implementation exactly)
        preimage = (
            epoch +
            hash_type +
            tx_version +
            tx_locktime +
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
        
        # Compute sighash
        sighash = tagged_hash("TapSighash", preimage)
        
        return sighash
    
    def sweep_normal(
        self,
        alice_privkey_hex: str,
        bob_privkey_hex: str,
        dest_address: str
    ) -> str:
        """
        Sweep using normal path (Alice + Bob cooperation).
        
        Args:
            alice_privkey_hex: Alice's private key (32 bytes hex)
            bob_privkey_hex: Bob's private key (32 bytes hex)
            dest_address: Destination address
        
        Returns:
            Signed transaction hex
        """
        # Compute sighash
        sighash = self._compute_bip341_sighash(dest_address, self.normal_script, locktime=0)
        
        # Sign with both keys (BIP-340 Schnorr)
        alice_privkey = bytes.fromhex(alice_privkey_hex)
        bob_privkey = bytes.fromhex(bob_privkey_hex)
        
        alice_sig = schnorr_sign(sighash, alice_privkey, aux_rand=bytes(32))
        bob_sig = schnorr_sign(sighash, bob_privkey, aux_rand=bytes(32))
        
        # Build witness
        # Witness stack for script-path spend:
        # Script execution: <alice_pk> CHECKSIGVERIFY <bob_pk> CHECKSIG
        # Stack is consumed from bottom to top, so:
        # - Bottom: Bob's signature (for <bob_pk> CHECKSIG at end)
        # - Next: Alice's signature (for <alice_pk> CHECKSIGVERIFY first)
        # - Script
        # - Control block
        
        witness_items = [
            bob_sig,    # Bottom of stack - consumed by CHECKSIG (bob_pk)
            alice_sig,  # consumed by CHECKSIGVERIFY (alice_pk)
            self.normal_script,
            self.normal_control
        ]
        
        # Build complete transaction with witness
        return self._finalize_transaction(dest_address, witness_items, locktime=0)
    
    def sweep_arbitration(
        self,
        lenny_privkey_hex: str,
        co_signer_privkey_hex: str,
        dest_address: str,
        locktime: int,
        use_alice: bool = True
    ) -> str:
        """
        Sweep using arbitration path (Lenny + Alice/Bob after timeout).
        
        Args:
            lenny_privkey_hex: Lenny's private key (32 bytes hex)
            co_signer_privkey_hex: Alice or Bob's private key (32 bytes hex)
            dest_address: Destination address
            locktime: Block height for CLTV
            use_alice: True if co_signer is Alice, False if Bob
        
        Returns:
            Signed transaction hex
        """
        # Compute sighash (with locktime)
        sighash = self._compute_bip341_sighash(dest_address, self.arbitration_script, locktime)
        
        # Sign with both keys
        lenny_privkey = bytes.fromhex(lenny_privkey_hex)
        co_signer_privkey = bytes.fromhex(co_signer_privkey_hex)
        
        lenny_sig = schnorr_sign(sighash, lenny_privkey, aux_rand=bytes(32))
        co_signer_sig = schnorr_sign(sighash, co_signer_privkey, aux_rand=bytes(32))
        
        # Build witness for CHECKSIGADD script
        # Script: <locktime> CLTV DROP <lenny> CHECKSIGADD <alice> CHECKSIGADD <bob> CHECKSIGADD 2 EQUAL
        #
        # BIP-342: CHECKSIGADD pops sig (top), n (second), and reads pk from script
        # Script execution (consuming witness top to bottom):
        #   1. CLTV pops locktime, DROP removes it
        #   2. <lenny_pk> pushes lenny's key
        #   3. CHECKSIGADD pops lenny_pk, 0 (counter), lenny_sig → pushes 1
        #   4. <alice_pk> pushes alice's key
        #   5. CHECKSIGADD pops alice_pk, 1, alice_sig → pushes 2
        #   6. <bob_pk> pushes bob's key
        #   7. CHECKSIGADD pops bob_pk, 2, bob_empty → pushes 2 (no increment for empty)
        #   8. OP_2 pushes 2
        #   9. EQUAL pops 2, 2 → pushes TRUE
        #
        # Witness stack ordering detail:
        # For the FIRST CHECKSIGADD (Lenny), after the script pushes <lenny_pk>, the stack top three must be:
        #   top:   <lenny_pk>
        #   second:<counter=0>
        #   third: <lenny_sig>
        # Therefore, BEFORE <lenny_pk> is pushed, the stack (bottom→top) must be [..., <lenny_sig>, <counter=0>].
        # We also need the co-signer's signature (or empty) below those, and the other party's placeholder at bottom.
        # Final witness (bottom→top, excluding script/control): [other_empty_or_sig, co_signer_sig_or_empty, lenny_sig, 0]
        # Then add [script, control].
        
        if use_alice:
            # Alice signs, Bob doesn't
            witness_items = [
                b'',             # Bob's empty signature (bottom - for third CHECKSIGADD)
                co_signer_sig,   # Alice's signature (for second CHECKSIGADD)
                lenny_sig,       # Lenny's signature (for first CHECKSIGADD, must be below the counter)
                b'',             # Initial counter = 0 (for first CHECKSIGADD)
                self.arbitration_script,
                self.arbitration_control
            ]
        else:
            # Bob signs, Alice doesn't
            witness_items = [
                co_signer_sig,   # Bob's signature (bottom - for third CHECKSIGADD)
                b'',             # Alice's empty signature (for second CHECKSIGADD)
                lenny_sig,       # Lenny's signature (for first CHECKSIGADD)
                b'',             # Initial counter = 0
                self.arbitration_script,
                self.arbitration_control
            ]
        
        return self._finalize_transaction(dest_address, witness_items, locktime)
    
    def _finalize_transaction(
        self,
        dest_address: str,
        witness_items: list,
        locktime: int
    ) -> str:
        """
        Build final transaction with witness.
        
        Args:
            dest_address: Destination address
            witness_items: List of witness stack items (bytes)
            locktime: nLockTime value
        
        Returns:
            Complete signed transaction hex
        """
        from bip_350_bech32_reference import decode
        
        # Parse destination
        if dest_address.startswith('tb1q') or dest_address.startswith('bc1q'):
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            dest_script = bytes([0x00, 0x14]) + bytes(witprog)
        elif dest_address.startswith('tb1p') or dest_address.startswith('bc1p'):
            witver, witprog = decode('tb' if self.network == 'signet' else 'bc', dest_address)
            dest_script = bytes([0x51, 0x20]) + bytes(witprog)
        else:
            raise ValueError(f"Unsupported address: {dest_address}")
        
        fee_sats = 200
        output_amount = self.amount_sats - fee_sats
        
        # Build complete transaction (matching working taproot_tx_builder.py)
        tx = bytearray()
        
        # Version
        tx.extend(struct.pack("<I", self.version))
        
        # Marker and flag for witness
        tx.append(0x00)
        tx.append(0x01)
        
        # Input count
        tx.extend(varint(1))
        
        # Input
        # - Previous outpoint (txid + vout)
        txid_bytes = bytes.fromhex(self.funding_txid)[::-1]
        tx.extend(txid_bytes)
        tx.extend(struct.pack("<I", self.funding_vout))
        
        # - ScriptSig (empty for witness input)
        tx.extend(varint(0))
        
        # - Sequence
        nsequence = self.nsequence if locktime > 0 else 0xffffffff
        tx.extend(struct.pack("<I", nsequence))
        
        # Output count
        tx.extend(varint(1))
        
        # Output
        # - Amount
        tx.extend(struct.pack("<Q", output_amount))
        
        # - ScriptPubKey
        tx.extend(varint(len(dest_script)))
        tx.extend(dest_script)
        
        # Witness data
        witness = varint(len(witness_items))
        for item in witness_items:
            witness += varint(len(item)) + item
        tx.extend(witness)
        
        # Locktime
        tx.extend(struct.pack("<I", locktime))
        
        return tx.hex()


if __name__ == '__main__':
    # Test sweep construction (won't broadcast, just builds the tx)
    from taproot_escrow_builder import create_taproot_escrow_address
    
    # Test keys (from conftest.py)
    alice_pubkey = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
    bob_pubkey = "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
    lenny_pubkey = "03d30199d74fb5a22d47b6e054e2f378cedacffcb89904a61d75d0dbd407143e65"
    
    alice_privkey = "0000000000000000000000000000000000000000000000000000000000000002"
    bob_privkey = "0000000000000000000000000000000000000000000000000000000000000003"
    lenny_privkey = "0000000000000000000000000000000000000000000000000000000000000020"
    
    locktime = 275840
    
    # Create address
    addr_info = create_taproot_escrow_address(
        locktime=locktime,
        alice_pubkey=alice_pubkey,
        bob_pubkey=bob_pubkey,
        lenny_pubkey=lenny_pubkey,
        network='signet'
    )
    
    print("="*80)
    print("Taproot Escrow Sweeper - Test Transaction Construction")
    print("="*80)
    print(f"\n📍 Escrow Address: {addr_info['address']}")
    
    # Simulate funding (fake UTXO for testing)
    fake_txid = "a" * 64
    fake_vout = 0
    fake_amount = 2000
    
    sweeper = TaprootEscrowSweeper(
        funding_txid=fake_txid,
        funding_vout=fake_vout,
        amount_sats=fake_amount,
        script_info=addr_info,
        network='signet'
    )
    
    # Test destination
    dest_addr = "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
    
    print(f"\n🔧 Building Normal Path Sweep (Alice + Bob)...")
    normal_tx = sweeper.sweep_normal(alice_privkey, bob_privkey, dest_addr)
    print(f"   TX Size: {len(normal_tx)//2} bytes")
    print(f"   TX Hex: {normal_tx[:80]}...")
    
    print(f"\n🔧 Building Arbitration Path Sweep (Lenny + Alice)...")
    arb_tx = sweeper.sweep_arbitration(lenny_privkey, alice_privkey, dest_addr, locktime, use_alice=True)
    print(f"   TX Size: {len(arb_tx)//2} bytes")
    print(f"   TX Hex: {arb_tx[:80]}...")
    
    print(f"\n✅ Transaction construction complete!")
    print(f"\nNote: These are test transactions with fake UTXOs.")
    print(f"Real E2E tests will use actual funded addresses.")
