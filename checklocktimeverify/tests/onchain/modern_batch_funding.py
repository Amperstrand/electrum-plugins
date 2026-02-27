#!/usr/bin/env python3
"""
Modern Batch Funding Utility (Signet)

Generates a set of CLTV-related script addresses using the production API
(registry + deterministic test keys) and prepares a single Electrum
`paytomany` command to fund them efficiently on signet.

Script Types Included:
  - Simple CLTV (after locktime)
  - Two-Party Escrow (cooperation or buyer refund)
  - Three-Party Escrow (2-of-3 after locktime)
  - Payment Channel (cooperative or sender refund)
  - Two-Factor (user+service or user+recovery after locktime)
  - Data Publishing (publisher spend or buyer refund)

Features:
  1. Builds scripts with `get_builder()` and deterministic `get_test_pubkey()`.
  2. Generates P2WSH signet addresses via `generate_address()`.
  3. Saves full metadata to `modern_funding_state.json`.
  4. Outputs a ready-to-run Electrum `paytomany` command.
  5. Optional: Direct RPC funding (`--fund`), using Electrum CLI.

Usage:
  # Just generate addresses and show paytomany command
  python modern_batch_funding.py --create

  # Create and immediately fund via Electrum CLI (needs wallet & daemon)
  python modern_batch_funding.py --create --fund

  # Only fund previously created set (if not yet funded)
  python modern_batch_funding.py --fund

  # Show status
  python modern_batch_funding.py --status

Notes:
  - Network: signet
  - Amount per address: 1000 sats
  - All keys come from `test_keys.py` ensuring determinism with UI.
  - After funding, wait 1 confirmation before sweeping in UI plugin.
"""

import json
import os
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

from cltv_lib import get_builder, generate_address
from test_keys import get_test_pubkey

AMOUNT_SATS = 1000
AMOUNT_BTC = AMOUNT_SATS / 1e8
STATE_FILE = Path(__file__).parent / 'modern_funding_state.json'
ELECTRUM_CLI = os.path.expanduser('/Users/macbook/src/electrum/venv/bin/electrum')
DEFAULT_WALLET = os.path.expanduser('~/.electrum/signet/wallets/default_wallet')

def parse_confirmations_output(text: str):
    """Extract confirmation count from electrum get_tx_status output.

    Supports either JSON ({"confirmations": N}) or plain 'confirmations: N'.
    Returns int or None.
    """
    if not text:
        return None
    import re, json
    # Try JSON first
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


def btc_amt(sats: int) -> str:
    return f"{sats/1e8:.8f}"  # Electrum paytomany expects decimal BTC strings


def build_all_addresses():
    """Build all script addresses with production API and return list of dicts."""
    specs = [
        # Only keep what UI wallet model needs: script type + lockheight
        ('cltv_simple_p2wsh', {'locktime': 120, 'pubkey': get_test_pubkey('hodl')}, 120),
        ('escrow_2party_cltv', {
            'refund_locktime': 180,
            'buyer_pubkey': get_test_pubkey('alice'),
            'seller_pubkey': get_test_pubkey('bob')
        }, 180),
        ('cltv_escrow_p2wsh', {
            'locktime': 200,
            'alice_pubkey': get_test_pubkey('alice'),
            'bob_pubkey': get_test_pubkey('bob'),
            'lenny_pubkey': get_test_pubkey('lenny')
        }, 200),
        ('cltv_payment_channel_p2wsh', {
            'locktime': 220,
            'sender_pubkey': get_test_pubkey('sender'),
            'receiver_pubkey': get_test_pubkey('receiver')
        }, 220),
        ('cltv_twofactor_p2wsh', {
            'locktime': 240,
            'user_pubkey': get_test_pubkey('user'),
            'service_pubkey': get_test_pubkey('service'),
            'recovery_pubkey': get_test_pubkey('recovery')
        }, 240),
        ('cltv_data_publishing_p2wsh', {
            'locktime': 260,
            'publisher_pubkey': get_test_pubkey('publisher'),
            'buyer_pubkey': get_test_pubkey('buyer'),
            'data_hash': '11' * 20  # 20-byte HASH160 placeholder
        }, 260),
    ]

    addresses = []
    for script_id, params, lockheight in specs:
        builder = get_builder(script_id)
        script = builder.build(params)
        addr_info = generate_address(script, 'p2wsh', 'signet')
        addresses.append({
            'script_id': script_id,
            'address': addr_info['address'],
            'lockheight': lockheight,
        })
    return addresses


