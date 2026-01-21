"""
Direct Address Generation Helpers - "The Electrum Way"

Simple, direct functions for creating CLTV addresses.
No factories, no builders, no over-engineering.

Philosophy:
- Direct and readable
- Easy to debug
- Follows Electrum patterns
- Minimal abstraction
"""

from typing import Dict, Any, Optional, Tuple
from electrum.bitcoin import hash_160, hash160_to_p2sh, construct_script
from electrum.transaction import opcodes
from electrum import constants
from electrum.util import bfh, BitcoinException, is_hex_str


def _wrap_address(script: bytes, output_type: str) -> Tuple[str, dict]:
    """
    Wrap script in P2SH or Taproot output.
    
    DRY helper to avoid repeating this logic in every address creation function.
    
    Args:
        script: Raw script bytes
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        Tuple of (address, extra_data_dict)
        - address: The encoded address string
        - extra_data: Additional data (e.g., taproot control block)
        
    Raises:
        ValueError: If output_type is unknown
    """
    if output_type == 'p2sh':
        script_hash = hash_160(script)
        address = hash160_to_p2sh(script_hash, net=constants.net)
        return address, {}
        
    elif output_type == 'taproot':
        # Taproot creation requires direct use of taproot module
        # This function is for P2SH wrapping only
        raise BitcoinException('Taproot creation not supported through _wrap_address. Use taproot module directly or handle taproot in the calling function.')
        
    else:
        raise BitcoinException(f'Unknown output type: {output_type}. Use "p2sh" or "taproot".')


def create_simple_timelock_address(
    locktime: int,
    pubkey: str,
    output_type: str = 'p2sh'
) -> Dict[str, Any]:
    """
    Create a simple timelock address (BIP-65 "Freezing Funds").
    
    Script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG
    
    Args:
        locktime: Block height or Unix timestamp
        pubkey: Public key hex string
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        dict with 'address', 'script_hex', 'control_block' (taproot), 'error' keys
        
    Example:
        >>> result = create_simple_timelock_address(
        ...     locktime=700000,
        ...     pubkey='02...',
        ...     output_type='p2sh'
        ... )
        >>> print(result['address'])
    """
    try:
if output_type == 'taproot':
            # Use taproot module for Taproot creation
            from .taproot import create_taproot_from_script
            result = create_taproot_from_script(script, internal_pubkey=pubkey_bytes)
            if result.get('error'):
                raise BitcoinException(f"Taproot address generation failed: {result['error']}")
            address = result['address']
        else:
            # P2SH path
            script_hash = hash_160(script)
            address = hash160_to_p2sh(script_hash, net=constants.net)
        
        return {
            'address': address,
            'script_hex': script_hex,
            'locktime': locktime,
            'output_type': output_type,
            'error': None
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'address': None,
            'script_hex': None
        }


def create_data_publishing_address(
    locktime: int,
    data_hash: str,
    publisher_pubkey: str,
    buyer_pubkey: str,
    output_type: str = 'p2sh'
) -> Dict[str, Any]:
    """
    Create a data publishing contract address.
    
    Two spending paths:
    1. Publisher claims: Reveals data preimage + signature
    2. Buyer refunds: After locktime, if data not delivered
    
    Script:
        OP_IF
            OP_SHA256 <data_hash> OP_EQUALVERIFY <publisher_pubkey> OP_CHECKSIG
        OP_ELSE
            <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <buyer_pubkey> OP_CHECKSIG
        OP_ENDIF
    
    Args:
        locktime: Refund timeout
        data_hash: SHA256 hash of the data (32 bytes hex)
        publisher_pubkey: Publisher's public key
        buyer_pubkey: Buyer's public key (can refund after timeout)
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        dict with 'address', 'script_hex', 'error' keys
    """
    try:
        if not is_hex_str(data_hash) or len(data_hash) != 64:
            raise BitcoinException(f"Data hash must be 32 bytes (64 hex chars), got {len(data_hash)}")
        
        data_hash_bytes = bfh(data_hash)
        publisher_bytes = bfh(publisher_pubkey)
        buyer_bytes = bfh(buyer_pubkey)
        
        script = construct_script([
            opcodes.OP_IF,
                # Publisher path: Reveal data preimage
                opcodes.OP_SHA256,
                data_hash_bytes,
                opcodes.OP_EQUALVERIFY,
                publisher_bytes,
                opcodes.OP_CHECKSIG,
            opcodes.OP_ELSE,
                # Buyer refund path: After timeout
                locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                buyer_bytes,
                opcodes.OP_CHECKSIG,
            opcodes.OP_ENDIF
        ])
        
        script_hex = script.hex()
        
        # Handle Taproot vs P2SH
        if output_type == 'taproot':
            # Use taproot module directly for complex scripts
            import taproot
            # Pass the raw script bytes to create taproot address
            result = taproot.create_taproot_from_script(script)
            if result.get('error'):
                raise BitcoinException(f"Taproot address generation failed: {result['error']}")
            address = result['address']
        else:
            # P2SH path
            script_hash = hash_160(script)
            address = hash160_to_p2sh(script_hash, net=constants.net)
        
        return {
            'address': address,
            'script_hex': script_hex,
            'data_hash': data_hash,
            'locktime': locktime,
            'output_type': output_type,
            'error': None
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'address': None,
            'script_hex': None
        }


def create_miner_sacrifice_script(
    locktime: int,
    output_type: str = 'bare'
) -> Dict[str, Any]:
    """
    Create a miner sacrifice script - funds are PERMANENTLY UNRECOVERABLE!
    
    After locktime expires, ANYONE can spend these coins (typically miners).
    
    Script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP OP_TRUE
    
    This is used for:
    - Provable economic commitment
    - Timestamping services
    - Spam prevention
    
    WARNING: Use TESTNET/SIGNET only! Funds are permanently lost!
    
    Args:
        locktime: Time after which coins can be claimed by anyone
        output_type: 'bare' (raw script), 'p2sh', or 'taproot'
        
    Returns:
        dict with 'address' (or None for bare), 'script_hex', 'error' keys
    """
    try:
        # Build the sacrifice script
        script = construct_script([
            locktime,                       # Push locktime value
            opcodes.OP_CHECKLOCKTIMEVERIFY, # Check locktime
            opcodes.OP_DROP,               # Drop locktime from stack
            opcodes.OP_TRUE                # Always succeeds (anyone can spend!)
        ])
        
        script_hex = script.hex()
        
        # Handle output type
        if output_type == 'bare':
            # Bare script - no address, just the raw script
            return {
                'address': None,
                'script_hex': script_hex,
                'output_type': output_type,
                'locktime': locktime,
                'warning': 'BARE SCRIPT: Funds are PERMANENTLY UNRECOVERABLE after locktime!',
                'error': None
            }
        else:
            # Wrap in P2SH or Taproot (safer, standard relay)
            address, extra = _wrap_address(script, output_type)
            
            return {
                'address': address,
                'script_hex': script_hex,
                'output_type': output_type,
                'locktime': locktime,
                'warning': 'SACRIFICE ADDRESS: Funds are PERMANENTLY UNRECOVERABLE after locktime!',
                'error': None
            }
        
    except Exception as e:
        return {
            'error': str(e),
            'address': None,
            'script_hex': None
        }
