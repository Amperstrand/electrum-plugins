"""
Custom Taproot Transaction Builder

Manual byte-level transaction construction for taproot script-path spending.
Based on bitcoin-tx-tutorial patterns. No dependency on Electrum's PartialTransaction.

This builder gives complete control over transaction construction to avoid
potential Electrum incompatibilities with taproot script-path spending.
"""

import struct
import hashlib
from typing import Tuple, Optional

# Import BIP-340 reference implementation
import sys
import os
# Prefer vendored BIP-340 reference (tests-only) to avoid external dependency
_THIRD_PARTY = os.path.join(os.path.dirname(__file__), 'third_party')
if _THIRD_PARTY not in sys.path:
    sys.path.insert(0, _THIRD_PARTY)
from bip_0340_reference import schnorr_sign


def tagged_hash(tag: str, msg: bytes) -> bytes:
    """Compute tagged hash (BIP-340 style)."""
    tag_hash = sha256(tag.encode())
    return sha256(tag_hash + tag_hash + msg)


def sha256(data: bytes) -> bytes:
    """Single SHA256 hash."""
    return hashlib.sha256(data).digest()


def double_sha256(data: bytes) -> bytes:
    """Double SHA256 hash."""
    return sha256(sha256(data))


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


class TaprootTxBuilder:
    """Build taproot script-path spend transactions manually."""
    
    def __init__(
        self,
        txid: str,
        vout: int,
        amount: int,
        scriptpubkey: str,
        script: str,
        control_block: str,
        privkey: bytes,
        locktime: int = 0
    ):
        """
        Initialize taproot transaction builder.
        
        Args:
            txid: Funding transaction ID (hex string)
            vout: Output index
            amount: Input amount in satoshis
            scriptpubkey: Taproot scriptPubKey (hex, e.g., "5120...")
            script: Spending script (hex)
            control_block: Control block for script-path spend (hex)
            privkey: Private key (32 bytes)
            locktime: Transaction locktime
        """
        self.txid = txid
        self.vout = vout
        self.amount = amount
        self.scriptpubkey = bytes.fromhex(scriptpubkey)
        self.script = bytes.fromhex(script)
        self.control_block = bytes.fromhex(control_block)
        self.privkey = privkey
        self.locktime = locktime
        
        # Transaction fields
        self.version = 2
        self.nsequence = 0xfffffffe  # Enable locktime (not 0xffffffff)
        
    def compute_tapleaf_hash(self) -> bytes:
        """Compute TapLeaf hash for the script."""
        leaf_version = bytes([0xc0])
        script_len = varint(len(self.script))
        return tagged_hash("TapLeaf", leaf_version + script_len + self.script)
    
    def compute_sighash(self, dest_scriptpubkey: bytes, dest_amount: int) -> bytes:
        """
        Compute BIP-341 sighash for script-path spend.
        
        Args:
            dest_scriptpubkey: Destination scriptPubKey bytes
            dest_amount: Output amount in satoshis
            
        Returns:
            32-byte sighash
        """
        # Build BIP-341 sighash preimage
        # Reference: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki#common-signature-message
        
        # Basic fields
        epoch = bytes([0])
        hash_type = bytes([0])  # SIGHASH_DEFAULT
        tx_version = struct.pack("<I", self.version)
        tx_locktime = struct.pack("<I", self.locktime)
        
        # sha_prevouts (txid in little-endian + vout)
        txid_bytes = bytes.fromhex(self.txid)[::-1]  # Reverse for little-endian
        prevout = txid_bytes + struct.pack("<I", self.vout)
        sha_prevouts = sha256(prevout)
        
        # sha_amounts
        sha_amounts = sha256(struct.pack("<Q", self.amount))
        
        # sha_scriptpubkeys (input scriptPubKey with varint length)
        sha_scriptpubkeys = sha256(varint(len(self.scriptpubkey)) + self.scriptpubkey)
        
        # sha_sequences
        sha_sequences = sha256(struct.pack("<I", self.nsequence))
        
        # sha_outputs
        output_data = struct.pack("<Q", dest_amount) + varint(len(dest_scriptpubkey)) + dest_scriptpubkey
        sha_outputs = sha256(output_data)
        
        # spend_type = 2 (script-path spend, no annex)
        spend_type = bytes([0x02])
        
        # input_index = 0 (only one input)
        input_index = struct.pack("<I", 0)
        
        # TapLeaf hash
        tapleaf_hash = self.compute_tapleaf_hash()
        
        # key_version = 0 (for BIP-342)
        key_version = bytes([0x00])
        
        # codeseparator_pos = 0xffffffff (no OP_CODESEPARATOR)
        codeseparator_pos = struct.pack("<I", 0xffffffff)
        
        # Build preimage
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
    
    def sign_transaction(self, dest_scriptpubkey: bytes, dest_amount: int) -> bytes:
        """
        Sign the transaction using BIP-340 Schnorr signature.
        
        Args:
            dest_scriptpubkey: Destination scriptPubKey bytes
            dest_amount: Output amount in satoshis
            
        Returns:
            64-byte Schnorr signature
        """
        sighash = self.compute_sighash(dest_scriptpubkey, dest_amount)
        
        # Use BIP-340 reference implementation for signing
        aux_rand = bytes(32)  # All zeros for deterministic signing
        signature = schnorr_sign(sighash, self.privkey, aux_rand)
        
        return signature
    
    def build_transaction(self, dest_scriptpubkey: bytes, dest_amount: int) -> str:
        """
        Build and sign the complete transaction.
        
        Args:
            dest_scriptpubkey: Destination scriptPubKey bytes
            dest_amount: Output amount in satoshis
            
        Returns:
            Signed transaction hex
        """
        # Sign the transaction
        signature = self.sign_transaction(dest_scriptpubkey, dest_amount)
        
        # Build transaction manually
        # Version
        tx_bytes = struct.pack("<I", self.version)
        
        # Marker and flag (for witness transactions)
        tx_bytes += bytes([0x00, 0x01])
        
        # Input count
        tx_bytes += varint(1)
        
        # Input: txid (little-endian) + vout + scriptSig + nsequence
        txid_bytes = bytes.fromhex(self.txid)[::-1]
        tx_bytes += txid_bytes
        tx_bytes += struct.pack("<I", self.vout)
        tx_bytes += varint(0)  # Empty scriptSig for witness input
        tx_bytes += struct.pack("<I", self.nsequence)
        
        # Output count
        tx_bytes += varint(1)
        
        # Output: amount + scriptPubKey
        tx_bytes += struct.pack("<Q", dest_amount)
        tx_bytes += varint(len(dest_scriptpubkey))
        tx_bytes += dest_scriptpubkey
        
        # Witness data
        # Number of witness items for input 0: 3 (signature, script, control_block)
        witness = varint(3)
        witness += varint(len(signature)) + signature
        witness += varint(len(self.script)) + self.script
        witness += varint(len(self.control_block)) + self.control_block
        tx_bytes += witness
        
        # Locktime
        tx_bytes += struct.pack("<I", self.locktime)
        
        return tx_bytes.hex()


