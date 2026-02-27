"""
Broadcast Utilities - Centralized transaction broadcasting

Provides educational, DRY broadcast helpers that work for both P2WSH and Taproot.

Key principles:
- Decide destination ONCE upfront (no rebuild callbacks needed)
- Keep educational timelock rejection behavior visible
- Same broadcast logic for P2WSH and Taproot (format-agnostic)
- Clear error messages and logging

Usage:
    from broadcast_utils import broadcast_transaction
    
    # Decide destination upfront
    dest = get_sweep_destination(test_data)
    
    # Build transaction with final destination
    tx_hex = sweeper.sweep_cooperative(key1, key2, dest)
    
    # Broadcast (handles timelock errors educationally)
    txid = broadcast_transaction(
        tx_hex=tx_hex,
        test_data=test_data,
        current_height=current_height
    )
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


def is_timelock_error(error_msg: str) -> bool:
    """
    Check if broadcast error is due to timelock not being reached.
    
    This is EXPECTED behavior when testing CLTV - the transaction should
    be rejected if we try to broadcast before the locktime is reached.
    
    Args:
        error_msg: Error message from Electrum broadcast
    
    Returns:
        True if error is expected "non-final" (CLTV not satisfied yet)
    
    Educational Note:
        Bitcoin nodes reject transactions where:
        - nSequence != 0xFFFFFFFF (we use 0xFFFFFFFE to enable nLockTime)
        - Current height < CLTV value in script
        This is consensus-level enforcement of BIP-65 CHECKLOCKTIMEVERIFY
    """
    if not error_msg:
        return False
    
    error_lower = error_msg.lower()
    return 'non-final' in error_lower or 'cltv' in error_lower


def broadcast_transaction(
    tx_hex: str,
    test_data: Optional[Dict] = None,
    current_height: Optional[int] = None,
    state_manager: Optional[object] = None,
    # Backward-compat kwargs used by some tests; accepted and handled gracefully.
    locktime: Optional[int] = None,
    network: Optional[str] = None,
) -> str:
    """
    Broadcast a transaction via Electrum CLI with educational error handling.
    
    This function is format-agnostic - it works the same for P2WSH and Taproot.
    The educational value comes from seeing actual consensus-level rejections
    when timelock conditions aren't met.
    
    Args:
        tx_hex: Serialized transaction hex
        test_data: Optional test state dict (for timelock error context)
        current_height: Optional current block height (for timelock messages)
        state_manager: Optional StateManager to update on success
    
    Returns:
        Transaction ID if successful
    
    Raises:
        Exception: If broadcast fails for non-timelock reasons
    
    Educational Behavior:
        - Timelock errors are logged educationally but DON'T raise exceptions
        - This lets students see: "tried to spend early → network rejected it"
        - Other errors raise exceptions as they indicate real problems
    
    Examples:
        >>> # Simple broadcast
        >>> txid = broadcast_transaction(tx_hex)
        
        >>> # Educational broadcast with timelock context
        >>> txid = broadcast_transaction(
        ...     tx_hex=tx_hex,
        ...     test_data=test_data,
        ...     current_height=107552
        ... )
    """
    from network_config import NETWORK_FLAG
    
    electrum_python = Path.home() / "src/electrum/venv/bin/python3"
    electrum_path = Path.home() / "src/electrum/run_electrum"
    
    if not electrum_python.exists():
        raise RuntimeError(f"Electrum Python not found: {electrum_python}")
    if not electrum_path.exists():
        raise RuntimeError(f"Electrum not found: {electrum_path}")
    
    try:
        result = subprocess.run(
            [str(electrum_python), str(electrum_path), NETWORK_FLAG, 'broadcast', tx_hex],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # SUCCESS: Parse and return TXID
            broadcast_output = result.stdout.strip()
            
            try:
                # Try parsing as JSON first (Electrum sometimes returns [true, "txid"])
                broadcast_result = json.loads(broadcast_output)
                if isinstance(broadcast_result, list) and len(broadcast_result) == 2:
                    success, txid = broadcast_result
                    if not success:
                        raise Exception(f"Broadcast returned false: {txid}")
                elif isinstance(broadcast_result, str):
                    txid = broadcast_result
                else:
                    txid = str(broadcast_result)
            except json.JSONDecodeError:
                # Raw TXID string
                txid = broadcast_output.strip('"')
            
            # Validate TXID format (64 hex chars)
            if not txid or len(txid) != 64:
                raise Exception(f"Invalid TXID from broadcast: {txid}")
            
 print(f" Sweep successful!")
            print(f"   Sweep TXID: {txid}")
            
            # Update state if provided
            if test_data and state_manager:
                test_data['sweep_txid'] = txid
                test_data['status'] = 'SWEPT'
                test_data['swept_at'] = datetime.now().isoformat()
                state_manager.save()
            
            return txid
        
        else:
            # FAILURE: Check if it's an expected timelock error
            error_msg = result.stderr if result.stderr else result.stdout
            
            if is_timelock_error(error_msg):
                # EDUCATIONAL: This is EXPECTED when CLTV hasn't been reached yet
                # Log it clearly so students understand what's happening
                
                if current_height is not None:
                    # Prefer explicit locktime if provided; fall back to test_data
                    _lt = locktime if locktime is not None else (test_data.get('locktime') if test_data else None)
                    if _lt is not None:
                        blocks_remaining = _lt - current_height
 print(f"\n TIMELOCK REJECTION (EXPECTED - This demonstrates BIP-65 enforcement)")
                        print(f"   ════════════════════════════════════════════════════════════")
                        print(f"   Bitcoin nodes rejected this transaction because:")
                        print(f"   • Current height: {current_height}")
                        print(f"   • CLTV locktime:  {_lt}")
                        print(f"   • Blocks remaining: {blocks_remaining}")
                        print(f"   ")
                        print(f"   This is consensus-level enforcement of CHECKLOCKTIMEVERIFY.")
                        print(f"   The transaction is valid but cannot be mined yet.")
                        print(f"   Wait {blocks_remaining} more block(s) to sweep this output.")
                        print(f"   ════════════════════════════════════════════════════════════")
                        # Return None to indicate "locked, try later"
                        return None
                
                # Fallback message if we don't have detailed context
 print(f"\n Transaction rejected: Timelock not yet reached (EXPECTED)")
                print(f"   This demonstrates BIP-65 CHECKLOCKTIMEVERIFY enforcement")
                print(f"   Error: {error_msg}")
                return None
            
            else:
                # REAL ERROR: Something actually went wrong
 print(f" Broadcast failed: {error_msg}")
                raise Exception(f"Broadcast failed: {error_msg}")
    
    except subprocess.TimeoutExpired:
        raise Exception("Broadcast timed out after 30 seconds")
    except Exception as e:
        if isinstance(e, Exception) and "Broadcast failed" in str(e):
            raise
        raise Exception(f"Broadcast error: {e}") from e


def get_explorer_url(txid: str, network: str = "signet") -> str:
    """
    Get block explorer URL for a transaction.
    
    Args:
        txid: Transaction ID
        network: Network name (signet, testnet4, mainnet)
    
    Returns:
        Full URL to view transaction in block explorer
    
    Examples:
        >>> url = get_explorer_url("abc123...", "signet")
        >>> print(f"View: {url}")
    """
    from network_config import EXPLORER_BASE
    return f"{EXPLORER_BASE}/tx/{txid}"


__all__ = [
    'broadcast_transaction',
    'is_timelock_error',
    'get_explorer_url'
]
