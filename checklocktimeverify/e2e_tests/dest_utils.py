"""
Destination Utilities - Centralized destination/OP_RETURN handling

Provides a DRY helper to decide whether to use OP_RETURN or a regular address
for sweep destinations, and to build the appropriate destination tuple/string.

Rationale (M2 in roadmap):
- OP_RETURN logic was duplicated across test_e2e_full.py and multiple Taproot sweepers.
- Canonical pushdata and dynamic wallet fallback logic was scattered.
- Centralize once to ensure consistency and reduce future maintenance.

Usage:
    from dest_utils import get_sweep_destination
    
    dest = get_sweep_destination(test_data)
    # Returns either ('op_return', hex_data) or an address string
"""

import os
from typing import Dict, Tuple, Union
from pathlib import Path
import subprocess


# OP_RETURN configuration
# Default behavior: use OP_RETURN when the swept UTXO amount is small.
# Threshold can be overridden via env var E2E_OP_RETURN_THRESHOLD (default 800 sats).
# You can force behavior with E2E_FORCE_OP_RETURN=1 or E2E_DISABLE_OP_RETURN=1.
OP_RETURN_THRESHOLD = int(os.getenv('E2E_OP_RETURN_THRESHOLD', '800'))


def use_op_return_for(test_data: Dict) -> bool:
    """
    Decide whether to use OP_RETURN for a given test based on amount and env overrides.
    
    Args:
        test_data: Test state dictionary with amount_sats or amount field
    
    Returns:
        True if OP_RETURN should be used, False for regular address
    
    Examples:
        >>> use_op_return_for({'amount_sats': 500})  # 500 < 800
        True
        >>> use_op_return_for({'amount_sats': 1000})  # 1000 >= 800
        False
    """
    # Env overrides
    if os.getenv('E2E_FORCE_OP_RETURN', '').strip() == '1':
        return True
    if os.getenv('E2E_DISABLE_OP_RETURN', '').strip() == '1':
        return False
    
    # Determine amount field name
    amt = test_data.get('amount_sats')
    if amt is None:
        amt = test_data.get('amount')
    
    try:
        if isinstance(amt, str):
            amt = int(amt)
    except Exception:
        return False
    
    return isinstance(amt, int) and amt > 0 and amt < OP_RETURN_THRESHOLD


def get_op_return_label(test_number: int, variant: str = "") -> str:
    """
    Get OP_RETURN label for each test following BIP-65 format:
    "BIP65 Example #{demo_number} {path_type}"
    
    Returns hex-encoded string suitable for OP_RETURN output.
    
    Args:
        test_number: Test number (1-20)
        variant: Optional variant name (unused currently)
    
    Returns:
        Hex-encoded OP_RETURN data
    
    Examples:
        >>> get_op_return_label(1)
        '42495036352045...'  # "BIP65 Example #1 Freezing"
    """
    labels = {
        # P2WSH Tests (#1-10) - All BIP-65 examples
        1: "BIP65 Example #1 Freezing",            # Simple CLTV (Freezing Funds)
        2: "BIP65 Example #2 Escrow Cooperation",  # Escrow: Alice + Bob cooperation
        3: "BIP65 Example #2 Escrow Arbitration Alice",  # Escrow: Lenny + Alice after timeout
        4: "BIP65 Example #2 Escrow Arbitration Bob",    # Escrow: Lenny + Bob after timeout
        5: "BIP65 Example #3 2FA Normal",          # Two-factor: User + Service
        6: "BIP65 Example #3 2FA Recovery",        # Two-factor: User + Recovery after timeout
        7: "BIP65 Example #4 Channel Cooperative", # Payment Channel: Cooperative close
        8: "BIP65 Example #4 Channel Refund",      # Payment Channel: Refund after timeout
        9: "BIP65 Example #5 PayPub Publisher",    # Data Publishing: Publisher reveals
        10: "BIP65 Example #5 PayPub Buyer",       # Data Publishing: Buyer refund
        
        # Taproot Tests (#11-20) - Same BIP-65 examples, Taproot format
        11: "BIP65 Example #1 Freezing",           # Simple CLTV Taproot
        12: "BIP65 Example #2 Escrow Cooperation",  # Escrow: Alice + Bob cooperation
        13: "BIP65 Example #2 Escrow Arbitration Alice", # Escrow: Lenny + Alice after timeout
        14: "BIP65 Example #2 Escrow Arbitration Bob",   # Escrow: Lenny + Bob after timeout
        15: "BIP65 Example #3 2FA Normal",         # Two-factor: User + Service
        16: "BIP65 Example #3 2FA Recovery",       # Two-factor: User + Recovery after timeout
        17: "BIP65 Example #4 Channel Cooperative",# Payment Channel: Cooperative close
        18: "BIP65 Example #4 Channel Refund",     # Payment Channel: Refund after timeout
        19: "BIP65 Example #5 PayPub Publisher",   # Data Publishing: Publisher reveals
        20: "BIP65 Example #5 PayPub Buyer",       # Data Publishing: Buyer refund
    }
    label = labels.get(test_number, f"BIP65 Test #{test_number}")
    return label.encode('utf-8').hex()


