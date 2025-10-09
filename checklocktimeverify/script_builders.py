"""
Script Builder Strategies for BIP-65 CHECKLOCKTIMEVERIFY Examples

This module provides a DRY architecture for building CLTV scripts.
Each example (Freezing Funds, Escrow, etc.) is a ScriptBuilder subclass.

Architecture:
- ScriptBuilder (ABC): Base class defining the interface
- Concrete builders: One per BIP-65 example
- AddressFactory: Uses builders to create P2SH or Taproot addresses

Benefits:
- Single source of truth for each script type
- Easy to add new examples (just subclass)
- Taproot support added once, works for all builders
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List
from electrum.bitcoin import opcodes, construct_script


@dataclass
class ScriptInputs:
    """Common inputs for all script types"""
    locktime: int
    locktime_type: str  # "block" or "timestamp"
    locktime_display: str
    output_type: str = "p2sh"  # "p2sh" or "taproot"


class ScriptBuilder(ABC):
    """
    Base class for all CLTV script builders.
    
    Each BIP-65 example subclasses this and implements:
    - get_input_spec(): What inputs are needed
    - build_script(): How to construct the script
    - get_metadata(): Metadata for storage
    - get_description(): User-facing description
    - get_bip65_quote(): Relevant BIP-65 quote
    """
    
    @abstractmethod
    def get_input_spec(self) -> Dict[str, type]:
        """
        Define what inputs this script needs.
        
        Returns:
            Dict mapping input name to expected type
            Example: {'pubkey': bytes, 'hash': bytes}
        """
        pass
    
    @abstractmethod
    def build_script(self, common: ScriptInputs, **kwargs) -> bytes:
        """
        Build the script bytes.
        
        Args:
            common: Common inputs (locktime, etc.)
            **kwargs: Type-specific inputs (pubkeys, hashes, etc.)
        
        Returns:
            Script bytes
        """
        pass
    
    @abstractmethod
    def get_metadata(self, common: ScriptInputs, **kwargs) -> Dict[str, Any]:
        """
        Get metadata for storage.
        
        Returns:
            Dict with type-specific metadata
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get human-readable description for UI"""
        pass
    
    @abstractmethod
    def get_bip65_quote(self) -> str:
        """Get relevant BIP-65 quote for educational display"""
        pass
    
    def get_script_type(self) -> str:
        """
        Get script type identifier.
        
        Default implementation uses class name.
        Override if you want custom identifier.
        """
        return self.__class__.__name__.replace('Builder', '').lower()
    
    # Common helper methods
    
    def build_simple_cltv(self, locktime: int, pubkey: bytes) -> bytes:
        """
        Standard CLTV pattern: <locktime> CLTV DROP <pubkey> CHECKSIG
        
        This is the most common pattern used in BIP-65 examples.
        """
        return construct_script([
            locktime,
            opcodes.OP_CHECKLOCKTIMEVERIFY,
            opcodes.OP_DROP,
            pubkey,
            opcodes.OP_CHECKSIG
        ])


class FreezingFundsBuilder(ScriptBuilder):
    """
    Freezing Funds - Simple timelock
    
    Script: <locktime> CLTV DROP <pubkey> CHECKSIG
    
    Use case: Lock coins until specific block/time
    """
    
    def get_input_spec(self) -> Dict[str, type]:
        return {'pubkey': bytes}
    
    def build_script(self, common: ScriptInputs, pubkey: bytes) -> bytes:
        return self.build_simple_cltv(common.locktime, pubkey)
    
    def get_metadata(self, common: ScriptInputs, pubkey: bytes) -> Dict[str, Any]:
        return {
            'locktime': common.locktime,
            'locktime_type': common.locktime_type,
            'locktime_display': common.locktime_display,
            'pubkey': pubkey.hex(),
            'script_type': 'freezing_funds'
        }
    
    def get_description(self) -> str:
        return """🔒 Freezing Funds (BIP-65 Motivation)

Funds can be frozen in UTXOs directly on the blockchain.
Nobody will be able to spend the encumbered output until the provided expiry time.

Script: <expiry time> CHECKLOCKTIMEVERIFY DROP DUP HASH160 <pubKeyHash> EQUALVERIFY CHECKSIG
(This plugin uses simplified form: <expiry time> CLTV DROP <pubkey> CHECKSIG)"""
    
    def get_bip65_quote(self) -> str:
        return """From BIP-65:
  'In addition to using cold storage, hardware wallets, and P2SH multisig
   outputs to control funds, now funds can be frozen in UTXOs directly on
   the blockchain. With the following scriptPubKey, nobody will be able to
   spend the encumbered output until the provided expiry time.'"""


