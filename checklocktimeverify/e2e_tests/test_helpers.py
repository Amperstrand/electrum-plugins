"""
Common test utilities and helpers for E2E tests.

Provides reusable functions to reduce code duplication and improve
test maintainability.
"""

import subprocess
import json
import time
from typing import Dict, Optional, Tuple
from network_config import NETWORK_FLAG


def fund_address_via_electrum(
    address: str,
    amount_sats: int,
    electrum_path: str = "~/src/electrum/run_electrum"
) -> Optional[Tuple[str, int]]:
    """
    Fund an address using Electrum CLI and return txid/vout.
    
    Args:
        address: Bitcoin address to fund
        amount_sats: Amount in satoshis
        electrum_path: Path to Electrum executable
        
    Returns:
        Tuple of (txid, vout) if successful, None if failed
    """
    try:
        amount_btc = amount_sats / 100_000_000
        
        # Create and broadcast payment
        result = subprocess.run(
            [electrum_path, NETWORK_FLAG, 'payto', address, str(amount_btc)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"   ❌ Payment failed: {result.stderr}")
            return None
            
        # Get transaction details to find vout
        tx_data = json.loads(result.stdout)
        
        # Find the output index for our address
        vout = None
        for idx, output in enumerate(tx_data.get('outputs', [])):
            if output.get('address') == address:
                vout = idx
                break
                
        if vout is None:
            print(f"   ⚠️  Could not find vout for {address}")
            return None
            
        txid = tx_data.get('txid')
        return (txid, vout)
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ Payment timed out")
        return None
    except Exception as e:
        print(f"   ❌ Funding error: {e}")
        return None


def verify_utxo_on_chain(
    address: str,
    expected_amount: Optional[int] = None,
    electrum_path: str = "~/src/electrum/run_electrum"
) -> Dict:
    """
    Verify a UTXO exists on the blockchain.
    
    Args:
        address: Bitcoin address to check
        expected_amount: Expected amount in satoshis (optional)
        electrum_path: Path to Electrum executable
        
    Returns:
        Dict with verification results:
            - found: bool
            - utxos: list of UTXOs
            - confirmed: bool (at least one confirmation)
            - amount_matches: bool (if expected_amount provided)
    """
    try:
        result = subprocess.run(
            [electrum_path, NETWORK_FLAG, 'getaddressunspent', address],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {
                'found': False,
                'utxos': [],
                'confirmed': False,
                'amount_matches': False,
                'error': result.stderr
            }
            
        utxos = json.loads(result.stdout)
        
        # Check if any UTXO matches expected amount
        amount_matches = False
        if expected_amount is not None:
            amount_matches = any(
                utxo.get('value') == expected_amount 
                for utxo in utxos
            )
        
        # Check if any UTXO is confirmed
        confirmed = any(
            utxo.get('height', 0) > 0 
            for utxo in utxos
        )
        
        return {
            'found': len(utxos) > 0,
            'utxos': utxos,
            'confirmed': confirmed,
            'amount_matches': amount_matches
        }
        
    except Exception as e:
        return {
            'found': False,
            'utxos': [],
            'confirmed': False,
            'amount_matches': False,
            'error': str(e)
        }


def verify_transaction_on_chain(
    txid: str,
    electrum_path: str = "~/src/electrum/run_electrum"
) -> Dict:
    """
    Verify a transaction exists on the blockchain.
    
    Args:
        txid: Transaction ID to verify
        electrum_path: Path to Electrum executable
        
    Returns:
        Dict with transaction details:
            - found: bool
            - confirmations: int
            - in_mempool: bool
            - tx_data: dict (full transaction data)
    """
    try:
        result = subprocess.run(
            [electrum_path, NETWORK_FLAG, 'gettransaction', txid],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {
                'found': False,
                'confirmations': 0,
                'in_mempool': False,
                'tx_data': None,
                'error': result.stderr
            }
            
        tx_data = json.loads(result.stdout)
        confirmations = tx_data.get('confirmations', 0)
        
        return {
            'found': True,
            'confirmations': confirmations,
            'in_mempool': confirmations == 0,
            'tx_data': tx_data
        }
        
    except Exception as e:
        return {
            'found': False,
            'confirmations': 0,
            'in_mempool': False,
            'tx_data': None,
            'error': str(e)
        }


def wait_for_confirmation(
    txid: str,
    required_confirmations: int = 1,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
    electrum_path: str = "~/src/electrum/run_electrum"
) -> bool:
    """
    Wait for a transaction to receive confirmations.
    
    Args:
        txid: Transaction ID to wait for
        required_confirmations: Number of confirmations needed
        timeout_seconds: Maximum time to wait
        poll_interval: Seconds between checks
        electrum_path: Path to Electrum executable
        
    Returns:
        True if transaction received confirmations, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        tx_info = verify_transaction_on_chain(txid, electrum_path)
        
        if tx_info['found'] and tx_info['confirmations'] >= required_confirmations:
            return True
            
        time.sleep(poll_interval)
    
    return False


def decode_script_hex(script_hex: str, expected_pattern: Optional[str] = None) -> Dict:
    """
    Decode a Bitcoin script and validate structure.
    
    Args:
        script_hex: Script as hex string
        expected_pattern: Expected script pattern (e.g., 'simple_cltv', 'escrow')
        
    Returns:
        Dict with script analysis:
            - valid: bool
            - pattern: str (detected pattern)
            - locktime: int (if applicable)
            - pubkeys: list (extracted pubkeys)
            - opcodes: list (opcode sequence)
    """
    script = bytes.fromhex(script_hex)
    
    # Basic opcode extraction
    opcodes = []
    i = 0
    while i < len(script):
        opcode = script[i]
        
        if opcode >= 1 and opcode <= 75:  # Data push
            data_len = opcode
            data = script[i+1:i+1+data_len]
            opcodes.append(('PUSH', data_len, data.hex()))
            i += 1 + data_len
        elif opcode == 0x00:
            opcodes.append(('OP_0', None, None))
            i += 1
        elif opcode >= 0x51 and opcode <= 0x60:  # OP_1 through OP_16
            opcodes.append((f'OP_{opcode - 0x50}', None, None))
            i += 1
        else:
            # Named opcodes
            opcode_names = {
                0xac: 'OP_CHECKSIG',
                0xad: 'OP_CHECKSIGVERIFY',
                0xae: 'OP_CHECKMULTISIG',
                0xb1: 'OP_CLTV',
                0xb2: 'OP_CSV',
                0x75: 'OP_DROP',
                0x87: 'OP_EQUAL',
                0x88: 'OP_EQUALVERIFY',
                0xa6: 'OP_RIPEMD160',
                0xa7: 'OP_SHA1',
                0xa8: 'OP_SHA256',
                0xa9: 'OP_HASH160',
                0xaa: 'OP_HASH256',
                0xba: 'OP_CHECKSIGADD',
            }
            name = opcode_names.get(opcode, f'OP_{opcode:02x}')
            opcodes.append((name, None, None))
            i += 1
    
    return {
        'valid': True,
        'opcodes': opcodes,
        'script_hex': script_hex,
        'script_len': len(script)
    }


def calculate_tx_fee(
    input_amount: int,
    output_amount: int
) -> int:
    """
    Calculate transaction fee.
    
    Args:
        input_amount: Total input amount in satoshis
        output_amount: Total output amount in satoshis
        
    Returns:
        Fee in satoshis
    """
    return input_amount - output_amount


def estimate_tx_size(
    num_inputs: int,
    num_outputs: int,
    witness_size: int = 100,
    script_type: str = 'p2wsh'
) -> int:
    """
    Estimate transaction size in bytes.
    
    Args:
        num_inputs: Number of inputs
        num_outputs: Number of outputs
        witness_size: Estimated witness data size per input
        script_type: Type of script ('p2wsh' or 'taproot')
        
    Returns:
        Estimated size in bytes
    """
    # Base transaction size
    base_size = (
        4 +  # version
        1 +  # marker
        1 +  # flag
        1 +  # input count
        num_inputs * (32 + 4 + 1 + 4) +  # inputs (txid + vout + scriptsig + sequence)
        1 +  # output count
        num_outputs * (8 + 25) +  # outputs (value + scriptpubkey)
        4  # locktime
    )
    
    # Witness data
    witness_total = num_inputs * witness_size
    
    # Total size (base + witness)
    return base_size + witness_total


def format_satoshis(sats: int) -> str:
    """
    Format satoshis as human-readable string.
    
    Args:
        sats: Amount in satoshis
        
    Returns:
        Formatted string (e.g., "0.00001234 BTC (1234 sats)")
    """
    btc = sats / 100_000_000
    return f"{btc:.8f} BTC ({sats:,} sats)"


def validate_address_format(address: str, expected_type: str) -> bool:
    """
    Validate address format matches expected type.
    
    Args:
        address: Bitcoin address
        expected_type: Expected type ('p2wsh' or 'taproot')
        
    Returns:
        True if format matches expected type
    """
    if expected_type == 'p2wsh':
        # P2WSH addresses start with bc1q (mainnet) or tb1q (testnet/signet)
        return address.startswith('bc1q') or address.startswith('tb1q')
    elif expected_type == 'taproot':
        # Taproot addresses start with bc1p (mainnet) or tb1p (testnet/signet)
        return address.startswith('bc1p') or address.startswith('tb1p')
    else:
        return False


# ============================================================================
# Additional DRY helpers (moved from test_e2e_full.py)
# ============================================================================

def get_test_amount(test_number: int) -> int:
    """Calculate standardized test amount using configurable base.
    
    Amount = FUND_BASE + test_number
    FUND_BASE is configurable via env var E2E_FUND_BASE (default: 500)
    """
    import os
    try:
        base = int(os.getenv('E2E_FUND_BASE', '500'))
    except Exception:
        base = 500
    return base + test_number


def is_output_locked(locktime: int, current_height: int) -> Tuple[bool, int]:
    """Check if an output is still locked by CLTV.
    
    CLTV is satisfied when: current_height >= locktime
    
    Returns: (is_locked, blocks_remaining)
        - is_locked: True if output is still locked (current_height < locktime)
        - blocks_remaining: Number of blocks until locktime is satisfied (0 or negative if satisfied)
    """
    blocks_remaining = locktime - current_height
    is_locked = current_height < locktime  # Locked if current height is less than locktime
    return is_locked, blocks_remaining


def log_test_info(test_name: str, test_data: Dict, current_height: int, spend_path: str = "N/A"):
    """Print comprehensive test information with Miniscript/descriptor if available."""
    print(f"\n{'='*80}")
    print(f"🧪 TEST #{test_data.get('test_number', '?')}: {test_name}")
    print(f"{'='*80}")
    print(f"Status:           {test_data.get('status', 'UNKNOWN')}")
    print(f"Test Number:      {test_data.get('test_number', 'N/A')}")
    print(f"Address:          {test_data.get('address', 'N/A')}")
    print(f"Amount:           {test_data.get('amount_sats', 'Not funded')} sats")
    print(f"Lockheight:       {test_data.get('locktime', 'N/A')} (current: {current_height})")
    print(f"Script Type:      {test_data.get('script_type', 'N/A')}")
    print(f"Format:           {test_data.get('format', 'N/A')}")
    print(f"Spend Path:       {spend_path}")

    # Miniscript and descriptor: print if present in state, otherwise compute on the fly
    try:
        ms_sym = test_data.get('miniscript_symbolic')
        ms_conc = test_data.get('miniscript_concrete')
        desc_any = test_data.get('descriptor') or test_data.get('descriptor_wsh') or test_data.get('descriptor_tr')
        if not (ms_sym and ms_conc):
            # Lazy import to avoid heavy deps at module import time
            from miniscript_registry import miniscript_for, descriptor_for
            st = (test_data.get('script_type') or '').lower()
            params = dict(test_data.get('script_params') or {})
            if 'locktime' not in params and test_data.get('locktime') is not None:
                params['locktime'] = test_data['locktime']
            # Fill params from top-level keys (using miniscript names - v12.0.0)
            for k in ('pubkey', 'alice', 'bob', 'lenny', 'user', 'service',
                      'sender', 'receiver', 'publisher', 'buyer', 'data_hash'):
                if k not in params and k in test_data:
                    params[k] = test_data[k]
            # v12.0.0: script_type is canonical (e.g., 'cltv_hodl_p2wsh')
            # Strip output type suffix to get base type for miniscript_for
            ms_type = st.replace('_p2wsh', '').replace('_taproot', '')
            if ms_type.startswith('cltv_'):
                ms_sym = miniscript_for(ms_type, params, style='symbolic')
                ms_conc = miniscript_for(ms_type, params, style='concrete')
                var = 'tr' if (test_data.get('format', '').upper() == 'TAPROOT') else 'wsh'
                desc = descriptor_for(ms_type, params, variant=var)
                if var == 'tr' and test_data.get('internal_key'):
                    desc = desc.replace('<internal_key>', test_data['internal_key'])
                # attach for subsequent prints
                test_data.setdefault('miniscript_symbolic', ms_sym)
                test_data.setdefault('miniscript_concrete', ms_conc)
                if var == 'wsh':
                    test_data.setdefault('descriptor_wsh', desc)
                else:
                    test_data.setdefault('descriptor_tr', desc)
                test_data.setdefault('descriptor', desc)
    except Exception:
        # best-effort enrichment; safe to ignore failures in logs
        pass

    # Show funding transaction
    if test_data.get('funding_txid'):
        print(f"Funding TXID:     {test_data.get('funding_txid')}")
        print(f"Funding VOUT:     {test_data.get('funding_vout')}")

    # Show sweep transaction
    if test_data.get('sweep_txid'):
        print(f"Sweep TXID:       {test_data.get('sweep_txid')}")

    # Show data preimage for data publishing tests
    if 'data_publishing' in test_name.lower() and test_data.get('data_preimage'):
        print(f"Data Preimage:    {test_data.get('data_preimage')}")
    elif 'data_publishing' in test_name.lower() and test_data.get('script_params', {}).get('data_hash'):
        print(f"Data Hash:        {test_data.get('script_params', {}).get('data_hash')}")

    print(f"{'='*80}\n")
