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
from electrum.util import bfh


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
        raise ValueError('Taproot creation not supported through _wrap_address. Use taproot module directly or handle taproot in the calling function.')
        
    else:
        raise ValueError(f'Unknown output type: {output_type}. Use "p2sh" or "taproot".')


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
            # Use taproot module directly for taproot addresses
            import taproot
            result = taproot.create_taproot_cltv_output(locktime, pubkey)
            # Add output_type to result
            if not result.get('error'):
                result['output_type'] = 'taproot'
                result['locktime'] = locktime
            return result
        else:
            # P2SH path
            pubkey_bytes = bfh(pubkey)
            
            # Build the script directly
            script = construct_script([
                locktime,                    # Push locktime value
                opcodes.OP_CHECKLOCKTIMEVERIFY,  # Check locktime
                opcodes.OP_DROP,            # Drop locktime from stack
                pubkey_bytes,               # Push pubkey
                opcodes.OP_CHECKSIG         # Check signature
            ])
            
            script_hex = script.hex()
            
            # Create P2SH address
            script_hash = hash_160(script)
            address = hash160_to_p2sh(script_hash, net=constants.net)
            
            return {
                'address': address,
                'script_hex': script_hex,
                'locktime': locktime,
                'output_type': 'p2sh',
                'error': None
            }
        
    except ValueError as e:
        return {'error': str(e), 'address': None, 'script_hex': None}
    except Exception as e:
        return {
            'error': str(e),
            'address': None,
            'script_hex': None
        }


def create_escrow_address(
    locktime: int,
    alice_pubkey: str,
    bob_pubkey: str,
    arbiter_pubkey: str,
    output_type: str = 'p2sh'
) -> Dict[str, Any]:
    """
    Create an escrow address with timeout arbitration.
    
    Two spending paths:
    1. Normal: Alice + Bob (2-of-2 multisig)
    2. Timeout: After locktime, Arbiter + (Alice OR Bob)
    
    Script:
        OP_IF
            2 <alice> <bob> 2 OP_CHECKMULTISIG
        OP_ELSE
            <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP
            2 <alice> <bob> <arbiter> 3 OP_CHECKMULTISIG
        OP_ENDIF
    
    Args:
        locktime: Timeout block height or timestamp
        alice_pubkey: Alice's public key (party 1)
        bob_pubkey: Bob's public key (party 2)
        arbiter_pubkey: Arbiter's public key (Lenny)
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        dict with 'address', 'script_hex', 'error' keys
    """
    try:
        # Convert pubkeys to bytes
        alice_bytes = bfh(alice_pubkey)
        bob_bytes = bfh(bob_pubkey)
        arbiter_bytes = bfh(arbiter_pubkey)
        
        # Build the escrow script directly
        script = construct_script([
            opcodes.OP_IF,
                # Path 1: Normal 2-of-2 multisig (Alice + Bob)
                2,
                alice_bytes,
                bob_bytes,
                2,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ELSE,
                # Path 2: After timeout, 2-of-3 with arbiter
                locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                2,
                alice_bytes,
                bob_bytes,
                arbiter_bytes,
                3,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ENDIF
        ])
        
        script_hex = script.hex()
        
        # Wrap in P2SH or Taproot using DRY helper
        address, extra = _wrap_address(script, output_type)
        
        return {
            'address': address,
            'script_hex': script_hex,
            'locktime': locktime,
            'output_type': output_type,
            'error': None
        }
        
    except ValueError as e:
        return {'error': str(e), 'address': None, 'script_hex': None}
    except Exception as e:
        return {
            'error': str(e),
            'address': None,
            'script_hex': None
        }


def create_twofactor_address(
    locktime: int,
    user_pubkey: str,
    service_pubkey: str,
    recovery_pubkey: str,
    output_type: str = 'p2sh'
) -> Dict[str, Any]:
    """
    Create a two-factor wallet address with recovery timeout.
    
    Two spending paths:
    1. Normal: User + Service (2-of-2)
    2. Recovery: After locktime, User + Recovery (2-of-2)
    
    Args:
        locktime: Recovery timeout
        user_pubkey: User's key
        service_pubkey: 2FA service key
        recovery_pubkey: Recovery key
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        dict with 'address', 'script_hex', 'error' keys
    """
    try:
        user_bytes = bfh(user_pubkey)
        service_bytes = bfh(service_pubkey)
        recovery_bytes = bfh(recovery_pubkey)
        
        script = construct_script([
            opcodes.OP_IF,
                # Normal path: User + Service
                2,
                user_bytes,
                service_bytes,
                2,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ELSE,
                # Recovery path after timeout
                locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                2,
                user_bytes,
                recovery_bytes,
                2,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ENDIF
        ])
        
        script_hex = script.hex()
        
        # Wrap in P2SH or Taproot using DRY helper
        address, extra = _wrap_address(script, output_type)
        
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


def create_payment_channel_address(
    locktime: int,
    sender_pubkey: str,
    receiver_pubkey: str,
    output_type: str = 'p2sh'
) -> Dict[str, Any]:
    """
    Create a payment channel address with refund timeout.
    
    Two spending paths:
    1. Cooperative: Sender + Receiver (2-of-2 multisig)
    2. Refund: After locktime, Sender reclaims funds
    
    Script:
        OP_IF
            2 <sender_pubkey> <receiver_pubkey> 2 OP_CHECKMULTISIG
        OP_ELSE
            <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP
            <sender_pubkey> OP_CHECKSIG
        OP_ENDIF
    
    Args:
        locktime: Refund timeout
        sender_pubkey: Sender's public key (can refund after timeout)
        receiver_pubkey: Receiver's public key
        output_type: 'p2sh' or 'taproot'
        
    Returns:
        dict with 'address', 'script_hex', 'error' keys
    """
    try:
        sender_bytes = bfh(sender_pubkey)
        receiver_bytes = bfh(receiver_pubkey)
        
        script = construct_script([
            opcodes.OP_IF,
                # Cooperative path: Sender + Receiver multisig
                2,
                sender_bytes,
                receiver_bytes,
                2,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ELSE,
                # Refund path: Sender only, after timeout
                locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                sender_bytes,
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
                raise ValueError(f"Taproot address generation failed: {result['error']}")
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
        # Validate and convert data hash
        if len(data_hash) != 64:  # 32 bytes = 64 hex chars
            raise ValueError(f"Data hash must be 32 bytes (64 hex chars), got {len(data_hash)}")
        
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
                raise ValueError(f"Taproot address generation failed: {result['error']}")
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
