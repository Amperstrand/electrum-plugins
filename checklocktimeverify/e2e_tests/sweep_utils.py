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
from sweepers.base import LockedError, ValidationError
from script_utils import ScriptFormat


class SweepError(Exception):
    """Raised when sweep fails"""
    pass


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
    # Registry expects: script_type like 'cltv_simple_hodl' or 'cltv_escrow_timeout'
    
    script_type = test_data.get('script_type')
    if not script_type:
        # Infer from format if not stored explicitly
        format_str = test_data.get('format', '').upper()
        
        # Determine base script type from data
        if 'alice_pubkey' in test_data or 'bob_pubkey' in test_data:
            # Escrow script
            base_type = 'cltv_escrow'
        else:
            # Simple CLTV script
            base_type = 'cltv_simple'
        
        # Add format suffix if needed
        if format_str == 'P2WSH':
            script_type = f'{base_type}_p2wsh'
        else:
            script_type = base_type  # P2SH is the default
    
    # Taproot is now supported via registry
    # Old comment kept for reference: was "not supported in this file - use taproot_tx_builder.py"
    
    try:
        sweeper = get_sweeper(script_type, **sweep_kwargs)
    except Exception as e:
        raise ValidationError(f"Failed to get sweeper for {script_type}: {e}")
    
    # 2. Build output data for sweeper
    output_data = {
        'script_hex': test_data['script_hex'],
        'script_type': script_type,
        'script_params': test_data.get('script_params', {}),
        'locktime': test_data.get('locktime'),  # Add locktime
        'data_preimage': test_data.get('data_preimage'),  # Data publishing
        'data_hash': test_data.get('data_hash')  # Data publishing
    }
    
    # Add locktime to script_params if not there
    if 'locktime' not in output_data['script_params'] and 'locktime' in test_data:
        output_data['script_params']['locktime'] = test_data['locktime']
    
    # 3. Validate sweep conditions (locktime check)
    try:
        is_unlocked = sweeper.validate_sweep_conditions(
            output_data,
            current_height,
            raise_if_locked=True
        )
    except LockedError as e:
        # Re-raise with more context
        locktime = test_data.get('locktime')
        raise LockedError(
            f"Output still locked. Current height: {current_height}, "
            f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
        ) from e
    
    # 4. Collect all available private keys
    keys = {}
    
    # Single-key scripts (simple CLTV)
    if 'private_key_hex' in test_data:
        keys['private_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['private_key_hex']))
    elif 'private_key_repr' in test_data:
        raise ValidationError(
            "Cannot sweep: private key not found in state. "
            "State has 'private_key_repr' but needs 'private_key_hex'. "
            "Please delete test_state.json and regenerate with proper key storage."
        )
    
    # Multi-key scripts (escrow, channels, etc.)
    if 'alice_private_key_hex' in test_data:
        keys['alice_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['alice_private_key_hex']))
    elif 'alice_private_key_repr' in test_data:
        raise ValidationError("State needs 'alice_private_key_hex', not 'alice_private_key_repr'")
    
    if 'bob_private_key_hex' in test_data:
        keys['bob_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['bob_private_key_hex']))
    elif 'bob_private_key_repr' in test_data:
        raise ValidationError("State needs 'bob_private_key_hex', not 'bob_private_key_repr'")
    
    # Two-factor wallet keys
    if 'user_private_key_hex' in test_data:
        keys['user_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['user_private_key_hex']))
    elif 'user_private_key_repr' in test_data:
        raise ValidationError("State needs 'user_private_key_hex', not 'user_private_key_repr'")
    
    if 'service_private_key_hex' in test_data:
        keys['service_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['service_private_key_hex']))
    elif 'service_private_key_repr' in test_data:
        raise ValidationError("State needs 'service_private_key_hex', not 'service_private_key_repr'")
    
    if 'recovery_private_key_hex' in test_data:
        keys['recovery_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['recovery_private_key_hex']))
    elif 'recovery_private_key_repr' in test_data:
        raise ValidationError("State needs 'recovery_private_key_hex', not 'recovery_private_key_repr'")
    
    # Data publishing keys
    if 'publisher_private_key_hex' in test_data:
        keys['publisher_private_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['publisher_private_key_hex']))
    elif 'publisher_private_key_repr' in test_data:
        raise ValidationError("State needs 'publisher_private_key_hex', not 'publisher_private_key_repr'")
    
    if 'buyer_private_key_hex' in test_data:
        keys['buyer_private_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['buyer_private_key_hex']))
    elif 'buyer_private_key_repr' in test_data:
        raise ValidationError("State needs 'buyer_private_key_hex', not 'buyer_private_key_repr'")
    
    # Escrow keys
    if 'alice_private_key_hex' in test_data:
        keys['alice_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['alice_private_key_hex']))
    elif 'alice_private_key_repr' in test_data:
        raise ValidationError("State needs 'alice_private_key_hex', not 'alice_private_key_repr'")
    
    if 'bob_private_key_hex' in test_data:
        keys['bob_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['bob_private_key_hex']))
    elif 'bob_private_key_repr' in test_data:
        raise ValidationError("State needs 'bob_private_key_hex', not 'bob_private_key_repr'")
    
    if 'lenny_private_key_hex' in test_data:
        keys['lenny_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['lenny_private_key_hex']))
    elif 'lenny_private_key_repr' in test_data:
        raise ValidationError("State needs 'lenny_private_key_hex', not 'lenny_private_key_repr'")
    
    # Payment channel keys
    if 'sender_private_key_hex' in test_data:
        keys['sender_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['sender_private_key_hex']))
    elif 'sender_private_key_repr' in test_data:
        raise ValidationError("State needs 'sender_private_key_hex', not 'sender_private_key_repr'")
    
    if 'receiver_private_key_hex' in test_data:
        keys['receiver_key'] = ecc.ECPrivkey(bytes.fromhex(test_data['receiver_private_key_hex']))
    elif 'receiver_private_key_repr' in test_data:
        raise ValidationError("State needs 'receiver_private_key_hex', not 'receiver_private_key_repr'")
    
    # Verify we have required keys
    required_keys = sweeper.get_required_keys(output_data)
    missing_keys = [k for k in required_keys if k not in keys]
    if missing_keys:
        raise ValidationError(f"Missing required keys: {missing_keys}")
    
    # 5. Build transaction
    input_txid = test_data['funding_txid']
    input_vout = test_data['funding_vout']
    
    # Use the stored amount (now correctly updated with actual UTXO value after fees)
    input_amount = test_data.get('amount_sats', 0)
    print(f"   Using stored UTXO value: {input_amount} sats")
    output_amount = input_amount - fee_sats
    locktime = test_data['locktime']
    
    if output_amount <= 0:
        raise ValidationError(f"Fee ({fee_sats}) >= input amount ({input_amount})")
    
    try:
        # Get script bytes
        script_bytes = bytes.fromhex(test_data['script_hex'])
        
        # Create input
        tx_input = PartialTxInput(
            prevout=TxOutpoint(txid=bytes.fromhex(input_txid), out_idx=input_vout),
            script_sig=None,
            nsequence=0xfffffffe  # Enable locktime (was 'sequence', Electrum uses 'nsequence')
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
            locktime=locktime
        )
    except Exception as e:
        raise SweepError(f"Failed to build transaction: {e}") from e
    
    # 6. Compute sighash
    try:
        from electrum.crypto import sha256d
        
        # Use Electrum's built-in sighash for P2WSH/P2SH
        preimage = tx.serialize_preimage(txin_index=0)
        sighash = sha256d(preimage)
        print(f"   ✅ Using Electrum's built-in sighash for {script_format}")
            
    except Exception as e:
        raise SweepError(f"Failed to compute sighash: {e}") from e
    
    # 7. Build witness using sweeper (handles signing internally)
    try:
        witness = sweeper.build_witness(output_data, keys, sighash)
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
            correct_locktime_bytes = locktime.to_bytes(4, 'little')
            tx_bytes_fixed = tx_bytes[:-4] + correct_locktime_bytes
            tx_hex = tx_bytes_fixed.hex()
            
            # Transaction successfully created with correct nLockTime
            print(f"   ✅ Fixed nLockTime: {locktime}")
            
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


def get_default_destination() -> str:
    """Get default sweep destination address (testnet4)"""
    return "tb1qc9adduvcuz6gx08xr6dm2v2l89jrrs43vynvt3"
