"""
Taproot Sighash Computation (BIP-341)

Computes the sighash for Taproot script-path spending according to BIP-341.

This is fundamentally different from P2WSH (BIP-143):
- Uses tagged SHA256 hashing
- Different preimage structure
- Includes TapLeaf hash
- No separate script code field

Usage:
    >>> from cltv_lib.builders.taproot.taproot_sighash_builder import compute_taproot_sighash
    >>> sighash = compute_taproot_sighash(
    ...     tx=tx,
    ...     input_index=0,
    ...     prevout_amount=1000,
    ...     prevout_scriptpubkey=bytes.fromhex('5120...'),
    ...     script=bytes.fromhex('...'),
    ...     control_block=bytes.fromhex('...')
    ... )
"""

import struct
from typing import Optional

# Import Electrum utilities
from electrum.crypto import sha256

# Import local taproot utilities
from .taproot_utils import tagged_hash, varint, compute_tapleaf_hash
from .taproot_constants import OP_WITNESS_V1, OP_PUSH_32


def compute_taproot_sighash(
    tx,  # PartialTransaction
    input_index: int,
    prevout_amount: int,
    prevout_scriptpubkey: bytes,
    script: bytes,
    control_block: Optional[bytes] = None,
    hash_type: int = 0  # SIGHASH_DEFAULT
) -> bytes:
    """
    Compute BIP-341 Taproot sighash for script-path spending.
    
    This implements the sighash algorithm for Taproot as specified in BIP-341.
    It's significantly different from the BIP-143 (SegWit v0) sighash used for P2WSH.
    
    Args:
        tx: Electrum PartialTransaction object
        input_index: Index of the input being signed (0-based)
        prevout_amount: Amount of the UTXO being spent (in satoshis)
        prevout_scriptpubkey: scriptPubKey of the UTXO (51 20 <32-bytes>)
        script: The Tapscript being executed
        control_block: Control block (optional, for validation)
        hash_type: Signature hash type (0 = SIGHASH_DEFAULT)
    
    Returns:
        32-byte sighash ready for Schnorr signing
    
    Raises:
        ValueError: If input_index is out of range
        ValueError: If transaction structure is invalid
    
    Reference:
        BIP-341 Signature Validation: 
        https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki#common-signature-message
    
    Example:
        >>> sighash = compute_taproot_sighash(
        ...     tx=my_tx,
        ...     input_index=0,
        ...     prevout_amount=1000,
        ...     prevout_scriptpubkey=bytes.fromhex('51201234...'),
        ...     script=bytes.fromhex('04e09304b17576a914...'),
        ...     control_block=bytes.fromhex('c050929b...')
        ... )
        >>> len(sighash)
        32
    """
    # Validate input index
    inputs = tx.inputs()
    if input_index >= len(inputs):
        raise ValueError(f"input_index {input_index} out of range (tx has {len(inputs)} inputs)")
    
    # Get transaction fields
    version = tx.version if hasattr(tx, 'version') else 2
    locktime = tx.locktime
    
    # BIP-341 sighash preimage structure
    # See: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki#common-signature-message
    
    # Epoch (always 0 for now)
    epoch = bytes([0])
    
    # Hash type (0 = SIGHASH_DEFAULT for Taproot)
    hash_type_byte = bytes([hash_type])
    
    # Transaction version (4 bytes, little-endian)
    tx_version = struct.pack("<I", version)
    
    # Transaction locktime (4 bytes, little-endian)
    tx_locktime = struct.pack("<I", locktime)
    
    # sha_prevouts: Hash of all input prevouts
    prevouts_data = b''
    for inp in inputs:
        # txid (32 bytes, little-endian)
        txid_bytes = bytes.fromhex(inp.prevout.txid.hex())[::-1]
        # vout (4 bytes, little-endian)
        vout_bytes = struct.pack("<I", inp.prevout.out_idx)
        prevouts_data += txid_bytes + vout_bytes
    sha_prevouts = sha256(prevouts_data)
    
    # sha_amounts: Hash of all input amounts
    amounts_data = b''
    for inp in inputs:
        amount = inp._trusted_value_sats if hasattr(inp, '_trusted_value_sats') else prevout_amount
        amounts_data += struct.pack("<Q", amount)
    sha_amounts = sha256(amounts_data)
    
    # sha_scriptpubkeys: Hash of all input scriptPubKeys
    # 
    # CRITICAL INSIGHT: scriptPubKey does NOT depend on the spending path!
    # - For Taproot: scriptPubKey = 0x51 0x20 <32-byte output_key>
    # - The output_key is derived from internal_key + merkle_root of ALL leaf scripts
    # - It's the SAME regardless of which path (key-path vs script-path, or which leaf) you take
    # - Only the WITNESS (script + control_block) changes based on the path
    #
    # BITCOIN CORE APPROACH:
    # - Gets scriptPubKey from witness_utxo or non_witness_utxo (actual UTXO data)
    # - Does NOT derive it - uses what was actually on the blockchain
    #
    # OUR APPROACH (for same-address sweeps):
    # - Derive scriptPubKey once from address params (deterministic)
    # - Store on all inputs from the same address (they share the same scriptPubKey)
    # - This is correct for our use case but should ideally verify against on-chain data
    #
    # MULTI-ADDRESS TRANSACTIONS:
    # - If inputs are from DIFFERENT addresses, each would have a DIFFERENT scriptPubKey
    # - In that case, we'd need to get scriptPubKey from each input's actual prevout data
    scriptpubkeys_data = b''
    for i, inp in enumerate(inputs):
        if i == input_index:
            # For the input being signed, use the provided prevout_scriptpubkey
            spk = prevout_scriptpubkey
        else:
            # For other inputs, try to get scriptPubKey from input object
            # This should be set when building the transaction (for same-address sweeps)
            if hasattr(inp, 'scriptpubkey') and inp.scriptpubkey is not None:
                spk = inp.scriptpubkey
            elif hasattr(inp, '_scriptpubkey') and inp._scriptpubkey is not None:
                # Fallback: check for _scriptpubkey (private attribute)
                spk = inp._scriptpubkey
            else:
                # Fallback: assume same address (all inputs share same scriptPubKey)
                # NOTE: This assumes all inputs are from the same address!
                # For multi-address transactions, this would be WRONG and we'd need
                # to get scriptPubKey from each input's actual prevout/UTXO data
                spk = prevout_scriptpubkey
        
        if spk is None:
            raise ValueError(
                f"Missing scriptPubKey for input {i}. "
                f"All inputs must have scriptPubKey set. "
                f"This should come from the actual UTXO data (like Bitcoin Core's witness_utxo), "
                f"not derived from spending path (scriptPubKey doesn't depend on path)."
            )
        
        scriptpubkeys_data += varint(len(spk)) + spk
    sha_scriptpubkeys = sha256(scriptpubkeys_data)
    
    # sha_sequences: Hash of all input sequences
    sequences_data = b''
    for inp in inputs:
        sequences_data += struct.pack("<I", inp.nsequence)
    sha_sequences = sha256(sequences_data)
    
    # sha_outputs: Hash of all outputs
    outputs = tx.outputs()
    outputs_data = b''
    for out in outputs:
        # Amount (8 bytes, little-endian)
        amount_bytes = struct.pack("<Q", out.value)
        # scriptPubKey
        spk_bytes = out.scriptpubkey
        outputs_data += amount_bytes + varint(len(spk_bytes)) + spk_bytes
    sha_outputs = sha256(outputs_data)
    
    # spend_type: 2 for script-path spending without annex
    # Bit 0: 0 = no annex, 1 = annex present
    # Bit 1: 0 = key-path, 1 = script-path
    spend_type = bytes([0x02])  # Script-path, no annex
    
    # input_index (4 bytes, little-endian)
    input_index_bytes = struct.pack("<I", input_index)
    
    # TapLeaf hash
    # CRITICAL: Must use TAPSCRIPT_LEAF_VERSION (0xC0) for tapscript v0
    from .taproot_constants import TAPSCRIPT_LEAF_VERSION
    tapleaf_hash = compute_tapleaf_hash(script, TAPSCRIPT_LEAF_VERSION)
    
    # key_version: Always 0 for BIP-342 (Tapscript)
    key_version = bytes([0x00])
    
    # codeseparator_pos: 0xffffffff (no OP_CODESEPARATOR)
    codeseparator_pos = struct.pack("<I", 0xffffffff)
    
    # Build the preimage
    preimage = (
        epoch +
        hash_type_byte +
        tx_version +
        tx_locktime +
        sha_prevouts +
        sha_amounts +
        sha_scriptpubkeys +
        sha_sequences +
        sha_outputs +
        spend_type +
        input_index_bytes +
        tapleaf_hash +
        key_version +
        codeseparator_pos
    )
    
    # Compute sighash using BIP-341 tagged hash
    sighash = tagged_hash("TapSighash", preimage)
    
    return sighash


