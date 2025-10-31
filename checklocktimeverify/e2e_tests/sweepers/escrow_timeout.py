"""
Escrow Sweeper - BIP-65 Example #1

Handles spending from BIP-65 escrow scripts with CHECKMULTISIG.

BIP-65 Escrow: Three-party arbitration with locktime protection.

Script structure:
    OP_IF
        <locktime> OP_CLTV OP_DROP
        <lenny_pubkey> OP_CHECKSIGVERIFY
        OP_1
    OP_ELSE
        OP_2
    OP_ENDIF
    <alice_pubkey> <bob_pubkey> OP_2 OP_CHECKMULTISIG

Spend paths:
1. Normal Operations (ELSE, anytime): Alice AND Bob (2-of-2 multisig)
   - Witness: [0, alice_sig, bob_sig, 0, script] (+ control for Taproot)
   
2. Arbitration (IF, after timeout): Lenny AND (Alice OR Bob) (1-of-2 multisig)
   - Witness: [0, alice_or_bob_sig, lenny_sig, 1, script] (+ control for Taproot)

Note: The initial 0 in witness is the CHECKMULTISIG off-by-one bug workaround.

Supports:
- P2WSH (Pay-to-Witness-Script-Hash) - SegWit v0  
- Taproot (Pay-to-Taproot) - SegWit v1
"""

from typing import List, Dict, Any
from .base import SweeperStrategy, LockedError, ValidationError
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from script_utils import get_signature_type, SignatureType


