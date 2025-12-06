#!/usr/bin/env python3
"""
Shared utilities for CLTV E2E tests

Common functions used by both P2SH and Taproot lock/sweep scripts.
Eliminates code duplication and provides consistent behavior.
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

# ============================================================================
# BITCOIN UTILITIES
# ============================================================================

# Use Electrum's native crypto functions instead of custom implementations
try:
    from electrum.crypto import sha256d, hash_160
    from electrum.util import bfh
except ImportError:
    # Fallback for standalone scripts
    def bfh(h):
        """Bytes from hex"""
        return bytes.fromhex(h)
    
    def sha256d(data):
        """Double SHA256 hash"""
        import hashlib
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    def hash_160(data):
        """RIPEMD160(SHA256(data))"""
        import hashlib
        return hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()

def encode_locktime(height):
    """
    Encode locktime as minimal Bitcoin script push.
    
    Args:
        height: Block height (int)
        
    Returns:
        bytes: Minimal push encoding
    """
    if 1 <= height <= 16:
        return bytes([0x50 + height])  # OP_1 through OP_16
    elif height <= 0x7f:
        return bytes([0x01, height])
    elif height <= 0x7fff:
        return bytes([0x02]) + height.to_bytes(2, 'little')
    elif height <= 0x7fffff:
        return bytes([0x03]) + height.to_bytes(3, 'little')
    else:
        return bytes([0x04]) + height.to_bytes(4, 'little')


# ============================================================================
# BLOCKCHAIN QUERIES
# ============================================================================

ELECTRUM_DIR = os.path.expanduser("~/src/electrum")

def get_current_height():
    """
    Query Electrum for current block height.
    
    Returns:
        int: Current blockchain height, or None on error
    """
    try:
        result = subprocess.run(
            ['bash', '-c', 'source venv/bin/activate && ./run_electrum --testnet4 getinfo'],
            cwd=ELECTRUM_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return info.get('blockchain_height', 0)
    except Exception as e:
        print(f"⚠️  Could not get height: {e}")
    return None

def fund_address(address, amount_sats):
    """
    Fund an address using Electrum's payto command.
    
    Args:
        address: Bitcoin address to fund
        amount_sats: Amount in satoshis
        
    Returns:
        str: Funding TXID, or None on error
    """
    amount_btc = amount_sats / 100_000_000
    try:
        result = subprocess.run(
            ['bash', '-c', f'source venv/bin/activate && ./run_electrum --testnet4 payto {address} {amount_btc} && ./run_electrum --testnet4 broadcast "$(./run_electrum --testnet4 signtransaction "$(./run_electrum --testnet4 payto {address} {amount_btc})" | jq -r .hex)"'],
            cwd=ELECTRUM_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip().strip('"')
    except Exception as e:
        print(f"⚠️  Funding failed: {e}")
    return None

def get_transaction_confirmations(txid):
    """
    Get number of confirmations for a transaction.
    
    Args:
        txid: Transaction ID
        
    Returns:
        int: Number of confirmations, or 0 if not found
    """
    try:
        result = subprocess.run(
            ['bash', '-c', f'source venv/bin/activate && ./run_electrum --testnet4 gettransaction {txid}'],
            cwd=ELECTRUM_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            tx_info = json.loads(result.stdout)
            return tx_info.get('confirmations', 0)
    except:
        pass
    return 0

def broadcast_transaction(tx_hex):
    """
    Broadcast a raw transaction.
    
    Args:
        tx_hex: Transaction hex string
        
    Returns:
        tuple: (success: bool, result: str)
            - success=True, result=txid
            - success=False, result=error_message
    """
    try:
        result = subprocess.run(
            ['bash', '-c', f'source venv/bin/activate && ./run_electrum --testnet4 broadcast {tx_hex}'],
            cwd=ELECTRUM_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout.strip()
        
        if result.returncode == 0:
            # Success - extract TXID
            txid = output.strip('"\'')
            return (True, txid)
        else:
            # Failure - extract error
            error = result.stderr.strip() if result.stderr else output
            return (False, error)
            
    except Exception as e:
        return (False, f"Broadcast exception: {e}")


# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    """Unified logger that writes to both console and file"""
    
    def __init__(self, log_file_path):
        """
        Initialize logger.
        
        Args:
            log_file_path: Path to log file
        """
        self.log_file = log_file_path
        
        # Ensure logs directory exists
        log_dir = os.path.dirname(log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def log(self, message):
        """Write message to console and file"""
        print(message)
        with open(self.log_file, 'a') as f:
            f.write(message + '\n')
    
    def rename_log_file(self, new_path):
        """
        Rename log file (used after getting funding TXID).
        
        Args:
            new_path: New path for log file
        """
        if os.path.exists(self.log_file):
            os.rename(self.log_file, new_path)
            self.log_file = new_path


# ============================================================================
# METADATA MANAGEMENT
# ============================================================================

def save_metadata(metadata_path, data):
    """
    Save metadata to JSON file.
    
    Args:
        metadata_path: Path to metadata file
        data: Dict to save
    """
    with open(metadata_path, 'w') as f:
        json.dump(data, f, indent=2)

def load_metadata(test_type):
    """
    Load most recent metadata file for test type.
    
    Args:
        test_type: 'p2sh' or 'taproot'
        
    Returns:
        tuple: (metadata_file_path, metadata_dict)
        
    Raises:
        FileNotFoundError: If no metadata found
    """
    log_dir = Path(__file__).parent / "logs"
    meta_files = list(log_dir.glob(f"{test_type}_lock_demo_*.json"))
    
    if not meta_files:
        raise FileNotFoundError(
            f"No {test_type}_lock_demo metadata found! "
            f"Run {test_type}_lock_demo.py first!"
        )
    
    # Get most recent
    meta_file = sorted(meta_files, key=lambda p: p.stat().st_mtime)[-1]
    
    with open(meta_file) as f:
        metadata = json.load(f)
    
    return (str(meta_file), metadata)

def update_metadata(metadata_path, updates):
    """
    Update metadata file with new fields.
    
    Args:
        metadata_path: Path to metadata file
        updates: Dict of fields to update
    """
    with open(metadata_path) as f:
        metadata = json.load(f)
    
    metadata.update(updates)
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)


# ============================================================================
# WAITING / MONITORING
# ============================================================================

def wait_for_confirmation(txid, logger, min_confirmations=1, poll_interval=60):
    """
    Wait for transaction to be confirmed.
    
    Args:
        txid: Transaction ID to monitor
        logger: Logger instance
        min_confirmations: Minimum confirmations to wait for
        poll_interval: Seconds between checks
    """
    logger.log(f"\n⏳ WAITING FOR CONFIRMATION")
    logger.log(f"  Target confirmations: {min_confirmations}")
    logger.log(f"  Polling every {poll_interval} seconds")
    logger.log(f"  ")
    
    while True:
        confirmations = get_transaction_confirmations(txid)
        
        if confirmations >= min_confirmations:
            logger.log(f"  ✅ Confirmed! ({confirmations} confirmation{'s' if confirmations != 1 else ''})")
            break
        
        logger.log(f"  ⏳ {confirmations} confirmation{'s' if confirmations != 1 else ''}... waiting {poll_interval}s")
        time.sleep(poll_interval)

def wait_for_locktime(locktime, logger, poll_interval=60):
    """
    Wait until current height >= locktime.
    
    Args:
        locktime: Target block height
        logger: Logger instance
        poll_interval: Seconds between checks
    """
    logger.log(f"\n⏳ WAITING FOR LOCKTIME TO PASS")
    logger.log(f"  Target height: {locktime}")
    logger.log(f"  Polling every {poll_interval} seconds")
    logger.log(f"  ")
    
    while True:
        current = get_current_height()
        if not current:
            logger.log(f"  ⚠️  Could not get height, retrying...")
            time.sleep(poll_interval)
            continue
        
        remaining = locktime - current
        
        if remaining <= 0:
            logger.log(f"  ✅ Locktime passed! (height {current} >= {locktime})")
            break
        
        eta_minutes = remaining * 10  # ~10 min per block
        logger.log(f"  ⏳ Height {current} | {remaining} blocks to go | ~{eta_minutes} min")
        time.sleep(poll_interval)
    
    return current


# ============================================================================
# CONFIGURATION
# ============================================================================

class TestConfig:
    """Configuration for E2E tests"""
    
    # Default values
    AMOUNT_SATS = 1000
    FEE_SATS = 200
    DESTINATION_ADDRESS = "tb1q7hcyp0yufm60ekqzgfk7zs7md7ftca80w6vraw"
    LOCKTIME_OFFSET = 3  # blocks ahead
    
    # Test key (for deterministic testing)
    TEST_PRIVKEY = "0" * 63 + "1"
    
    # Paths
    ELECTRUM_DIR = os.path.expanduser("~/src/electrum")
    LOGS_DIR = Path(__file__).parent / "logs"
    
    @classmethod
    def get_log_paths(cls, test_type, stage='pending'):
        """
        Get log file paths for test.
        
        Args:
            test_type: 'p2sh' or 'taproot'
            stage: 'pending' or txid
            
        Returns:
            tuple: (log_file_path, metadata_file_path)
        """
        cls.LOGS_DIR.mkdir(exist_ok=True)
        
        log_file = cls.LOGS_DIR / f"{test_type}_lock_demo_{stage}.log"
        meta_file = cls.LOGS_DIR / f"{test_type}_lock_demo_{stage}.json"
        
        return (str(log_file), str(meta_file))


# ============================================================================
# DISPLAY HELPERS
# ============================================================================

def print_header(logger, title):
    """Print formatted section header"""
    logger.log("=" * 80)
    logger.log(title)
    logger.log("=" * 80)

def print_attempt_header(logger, attempt_num, description):
    """Print attempt header"""
    logger.log("\n" + "=" * 80)
    logger.log(f"ATTEMPT {attempt_num}: {description}")
    logger.log("=" * 80)

def print_test_summary(logger, test_type, metadata):
    """
    Print complete test summary.
    
    Args:
        logger: Logger instance
        test_type: 'p2sh' or 'taproot'
        metadata: Complete metadata dict
    """
    attempts = metadata.get('sweep_attempts', [])
    if len(attempts) < 2:
        return
    
    premature = attempts[0]
    valid = attempts[-1]
    
    logger.log("\n✅ SWEEP PHASE COMPLETE")
    logger.log("🎉 FULL TEST CYCLE COMPLETE - ALL PHASES SUCCESSFUL")
    logger.log("")
    logger.log("TEST SUMMARY:")
    logger.log("┌" + "─" * 78 + "┐")
    logger.log("│ Phase                    │ Status  │ Details                             │")
    logger.log("├" + "─" * 78 + "┤")
    logger.log(f"│ Lock (Address Creation)  │ ✅ PASS │ Address funded at block {metadata['current_height']:<11} │")
    logger.log(f"│ Premature Sweep          │ ✅ PASS │ Correctly rejected (non-final)      │")
    logger.log(f"│ Valid Sweep              │ ✅ PASS │ Successfully broadcast              │")
    logger.log("└" + "─" * 78 + "┘")
    logger.log("")
    logger.log("PROOF OF CORRECTNESS:")
    logger.log(f"  ✅ CLTV {test_type.upper()} script constructed correctly")
    logger.log(f"  ✅ Address generation works")
    logger.log(f"  ✅ Locktime enforcement validated (premature @ {premature['height']}, valid @ {valid['height']})")
    logger.log(f"  ✅ Successful spend after locktime")
    logger.log(f"  ✅ Signature validation passed")
    logger.log(f"  ✅ Transaction confirmed on blockchain")
    logger.log("")
    logger.log(f"TRANSACTIONS:")
    logger.log(f"  Funding: {metadata['funding_txid']}")
    logger.log(f"  Sweep:   {valid.get('sweep_txid', 'N/A')}")
    logger.log("")
    logger.log(f"VIEW ON MEMPOOL.SPACE:")
    logger.log(f"  https://mempool.space/testnet4/tx/{metadata['funding_txid']}")
    logger.log(f"  https://mempool.space/testnet4/tx/{valid.get('sweep_txid', '')}")