def build_taproot_sweep_tx(
    txid: str,
    vout: int,
    amount: int,
    scriptpubkey: str,
    script: str,
    control_block: str,
    privkey_hex: str,
    dest_scriptpubkey: str,
    locktime: int = 0,
    fee: int = 200
) -> Tuple[str, bytes, bytes]:
    """
    Convenience function to build a taproot sweep transaction.
    
    Args:
        txid: Funding transaction ID
        vout: Output index
        amount: Input amount in satoshis
        scriptpubkey: Taproot scriptPubKey (hex)
        script: Spending script (hex)
        control_block: Control block (hex)
        privkey_hex: Private key (hex)
        dest_scriptpubkey: Destination scriptPubKey (hex)
        locktime: Transaction locktime
        fee: Transaction fee in satoshis
        
    Returns:
        Tuple of (transaction_hex, sighash, signature)
    """
    # Convert private key
    privkey = bytes.fromhex(privkey_hex)
    if len(privkey) != 32:
        # Pad with zeros if needed
        privkey = privkey.rjust(32, b'\x00')
    
    # Convert destination scriptPubKey
    dest_spk = bytes.fromhex(dest_scriptpubkey)
    
    # Detect OP_RETURN outputs (start with 0x6a) and force amount to 0
    # This prevents "maxburnamount" policy errors
    if dest_spk[0:1] == bytes([0x6a]):
        output_amount = 0
        print(f"   OP_RETURN detected: output_amount set to 0 (full {amount} sats burned as fee)")
    else:
        # Calculate output amount
        output_amount = amount - fee
        if output_amount <= 0:
            raise ValueError(f"Amount ({amount}) must be greater than fee ({fee})")
    
    # Build transaction
    builder = TaprootTxBuilder(
        txid=txid,
        vout=vout,
        amount=amount,
        scriptpubkey=scriptpubkey,
        script=script,
        control_block=control_block,
        privkey=privkey,
        locktime=locktime
    )
    
    # Get sighash for debugging
    sighash = builder.compute_sighash(dest_spk, output_amount)
    
    # Build and sign
    tx_hex = builder.build_transaction(dest_spk, output_amount)
    
    # Get signature for debugging
    signature = builder.sign_transaction(dest_spk, output_amount)
    
    return tx_hex, sighash, signature


