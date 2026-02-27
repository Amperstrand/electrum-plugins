#!/usr/bin/env python3
"""
Fund All Spend Paths (P2WSH Examples)

Creates and (optionally) funds outputs for every distinct spend path across the
five core P2WSH contract types using the production builder API and deterministic
UI test keys:

  1. Simple CLTV            → after_locktime
  2. Escrow (2-party)       → cooperation, refund
  3. Escrow (3-party)       → normal, arbitration_alice, arbitration_bob
  4. Payment Channel        → cooperative, refund
  5. Two-Factor Wallet      → normal, recovery

Each path gets its own output (duplicate addresses appear where a single script
serves multiple paths). We store minimal metadata required by the simplified UI
wallet model: script_id, address, lockheight, path_name, vout (after funding),
funding_txid.

Usage:
  # Create only (no funding)
  python fund_all_paths.py --create

  # Create and fund via Electrum RPC (paytomany + broadcast)
  python fund_all_paths.py --create --fund

  # Fund previously created set
  python fund_all_paths.py --fund

  # Poll confirmations after funding
  python fund_all_paths.py --confirm

  # Show status
  python fund_all_paths.py --status
"""

import os, json, time, argparse, subprocess
from pathlib import Path
from datetime import datetime

from cltv_lib.builders.unified.generic import build_contract
from test_keys import get_test_pubkey

AMOUNT_SATS = 1000
STATE_FILE = Path(__file__).parent / 'fund_all_paths_state.json'
ELECTRUM_CLI = os.path.expanduser('/Users/macbook/src/electrum/venv/bin/electrum')
DEFAULT_WALLET = os.path.expanduser('~/.electrum/signet/wallets/default_wallet')

def btc_amt(sats: int) -> str:
    return f"{sats/1e8:.8f}"

def ensure_daemon():
    # Prefer 'daemon start' — treat 'already running' as success.
    try:
        # Quick RPC check first
        ok = subprocess.run([ELECTRUM_CLI, '--signet', 'getinfo'], capture_output=True, text=True)
        if ok.returncode == 0:
            return True
        # Try to start daemon in detached mode (older electrum versions)
        proc = subprocess.run([ELECTRUM_CLI, '--signet', 'daemon', '-d'], capture_output=True, text=True)
        stderr = (proc.stderr or '') + (proc.stdout or '')
        if proc.returncode == 0:
            time.sleep(1)
            return True
        # Common message when daemon is already running
        if 'already running' in stderr.lower() or 'lockfile detected' in stderr.lower():
            return True
        print(' Starting daemon (fallback)...')
        proc2 = subprocess.run([ELECTRUM_CLI, '--signet', 'daemon', '-d'], capture_output=True, text=True)
        if proc2.returncode == 0:
            time.sleep(1)
            return True
        print(f" Daemon start failed: {proc2.stderr.strip()}")
    except Exception:
        pass
    # If we couldn't start but electrum CLI returns info, consider daemon responsive
    try:
        ok = subprocess.run([ELECTRUM_CLI, '--signet', 'getinfo'], capture_output=True, text=True)
        if ok.returncode == 0:
            return True
    except Exception:
        pass
    return False

def parse_confirmations_output(text: str):
    import json, re
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and 'confirmations' in data:
            return int(data['confirmations'])
    except Exception:
        pass
    m = re.search(r'confirmations\s*[:=]\s*(\d+)', text)
    if m:
        return int(m.group(1))
    return None

def poll_confirmations(state, max_wait=60, interval=5):
    txid = state.get('funding_txid')
    if not txid:
        print(' No funding_txid recorded.')
        return None
    if not ensure_daemon():
        print(' Daemon unavailable; cannot poll.')
        return None
    elapsed = 0
    confirmations = None
    while elapsed <= max_wait:
        res = subprocess.run([ELECTRUM_CLI, '--signet', 'get_tx_status', txid], capture_output=True, text=True)
        if res.returncode == 0:
            confirmations = parse_confirmations_output(res.stdout.strip())
            if confirmations is not None:
                state['confirmations'] = confirmations
                STATE_FILE.write_text(json.dumps(state, indent=2))
                print(f" {txid} confirmations={confirmations}")
                if confirmations >= 1:
                    break
        else:
            print(f" get_tx_status failed: {res.stderr.strip()}")
        time.sleep(interval)
        elapsed += interval
    return confirmations

