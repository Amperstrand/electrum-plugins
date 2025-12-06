"""
Generic Sweeper - Single sweeper for ALL contract types

This sweeper uses ContractHelper as the single source of truth.
No per-contract sweeper files needed!

Usage:
    from cltv_lib.sweepers.generic import GenericSweeper, sweep_output
    
    # Sweep any contract
    witness = sweep_output(
        script_type='cltv_escrow_taproot',
        params={'locktime': ..., 'alice_pubkey': ..., ...},
        path='normal',  # or 'arbitration_alice', etc.
        keys={'alice_key': privkey1, 'bob_key': privkey2},
        sighash=sighash_bytes
    )
"""

from typing import List, Dict, Any, Optional, Tuple
from electrum_ecc import ECPrivkey, ecdsa_der_sig_from_ecdsa_sig64

from ..contracts import CONTRACTS, SpendingPath
from ..builders.unified.generic import build_contract
from ..address_regenerator import parse_script_type
from ..contract_helper import ContractHelper


class SweepError(Exception):
    """Base error for sweep failures."""
    pass


class LockedError(SweepError):
    """Output is still timelocked."""
    pass


class ValidationError(SweepError):
    """Missing required data."""
    pass


def get_spending_path(contract_name: str, path_name: str) -> SpendingPath:
    """Get SpendingPath using ContractHelper (single source of truth)."""
    try:
        helper = ContractHelper(contract_name)
        return helper.get_path(path_name)
    except ValueError as e:
        raise ValidationError(str(e))


def validate_sweep_conditions(
    contract_name: str,
    path_name: str,
    locktime: int,
    current_height: int
) -> Tuple[bool, Optional[str]]:
    """
    Check if sweep conditions are met using ContractHelper.
    
    Returns:
        (can_sweep: bool, error_message: Optional[str])
    """
    helper = ContractHelper(contract_name)
    return helper.validate_sweep_conditions(path_name, locktime, current_height)


def get_required_keys(contract_name: str, path_name: str) -> List[str]:
    """Get required key names using ContractHelper."""
    helper = ContractHelper(contract_name)
    return helper.get_required_keys(path_name)


def normalize_key(key: Any) -> ECPrivkey:
    """
    Normalize key to ECPrivkey - single source of truth for key conversion.
    
    This handles the various formats keys can come in:
    - ECPrivkey: returned as-is
    - str: treated as hex, converted to ECPrivkey
    - bytes: converted to ECPrivkey
    
    Args:
        key: Key in any supported format
        
    Returns:
        ECPrivkey object
        
    Raises:
        ValueError: If key format is not recognized
    """
    if isinstance(key, ECPrivkey):
        return key
    elif isinstance(key, str):
        return ECPrivkey(bytes.fromhex(key))
    elif isinstance(key, bytes):
        return ECPrivkey(key)
    else:
        raise ValueError(f"Unsupported key type: {type(key)}")


def build_witness(
    script_type: str,
    params: Dict[str, Any],
    path_name: str,
    keys: Dict[str, ECPrivkey],
    sighash: bytes,
    script_hex: Optional[str] = None,
    control_block_hex: Optional[str] = None
) -> List[bytes]:
    """
    Build witness stack for any contract/path combination.

    Like Bitcoin Core's sign.cpp, this implements a fallback satisfaction chain:
    1. Try our known contract/path logic first (fastest)
    2. Fall back to miniscript FromScript parsing/satisfaction (Bitcoin Core style)
    3. Fall back to other methods if needed

    The CHECKMULTISIG dummy element requirement is handled automatically.

    NOTE: We implemented MORE COMPLEXITY THAN WE CURRENTLY NEED to match Bitcoin Core.
    For our CLTV contracts, Strategy 1 always succeeds. Strategy 2 (FromScript fallback)
    exists for architectural alignment but is never triggered in our use case.

    Args:
        script_type: e.g., 'cltv_escrow_taproot'
        params: Contract parameters
        path_name: Spending path name
        keys: Dict of key_name -> ECPrivkey
        sighash: 32-byte sighash to sign
        script_hex: Optional pre-computed script (if not provided, will regenerate)
        control_block_hex: Optional pre-computed control block (Taproot only)

    Returns:
        Witness stack as list of bytes
    """
    try:
        # Strategy 1: Known contract/path logic (fastest, most reliable)
        return _build_witness_known_contract(
            script_type, params, path_name, keys, sighash,
            script_hex, control_block_hex
        )
    except Exception:
        # Strategy 2: Miniscript FromScript fallback (Bitcoin Core style)
        try:
            return _build_witness_from_script_fallback(
                script_hex, keys, sighash, control_block_hex
            )
        except Exception:
            # Strategy 3: Other fallbacks could go here
            raise