class EscrowTimeoutSweeper(SweeperStrategy):
    """
    Sweeper for BIP-65 escrow scripts with three-party arbitration.
    
    Two spend paths:
    1. Normal Operations (ELSE branch, anytime):
       - 2-of-2 multisig: Alice AND Bob
       - Witness: [0, alice_sig, bob_sig, 0, script]
       - No timeout required
    
    2. Arbitration (IF branch, after timeout):
       - Lenny + 1-of-2 multisig: Lenny AND (Alice OR Bob)
       - Witness: [0, alice_or_bob_sig, lenny_sig, 1, script]
       - Must wait for locktime
    
    Args:
        use_arbitration_path: bool - If True, use arbitration (after timeout)
                                     If False, use normal operations (anytime)
        arbitration_co_signer: str - For arbitration: 'alice' or 'bob'
                                     Who signs alongside Lenny
    """
    
    SCRIPT_TYPE = "cltv_escrow"
    
    def __init__(self, use_arbitration_path: bool = False, arbitration_co_signer: str = 'alice'):
        """
        Initialize sweeper with path selection.
        
        Args:
            use_arbitration_path: Use arbitration path instead of normal operations
            arbitration_co_signer: Who signs with Lenny ('alice' or 'bob')
        """
        self.use_arbitration_path = use_arbitration_path
        self.arbitration_co_signer = arbitration_co_signer
        
        if arbitration_co_signer not in ('alice', 'bob'):
            raise ValidationError(
                f"arbitration_co_signer must be 'alice' or 'bob', got {arbitration_co_signer}"
            )
    
    def get_required_keys(self, output: Dict[str, Any]) -> List[str]:
        """
        Identify which keys are needed.
        
        Normal operations: alice_key and bob_key (2-of-2 multisig)
        Arbitration: lenny_key and (alice_key OR bob_key) (Lenny + 1-of-2)
        """
        if self.use_arbitration_path:
            # Arbitration: Lenny + one of Alice/Bob
            co_signer_key = f'{self.arbitration_co_signer}_key'
            return ['lenny_key', co_signer_key]
        else:
            # Normal operations: both Alice and Bob
            return ['alice_key', 'bob_key']
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, bytes],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """
        Build witness stack for chosen path.
        
        Normal operations witness:
            [0, alice_sig, bob_sig, 0, script]
            - 0: CHECKMULTISIG bug workaround
            - alice_sig, bob_sig: 2-of-2 multisig signatures
            - 0: triggers ELSE branch
            - script: the escrow script
            (+control_block for Taproot)
        
        Arbitration witness:
            [0, alice_or_bob_sig, lenny_sig, 1, script]
            - 0: CHECKMULTISIG bug workaround
            - alice_or_bob_sig: one signature for 1-of-2 multisig
            - lenny_sig: Lenny's signature for CHECKSIGVERIFY
            - 1: triggers IF branch
            - script: the escrow script
            (+control_block for Taproot)
        """
        script = bytes.fromhex(output['script_hex'])
        script_type = output.get('script_type', 'cltv_escrow')
        sig_type = get_signature_type(script_type)
        
        if self.use_arbitration_path:
            # Arbitration path: Lenny + one of Alice/Bob
            
            lenny_key = keys.get('lenny_key')
            if not lenny_key:
                raise ValidationError("lenny_key not provided for arbitration path")
            
            # Get co-signer key
            co_signer_key = keys.get(f'{self.arbitration_co_signer}_key')
            if not co_signer_key:
                raise ValidationError(
                    f"{self.arbitration_co_signer}_key not provided for arbitration path"
                )
            
            # Sign with both keys (ECDSA for P2WSH)
            lenny_sig = self._ecdsa_sign(lenny_key, sighash)
            co_signer_sig = self._ecdsa_sign(co_signer_key, sighash)
            
            # BIP-65 ScriptSig: 0 <Alice/Bob's signature> <Lenny's signature> 1
            # For P2WSH, this becomes witness: [0, alice_or_bob_sig, lenny_sig, 1, script]
            # Script: IF <locktime> CLTV DROP <lenny> CHECKSIGVERIFY 1 ELSE 2 ENDIF <alice> <bob> 2 CHECKMULTISIG
            # Execution for IF branch (arbitration):
            # 1. Witness items pushed to stack: [0, alice_or_bob_sig, lenny_sig, 1]
            # 2. OP_IF consumes 1 (true), enters IF branch
            # 3. CLTV checks locktime, DROP removes it
            # 4. Lenny's pubkey CHECKSIGVERIFY consumes lenny_sig
            # 5. OP_1 pushes M=1 for multisig
            # 6. Alice and Bob pubkeys pushed
            # 7. OP_2 pushes N=2
            # 8. Stack is now: [0, alice_or_bob_sig, 1, alice_pubkey, bob_pubkey, 2]
            # 9. CHECKMULTISIG verifies 1-of-2 signatures
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                0,                # CHECKMULTISIG bug workaround (off-by-one) - converts to b''
                co_signer_sig,    # Alice or Bob's signature (first in BIP-65)
                lenny_sig,        # Lenny's signature (second in BIP-65)
                1,                # True - triggers IF branch - converts to b'\x01'
                script
            ]
        
        else:
            # Normal operations path: 2-of-2 multisig (Alice AND Bob)
            
            alice_key = keys.get('alice_key')
            bob_key = keys.get('bob_key')
            
            if not alice_key:
                raise ValidationError("alice_key not provided for normal operations")
            if not bob_key:
                raise ValidationError("bob_key not provided for normal operations")
            
            # Sign with both keys (ECDSA for P2WSH)
            alice_sig = self._ecdsa_sign(alice_key, sighash)
            bob_sig = self._ecdsa_sign(bob_key, sighash)
            
            # BIP-65 ScriptSig: 0 <Alice's signature> <Bob's signature> 0
            # For P2WSH, this becomes witness: [0, alice_sig, bob_sig, 0, script]
            # Script: IF <locktime> CLTV DROP <lenny> CHECKSIGVERIFY 1 ELSE 2 ENDIF <alice> <bob> 2 CHECKMULTISIG
            # Execution for ELSE branch (normal ops):
            # 1. Witness items pushed to stack: [0, alice_sig, bob_sig, 0]
            # 2. Script executes, OP_IF consumes 0 (false), goes to ELSE
            # 3. ELSE pushes OP_2 (M value for multisig)
            # 4. ENDIF
            # 5. Alice and Bob pubkeys pushed
            # 6. OP_2 (N value) pushed
            # 7. Stack is now: [0, alice_sig, bob_sig, 2, alice_pubkey, bob_pubkey, 2]
            # 8. CHECKMULTISIG verifies 2-of-2 signatures
            # Note: construct_witness() will convert integers to proper Bitcoin script numbers
            witness = [
                0,                # CHECKMULTISIG bug workaround (off-by-one) - converts to b''
                alice_sig,        # Alice's signature (first in BIP-65)
                bob_sig,          # Bob's signature (second in BIP-65)
                0,                # False - triggers ELSE branch (which pushes M=2) - converts to b''
                script
            ]
        
        # Add control block for Taproot
        if 'taproot' in script_type.lower():
            control_block = output.get('control_block')
            if not control_block:
                raise ValidationError("Taproot output missing control_block")
            witness.append(bytes.fromhex(control_block))
        
        return witness
    
    def validate_sweep_conditions(
        self,
        output: Dict[str, Any],
        current_height: int,
        **kwargs
    ) -> bool:
        """
        Check if sweep is possible.
        
        Normal operations: Can sweep anytime (no timeout)
        Arbitration: Can only sweep after locktime
        """
        locktime = output.get('script_params', {}).get('locktime')
        
        # Fallback to top-level locktime
        if locktime is None:
            locktime = output.get('locktime')
        
        if locktime is None:
            raise ValidationError("No locktime found in output")
        
        if self.use_arbitration_path:
            # Arbitration path: must wait for locktime
            is_unlocked = current_height >= locktime
            
            if not is_unlocked and kwargs.get('raise_if_locked', False):
                raise LockedError(
                    f"Arbitration path locked. Current height: {current_height}, "
                    f"Locktime: {locktime}, Blocks remaining: {locktime - current_height}"
                )
            
            return is_unlocked
        else:
            # Normal operations: can sweep anytime
            return True
    
    def estimate_witness_size(self, output: Dict[str, Any]) -> int:
        """
        Estimate witness size for fee calculation.
        
        Normal operations: ~200 bytes (2 sigs + multisig overhead)
        Arbitration: ~220 bytes (2 sigs + Lenny's CHECKSIGVERIFY + multisig overhead)
        
        Both paths use CHECKMULTISIG which adds overhead.
        """
        from script_utils import get_witness_size_estimate
        
        script_type = output.get('script_type', 'cltv_escrow')
        
        if self.use_arbitration_path:
            path = 'arbitration'
        else:
            path = 'normal_operations'
        
        return get_witness_size_estimate(script_type, path)
    
    # Helper methods are now inherited from base class