def get_default_address() -> str:
    """
    Get a valid default sweep destination address from Electrum wallet.
    
    Tries, in order:
    - getunusedaddress (preferred, stable across Electrum versions)
    - createnewaddress (fallback)
    - getnewaddress (legacy alias)
    
    Returns:
        Bitcoin address string (testnet/signet format)
    
    Raises:
        RuntimeError: If Electrum CLI is not available or all commands fail
    
    Notes:
        - Uses sweep_utils.get_default_destination() for actual implementation
        - Imports at call time to avoid circular dependencies
    """
    # Import here to avoid circular dependency
    from sweep_utils import get_default_destination
    return get_default_destination()


def get_sweep_destination(test_data: Dict) -> Union[Tuple[str, str], str]:
    """
    Get the appropriate sweep destination for a test.
    
    Decides between OP_RETURN and regular address based on test amount
    and environment configuration. This is the main entry point for
    determining sweep destinations.
    
    Args:
        test_data: Test state dictionary with amount_sats/amount and test_number
    
    Returns:
        Either:
        - Tuple ('op_return', hex_data) for OP_RETURN outputs
        - String address for regular outputs
    
    Examples:
        >>> get_sweep_destination({'test_number': 1, 'amount_sats': 501})
        ('op_return', '42495036...')  # OP_RETURN for small amount
        
        >>> get_sweep_destination({'test_number': 1, 'amount_sats': 10000})
        'tb1q...'  # Regular address for larger amount
    
    Notes:
        - Uses OP_RETURN for amounts < OP_RETURN_THRESHOLD (default 800 sats)
        - Falls back to dynamic wallet address for larger amounts
        - Respects E2E_FORCE_OP_RETURN and E2E_DISABLE_OP_RETURN env vars
    """
    if use_op_return_for(test_data):
        test_number = test_data.get('test_number', 0)
        op_return_hex = get_op_return_label(test_number)
        return ('op_return', op_return_hex)
    else:
        return get_default_address()


def format_destination_for_display(destination: Union[Tuple[str, str], str]) -> str:
    """
    Format a destination for human-readable display in logs.
    
    Args:
        destination: Either ('op_return', hex_data) or an address string
    
    Returns:
        Human-readable destination string
    
    Examples:
        >>> format_destination_for_display(('op_return', '42495036...'))
        'OP_RETURN [BIP65 Example #1 Freezing]'
        
        >>> format_destination_for_display('tb1q...')
        'tb1q...'
    """
    if isinstance(destination, tuple) and len(destination) == 2 and destination[0] == 'op_return':
        op_return_hex = destination[1]
        try:
            label = bytes.fromhex(op_return_hex).decode('utf-8', errors='ignore')
            return f"OP_RETURN [{label}]"
        except Exception:
            return f"OP_RETURN [{op_return_hex[:32]}...]"
    else:
        return str(destination)


__all__ = [
    'get_sweep_destination',
    'format_destination_for_display',
    'use_op_return_for',
    'get_op_return_label',
    'get_default_address',
    'OP_RETURN_THRESHOLD'
]