def _build_witness_known_contract(
    script_type: str,
    params: Dict[str, Any],
    path_name: str,
    keys: Dict[str, ECPrivkey],
    sighash: bytes,
    script_hex: Optional[str] = None,
    control_block_hex: Optional[str] = None
) -> List[bytes]:
    """
    Strategy 1: Build witness using our known contract/path logic.
    This is the primary, most reliable method.
    """
    contract_name, output_type = parse_script_type(script_type)
    path = get_spending_path(contract_name, path_name)

    # Get required keys from ContractDefinition
    required_keys = path.required_keys

    # Validate we have all required keys
    missing = [k for k in required_keys if k not in keys]
    if missing:
        raise ValidationError(f"Missing required keys: {missing}")

    def get_key(name: str) -> ECPrivkey:
        return normalize_key(keys[name])

    # CRITICAL: Use provided script_hex if available - never regenerate
    # The script used for sighash MUST match the script in the witness exactly
    # Regenerating the script can cause mismatches due to encoding differences
    if not script_hex:
        # Only regenerate if absolutely necessary (shouldn't happen in normal flow)
        # This is a fallback, but the caller should always provide script_hex
        result = build_contract(contract_name, params, output_type)
        script_hex = result.get('script_hex', '')

        # For multi-path contracts, get the specific path's script
        if 'leaf_scripts' in result:
            path_to_leaf = _get_path_leaf_index(contract_name, path_name)
            if path_to_leaf is not None:
                script_hex = result['leaf_scripts'].get(f'leaf_{path_to_leaf}', script_hex)
        if 'control_blocks' in result and not control_block_hex:
            path_to_leaf = _get_path_leaf_index(contract_name, path_name)
            if path_to_leaf is not None:
                control_block_hex = result['control_blocks'].get(f'leaf_{path_to_leaf}', '')

    if not script_hex:
        raise ValidationError(f"Missing script_hex for {script_type} path {path_name}. "
                             f"This should be provided by the caller to ensure sighash/witness match.")

    script_bytes = bytes.fromhex(script_hex) if script_hex else b''

    # Check if this path requires a preimage (e.g., data_publishing publisher)
    preimage = None
    if path.requires_preimage:
        # Get preimage from params - try various field names
        preimage_hex = params.get('data_preimage') or params.get('preimage')
        if preimage_hex:
            if isinstance(preimage_hex, str):
                preimage = bytes.fromhex(preimage_hex)
            elif isinstance(preimage_hex, bytes):
                preimage = preimage_hex

    if output_type == 'taproot':
        return _build_taproot_witness(
            required_keys, get_key, sighash, script_bytes,
            bytes.fromhex(control_block_hex) if control_block_hex else b'',
            preimage=preimage,
            contract_name=contract_name,
            path_name=path_name
        )
    else:
        # For P2WSH: check if the BRANCH we're executing uses CHECKMULTISIG
        # 
        # IMPORTANT: The full P2WSH script contains or_i(X, Y), but only ONE branch
        # is executed. We must check if THAT branch uses CHECKMULTISIG.
        # 
        # - IF branch (leaf_index=0) executes first sub-expression
        # - ELSE branch (leaf_index=1) executes second sub-expression
        #
        # SINGLE SOURCE OF TRUTH: Check the branch-specific miniscript expression
        # from taproot_leaves[leaf_index] for "multi(" (not "multi_a(")
        needs_multisig_dummy = _branch_uses_checkmultisig(contract_name, path_name)

        return _build_p2wsh_witness(
            contract_name, path_name, required_keys, get_key, sighash, script_bytes,
            preimage=preimage,
            needs_multisig_dummy=needs_multisig_dummy
        )