class EscrowBuilder(ScriptBuilder):
    """
    Escrow - 2-of-3 multisig with timeout
    
    Script: IF <locktime> CLTV DROP <agent> CHECKSIGVERIFY 1
            ELSE 2 ENDIF
            <pubkey1> <pubkey2> 2 CHECKMULTISIG
    
    Use case: Two parties + arbiter, arbiter can intervene after timeout
    """
    
    def get_input_spec(self) -> Dict[str, type]:
        return {
            'pubkey1': bytes,
            'pubkey2': bytes,
            'pubkey_agent': bytes
        }
    
    def build_script(self, common: ScriptInputs, **kwargs) -> bytes:
        return construct_script([
            opcodes.OP_IF,
                common.locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                kwargs['pubkey_agent'],
                opcodes.OP_CHECKSIGVERIFY,
                1,
            opcodes.OP_ELSE,
                2,
            opcodes.OP_ENDIF,
            kwargs['pubkey1'],
            kwargs['pubkey2'],
            2,
            opcodes.OP_CHECKMULTISIG
        ])
    
    def get_metadata(self, common: ScriptInputs, **kwargs) -> Dict[str, Any]:
        return {
            'locktime': common.locktime,
            'locktime_type': common.locktime_type,
            'locktime_display': common.locktime_display,
            'pubkey1': kwargs['pubkey1'].hex(),
            'pubkey2': kwargs['pubkey2'].hex(),
            'pubkey_agent': kwargs['pubkey_agent'].hex(),
            'script_type': 'escrow'
        }
    
    def get_description(self) -> str:
        return """🤝 Escrow (BIP-65 Example)

If Alice and Bob jointly operate a business, they may want to ensure that all
funds are kept in 2-of-2 multisig outputs. However, they need a backup plan.
They appoint their lawyer, Lenny, to act as a third-party.

At any time: Alice + Bob can spend (2-of-2)
After timeout: Lenny + either Alice or Bob (2-of-3 with third-party)"""
    
    def get_bip65_quote(self) -> str:
        return """From BIP-65 Escrow:
  'With a standard 2-of-3 CHECKMULTISIG at any time Lenny could conspire with
   either Alice or Bob to steal the funds illegitimately. However, with
   CHECKLOCKTIMEVERIFY the funds can be stored in scriptPubKeys such that
   at any time the funds can be spent with Alice + Bob, but after the timeout
   Lenny and one of either Alice or Bob can spend the funds.'"""


class TwoFactorBuilder(ScriptBuilder):
    """
    Two-Factor Wallets (Non-interactive Time-locked Refunds)
    
    Paths:
    1. User + service (immediate)
    2. User + recovery key (after timeout)
    
    Use case: Services like GreenAddress with two-factor authentication.
              User can recover funds if service becomes unavailable.
    """
    
    def get_input_spec(self) -> Dict[str, type]:
        return {
            'user_pubkey': bytes,
            'service_pubkey': bytes,
            'recovery_pubkey': bytes
        }
    
    def build_script(self, common: ScriptInputs, **kwargs) -> bytes:
        return construct_script([
            opcodes.OP_IF,
                # Normal path: user + service
                kwargs['user_pubkey'],
                opcodes.OP_CHECKSIGVERIFY,
                kwargs['service_pubkey'],
                opcodes.OP_CHECKSIG,
            opcodes.OP_ELSE,
                # Recovery path: user + recovery (after expiry time)
                common.locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                kwargs['user_pubkey'],
                opcodes.OP_CHECKSIGVERIFY,
                kwargs['recovery_pubkey'],
                opcodes.OP_CHECKSIG,
            opcodes.OP_ENDIF
        ])
    
    def get_metadata(self, common: ScriptInputs, **kwargs) -> Dict[str, Any]:
        return {
            'locktime': common.locktime,
            'locktime_type': common.locktime_type,
            'locktime_display': common.locktime_display,
            'user_pubkey': kwargs['user_pubkey'].hex(),
            'service_pubkey': kwargs['service_pubkey'].hex(),
            'recovery_pubkey': kwargs['recovery_pubkey'].hex(),
            'script_type': 'twofactor'
        }
    
    def get_description(self) -> str:
        return """🔐 Two-Factor Wallets (BIP-65: Non-interactive Time-locked Refunds)

Services like GreenAddress store bitcoins with 2-of-2 multisig scriptPubKeys
where one keypair is controlled by the user, and the other by the service.

Normal spending: User + service (both signatures required)
Recovery path: If service is not available, user waits until nLockTime expires

The user is always able to spend their funds without the co-operation of the
service by waiting for the expiry time to be reached."""
    
    def get_bip65_quote(self) -> str:
        return """From BIP-65 Two-factor Wallets:
  'With CHECKLOCKTIMEVERIFY rather than creating refund signatures on demand,
   scriptPubKeys are used such that the user is always able to spend their
   funds without the co-operation of the service by waiting for the expiry
   time to be reached.'"""


