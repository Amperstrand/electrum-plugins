"""
Dedicated sweeper for BIP-65 Escrow example.

This is a standalone implementation focused on getting the escrow example working.
No inheritance, no shared logic - just what's needed for escrow.

Once this works, we can refactor and extract common patterns.
"""

from typing import Dict, List, Optional
from electrum.transaction import Transaction
from electrum.bitcoin import construct_witness
from electrum_ecc import ECPrivkey


class EscrowDedicatedSweeper:
    """
    Dedicated sweeper for BIP-65 Escrow with timeout.
    
    Script (from BIP-65):
        IF
            <now + 3 months> CHECKLOCKTIMEVERIFY DROP
            <Lenny's pubkey> CHECKSIGVERIFY
            1
        ELSE
            2
        ENDIF
        <Alice's pubkey> <Bob's pubkey> 2 CHECKMULTISIG
    
    Two spending paths:
    1. Normal operations (ELSE): Alice + Bob sign anytime
    2. Arbitration (IF): Lenny + one of (Alice OR Bob) sign after timeout
    """
    
    def __init__(self, use_refund_path: bool = False, **kwargs):
        """
        Initialize escrow sweeper.
        
        Args:
            use_refund_path: If True, use arbitration path (Lenny + co-signer)
                           If False, use normal operations path (Alice + Bob)
            **kwargs: Additional parameters (ignored for compatibility)
        """
        # Map use_refund_path to use_arbitration_path for internal logic
        self.use_arbitration_path = use_refund_path
        self.arbitration_co_signer = kwargs.get('refund_signer', 'alice')
    
    def build_witness(
        self,
        output: Dict,
        keys: Dict[str, ECPrivkey],
        sighash: bytes
    ) -> List:
        """
        Build witness for escrow spending.
        
        Args:
            output: Output data including script
            keys: Dictionary of private keys
            sighash: Pre-calculated sighash to sign
            
        Returns:
            List of witness items
        """
        script_hex = output.get('script_hex')
        if not script_hex:
            raise ValueError("No script_hex in output")
        
        script = bytes.fromhex(script_hex)
        
        if self.use_arbitration_path:
            # Arbitration path: Lenny + one of (Alice OR Bob) after timeout
            return self._build_arbitration_witness(sighash, script, keys)
        else:
            # Normal operations: Alice + Bob anytime
            return self._build_normal_witness(sighash, script, keys)
    
    def _calculate_sighash(
        self,
        tx: Transaction,
        input_index: int,
        script: bytes,
        amount: int
    ) -> bytes:
        """Calculate sighash for P2WSH input."""
        from electrum.transaction import Transaction
        
        # For P2WSH, use BIP143 sighash calculation
        # SIGHASH_ALL = 1
        sighash_type = 1
        
        # Get the sighash
        # tx.serialize_preimage uses BIP143 for segwit
        preimage = tx.serialize_preimage(input_index, script, amount, sighash_type)
        
        import hashlib
        sighash = hashlib.sha256(hashlib.sha256(preimage).digest()).digest()
        
        return sighash
    
    def _build_normal_witness(
        self,
        sighash: bytes,
        script: bytes,
        keys: Dict[str, ECPrivkey]
    ) -> List:
        """
        Build witness for normal operations path (ELSE branch).
        
        BIP-65 ScriptSig: 0 <Alice's signature> <Bob's signature> 0
        P2WSH Witness: [0, alice_sig, bob_sig, 0, script]
        """
        alice_key = keys.get('alice_key')
        bob_key = keys.get('bob_key')
        
        if not alice_key or not bob_key:
            raise ValueError("alice_key and bob_key required for normal operations")
        
        # Sign with both keys (ECDSA for P2WSH)
        alice_sig = self._sign_ecdsa(alice_key, sighash)
        bob_sig = self._sign_ecdsa(bob_key, sighash)
        
        # Witness order from BIP-65
        witness = [
            0,          # CHECKMULTISIG bug workaround
            alice_sig,  # Alice's signature (first)
            bob_sig,    # Bob's signature (second)
            0,          # False - triggers ELSE branch
            script      # The witness script
        ]
        
        return witness
    
    def _build_arbitration_witness(
        self,
        sighash: bytes,
        script: bytes,
        keys: Dict[str, ECPrivkey]
    ) -> List:
        """
        Build witness for arbitration path (IF branch).
        
        BIP-65 ScriptSig: 0 <Alice/Bob's signature> <Lenny's signature> 1
        P2WSH Witness: [0, alice_or_bob_sig, lenny_sig, 1, script]
        """
        lenny_key = keys.get('lenny_key')
        co_signer_key = keys.get(f'{self.arbitration_co_signer}_key')
        
        if not lenny_key or not co_signer_key:
            raise ValueError(f"lenny_key and {self.arbitration_co_signer}_key required for arbitration")
        
        # Sign with both keys (ECDSA for P2WSH)
        co_signer_sig = self._sign_ecdsa(co_signer_key, sighash)
        lenny_sig = self._sign_ecdsa(lenny_key, sighash)
        
        # Witness order from BIP-65
        witness = [
            0,              # CHECKMULTISIG bug workaround
            co_signer_sig,  # Alice or Bob's signature (first)
            lenny_sig,      # Lenny's signature (second)
            1,              # True - triggers IF branch
            script          # The witness script
        ]
        
        return witness
    
    def _sign_ecdsa(self, privkey: ECPrivkey, sighash: bytes) -> bytes:
        """
        Sign sighash with ECDSA and return DER signature + SIGHASH_ALL.
        
        Args:
            privkey: ECPrivkey object
            sighash: 32-byte hash to sign
            
        Returns:
            DER signature + SIGHASH_ALL byte
        """
        # Sign the sighash (returns 64-byte compact signature)
        sig_compact = privkey.ecdsa_sign(sighash)
        
        # Convert to DER format
        from electrum_ecc import ecdsa_der_sig_from_ecdsa_sig64
        sig_der = ecdsa_der_sig_from_ecdsa_sig64(sig_compact)
        
        # Append SIGHASH_ALL (0x01)
        return sig_der + b'\x01'
    
    def get_required_keys(self, output: Optional[Dict] = None) -> List[str]:
        """
        Return list of required key names for this spending path.
        
        Args:
            output: Output data (not used, but included for compatibility)
            
        Returns:
            List of key names (e.g., ['alice_key', 'bob_key'])
        """
        if self.use_arbitration_path:
            return ['lenny_key', f'{self.arbitration_co_signer}_key']
        else:
            return ['alice_key', 'bob_key']
    
    def validate_sweep_conditions(
        self,
        output: Dict,
        current_height: int,
        raise_if_locked: bool = False
    ) -> bool:
        """
        Validate that conditions are met for spending.
        
        Args:
            output: Output data
            current_height: Current blockchain height
            raise_if_locked: If True, raise LockedError instead of returning False
            
        Returns:
            True if can sweep, False otherwise
            
        Raises:
            LockedError: If raise_if_locked=True and conditions not met
        """
        locktime = output.get('locktime', 0)
        
        if self.use_arbitration_path:
            # Arbitration requires locktime to have passed
            if current_height < locktime:
                blocks_remaining = locktime - current_height
                error_msg = f"Locktime not reached. Need {blocks_remaining} more blocks."
                if raise_if_locked:
                    from sweepers.base import LockedError
                    raise LockedError(error_msg)
                return False
        
        # Normal operations can spend anytime
        return True