def _build_witness_from_script_fallback(
    script_hex: str,
    keys: Dict[str, ECPrivkey],
    sighash: bytes,
    control_block_hex: Optional[str] = None
) -> List[bytes]:
    """
    Strategy 2: Fallback satisfaction using miniscript FromScript parsing.

    THIS IS ARCHITECTURAL COMPATIBILITY WITH BITCOIN CORE - NOT CURRENTLY USED.

    Why we implemented this (even though our contracts don't need it):
    - Bitcoin Core implements FromScript() fallback in sign.cpp for arbitrary P2WSH scripts
    - It allows signing scripts that are miniscript-compatible but not known descriptors
    - Maintains API compatibility for future expansion
    - Our current contracts use known paths, so this fallback is never triggered

    For our CLTV contracts, we always use Strategy 1 (known contract logic) because:
    - We know all our contract definitions and their spending paths
    - We determine CHECKMULTISIG needs directly from ContractDefinition.miniscript analysis
    - No need to reverse-engineer compiled scripts

    This fallback exists for Bitcoin Core architectural alignment and future extensibility.
    """
    if not script_hex:
        raise ValidationError("Cannot use FromScript fallback without script_hex")

    script_bytes = bytes.fromhex(script_hex)

    # Try to determine context from control block (Taproot vs P2WSH)
    is_taproot = control_block_hex is not None

    # Parse script using FromScript (Bitcoin Core style)
    from ..miniscript import from_script, MiniscriptContext

    context = MiniscriptContext.TAPSCRIPT if is_taproot else MiniscriptContext.P2WSH
    node = from_script(script_bytes, context)

    if not node:
        raise ValidationError(f"Script is not valid miniscript in {context.value} context")

    # Try to satisfy the parsed miniscript
    # This is a simplified version - full implementation would need proper key matching
    # For now, this is just a proof of concept of the fallback mechanism

    # TODO: Implement full miniscript satisfaction here
    # This would involve:
    # 1. Extracting required keys from the AST
    # 2. Matching available keys to requirements
    # 3. Building appropriate witness stack

    raise ValidationError("FromScript fallback satisfaction not yet implemented")


def _get_path_leaf_index(contract_name: str, path_name: str) -> Optional[int]:
    """Get leaf index using ContractHelper."""
    try:
        helper = ContractHelper(contract_name)
        return helper.get_leaf_index(path_name)
    except ValueError:
        return None


def _create_schnorr_signature(privkey: ECPrivkey, sighash: bytes) -> bytes:
    """
    Create Schnorr signature - single source of truth for all Taproot signatures.
    
    Args:
        privkey: ECPrivkey object
        sighash: 32-byte sighash to sign
    
    Returns:
        64-byte Schnorr signature (no hash type byte)
    """
    # Always use aux_rand32=None for deterministic signatures
    # This ensures consistent signature creation across all code paths
    return privkey.schnorr_sign(sighash, aux_rand32=None)