class PaymentChannelBuilder(ScriptBuilder):
    """
    Payment Channel (Refundable Payments)
    
    Paths:
    1. Receiver + sender signature (immediate)
    2. Sender refund (after timeout)
    
    Use case: Off-chain payments with refund guarantee
    """
    
    def get_input_spec(self) -> Dict[str, type]:
        return {
            'sender_pubkey': bytes,
            'receiver_pubkey': bytes
        }
    
    def build_script(self, common: ScriptInputs, **kwargs) -> bytes:
        return construct_script([
            opcodes.OP_IF,
                # Receiver path (with sender signature)
                2,
                kwargs['sender_pubkey'],
                kwargs['receiver_pubkey'],
                2,
                opcodes.OP_CHECKMULTISIG,
            opcodes.OP_ELSE,
                # Sender refund path (after timeout)
                common.locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                kwargs['sender_pubkey'],
                opcodes.OP_CHECKSIG,
            opcodes.OP_ENDIF
        ])
    
    def get_metadata(self, common: ScriptInputs, **kwargs) -> Dict[str, Any]:
        return {
            'locktime': common.locktime,
            'locktime_type': common.locktime_type,
            'locktime_display': common.locktime_display,
            'sender_pubkey': kwargs['sender_pubkey'].hex(),
            'receiver_pubkey': kwargs['receiver_pubkey'].hex(),
            'script_type': 'payment_channel'
        }
    
    def get_description(self) -> str:
        return """💳 Payment Channels (BIP-65: Non-interactive Time-locked Refunds)

Jeremy Spilman style payment channels first setup a deposit controlled by
2-of-2 multisig, tx1, and then adjust a second transaction, tx2, that spends
the output of tx1 to payor and payee.

Prior to publishing tx1, a refund transaction tx3 is created to ensure that
should the payee vanish, the payor can get their deposit back. CHECKLOCKTIMEVERIFY
solves transaction malleability attacks and removes the need to store refund sigs."""
    
    def get_bip65_quote(self) -> str:
        return """From BIP-65 Payment Channels:
  'The process by which the refund transaction is created is currently
   vulnerable to transaction malleability attacks, and additionally, requires
   the payor to store the refund. Using CHECKLOCKTIMEVERIFY solves both these
   issues.'"""


class DataPublishingBuilder(ScriptBuilder):
    """
    Trustless Payments for Publishing Data
    
    Paths:
    1. Publisher reveals preimage (immediate)
    2. Buyer refund (after timeout)
    
    Use case: Pay for data revelation, refund if not published
    """
    
    def get_input_spec(self) -> Dict[str, type]:
        return {
            'publisher_pubkey': bytes,
            'buyer_pubkey': bytes,
            'data_hash': bytes  # HASH160 of the data
        }
    
    def build_script(self, common: ScriptInputs, **kwargs) -> bytes:
        return construct_script([
            opcodes.OP_IF,
                # Publisher path (reveals preimage)
                opcodes.OP_HASH160,
                kwargs['data_hash'],
                opcodes.OP_EQUALVERIFY,
                kwargs['publisher_pubkey'],
                opcodes.OP_CHECKSIG,
            opcodes.OP_ELSE,
                # Buyer refund path (after timeout)
                common.locktime,
                opcodes.OP_CHECKLOCKTIMEVERIFY,
                opcodes.OP_DROP,
                kwargs['buyer_pubkey'],
                opcodes.OP_CHECKSIG,
            opcodes.OP_ENDIF
        ])
    
    def get_metadata(self, common: ScriptInputs, **kwargs) -> Dict[str, Any]:
        return {
            'locktime': common.locktime,
            'locktime_type': common.locktime_type,
            'locktime_display': common.locktime_display,
            'publisher_pubkey': kwargs['publisher_pubkey'].hex(),
            'buyer_pubkey': kwargs['buyer_pubkey'].hex(),
            'data_hash': kwargs['data_hash'].hex(),
            'script_type': 'data_publishing'
        }
    
    def get_description(self) -> str:
        return """📄 Trustless Payments for Publishing Data (BIP-65 PayPub Protocol)

The PayPub protocol makes it possible to pay for information in a trustless way
by first proving that an encrypted file contains the desired data, and secondly
crafting scriptPubKeys used for payment such that spending them reveals the
encryption keys to the data.

Publisher path: Reveals encryption key (hash preimage) to claim payment
Buyer refund path: If publisher fails to accept offer before expiry, buyer can cancel

The buyer is making a secure offer with an expiry time."""
    
    def get_bip65_quote(self) -> str:
        return """From BIP-65 Trustless Payments for Publishing Data:
  'The PayPub protocol makes it possible to pay for information in a trustless
   way. However the existing implementation has a significant flaw: the publisher
   can delay the release of the keys indefinitely. This problem can be
   non-interactively solved using CHECKLOCKTIMEVERIFY with the buyer making a
   secure offer with an expiry time.'"""


# Registry of all builders for easy access
SCRIPT_BUILDERS = {
    'freezing_funds': FreezingFundsBuilder(),
    'escrow': EscrowBuilder(),
    'twofactor': TwoFactorBuilder(),
    'payment_channel': PaymentChannelBuilder(),
    'data_publishing': DataPublishingBuilder()
}


def get_builder(script_type: str) -> ScriptBuilder:
    """
    Get builder by script type.
    
    Args:
        script_type: One of: freezing_funds, escrow, twofactor, 
                     payment_channel, data_publishing
    
    Returns:
        ScriptBuilder instance
    
    Raises:
        ValueError: If script_type not recognized
    """
    if script_type not in SCRIPT_BUILDERS:
        raise ValueError(f"Unknown script type: {script_type}. "
                        f"Available: {list(SCRIPT_BUILDERS.keys())}")
    return SCRIPT_BUILDERS[script_type]
