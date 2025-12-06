"""
Sweep Utilities - DRY sweep helper for E2E tests

Generic sweep function that works for all script types and formats:
- Simple CLTV (1 signature)
- Escrow Cooperation (2 signatures)
- Escrow Refund (1 signature)
- Future: Channels, HTLC, etc.

Supports: P2SH, P2WSH (Taproot removed - see taproot_tx_builder.py)

IMPORTANT: Taproot support was removed from this file on October 28, 2025.
Reason: Critical BIP-341 bug - used double SHA256 instead of single SHA256.
See: archive/broken_taproot_electrum_implementation/README.md
Use: taproot_tx_builder.py for working taproot implementation.

Uses sweeper classes from registry - fully format-agnostic.
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import sys
import os

# Import network configuration
from network_config import NETWORK_FLAG, configure_electrum
configure_electrum()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import electrum_ecc as ecc
from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput
from electrum.transaction import TxOutpoint

from registry import get_sweeper, get_format
from cltv_lib.sweepers import SweepError, LockedError, ValidationError
from script_utils import ScriptFormat


def sweep_funded_output(
    test_data: Dict[str, Any],
    destination_address: str,
    current_height: int,
    fee_sats: int = 200,
    **sweep_kwargs
) -> str:
    """
    Generic sweep function that works for P2SH and P2WSH script types.
    
    NOTE: For Taproot, use taproot_tx_builder.py instead.
    
    Uses the sweeper class architecture to handle all complexity:
    - Sweeper determines required keys
    - Sweeper builds correct witness (1-N signatures)
    - Sweeper handles format differences (P2SH, P2WSH)
    
    Args:
        test_data: State data with script_hex, funding info, private keys
        destination_address: Where to send swept funds (address string or ('op_return', hex_data) tuple)
        current_height: Current blockchain height (for locktime validation)
        fee_sats: Transaction fee in satoshis
        **sweep_kwargs: Options passed to sweeper constructor
            - use_refund_path: bool (for escrow)
            - refund_signer: str (for escrow refund: 'alice' or 'bob')
            - reveal_preimage: bytes (for HTLC in future)
    
    Returns:
        sweep_txid: Transaction ID of successful sweep
    
    Raises:
        LockedError: If output still locked (locktime not reached)
        ValidationError: If missing required data
        SweepError: If transaction creation or broadcast fails
    
    Example:
        # Simple CLTV (1 key)
        sweep_txid = sweep_funded_output(
            test_data=simple_test,
            destination_address="tb1q...",
            current_height=107552
        )
        
        # Escrow cooperation (2 keys)
        sweep_txid = sweep_funded_output(
            test_data=escrow_test,
            destination_address="tb1q...",
            current_height=107552,
            use_refund_path=False  # Cooperation path
        )
        
        # Escrow refund (1 key from 2 available)
        sweep_txid = sweep_funded_output(
            test_data=escrow_test,
            destination_address="tb1q...",
            current_height=107552,
            use_refund_path=True,   # Refund path
            refund_signer='alice'    # Which key to use
        )
    """
    
    # 0. Print comprehensive debugging information
    print(f"\n{'='*80}")
    print(f"🔧 SWEEP DEBUGGING INFO")
    print(f"{'='*80}")
    print(f"Test Number: {test_data.get('test_number', 'N/A')}")
    print(f"Script Type: {test_data.get('script_type', 'N/A')}")
    print(f"Address: {test_data.get('address', 'N/A')}")
    print(f"Amount: {test_data.get('amount_sats', 'N/A')} sats")
    print(f"UTXO: {test_data.get('funding_txid', 'N/A')}:{test_data.get('funding_vout', 'N/A')}")
    print(f"Current Height: {current_height}")
    print(f"Locktime: {test_data.get('locktime', 'N/A')}")
    print(f"Spend Path: {sweep_kwargs}")
    print(f"Format: {test_data.get('format', 'N/A')}")
    print(f"Script Hex: {test_data.get('script_hex', 'N/A')[:40]}..." if test_data.get('script_hex') else "Script Hex: N/A")
    print(f"{'='*80}\n")
    
    # 1. Determine script_type from state data
    # State structure: category (simple_cltv/escrow_timeout) + variant (p2sh/p2wsh)
    # Registry expects: script_type like 'cltv_hodl' or 'cltv_escrow_timeout'
    
    # v12.0.0: script_type is always stored - no legacy inference needed
    script_type = test_data.get('script_type')
    if not script_type:
        raise ValueError("script_type is required in test_data (v12.0.0+)")
    
    # 2. Get sweeper - it determines path from kwargs automatically
    # GenericSweeper uses ContractDefinition as single source of truth
    from cltv_lib.contracts import CONTRACTS
    from cltv_lib.address_regenerator import parse_script_type
    
    # Extract path from kwargs (sweeper will use this)
    path = sweep_kwargs.get('path', 'sweep')
    # Avoid passing 'path' twice (both positionally and in **kwargs)
    # which would cause: get_sweeper() got multiple values for 'path'
    if 'path' in sweep_kwargs:
        sweep_kwargs = {k: v for k, v in sweep_kwargs.items() if k != 'path'}
    
    try:
        sweeper = get_sweeper(script_type, path=path, **sweep_kwargs)
    except Exception as e:
        raise ValidationError(f"Failed to get sweeper for {script_type}: {e}")
    
    # Use sweeper's resolved path (it handles all legacy kwargs like use_refund_path)
    path = sweeper.path
    
    # path_kwargs for functions that still need it
    path_kwargs = {'path': path}
    
    # Get ContractDefinition for path-specific script selection
    contract_name, _ = parse_script_type(script_type)
    contract = CONTRACTS.get(contract_name) if contract_name else None
    
    def _get_leaf_index_for_path(path_name: str) -> int:
        """Get leaf index from SpendingPath.leaf_index (single source of truth)."""
        if contract:
            path_obj = contract.get_path(path_name)
            if path_obj and path_obj.leaf_index is not None:
                return path_obj.leaf_index
        return 0
    
    def _get_path_script(path_name: str, leaf_idx: int):
        """Get path-specific script, with fallback to leaf_scripts."""
        script = test_data.get(f'{path_name}_script')
        control = test_data.get(f'{path_name}_control')
        
        if not script and 'leaf_scripts' in test_data:
            script = test_data['leaf_scripts'].get(f'leaf_{leaf_idx}')
        if not control and 'control_blocks' in test_data:
            control = test_data['control_blocks'].get(f'leaf_{leaf_idx}')
        
        return script, control
    
    # Get script for the path using ContractDefinition
    script_hex = None
    control_block_hex = None
    leaf_idx = _get_leaf_index_for_path(path)
    script_hex, control_block_hex = _get_path_script(path, leaf_idx)
    
    # Fallback to generic script_hex if path-specific not found
    if not script_hex:
        script_hex = test_data.get('script_hex')
    if not control_block_hex:
        control_block_hex = test_data.get('control_block_hex') or test_data.get('control_block')
    
    if not script_hex:
        raise ValidationError(f"Missing script_hex for {script_type}")
    
    # Sweeper already obtained above - no need to get it again
    
    output_data = {
        'script_hex': script_hex,
        'script_type': script_type,
        'script_params': test_data.get('script_params', {}),
        'locktime': test_data.get('locktime'),  # Add locktime
        'data_preimage': test_data.get('data_preimage'),  # Data publishing
        'data_hash': test_data.get('data_hash'),  # Data publishing
        # Taproot-specific fields
        'control_block_hex': control_block_hex,
        'internal_key': test_data.get('internal_key'),
        'output_key': test_data.get('output_key'),
        'output_script': test_data.get('output_script'),
    }
    
    # Add locktime to script_params if not there
    if 'locktime' not in output_data['script_params'] and 'locktime' in test_data:
        output_data['script_params']['locktime'] = test_data['locktime']
    
    # Add data_preimage to script_params for data_publishing publisher path
    if 'data_preimage' not in output_data['script_params'] and test_data.get('data_preimage'):
        output_data['script_params']['data_preimage'] = test_data['data_preimage']
    
    # 3. Validate sweep conditions (locktime check)
    # Pass path_kwargs to validate_sweep_conditions so it knows which path to check
    try:
        is_unlocked = sweeper.validate_sweep_conditions(
            output_data,
            current_height,
            raise_if_locked=True,
            **path_kwargs
        )
    except LockedError as e:
        # Re-raise with more context
        locktime = test_data.get('locktime')
        blocks_remaining = locktime - current_height
        raise LockedError(
            f"Output still locked. Current height: {current_height}, "
            f"Locktime: {locktime}, Blocks remaining: {blocks_remaining} "
            f"(need {abs(blocks_remaining)} more blocks)"
        ) from e
    
    # 4. Collect all available private keys
    # SINGLE SOURCE OF TRUTH: Derive key mappings from ContractDefinition
    keys = {}
    
    # contract_name and contract already determined above
    
    # Get required keys for the path from ContractDefinition (single source of truth)
    required_key_names = []
    if contract and path:
        path_obj = contract.get_path(path)
        if path_obj:
            required_key_names = path_obj.required_keys
    
    # Helper: Extract private key hex from test_data
    def get_key_hex(key_name: str) -> Optional[str]:
        """Get private key hex from test_data using various naming conventions."""
        # Try: {key_name}_private_key_hex, {key_name}_private_key, {key_name}_key_hex
        for suffix in ['_private_key_hex', '_private_key', '_key_hex']:
            full_name = f'{key_name}{suffix}'
            if full_name in test_data:
                return test_data[full_name]
        return None
    
    # Extract keys from test_data using ContractDefinition as guide
    # Test data stores keys as: {role}_private_key_hex or private_key_hex (for simple contracts)
    for key_name in required_key_names:
        key_hex = get_key_hex(key_name)
        if key_hex:
            keys[key_name] = ecc.ECPrivkey(bytes.fromhex(key_hex))
    
    # Also check test_data['keys'] dict if present
    if 'keys' in test_data and isinstance(test_data['keys'], dict):
        keys_dict = test_data['keys']
        
        for key_name in required_key_names:
            if key_name in keys_dict:
                keypair = keys_dict[key_name]
                if isinstance(keypair, dict):
                    privkey_hex = keypair.get('privkey_hex') or keypair.get('private_key_hex')
                elif isinstance(keypair, str):
                    privkey_hex = keypair
                else:
                    continue
                if privkey_hex:
                    keys[key_name] = ecc.ECPrivkey(bytes.fromhex(privkey_hex))
        
        # Handle unnamed single key (keys[''] = {...}) - maps to first required key
        if '' in keys_dict and required_key_names:
            keypair = keys_dict['']
            privkey_hex = (keypair.get('privkey_hex') or keypair.get('private_key_hex') 
                          if isinstance(keypair, dict) else keypair if isinstance(keypair, str) else None)
            if privkey_hex:
                # Map to first required key (for simple contracts with single key)
                keys[required_key_names[0]] = ecc.ECPrivkey(bytes.fromhex(privkey_hex))
    
    # Verify we have all required keys
    required_keys = sweeper.get_required_keys(output_data)
    missing_keys = [k for k in required_keys if k not in keys]
    if missing_keys:
        raise ValidationError(f"Missing required keys: {missing_keys}")
    
    # 5. Build transaction
    # UTXO tracking: Uses UTXO offset (vout index) stored in funding_vout
    # This is more reliable than amount matching because:
    # - paytomany preserves output order, so vout = position in outputs_list
    # - Works even if amounts aren't unique
    # - Verified with address during funding phase
    input_txid = test_data['funding_txid']
    input_vout = test_data['funding_vout']
    
    # Use the stored amount (now correctly updated with actual UTXO value after fees)
    input_amount = test_data.get('amount_sats', 0)
    print(f"   Using stored UTXO value: {input_amount} sats")
    
    # Calculate dynamic fee based on script size
    # Larger scripts (like Trident Vault with 332 bytes) need higher fees
    script_hex = test_data.get('script_hex', '')
    script_size = len(script_hex) // 2 if script_hex else 0
    
    # Estimate transaction vsize:
    # - Base: ~84 bytes (version, marker, flag, input, output, locktime)
    # - Witness: script_size + signatures (4 sigs @ 72 bytes for multisig)
    # - Witness discount: divide by 4
    estimated_sigs = 4 if 'trident' in script_type.lower() else 2
    witness_size = script_size + (estimated_sigs * 72) + 10  # +10 for overhead
    vsize = 84 + (witness_size // 4)
    
    # Use dynamic fee if it's higher than the provided fee_sats
    dynamic_fee = max(fee_sats, vsize + 10)  # +10 for safety margin
    if dynamic_fee > fee_sats:
        print(f"   📊 Dynamic fee: {dynamic_fee} sats (script size: {script_size} bytes, vsize: ~{vsize})")
        fee_sats = dynamic_fee
    
    output_amount = input_amount - fee_sats
    
    # LOCKTIME CLARIFICATION:
    # - 'locktime' variable (from test_data) = CLTV value in script (minimum block height)
    # - 'tx_locktime' = transaction nLockTime field (must be >= CLTV value)
    # 
    # IMPORTANT: Transaction nLockTime must be >= CLTV locktime value
    # - CLTV value is the MINIMUM height required to spend
    # - Transaction nLockTime must be >= CLTV value to satisfy the script
    # - For cooperative paths (normal, cooperative), use current_height
    # - For timelocked paths (refund, recovery, arbitration), use max(current_height, locktime)
    script_locktime = test_data.get('locktime', 0)
    
    # Determine transaction locktime
    # For cooperative paths: use current_height (CLTV not executed in this path)
    # For timelocked paths: use max(current_height, script_locktime)
    # For simple CLTV: use max(current_height, script_locktime)
    
    sweeper_path = getattr(sweeper, 'path', None)
    is_cooperative_path = (
        sweeper_path in ('normal', 'cooperative', 'publisher') and
        'hodl' not in script_type  # hodl always requires CLTV
    )
    
    if is_cooperative_path:
        # Cooperative path - CLTV not executed in this path, but script may still have CLTV
        # Bitcoin requires tx.locktime >= script_locktime when CLTV is present, even if not executed
        # So we must ensure tx_locktime >= script_locktime
        tx_locktime = max(current_height, script_locktime) if script_locktime > 0 else current_height
    elif script_locktime > 0:
        # Script has CLTV - must satisfy it
        tx_locktime = max(current_height, script_locktime)
    else:
        # No CLTV in script - use current height
        tx_locktime = current_height
    
    if output_amount <= 0:
        raise ValidationError(f"Fee ({fee_sats}) >= input amount ({input_amount})")
    
    try:
        # Get script bytes - MUST use output_data['script_hex'] which has the path-specific script
        # Using test_data['script_hex'] would use the wrong script for path-specific sweeps!
        script_bytes = bytes.fromhex(output_data['script_hex'])
        
        # Create input
        # CRITICAL: nSequence determines whether nLockTime is enabled
        # - nSequence=0xfffffffe enables nLockTime (required when script has CLTV)
        # - nSequence=0xffffffff disables nLockTime (can be used when script has no timelock)
        # For paths without timelocks in the script, we can disable nLockTime
        # For paths with timelocks, we must enable nLockTime and set it >= script locktime
        has_timelock_in_script = script_locktime > 0
        nsequence = 0xfffffffe if has_timelock_in_script else 0xffffffff
        
        tx_input = PartialTxInput(
            prevout=TxOutpoint(txid=bytes.fromhex(input_txid), out_idx=input_vout),
            script_sig=None,
            nsequence=nsequence
        )
        
        # Set input amount (required for segwit sighash)
        tx_input._trusted_value_sats = input_amount
        
        # Set witness script for sighash computation
        # Note: For P2WSH, the witness_script is used by Electrum to compute the sighash
        # The actual witness stack (with script) is added later via build_witness()
        script_format = get_format(script_type)
        if script_format == ScriptFormat.P2WSH:
            # P2WSH needs witness_script for sighash, script goes in witness stack
            tx_input.witness_script = script_bytes
        # Note: Taproot removed - use taproot_tx_builder.py
        
        # Create output (support both address and OP_RETURN)
        if isinstance(destination_address, tuple) and destination_address[0] == 'op_return':
            # OP_RETURN output
            op_return_data = destination_address[1]  # hex string
            print(f"   📝 Creating OP_RETURN output with data: {bytes.fromhex(op_return_data).decode('utf-8', errors='ignore')}")
            
            # Build OP_RETURN scriptPubKey
            import electrum.bitcoin as bitcoin
            op_return_bytes = bytes.fromhex(op_return_data)
            # OP_RETURN + PUSH + data
            script_pubkey = bytes([0x6a, len(op_return_bytes)]) + op_return_bytes
            
            tx_output = PartialTxOutput(
                scriptpubkey=script_pubkey,
                value=0  # OP_RETURN outputs have 0 value
            )
            
            # Note: Fees will be higher since all input goes to fees
            print(f"   ⚠️  OP_RETURN: All {input_amount} sats will be consumed as fees")
        else:
            # Regular address output
            tx_output = PartialTxOutput.from_address_and_value(
                destination_address,
                output_amount
            )
        
        # Build transaction
        tx = PartialTransaction.from_io(
            inputs=[tx_input],
            outputs=[tx_output],
            locktime=tx_locktime
        )
    except Exception as e:
        raise SweepError(f"Failed to build transaction: {e}") from e
    
    # 6. Compute sighash
    try:
        from electrum.crypto import sha256d
        
        # Check if this is Taproot
        # Note: get_format returns uppercase string ("TAPROOT"), but ScriptFormat uses lowercase
        is_taproot = script_format.upper() == "TAPROOT" if isinstance(script_format, str) else script_format == ScriptFormat.TAPROOT
        print(f"   🔍 Script format: {script_format}, is_taproot: {is_taproot}")
        if is_taproot:
            print(f"   🔍 Taking Taproot code path")
            # Use our consolidated BIP-341 sighash computation from cltv_lib
            from cltv_lib.builders.taproot import compute_bip341_sighash
            # Note: compute_tapleaf_hash is in taproot_utils
            from cltv_lib.builders.taproot.taproot_constants import TAPSCRIPT_LEAF_VERSION
            
            # Get control block and script from test data
            control_block_hex = test_data.get('control_block_hex') or test_data.get('control_block')
            if not control_block_hex:
                raise ValidationError("Missing control_block for Taproot sweep")
            control_block = bytes.fromhex(control_block_hex)
            
            # Get output scriptPubKey (the P2TR scriptPubKey)
            output_script_hex = test_data.get('output_script')
            if not output_script_hex:
                raise ValidationError("Missing output_script for Taproot sweep")
            output_script = bytes.fromhex(output_script_hex)
            
            # Compute destination scriptPubKey and amount
            if isinstance(destination_address, tuple) and destination_address[0] == 'op_return':
                dest_spk = tx_output.scriptpubkey
                dest_amount = 0  # OP_RETURN outputs always have 0 value
            else:
                from electrum.bitcoin import address_to_script
                addr_script = address_to_script(destination_address)
                # Electrum may return bytes (scriptPubKey) or hex string depending on version
                if isinstance(addr_script, (bytes, bytearray)):
                    dest_spk = bytes(addr_script)
                else:
                    dest_spk = bytes.fromhex(addr_script)
                dest_amount = output_amount  # Regular outputs use calculated amount
            
            # Get output key (x-only pubkey) for sighash computation
            output_key = test_data.get('output_key')
            if not output_key:
                raise ValidationError("Missing output_key for Taproot sweep")
            
            # Use our consolidated sighash computation
            # Note: compute_bip341_sighash takes an address or op_return tuple, not raw scriptpubkey
            if isinstance(destination_address, tuple) and destination_address[0] == 'op_return':
                dest_for_sighash = destination_address  # ('op_return', data_hex)
            else:
                dest_for_sighash = destination_address  # Regular address string
            
            # CRITICAL: The script_hex passed to compute_bip341_sighash MUST match
            # the exact script that will be pushed in the witness stack
            script_hex_for_sighash = output_data['script_hex']
            script_bytes_for_sighash = bytes.fromhex(script_hex_for_sighash)
            
            print(f"   🔍 Taproot sighash params (EXPERT DEBUG):")
            print(f"      funding_txid: {input_txid}")
            print(f"      funding_vout: {input_vout}")
            print(f"      amount_sats: {input_amount}")
            print(f"      output_key: {output_key[:20]}...")
            print(f"      script_hex (for sighash): {script_hex_for_sighash[:40]}... (len={len(script_bytes_for_sighash)})")
            print(f"      script_hex (full): {script_hex_for_sighash}")
            print(f"      control_block_hex: {output_data.get('control_block_hex', 'N/A')[:40]}...")
            print(f"      dest_address: {dest_for_sighash}")
            print(f"      locktime: {tx_locktime}")
            print(f"      fee_sats: {fee_sats}")
            print(f"      ⚠️  VERIFY: This script MUST match the script in the witness!")
            
            sighash = compute_bip341_sighash(
                funding_txid=input_txid,
                funding_vout=input_vout,
                amount_sats=input_amount,
                output_key=output_key,
                script_hex=script_hex_for_sighash,  # Must match witness script exactly
                dest_address=dest_for_sighash,
                network='signet',
                locktime=tx_locktime,
                fee_sats=fee_sats
            )
            print(f"   ✅ Sighash digest: {sighash.hex()}")
            print(f"      Sighash length: {len(sighash)} bytes (should be 32)")
        else:
            # Compute BIP-143 sighash manually for P2WSH
            # Electrum's serialize_preimage fails for custom scripts
            
            # BIP-143 sighash preimage components
            # 1. nVersion (4 bytes, little-endian)
            version = tx.version.to_bytes(4, 'little')
            
            # 2. hashPrevouts (32 bytes)
            # Each prevout: txid[32 bytes LE] + vout[4 bytes LE]
            prevouts_preimage = b''
            for txin in tx.inputs():
                # Convert txid to bytes and reverse for little-endian
                # txin.prevout.txid can be bytes, hex string, or have a .hex() method
                if hasattr(txin.prevout.txid, 'hex'):
                    # It's a bytes-like object with .hex() method
                    txid_bytes = bytes.fromhex(txin.prevout.txid.hex())
                elif isinstance(txin.prevout.txid, str):
                    # It's a hex string
                    txid_bytes = bytes.fromhex(txin.prevout.txid)
                else:
                    # Already bytes or bytes-like
                    txid_bytes = bytes(txin.prevout.txid)
                prevouts_preimage += txid_bytes[::-1]  # Reverse for little-endian
                prevouts_preimage += txin.prevout.out_idx.to_bytes(4, 'little')
            hashPrevouts = sha256d(prevouts_preimage)
            
            # 3. hashSequence (32 bytes)
            sequence_preimage = b''.join(
                txin.nsequence.to_bytes(4, 'little') for txin in tx.inputs()
            )
            hashSequence = sha256d(sequence_preimage)
            
            # 4. outpoint (36 bytes) - txid (32 LE) + vout (4 LE)
            txin = tx.inputs()[0]
            # Convert txid to bytes and reverse for little-endian
            # txin.prevout.txid can be bytes, hex string, or have a .hex() method
            if hasattr(txin.prevout.txid, 'hex'):
                # It's a bytes-like object with .hex() method
                txid_bytes = bytes.fromhex(txin.prevout.txid.hex())
            elif isinstance(txin.prevout.txid, str):
                # It's a hex string
                txid_bytes = bytes.fromhex(txin.prevout.txid)
            else:
                # Already bytes or bytes-like
                txid_bytes = bytes(txin.prevout.txid)
            outpoint = txid_bytes[::-1] + txin.prevout.out_idx.to_bytes(4, 'little')
            print(f"   🔍 Outpoint computation:")
            print(f"      txid type: {type(txin.prevout.txid)}")
            if hasattr(txin.prevout.txid, 'hex'):
                print(f"      txid (hex): {txin.prevout.txid.hex()}")
            else:
                print(f"      txid (raw): {txin.prevout.txid}")
            print(f"      txid (bytes): {txid_bytes.hex()}")
            print(f"      txid (LE): {txid_bytes[::-1].hex()}")
            print(f"      vout: {txin.prevout.out_idx}")
            print(f"      outpoint: {outpoint.hex()}")
            
            # 5. scriptCode - for P2WSH, it's the witness script
            # For BIP-143, scriptCode = length prefix + script
            # CRITICAL: This MUST exactly match the script that will be in the witness stack
            print(f"   🔍 BIP-143 scriptCode computation:")
            print(f"      Script length: {len(script_bytes)} bytes")
            print(f"      Script hex: {script_hex[:80]}...")
            print(f"      Script first byte: 0x{script_bytes[0]:02x} (should be OP_IF = 0x63)")
            
            scriptCode = bytes([len(script_bytes)]) + script_bytes if len(script_bytes) < 0xfd else b''
            if len(script_bytes) >= 0xfd:
                # Use varint for longer scripts
                if len(script_bytes) <= 0xffff:
                    scriptCode = b'\xfd' + len(script_bytes).to_bytes(2, 'little') + script_bytes
                else:
                    scriptCode = b'\xfe' + len(script_bytes).to_bytes(4, 'little') + script_bytes
            
            print(f"      ScriptCode length prefix: 0x{scriptCode[0]:02x} ({scriptCode[0]} bytes)")
            print(f"      ScriptCode hex: {scriptCode.hex()[:80]}...")
            print(f"      ⚠️  VERIFY: This scriptCode MUST match the witnessScript in the witness!")
            
            # 6. value (8 bytes, little-endian)
            # NOTE: Bitcoin Core uses signed=True, but for BIP-143 we use unsigned
            # BIP-143 spec says "value" (8 bytes) - no mention of signed, so unsigned is correct
            value = input_amount.to_bytes(8, 'little', signed=False)
            
            # 7. nSequence (4 bytes, little-endian)
            nSequence = txin.nsequence.to_bytes(4, 'little')
            
            # 8. hashOutputs (32 bytes)
            # BIP-143: hashOutputs = hash256 of all outputs
            # Each output: value (8 bytes LE) + scriptPubKey length (varint) + scriptPubKey
            outputs_preimage = b''
            for txout in tx.outputs():
                # Value (8 bytes, little-endian, unsigned)
                # BIP-143: value is 8 bytes, little-endian (unsigned)
                outputs_preimage += txout.value.to_bytes(8, 'little', signed=False)
                # ScriptPubKey length (varint) + scriptPubKey
                spk = txout.scriptpubkey
                spk_len = len(spk)
                if spk_len < 0xfd:
                    # Single byte length prefix
                    outputs_preimage += bytes([spk_len]) + spk
                elif spk_len <= 0xffff:
                    # 0xfd + 2-byte length (little-endian)
                    outputs_preimage += b'\xfd' + spk_len.to_bytes(2, 'little') + spk
                elif spk_len <= 0xffffffff:
                    # 0xfe + 4-byte length (little-endian)
                    outputs_preimage += b'\xfe' + spk_len.to_bytes(4, 'little') + spk
                else:
                    # 0xff + 8-byte length (little-endian) - extremely rare
                    outputs_preimage += b'\xff' + spk_len.to_bytes(8, 'little') + spk
            hashOutputs = sha256d(outputs_preimage)
            print(f"   🔍 hashOutputs computation:")
            print(f"      Number of outputs: {len(tx.outputs())}")
            for i, txout in enumerate(tx.outputs()):
                print(f"      Output {i}: value={txout.value} sats, spk_len={len(txout.scriptpubkey)} bytes")
            print(f"      hashOutputs: {hashOutputs.hex()[:32]}...")
            
            # 9. nLocktime (4 bytes, little-endian)
            nLocktime = tx_locktime.to_bytes(4, 'little')
            
            # 10. sighash type (4 bytes, little-endian) - SIGHASH_ALL = 1
            sighash_type = (1).to_bytes(4, 'little')
            
            # Build preimage
            preimage = (
                version +
                hashPrevouts +
                hashSequence +
                outpoint +
                scriptCode +
                value +
                nSequence +
                hashOutputs +
                nLocktime +
                sighash_type
            )
            
            sighash = sha256d(preimage)
            print(f"   ✅ Using manual BIP-143 sighash for P2WSH")
            print(f"   🔍 BIP-143 sighash preimage components:")
            print(f"      nVersion: {version.hex()}")
            print(f"      hashPrevouts: {hashPrevouts.hex()[:32]}...")
            print(f"      hashSequence: {hashSequence.hex()[:32]}...")
            print(f"      outpoint: {outpoint.hex()}")
            print(f"      scriptCode: {scriptCode.hex()[:80]}... (length: {len(scriptCode)} bytes)")
            print(f"      value: {value.hex()} ({input_amount} sats)")
            print(f"      nSequence: {nSequence.hex()}")
            print(f"      hashOutputs: {hashOutputs.hex()[:32]}...")
            print(f"      nLocktime: {nLocktime.hex()} ({tx_locktime})")
            print(f"      sighash_type: {sighash_type.hex()} (SIGHASH_ALL = 1)")
            print(f"   🔍 Final sighash: {sighash.hex()}")
            
    except Exception as e:
        raise SweepError(f"Failed to compute sighash: {e}") from e
    
    # 7. Build witness using sweeper (handles signing internally)
    try:
        # Pass path_kwargs to build_witness for path-aware sweepers
        print(f"   🔍 Building witness with:")
        print(f"      script_hex: {output_data.get('script_hex', 'N/A')[:80]}...")
        print(f"      sighash: {sighash.hex()[:32]}...")
        print(f"      path_kwargs: {path_kwargs}")
        witness = sweeper.build_witness(output_data, keys, sighash, **path_kwargs)
        print(f"   🔍 Witness built: {len(witness)} items")
        for i, item in enumerate(witness):
            if isinstance(item, bytes):
                print(f"      Item {i}: {len(item)} bytes - {item.hex()[:40]}...")
            else:
                print(f"      Item {i}: {item}")
        # Verify the script in witness matches scriptCode
        # For Taproot: witness = [sig1, sig2, ..., script, control_block]
        # For P2WSH: witness = [OP_0, sig1, sig2, ..., branch, script]
        if len(witness) > 0:
            # For Taproot, script is second-to-last (before control block)
            # For P2WSH, script is last
            script_format = get_format(script_type)
            if script_format == ScriptFormat.TAPROOT and len(witness) >= 2:
                witness_script = witness[-2] if isinstance(witness[-2], bytes) else None
            else:
                witness_script = witness[-1] if isinstance(witness[-1], bytes) else None
            
            if witness_script:
                print(f"   🔍 Witness script: {witness_script.hex()[:80]}...")
                print(f"      Length: {len(witness_script)} bytes")
                print(f"      First byte: 0x{witness_script[0]:02x}")
                if witness_script == script_bytes:
                    print(f"      ✅ Witness script matches scriptCode script!")
                else:
                    print(f"      ❌ WARNING: Witness script does NOT match scriptCode script!")
                    print(f"         scriptCode script: {script_bytes.hex()[:80]}...")
                    print(f"         witness script:    {witness_script.hex()[:80]}...")
        print(f"   🔍 Witness from sweeper: {len(witness)} items")
        for i, item in enumerate(witness):
            if isinstance(item, int):
                print(f"   🔍 Witness item {i}: integer {item}")
            elif isinstance(item, bytes):
                print(f"   🔍 Witness item {i}: {len(item)} bytes - {item.hex()[:64]}...")
            else:
                print(f"   🔍 Witness item {i}: {type(item)}")
    except Exception as e:
        raise SweepError(f"Failed to build witness: {e}") from e
    
    # 8. Add witness to transaction
    # Use Electrum's construct_witness function
    try:
        if witness:
            tx_input = tx.inputs()[0]
            
            # Check if witness is already constructed (bytes) or needs construction (list)
            if isinstance(witness, bytes):
                # Witness is already constructed by sweeper
                print(f"   🔍 Witness already constructed: {len(witness)} bytes - {witness.hex()[:64]}...")
                tx_input.witness = witness
            else:
                # Witness is a list of items, need to construct it
                print(f"   🔍 Witness before construct_witness: {len(witness)} items")
                for i, item in enumerate(witness):
                    if isinstance(item, int):
                        print(f"   🔍 Witness item {i}: integer {item}")
                    elif isinstance(item, bytes):
                        print(f"   🔍 Witness item {i}: {len(item)} bytes - {item.hex()[:32]}...")
                    else:
                        print(f"   🔍 Witness item {i}: {type(item)}")
                
                # Use Electrum's construct_witness to properly format the witness
                from electrum.bitcoin import construct_witness
                constructed_witness = construct_witness(witness)
                print(f"   🔍 Constructed witness: {len(constructed_witness)} bytes - {constructed_witness.hex()[:64]}...")
                
                tx_input.witness = constructed_witness
            
            tx_input.script_sig = b''  # Empty scriptSig for witness-based formats
    except Exception as e:
        raise SweepError(f"Failed to set witness: {e}") from e
    
    # 9. Serialize and broadcast
    try:
        tx_hex = tx.serialize()
        
        # WORKAROUND: Fix Electrum's nLockTime bug
        # Electrum's PartialTransaction.locktime property is not serialized correctly
        # We need to manually fix the nLockTime in the raw transaction bytes
        import base64
        
        try:
            # tx.serialize() returns raw hex, not base64
            tx_bytes = bytes.fromhex(tx_hex)
            
            # Replace the last 4 bytes (nLockTime) with the correct value
            correct_locktime_bytes = tx_locktime.to_bytes(4, 'little')
            tx_bytes_fixed = tx_bytes[:-4] + correct_locktime_bytes
            tx_hex = tx_bytes_fixed.hex()
            
            # Transaction successfully created with correct nLockTime
            print(f"   ✅ Fixed nLockTime: {tx_locktime}")
            
        except Exception as e:
            print(f"   ⚠️ Failed to fix nLockTime: {e}")
            # Continue with original transaction hex
        
    except Exception as e:
        raise SweepError(f"Failed to serialize transaction: {e}") from e
    
    # Broadcast via Electrum CLI
    electrum_python = Path.home() / "src/electrum/venv/bin/python3"
    electrum_path = Path.home() / "src/electrum/run_electrum"
    
    if not electrum_python.exists():
        raise SweepError(f"Electrum Python not found: {electrum_python}")
    if not electrum_path.exists():
        raise SweepError(f"Electrum not found: {electrum_path}")
    
    try:
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, "broadcast", tx_hex],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            # Check for specific errors and print raw transaction hex
            if "bad-txns-inputs-missingorspent" in result.stderr or "Witness program hash mismatch" in result.stderr:
                error_type = "UTXO ERROR" if "bad-txns-inputs-missingorspent" in result.stderr else "WITNESS HASH MISMATCH"
                print(f"\n" + "="*80)
                print(f"🔍 {error_type} DETECTED - RAW TRANSACTION HEX")
                print(f"="*80)
                print(f"Raw TX: {tx_hex}")
                print(f"="*80)
                print(f"📋 You can push this transaction manually at:")
                print(f"https://mempool.space/testnet/pushtx")
                print(f"\n🔍 Error details: {result.stderr}")
                if "bad-txns-inputs-missingorspent" in result.stderr:
                    print(f"\n⚠️  This might be due to UTXO conflicts or double-spending attempts.")
                elif "Witness program hash mismatch" in result.stderr:
                    print(f"\n⚠️  This might be due to script hash mismatch - check script generation.")
                print(f"="*80)
                
                # Additional debugging info
                print(f"\n🔍 DEBUGGING INFO:")
                print(f"   UTXO: {test_data.get('funding_txid', 'N/A')}:{test_data.get('funding_vout', 'N/A')}")
                print(f"   Amount: {test_data.get('amount_sats', 'N/A')} sats")
                print(f"   Address: {test_data.get('address', 'N/A')}")
                print(f"   Script Type: {script_type}")
                print(f"   Current Height: {current_height}")
                if 'locktime' in test_data:
                    print(f"   Locktime: {test_data['locktime']}")
                print(f"="*80)
                
            raise SweepError(
                f"Broadcast failed (return code {result.returncode}): "
                f"stdout={result.stdout}, stderr={result.stderr}"
            )
        
        # Parse TXID from output (might be JSON or raw string)
        broadcast_output = result.stdout.strip()
        
        try:
            # Try parsing as JSON first
            broadcast_result = json.loads(broadcast_output)
            if isinstance(broadcast_result, list) and len(broadcast_result) == 2:
                success, txid = broadcast_result
                if not success:
                    raise SweepError(f"Broadcast returned false: {txid}")
            elif isinstance(broadcast_result, str):
                txid = broadcast_result
            else:
                txid = str(broadcast_result)
        except json.JSONDecodeError:
            # Raw TXID string
            txid = broadcast_output.strip('"')
        
        # Validate TXID format (64 hex chars)
        if not txid or len(txid) != 64:
            raise SweepError(f"Invalid TXID from broadcast: {txid}")
        
        return txid
        
    except subprocess.TimeoutExpired:
        raise SweepError("Broadcast timed out after 30 seconds")
    except Exception as e:
        if isinstance(e, SweepError):
            raise
        raise SweepError(f"Broadcast error: {e}") from e


# Module-level cache for default destination address
# All tests use the same address to avoid Electrum rate limiting
_DEFAULT_DESTINATION_CACHE: Optional[str] = None


def get_default_destination() -> str:
    """Get a valid default sweep destination address from Electrum wallet.

    Uses a cached address to avoid rate limiting. All tests share the same
    destination address, which is fetched once and reused.

    Tries, in order:
    - getunusedaddress (preferred, stable across Electrum versions)
    - createnewaddress (fallback)
    - getnewaddress (legacy alias)
    
    Returns:
        Cached address string (same for all calls in this process)
    """
    global _DEFAULT_DESTINATION_CACHE
    
    # Return cached address if available
    if _DEFAULT_DESTINATION_CACHE is not None:
        return _DEFAULT_DESTINATION_CACHE
    
    electrum_python = Path.home() / "src/electrum/venv/bin/python3"
    electrum_path = Path.home() / "src/electrum/run_electrum"

    if not electrum_python.exists() or not electrum_path.exists():
        # Last-resort static address (must be valid bech32m/v0). Avoid failing outright.
        # Note: Prefer dynamic retrieval whenever possible.
        raise SweepError("Electrum CLI not found for obtaining destination address")

    def _run(cmd: list[str]) -> Optional[str]:
        try:
            res = subprocess.run(
                [str(electrum_python), str(electrum_path), NETWORK_FLAG] + cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            if res.returncode == 0:
                return (res.stdout or "").strip().strip('"')
            return None
        except Exception:
            return None

    # Try to get address from Electrum
    for subcmd in (["getunusedaddress"], ["createnewaddress"], ["getnewaddress"]):
        addr = _run(subcmd)
        if addr and addr.startswith(("tb1", "bc1", "bcrt1")):
            # Cache the address for all future calls
            _DEFAULT_DESTINATION_CACHE = addr
            return addr

    raise SweepError("Failed to obtain a default destination address from Electrum")