def _build_taproot_witness(
    required_keys: List[str],
    get_key,
    sighash: bytes,
    script_bytes: bytes,
    control_block_bytes: bytes,
    preimage: Optional[bytes] = None,
    contract_name: Optional[str] = None,
    path_name: Optional[str] = None
) -> List[bytes]:
    """
    Build Taproot witness.
    
    Taproot witness structure:
        [signature(s)...] [preimage (if required)] [script] [control_block]
    
    IMPORTANT: For multi_a(k, key1, key2, ...), we must provide signatures
    (or empty) for ALL keys in the multi_a, not just the signing ones.
    
    For CHECKSIGVERIFY + CHECKSIG chains (e.g., twofactor normal):
        Script: <service> CHECKSIGVERIFY <user> CHECKSIG
        Stack needs: [user_sig (bottom), service_sig (top)]
        witness = [user_sig, service_sig, script, control]
    
    For CHECKSIGVERIFY + multi_a (e.g., escrow arbitration_alice):
        Script: <lenny> CHECKSIGVERIFY <alice> CHECKSIG <bob> CHECKSIGADD 1 NUMEQUAL
        Stack needs: [bob_empty, alice_sig, lenny_sig] 
        (bob_empty for CHECKSIGADD, alice_sig for CHECKSIG, lenny_sig for CHECKSIGVERIFY)
        witness = [bob_empty, alice_sig, lenny_sig, script, control]
    """
    import re
    
    # Get the script miniscript to check for multi_a
    contract = CONTRACTS.get(contract_name) if contract_name else None
    path_def = contract.get_path(path_name) if contract and path_name else None
    
    # Get the leaf-specific miniscript (for Taproot)
    leaf_miniscript = None
    if contract and path_def and contract.taproot_leaves:
        leaf_index = path_def.leaf_index
        if leaf_index < len(contract.taproot_leaves):
            leaf_miniscript = contract.taproot_leaves[leaf_index]
    
    # Check for multi_a in the leaf script
    multi_a_keys = []
    if leaf_miniscript:
        # Capture ONLY the key names, not the threshold.
        # Example: multi_a(2, alice, bob) -> group(1) == "alice, bob"
        match = re.search(r'multi_a\s*\(\s*\d+\s*,\s*([^)]+)\)', leaf_miniscript)
        if match:
            # Split on commas, strip whitespace and defensively drop any
            # purely-numeric fragments (e.g. a mis-parsed threshold).
            raw_keys = [k.strip() for k in match.group(1).split(',')]
            multi_a_keys = [k for k in raw_keys if k and not k.isdigit()]
    
    # Build signatures list
    witness = []
    
    if multi_a_keys:
        # For multi_a(k, key1, key2, ...): 
        # Script is: <key1> CHECKSIG <key2> CHECKSIGADD ... k NUMEQUAL
        # 
        # Stack consumption order (LIFO):
        # - CHECKSIG for key1 pops from position closest to top
        # - CHECKSIGADD for key2 pops from position below
        # - etc.
        #
        # So multi_a keys need to be in REVERSE order on the stack!
        # Witness: [keyN_sig, ..., key2_sig, key1_sig]
        #
        # Example: multi_a(1, alice, bob)
        # Script: <alice> CHECKSIG <bob> CHECKSIGADD 1 NUMEQUAL
        # - alice consumed by CHECKSIG (from higher position)
        # - bob consumed by CHECKSIGADD (from lower position)
        # Witness: [bob_sig, alice_sig] (bob at bottom, alice above)
        
        for key_name in reversed(multi_a_keys):  # REVERSE order!
            if key_name in required_keys:
                privkey = get_key(key_name)
                sig = _create_schnorr_signature(privkey, sighash)
                witness.append(sig)
            else:
                witness.append(b'')  # Empty signature for non-signing keys
        
        # Add signatures for keys NOT in multi_a (e.g., lenny for CHECKSIGVERIFY)
        # These are consumed FIRST (from stack top), so they go LAST in witness
        for key_name in required_keys:
            if key_name not in multi_a_keys:
                privkey = get_key(key_name)
                sig = _create_schnorr_signature(privkey, sighash)
                witness.append(sig)
    else:
        # No multi_a: simple signature list in required_keys order
        for key_name in required_keys:
            privkey = get_key(key_name)
            sig = _create_schnorr_signature(privkey, sighash)
            witness.append(sig)
    
    # Add preimage if required (e.g., data_publishing publisher path)
    if preimage:
        witness.append(preimage)
    
    witness.append(script_bytes)
    witness.append(control_block_bytes)
    
    return witness