def create_taproot_cltv_address(locktime: int, pubkey_hex: str, network: str = 'signet'):
    """
    Create a taproot address for simple CLTV script.
    
    Args:
        locktime: Block height or timestamp (4 bytes when encoded)
        pubkey_hex: Public key hex string (33 bytes compressed or 32 bytes x-only)
        network: 'signet', 'testnet', or 'mainnet'
        
    Returns:
        dict with:
            - address: bech32m taproot address
            - output_script: scriptPubKey hex
            - script_hex: the CLTV script hex
            - control_block: control block for script-path spending
            - internal_key: internal pubkey (NUMS point)
            - output_key: tweaked output key
    """
    import sys
    import os
    # Import from vendored third_party copies (tests-only)
    _THIRD_PARTY = os.path.join(os.path.dirname(__file__), 'third_party')
    if _THIRD_PARTY not in sys.path:
        sys.path.insert(0, _THIRD_PARTY)
    from bip_0340_reference import point_mul, lift_x, G, point_add
    from bip_350_bech32_reference import encode as bech32_encode
    
    # Build CLTV script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG
    # IMPORTANT: Use minimal script-number encoding for locktime (BIP-342 requires minimal number encoding in Tapscript)
    try:
        from script_builders.base import encode_script_number
        locktime_bytes = encode_script_number(locktime)
    except Exception:
        # Fallback minimal script-number encoding (little-endian, strip leading zeros, sign bit in MSB)
        def _enc(n: int) -> bytes:
            if n == 0:
                return b""
            neg = n < 0
            n = -n if neg else n
            out = bytearray()
            while n:
                out.append(n & 0xff)
                n >>= 8
            if out[-1] & 0x80:
                out.append(0x80 if neg else 0x00)
            elif neg:
                out[-1] |= 0x80
            return bytes(out)
        locktime_bytes = _enc(locktime)
    
    # Handle pubkey format (compressed or x-only)
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    if len(pubkey_bytes) == 33:
        # Compressed - strip prefix
        pubkey_xonly = pubkey_bytes[1:]
    elif len(pubkey_bytes) == 32:
        # Already x-only
        pubkey_xonly = pubkey_bytes
    else:
        raise ValueError(f"Invalid pubkey length: {len(pubkey_bytes)}")
    
    # Build script with minimal push for locktime
    script = (
        bytes([len(locktime_bytes)]) + locktime_bytes +
        bytes([0xb1]) +  # OP_CHECKLOCKTIMEVERIFY
        bytes([0x75]) +  # OP_DROP
        bytes([0x20]) + pubkey_xonly +  # PUSH pubkey (32 bytes)
        bytes([0xac])    # OP_CHECKSIG
    )
    
    # Use NUMS point as internal key (BIP-341 standard)
    # H = lift_x(0x50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0)
    NUMS_H = 0x50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0
    internal_key = NUMS_H.to_bytes(32, 'big')
    
    # Compute TapLeaf hash
    leaf_version = bytes([0xc0])
    script_len = varint(len(script))
    tapleaf_hash = tagged_hash("TapLeaf", leaf_version + script_len + script)
    
    # Compute TapTweak
    taptweak = tagged_hash("TapTweak", internal_key + tapleaf_hash)
    
    # Compute output key: P = lift_x(internal_key) + int(taptweak)*G
    P = lift_x(int.from_bytes(internal_key, 'big'))
    t = int.from_bytes(taptweak, 'big')
    Q = point_mul(G, t)
    
    # Add points using BIP-340 reference implementation
    output_point = point_add(P, Q)
    if output_point is None:
        raise ValueError("Point addition failed")
    
    # Get x-coordinate (even y-coordinate for taproot)
    output_key = output_point[0].to_bytes(32, 'big')
    
    # Build control block: <leaf_version|parity_bit> <internal_key>
    # Parity bit (LSB) is 0 if output key has even y, 1 if odd
    y_parity_bit = output_point[1] & 1
    control_block = bytes([leaf_version[0] | y_parity_bit]) + internal_key
    
    # Build scriptPubKey: OP_1 <32-byte-output-key>
    scriptpubkey = bytes([0x51, 0x20]) + output_key
    
    # Encode address
    network_hrp = {
        'mainnet': 'bc',
        'testnet': 'tb',
        'signet': 'tb'
    }[network]
    
    address = bech32_encode(network_hrp, 1, output_key)
    
    return {
        'address': address,
        'output_script': scriptpubkey.hex(),
        'script_hex': script.hex(),
        'control_block': control_block.hex(),
        'internal_key': internal_key.hex(),
        'output_key': output_key.hex(),
        'locktime': locktime
    }