def compute_taproot_sighash_simple(
    txid: str,
    vout: int,
    amount: int,
    scriptpubkey: bytes,
    script: bytes,
    dest_scriptpubkey: bytes,
    dest_amount: int,
    locktime: int = 0,
    nsequence: int = 0xfffffffe,
    version: int = 2
) -> bytes:
    """
    Simplified Taproot sighash for single-input, single-output transactions.
    
    This is a convenience function for simple cases where you don't have
    a full PartialTransaction object. Use compute_taproot_sighash() for
    complex transactions.
    
    Args:
        txid: Funding transaction ID (hex string)
        vout: Output index
        amount: Input amount in satoshis
        scriptpubkey: Taproot scriptPubKey (51 20 <32-bytes>)
        script: The Tapscript being executed
        dest_scriptpubkey: Destination output scriptPubKey
        dest_amount: Destination output amount
        locktime: Transaction locktime (default: 0)
        nsequence: Input sequence (default: 0xfffffffe for locktime)
        version: Transaction version (default: 2)
    
    Returns:
        32-byte sighash
    
    Example:
        >>> sighash = compute_taproot_sighash_simple(
        ...     txid='abcd1234...',
        ...     vout=0,
        ...     amount=1000,
        ...     scriptpubkey=bytes.fromhex('5120...'),
        ...     script=bytes.fromhex('...'),
        ...     dest_scriptpubkey=bytes.fromhex('...'),
        ...     dest_amount=800,
        ...     locktime=600000
        ... )
    """
    # BIP-341 sighash components
    epoch = bytes([0])
    hash_type = bytes([0])  # SIGHASH_DEFAULT
    
    # Transaction fields
    tx_version = struct.pack("<I", version)
    tx_locktime = struct.pack("<I", locktime)
    
    # sha_prevouts
    txid_bytes = bytes.fromhex(txid)[::-1]  # Reverse for little-endian
    prevout = txid_bytes + struct.pack("<I", vout)
    sha_prevouts = sha256(prevout)
    
    # sha_amounts
    sha_amounts = sha256(struct.pack("<Q", amount))
    
    # sha_scriptpubkeys
    sha_scriptpubkeys = sha256(varint(len(scriptpubkey)) + scriptpubkey)
    
    # sha_sequences
    sha_sequences = sha256(struct.pack("<I", nsequence))
    
    # sha_outputs
    output_data = struct.pack("<Q", dest_amount) + varint(len(dest_scriptpubkey)) + dest_scriptpubkey
    sha_outputs = sha256(output_data)
    
    # spend_type (script-path, no annex)
    spend_type = bytes([0x02])
    
    # input_index (always 0 for single-input)
    input_index = struct.pack("<I", 0)
    
    # TapLeaf hash
    # CRITICAL: Must use TAPSCRIPT_LEAF_VERSION (0xC0) for tapscript v0
    from .taproot_constants import TAPSCRIPT_LEAF_VERSION
    tapleaf_hash = compute_tapleaf_hash(script, TAPSCRIPT_LEAF_VERSION)
    
    # key_version and codeseparator
    key_version = bytes([0x00])
    codeseparator_pos = struct.pack("<I", 0xffffffff)
    
    # Build preimage
    preimage = (
        epoch + hash_type + tx_version + tx_locktime +
        sha_prevouts + sha_amounts + sha_scriptpubkeys + sha_sequences +
        sha_outputs + spend_type + input_index + tapleaf_hash +
        key_version + codeseparator_pos
    )
    
    # Compute sighash
    return tagged_hash("TapSighash", preimage)