def _build_p2wsh_witness(
    contract_name: str,
    path_name: str,
    required_keys: List[str],
    get_key,
    sighash: bytes,
    script_bytes: bytes,
    preimage: Optional[bytes] = None,
    needs_multisig_dummy: bool = False
) -> List[bytes]:
    """
    Build P2WSH witness stack for any contract/path combination.
    
    P2WSH witness structure depends on the script opcodes:
    
    1. CHECKMULTISIG scripts (escrow normal, payment_channel cooperative):
       - Compiled from: multi(2, alice, bob) → 2 <pk> <pk> 2 OP_CHECKMULTISIG
       - Witness: [OP_0, sig_alice, sig_bob, branch_condition, script]
       - The OP_0 is required due to Bitcoin's CHECKMULTISIG off-by-one bug
    
    2. CHECKSIGVERIFY chain scripts (twofactor normal):
       - Compiled from: and_v(v:c:pk(service), c:pk(user)) → <pk> CHECKSIGVERIFY <pk> CHECKSIG
       - Witness: [sig_user, sig_service, branch_condition, script]
       - NO OP_0 needed - each CHECKSIG/CHECKSIGVERIFY pops exactly what it needs
    
    3. Single signature scripts (hodl, refund paths):
       - Compiled from: c:pk(pubkey) → <pk> OP_CHECKSIG
       - Witness: [sig, branch_condition, script]
    
    4. Hash-locked scripts (data_publishing publisher):
       - Compiled from: and_v(hash160_simple(data_hash), c:pk(publisher))
       - Witness: [sig, preimage, branch_condition, script]
       - The preimage is revealed on-chain when spending
    
    IMPORTANT: The needs_multisig_dummy flag is derived from the ContractDefinition.
    If the P2WSH miniscript contains multi() (not multi_a()), it compiles to CHECKMULTISIG
    which requires the OP_0 dummy due to Bitcoin's off-by-one bug.
    
    For Taproot: CHECKMULTISIG is disabled (BIP-342), so this never applies.
    Tapscript uses multi_a() which compiles to CHECKSIGADD instead.
    
    See: Bitcoin Core interpreter.cpp line 1107 - CHECKMULTISIG in Tapscript errors
    """
    # Sign with all required keys (ECDSA)
    signatures = []
    for key_name in required_keys:
        privkey = get_key(key_name)
        sig_compact = privkey.ecdsa_sign(sighash)
        sig_der = ecdsa_der_sig_from_ecdsa_sig64(sig_compact)
        signatures.append(sig_der + b'\x01')  # SIGHASH_ALL
    
    # Determine branch condition
    is_if_branch = _is_if_branch(contract_name, path_name)
    
    witness = []
    
    # CHECKMULTISIG requires dummy OP_0 (Bitcoin's off-by-one bug)
    # This is determined by analyzing the script for OP_CHECKMULTISIG opcode
    # CHECKSIGVERIFY+CHECKSIG chains do NOT need this
    if needs_multisig_dummy:
        witness.append(bytes([]))  # OP_0 for CHECKMULTISIG bug
    
    # Add signatures
    witness.extend(signatures)
    
    # Add preimage if required (e.g., data_publishing publisher path)
    if preimage:
        witness.append(preimage)
    
    # Add branch condition (for IF/ELSE scripts)
    if _has_branch(contract_name):
        witness.append(bytes([1]) if is_if_branch else bytes([]))
    
    # Add script
    witness.append(script_bytes)
    
    return witness


def _is_if_branch(contract_name: str, path_name: str) -> bool:
    """Check if path uses IF branch using ContractHelper."""
    try:
        helper = ContractHelper(contract_name)
        return helper.get_is_if_branch(path_name)
    except ValueError:
        return True  # Default to IF branch


def _has_branch(contract_name: str) -> bool:
    """Check if contract has IF/ELSE branches using ContractHelper."""
    try:
        helper = ContractHelper(contract_name)
        return helper.has_branches()
    except ValueError:
        return False