def build_all_path_outputs():
    outputs = []
    # Use locktime 0 for all tests - makes it fast to spend and easy to import in UI
    locktime = 0
    
    # 1. Simple CLTV (now called HODL)
    result = build_contract('hodl', {'locktime': locktime, 'pubkey': get_test_pubkey('hodl')}, 'p2wsh', 'signet')
    addr_simple = result['address']
    outputs.append({'script_id': 'cltv_hodl_p2wsh', 'address': addr_simple, 'lockheight': locktime, 'path_name': 'after_locktime'})
    
    # 2. Escrow (now always 3-party)
    result_e3 = build_contract('escrow', {
        'locktime': locktime,
        'alice': get_test_pubkey('alice'),
        'bob': get_test_pubkey('bob'),
        'lenny': get_test_pubkey('lenny')
    }, 'p2wsh', 'signet')
    addr_e3 = result_e3['address']
    outputs.append({'script_id': 'cltv_escrow_p2wsh', 'address': addr_e3, 'lockheight': locktime, 'path_name': 'normal'})
    outputs.append({'script_id': 'cltv_escrow_p2wsh', 'address': addr_e3, 'lockheight': locktime, 'path_name': 'arbitration_alice'})
    outputs.append({'script_id': 'cltv_escrow_p2wsh', 'address': addr_e3, 'lockheight': locktime, 'path_name': 'arbitration_bob'})
    
    # 4. Payment Channel
    result_pc = build_contract('payment_channel', {
        'locktime': locktime,
        'sender': get_test_pubkey('sender'),
        'receiver': get_test_pubkey('receiver')
    }, 'p2wsh', 'signet')
    addr_pc = result_pc['address']
    outputs.append({'script_id': 'cltv_payment_channel_p2wsh', 'address': addr_pc, 'lockheight': locktime, 'path_name': 'cooperative'})
    outputs.append({'script_id': 'cltv_payment_channel_p2wsh', 'address': addr_pc, 'lockheight': locktime, 'path_name': 'refund'})
    
    # 5. Two-Factor
    result_tf = build_contract('twofactor', {
        'locktime': locktime,
        'user': get_test_pubkey('user'),
        'service': get_test_pubkey('service')
    }, 'p2wsh', 'signet')
    addr_tf = result_tf['address']
    outputs.append({'script_id': 'cltv_twofactor_p2wsh', 'address': addr_tf, 'lockheight': locktime, 'path_name': 'normal'})
    outputs.append({'script_id': 'cltv_twofactor_p2wsh', 'address': addr_tf, 'lockheight': locktime, 'path_name': 'recovery'})
    
    # 6. Data Publishing
    import hashlib
    data_preimage = b'secret_data'
    data_hash = hashlib.new('ripemd160', hashlib.sha256(data_preimage).digest()).hexdigest()
    
    result_dp = build_contract('data_publishing', {
        'locktime': locktime,
        'publisher': get_test_pubkey('publisher'),
        'buyer': get_test_pubkey('buyer'),
        'data_hash': data_hash
    }, 'p2wsh', 'signet')
    addr_dp = result_dp['address']
    # Include data_preimage for publisher path test
    outputs.append({'script_id': 'cltv_data_publishing_p2wsh', 'address': addr_dp, 'lockheight': locktime, 'path_name': 'publisher', 'data_preimage': data_preimage.hex()})
    outputs.append({'script_id': 'cltv_data_publishing_p2wsh', 'address': addr_dp, 'lockheight': locktime, 'path_name': 'buyer_refund'})
    
    return outputs

def save_state(outputs, txid=None):
    state = {
        'created_at': datetime.now().isoformat(),
        'network': 'signet',
        'amount_sats': AMOUNT_SATS,
        'status': 'FUNDED' if txid else 'CREATED',
        'funding_txid': txid,
        'outputs': outputs,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    return state

def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())