def compute_bip341_sighash(
    funding_txid: str,
    funding_vout: int,
    amount_sats: int,
    output_key: str,
    script_hex: str,
    dest_address,  # Union[str, Tuple[str, str]] - address or ('op_return', data_hex)
    network: str = 'signet',
    locktime: int = 0,
    fee_sats: int = 200
) -> bytes:
    """
    Compute BIP-341 sighash for script-path spending with address-based destination.
    
    This is a convenience function that handles address decoding internally.
    Used by Taproot sweepers for simplified sighash computation.
    
    Args:
        funding_txid: Transaction ID of the funding transaction (hex string)
        funding_vout: Output index being spent
        amount_sats: Amount in satoshis of the UTXO being spent
        output_key: Taproot output key (32-byte hex string)
        script_hex: Tapscript being executed (hex string)
        dest_address: Destination address (bech32m) or ('op_return', data_hex)
        network: 'mainnet', 'testnet', 'testnet4', 'signet', or 'regtest'
        locktime: nLockTime value (0 for no locktime)
        fee_sats: Fee in satoshis (default 200)
    
    Returns:
        32-byte sighash for signing
    
    Example:
        >>> sighash = compute_bip341_sighash(
        ...     funding_txid='abcd1234...',
        ...     funding_vout=0,
        ...     amount_sats=1000,
        ...     output_key='50929b74...',
        ...     script_hex='04e09304b17576a914...',
        ...     dest_address='tb1p...',
        ...     network='signet',
        ...     locktime=600000,
        ...     fee_sats=200
        ... )
    """
    from electrum.bitcoin import address_to_script, make_op_return
    
    script = bytes.fromhex(script_hex)
    
    # Decode destination address or OP_RETURN
    if isinstance(dest_address, tuple) and dest_address[0] == 'op_return':
        # OP_RETURN output - use Electrum's make_op_return for correct push opcodes
        data_hex = dest_address[1]
        data_bytes = bytes.fromhex(data_hex)
        dest_script = make_op_return(data_bytes)
        output_amount = 0
    else:
        # Regular address output - use Electrum's address decoding
        try:
            addr_script = address_to_script(dest_address)
            # address_to_script may return bytes or hex string depending on Electrum version
            if isinstance(addr_script, (bytes, bytearray)):
                dest_script = bytes(addr_script)
            else:
                dest_script = bytes.fromhex(addr_script)
        except Exception as e:
            raise ValueError(f"Invalid destination address: {dest_address}") from e
        output_amount = amount_sats - fee_sats
    
    # Build Taproot scriptPubKey for prevout
    if isinstance(output_key, bytes):
        output_key_bytes = output_key
    else:
        output_key_bytes = bytes.fromhex(output_key)
    prevout_scriptpubkey = bytes([OP_WITNESS_V1, OP_PUSH_32]) + output_key_bytes  # OP_1 <32-byte-key>
    
    # Compute nSequence
    nsequence = 0xfffffffe if locktime > 0 else 0xffffffff
    
    # Use the simple sighash function
    return compute_taproot_sighash_simple(
        txid=funding_txid,
        vout=funding_vout,
        amount=amount_sats,
        scriptpubkey=prevout_scriptpubkey,
        script=script,
        dest_scriptpubkey=dest_script,
        dest_amount=output_amount,
        locktime=locktime,
        nsequence=nsequence,
        version=2
    )