def _branch_uses_checkmultisig(contract_name: str, path_name: str) -> bool:
    """
    Check if the SPECIFIC BRANCH being executed uses CHECKMULTISIG.
    
    Simple string check: does the branch miniscript contain `multi(` (not `multi_a(`)?
    - multi() compiles to OP_CHECKMULTISIG (P2WSH) - needs dummy OP_0
    - multi_a() compiles to CHECKSIGADD chain (Tapscript) - no dummy needed
    
    WHY WE HANDLE THIS (not Electrum):
    - Electrum's descriptor.satisfy() handles the dummy automatically
    - But we manually build witnesses (Electrum lacks native Miniscript support)
    - So we must handle the CHECKMULTISIG dummy ourselves
    
    For or_i(X, Y) in P2WSH:
    - IF branch (leaf_index=0) executes X
    - ELSE branch (leaf_index=1) executes Y
    - We only need the dummy if the EXECUTED branch uses multi()
    """
    import re
    
    contract = CONTRACTS.get(contract_name)
    if not contract:
        return False
    
    path_def = contract.get_path(path_name)
    if not path_def:
        return False
    
    # Get the branch-specific miniscript from single source of truth
    # taproot_leaves[leaf_index] gives us just this branch's expression
    leaf_index = path_def.leaf_index
    
    if contract.taproot_leaves and leaf_index < len(contract.taproot_leaves):
        branch_miniscript = contract.taproot_leaves[leaf_index]
    else:
        branch_miniscript = contract.miniscript
    
    # For P2WSH context: taproot_leaves uses multi_a (Tapscript), but P2WSH uses multi
    # Convert multi_a → multi for the check
    p2wsh_branch = branch_miniscript.replace('multi_a(', 'multi(')
    
    # Simple string check: does this branch use multi()?
    # multi() → CHECKMULTISIG (needs dummy OP_0)
    return bool(re.search(r'\bmulti\s*\(', p2wsh_branch))