def fund_rpc(outputs, wallet_path=None):
    wallet_path = os.path.expanduser(wallet_path or DEFAULT_WALLET)
    if not os.path.exists(wallet_path):
        print(f" Wallet not found: {wallet_path}")
        return None
    if not ensure_daemon():
        return None
    outputs_json = json.dumps([[o['address'], btc_amt(AMOUNT_SATS)] for o in outputs])
    print(f"\n paytomany outputs JSON: {outputs_json}")
    pay = subprocess.run([ELECTRUM_CLI, '--signet', '-w', wallet_path, 'paytomany', outputs_json, '--addtransaction'], capture_output=True, text=True)
    if pay.returncode != 0:
        print(f" paytomany failed: {pay.stderr.strip()}")
        return None
    raw_tx = pay.stdout.strip().splitlines()[-1]
    if len(raw_tx) < 40:
        print(f" Unexpected paytomany output: {pay.stdout}")
        return None
    bcast = subprocess.run([ELECTRUM_CLI, '--signet', 'broadcast', raw_tx], capture_output=True, text=True)
    if bcast.returncode != 0:
        print(f" Broadcast failed: {bcast.stderr.strip()}")
        return None
    txid_candidates = [tok for tok in bcast.stdout.split() if len(tok) == 64 and all(c in '0123456789abcdef' for c in tok.lower())]
    txid = txid_candidates[-1] if txid_candidates else bcast.stdout.strip()[-64:]
    print(f" Broadcast TXID: {txid}")
    return txid

def annotate_vouts(outputs, txid):
    # Sort stable for deterministic vout mapping
    for i, o in enumerate(outputs):
        o['funding_txid'] = txid
        o['vout'] = i
        o['amount_sats'] = AMOUNT_SATS
    return outputs

def show_status():
    state = load_state()
    if not state:
        print(' No state. Run --create.')
        return
    print('='*72)
    print('FUND ALL PATHS STATUS')
    print('='*72)
    print(f"State file: {STATE_FILE}")
    print(f"Status: {state['status']}")
    if state.get('funding_txid'):
        print(f"Funding TXID: {state['funding_txid']}")
    if 'confirmations' in state:
        print(f"Confirmations: {state['confirmations']}")
    print(f"Outputs: {len(state['outputs'])}")
    for o in state['outputs']:
        path = o['path_name']
        addr = o['address']
        print(f"  - {o['script_id']:<24} {path:<18} {addr} lock={o['lockheight']}")

def main():
    p = argparse.ArgumentParser(description='Fund all spend paths for five P2WSH examples (signet)')
    p.add_argument('--create', action='store_true', help='Create outputs for all paths')
    p.add_argument('--fund', action='store_true', help='Fund all path outputs via RPC')
    p.add_argument('--status', action='store_true', help='Show status')
    p.add_argument('--confirm', action='store_true', help='Poll confirmations until >=1 or timeout')
    p.add_argument('--wallet', help='Custom Electrum wallet path')
    args = p.parse_args()

    if args.create:
        outputs = build_all_path_outputs()
        save_state(outputs)
        # Show manual command alternative
        pay_cmd = '; '.join(f"{o['address']}, {btc_amt(AMOUNT_SATS)}" for o in outputs)
        print('\n='*72)
        print('PAYTOMANY (manual funding alternative)')
        print('='*72)
        print(f"./run_electrum --signet paytomany '{pay_cmd}'")
    if args.fund:
        state = load_state()
        if not state:
            outputs = build_all_path_outputs()
            state = save_state(outputs)
        if state['status'] == 'FUNDED':
            print(' Already funded.')
        else:
            txid = fund_rpc(state['outputs'], args.wallet)
            if txid:
                outputs = annotate_vouts(state['outputs'], txid)
                save_state(outputs, txid)
    if args.status:
        show_status()
    if args.confirm:
        state = load_state()
        if not state:
            print(' No state file.')
        elif state['status'] != 'FUNDED':
            print(' Not funded yet.')
        else:
            poll_confirmations(state)
    if not (args.create or args.fund or args.status or args.confirm):
        p.print_help()

if __name__ == '__main__':
    main()