def save_state(addresses, funding_txid=None):
    state = {
        'created_at': datetime.now().isoformat(),
        'network': 'signet',
        'amount_sats': AMOUNT_SATS,
        'status': 'FUNDED' if funding_txid else 'CREATED',
        'funding_txid': funding_txid,
        'addresses': addresses,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    return state


def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


def build_paytomany_string(addresses):
    parts = [f"{a['address']}, {btc_amt(AMOUNT_SATS)}" for a in addresses]
    return '; '.join(parts)


def ensure_daemon():
    # Daemon start: electrum --signet daemon -d
    try:
        status = subprocess.run([ELECTRUM_CLI, '--signet', 'daemon', 'status'], capture_output=True, text=True)
        if status.returncode == 0 and 'is_running' in status.stdout:
            return True
    except Exception:
        pass
 print(' Starting daemon...')
    proc = subprocess.run([ELECTRUM_CLI, '--signet', 'daemon', '-d'], capture_output=True, text=True)
    if proc.returncode != 0:
 print(f" Daemon start failed: {proc.stderr.strip()}")
        return False
    time.sleep(2)
    return True


def fund_rpc(addresses, wallet_path=None):
    wallet_path = os.path.expanduser(wallet_path or DEFAULT_WALLET)
    if not os.path.exists(wallet_path):
 print(f" Wallet not found: {wallet_path}")
        return None
    if not ensure_daemon():
        return None
    outputs_json = json.dumps([[a['address'], btc_amt(AMOUNT_SATS)] for a in addresses])
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
    # Parse txid (last 64 hex chars in output)
    txid_candidates = [tok for tok in bcast.stdout.split() if len(tok) == 64 and all(c in '0123456789abcdef' for c in tok.lower())]
    txid = txid_candidates[-1] if txid_candidates else bcast.stdout.strip()[-64:]
 print(f" Broadcast TXID: {txid}")
    return txid

def poll_confirmations(state, max_wait=60, interval=5):
    """Poll Electrum daemon for funding tx confirmations. Updates state file.

    Stops early once confirmations >= 1 or timeout reached.
    Returns final confirmation count or None.
    """
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


def show_status():
    state = load_state()
    if not state:
 print(" No state file. Run --create first.")
        return
    print("="*70)
    print("MODERN BATCH FUNDING STATUS")
    print("="*70)
    print(f"State file: {STATE_FILE}")
    print(f"Created: {state['created_at']}")
    print(f"Status: {state['status']}")
    if state.get('funding_txid'):
        print(f"Funding TXID: {state['funding_txid']}")
    print(f"Addresses: {len(state['addresses'])}")
    for a in state['addresses']:
        print(f"  - {a['script_id']:25} {a['address']} (lockheight={a['lockheight']})")
    if 'confirmations' in state:
        print(f"Confirmations: {state['confirmations']}")


def main():
    parser = argparse.ArgumentParser(description='Modern batch funding generator (signet)')
    parser.add_argument('--create', action='store_true', help='Create addresses and show paytomany command')
    parser.add_argument('--fund', action='store_true', help='Fund (RPC paytomany) newly created or existing unfunded set')
    parser.add_argument('--wallet', help='Electrum wallet path (default signet default_wallet)')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--confirm', action='store_true', help='Poll confirmations for funding txid')
    args = parser.parse_args()

    if args.create:
        addresses = build_all_addresses()
        save_state(addresses)
        pay_cmd = build_paytomany_string(addresses)
        print("\n" + "="*70)
        print("PAYTOMANY COMMAND (manual funding alternative)")
        print("="*70)
        print("Run in Electrum source checkout:")
        print(f"./run_electrum --signet paytomany '{pay_cmd}'")
        print("\nOr use --fund for automatic RPC funding.")
    if args.fund:
        state = load_state()
        if not state:
            addresses = build_all_addresses()
            state = save_state(addresses)
        if state['status'] == 'FUNDED':
 print(" Already funded.")
        else:
            txid = fund_rpc(state['addresses'], args.wallet)
            if txid:
                # Update per-address funding details
                for i, a in enumerate(state['addresses']):
                    a['funding_txid'] = txid
                    a['funding_vout'] = i
                    a['amount_sats'] = AMOUNT_SATS
                save_state(state['addresses'], funding_txid=txid)
    if args.status:
        show_status()
    if args.confirm:
        state = load_state()
        if not state:
 print(' No state file to confirm.')
        elif state.get('status') != 'FUNDED':
 print(' Not funded yet.')
        else:
            poll_confirmations(state)
    if not (args.create or args.fund or args.status):
        parser.print_help()


if __name__ == '__main__':
    main()