class GenericSweeper:
    """
    Generic sweeper that works for ANY contract type.
    
    This replaces all individual sweeper classes.
    
    Usage:
        sweeper = GenericSweeper(
            script_type='cltv_escrow_taproot',
            path='normal'
        )
        
        required_keys = sweeper.get_required_keys()
        sweeper.validate_sweep_conditions(output_data, current_height)
        witness = sweeper.build_witness(output_data, keys, sighash)
    """
    
    def __init__(
        self,
        script_type: str,
        path: str = 'sweep',
        **kwargs  # For legacy compatibility
    ):
        self.script_type = script_type
        self.contract_name, self.output_type = parse_script_type(script_type)
        
        # Handle legacy path parameters
        if kwargs.get('use_refund_path'):
            self.path = 'refund'
        elif kwargs.get('use_recovery_path'):
            self.path = 'recovery'
        elif kwargs.get('use_arbitration_path'):
            self.path = kwargs.get('arbitration_co_signer', 'arbitration_alice')
        else:
            self.path = path
    
    def get_required_keys(self, output: Dict[str, Any] = None) -> List[str]:
        """Get required key names for the current path."""
        return get_required_keys(self.contract_name, self.path)
    
    def validate_sweep_conditions(
        self,
        output: Dict[str, Any],
        current_height: int,
        raise_if_locked: bool = True,
        **kwargs
    ) -> bool:
        """Validate sweep conditions."""
        locktime = output.get('locktime', 0)
        can_sweep, error_msg = validate_sweep_conditions(
            self.contract_name, self.path, locktime, current_height
        )
        
        if not can_sweep and raise_if_locked:
            raise LockedError(error_msg)
        
        return can_sweep
    
    def compute_sighash(
        self,
        tx,  # PartialTransaction
        input_index: int,
        output: Dict[str, Any],
        **kwargs
    ) -> bytes:
        """
        Compute sighash for the transaction input - single source of truth.
        
        Args:
            tx: PartialTransaction object
            input_index: Index of input being signed
            output: Output data dict with script_hex, control_block_hex, etc.
            **kwargs: Additional parameters (prevout_amount, scriptpubkey, etc.)
        
        Returns:
            32-byte sighash ready for signing
        """
        if self.output_type == 'taproot':
            # Use BIP-341 Taproot sighash
            from ..builders.taproot.taproot_sighash_builder import compute_taproot_sighash
            
            # Get required data
            prevout_amount = kwargs.get('prevout_amount') or tx.inputs()[input_index]._trusted_value_sats
            script_hex = output.get('script_hex', '')
            
            # CRITICAL: If script_hex is missing, we MUST regenerate it from params
            # The script used for sighash MUST match the script in the witness exactly
            if not script_hex:
                # Regenerate script from params to ensure it matches what build_witness() will use
                from ..builders.unified.generic import build_contract
                contract_name, _ = parse_script_type(self.script_type)
                params = output.get('script_params', output.get('params', {}))
                path_name = self.path
                
                result = build_contract(contract_name, params, self.output_type)
                
                # For multi-path contracts, get the specific path's script
                if 'leaf_scripts' in result:
                    path_to_leaf = _get_path_leaf_index(contract_name, path_name)
                    if path_to_leaf is not None:
                        script_hex = result['leaf_scripts'].get(f'leaf_{path_to_leaf}', result.get('script_hex', ''))
                else:
                    script_hex = result.get('script_hex', '')
            
            script_bytes = bytes.fromhex(script_hex) if script_hex else b''
            if not script_bytes:
                raise ValidationError(f"Missing script_hex for path '{self.path}' - cannot compute sighash")
            
            control_block_hex = output.get('control_block_hex') or output.get('control_block', '')
            control_block_bytes = bytes.fromhex(control_block_hex) if control_block_hex else b''
            if not control_block_bytes and self.output_type == 'taproot':
                raise ValidationError(f"Missing control_block_hex for path '{self.path}' - cannot compute sighash")
            
            # Reconstruct scriptpubkey from output_key (Taproot: 0x5120 + output_key)
            output_key = output.get('output_key')
            if isinstance(output_key, str):
                output_key = bytes.fromhex(output_key)
            scriptpubkey = bytes([0x51, 0x20]) + output_key if output_key else kwargs.get('scriptpubkey', b'')
            
            return compute_taproot_sighash(
                tx=tx,
                input_index=input_index,
                prevout_amount=prevout_amount,
                prevout_scriptpubkey=scriptpubkey,
                script=script_bytes,
                control_block=control_block_bytes
            )
        else:
            # Use BIP-143 P2WSH sighash
            from electrum.crypto import sha256d
            preimage = tx.serialize_preimage(txin_index=input_index)
            return sha256d(preimage)
    
    def build_witness(
        self,
        output: Dict[str, Any],
        keys: Dict[str, Any],
        sighash: bytes,
        **kwargs
    ) -> List[bytes]:
        """Build witness stack."""
        # CRITICAL: script_hex MUST be provided and match the script used for sighash
        script_hex = output.get('script_hex')
        if not script_hex:
            raise ValidationError(
                f"Missing script_hex in output data for {self.script_type} path {self.path}. "
                f"The script used for sighash computation must match the script in the witness exactly. "
                f"Please ensure script_hex is set in output_data before calling build_witness()."
            )
        
        # Convert keys to ECPrivkey using single normalize_key utility
        normalized_keys = {name: normalize_key(key) for name, key in keys.items()}
        
        return build_witness(
            script_type=self.script_type,
            params=output.get('script_params', output.get('params', {})),
            path_name=self.path,
            keys=normalized_keys,
            sighash=sighash,
            script_hex=script_hex,  # Always use provided script_hex - never regenerate
            control_block_hex=output.get('control_block_hex') or output.get('control_block'),
        )


# Convenience function
def sweep_output(
    script_type: str,
    params: Dict[str, Any],
    path: str,
    keys: Dict[str, Any],
    sighash: bytes,
    current_height: int = 0
) -> List[bytes]:
    """
    One-shot sweep function.
    
    Args:
        script_type: e.g., 'cltv_escrow_taproot'
        params: Contract parameters
        path: Spending path name
        keys: Dict of key_name -> private key (hex, bytes, or ECPrivkey)
        sighash: 32-byte sighash
        current_height: Current blockchain height (for locktime validation)
    
    Returns:
        Witness stack
    """
    sweeper = GenericSweeper(script_type=script_type, path=path)
    
    output = {
        'locktime': params.get('locktime', 0),
        'params': params
    }
    
    if current_height > 0:
        sweeper.validate_sweep_conditions(output, current_height)
    
    return sweeper.build_witness(output, keys, sighash)


__all__ = [
    'GenericSweeper',
    'sweep_output',
    'get_required_keys',
    'validate_sweep_conditions',
    'build_witness',
    'normalize_key',
    'SweepError',
    'LockedError',
    'ValidationError',
]

