"""
ContractHelper - Unified helper for all contract operations

This is the SINGLE interface for working with contracts. Used by:
- UnifiedContractBuilder (address generation)
- GenericSweeper (witness building)
- FeeCalculator (witness size estimation)
- UI dialogs (path display, key requirements)

All methods derive from ContractDefinition - no duplicated logic.

Usage:
    from cltv_lib.contract_helper import ContractHelper
    
    # From script_type
    helper = ContractHelper.from_script_type('cltv_escrow_taproot')
    
    # Get path info
    path = helper.get_path('normal')
    required_keys = path.required_keys
    
    # Get script for a path
    script_bytes = helper.get_script_for_path('normal', params)
    
    # Get witness size
    witness_size = helper.calculate_witness_size('normal', params)
"""

from typing import Dict, Any, Optional, List, Tuple, Union
from functools import lru_cache

from .contracts import CONTRACTS, ContractDefinition, SpendingPath
from .address_regenerator import parse_script_type


class ContractHelper:
    """
    Unified helper for contract operations.
    
    Consolidates all contract-related lookups and calculations that were
    previously duplicated across builder, sweeper, and fee_calculator.
    
    Thread-safe and cacheable for performance.
    """
    
    def __init__(
        self,
        contract_name: str,
        output_type: str = 'p2wsh'
    ):
        """
        Initialize helper for a specific contract.
        
        Args:
            contract_name: Contract name (e.g., 'escrow', 'hodl')
            output_type: 'p2wsh' or 'taproot'
        """
        self.contract_name = contract_name
        self.output_type = output_type
        
        self.contract = CONTRACTS.get(contract_name)
        if not self.contract:
            raise ValueError(f"Unknown contract: {contract_name}. "
                           f"Available: {list(CONTRACTS.keys())}")
    
    @classmethod
    def from_script_type(cls, script_type: str) -> 'ContractHelper':
        """
        Create helper from script_type string.
        
        Args:
            script_type: e.g., 'cltv_escrow_taproot', 'cltv_hodl_p2wsh'
        
        Returns:
            ContractHelper instance
        """
        contract_name, output_type = parse_script_type(script_type)
        return cls(contract_name, output_type)
    
    @property
    def script_type(self) -> str:
        """Get the canonical script_type string."""
        return f"cltv_{self.contract_name}_{self.output_type}"
    
    @property
    def is_taproot(self) -> bool:
        """Check if this is a Taproot output."""
        return self.output_type == 'taproot'
    
    # =========================================================================
    # Path Operations
    # =========================================================================
    
    def get_path(self, path_name: str) -> SpendingPath:
        """
        Get SpendingPath by name.
        
        Args:
            path_name: Path name (e.g., 'normal', 'refund', 'arbitration_alice')
        
        Returns:
            SpendingPath object
        
        Raises:
            ValueError: If path not found
        """
        path = self.contract.get_path(path_name)
        if not path:
            valid_paths = [p.name for p in self.contract.paths]
            raise ValueError(f"Unknown path '{path_name}' for {self.contract_name}. "
                           f"Valid: {valid_paths}")
        return path
    
    def get_all_paths(self) -> List[SpendingPath]:
        """Get all spending paths for this contract."""
        return self.contract.paths
    
    def get_path_names(self) -> List[str]:
        """Get names of all spending paths."""
        return [p.name for p in self.contract.paths]
    
    def get_required_keys(self, path_name: str) -> List[str]:
        """Get required key names for a path."""
        return self.get_path(path_name).required_keys
    
    def path_requires_locktime(self, path_name: str) -> bool:
        """Check if path requires locktime to be satisfied."""
        return self.get_path(path_name).requires_locktime
    
    def path_requires_preimage(self, path_name: str) -> bool:
        """Check if path requires a preimage (e.g., data_publishing publisher)."""
        return self.get_path(path_name).requires_preimage
    
    def p2wsh_uses_checkmultisig(self) -> bool:
        """
        Check if the P2WSH version uses CHECKMULTISIG.
        
        This determines whether OP_0 dummy element is needed in witness.
        Derived directly from the ContractDefinition - no metadata tracking needed.
        
        NOTE: Taproot never uses CHECKMULTISIG - it's disabled in Tapscript (BIP-342).
        This method returns False for Taproot regardless of the contract.
        
        Returns:
            True if P2WSH and contract miniscript contains multi(), False otherwise
        """
        if self.is_taproot:
            # CHECKMULTISIG is disabled in Tapscript - replaced with CHECKSIGADD
            return False
        return self.contract.p2wsh_uses_checkmultisig()
    
    def _get_script_bytes_for_path(
        self,
        path_name: str,
        params: Dict[str, Any]
    ) -> Optional[bytes]:
        """Get compiled script bytes for a specific path."""
        try:
            params_tuple = tuple(sorted(params.items()))
            result = _cached_build_contract(
                self.contract_name, params_tuple, self.output_type
            )
            
            script_hex = result.get('script_hex', '')
            
            # Get path-specific script for Taproot
            if self.is_taproot and 'leaf_scripts' in result:
                leaf_idx = self.get_leaf_index(path_name)
                if leaf_idx is not None:
                    script_hex = result['leaf_scripts'].get(
                        f'leaf_{leaf_idx}', script_hex
                    )
            
            return bytes.fromhex(script_hex) if script_hex else None
        except Exception:
            return None
    
    # =========================================================================
    # Script Operations
    # =========================================================================
    
    def get_leaf_index(self, path_name: str) -> Optional[int]:
        """
        Get Taproot leaf index for a path.
        
        Returns:
            Leaf index (0-based), or None if not applicable
        """
        path = self.get_path(path_name)
        return path.leaf_index
    
    def get_is_if_branch(self, path_name: str) -> bool:
        """
        Check if path uses IF branch (vs ELSE branch) in P2WSH.
        
        Returns:
            True for IF branch (pushes [1]), False for ELSE branch (pushes [])
        """
        path = self.get_path(path_name)
        return path.is_if_branch
    
    def has_branches(self) -> bool:
        """Check if contract has IF/ELSE branches in P2WSH."""
        return self.contract.has_branches()
    
    def get_tree_depth(self) -> int:
        """
        Get Taproot tree depth for this contract.
        
        Returns:
            0 = single leaf, 1 = 2 leaves, etc.
        """
        num_paths = len(self.contract.paths)
        if num_paths <= 1:
            return 0
        elif num_paths == 2:
            return 1
        else:
            return (num_paths - 1).bit_length()
    
    # =========================================================================
    # Witness Size Calculation
    # =========================================================================
    
    def calculate_witness_size(
        self,
        path_name: str,
        params: Dict[str, Any],
        script_len: Optional[int] = None
    ) -> int:
        """
        Calculate witness size for a specific path.
        
        Args:
            path_name: Spending path name
            params: Contract parameters (for script length calculation)
            script_len: Optional pre-computed script length
        
        Returns:
            Witness size in bytes
        """
        path = self.get_path(path_name)
        
        # Get script length if not provided
        if script_len is None:
            script_len = self._estimate_script_length(path_name, params)
        
        # Get extra data size (e.g., preimage)
        extra_data_len = self._get_extra_data_size(path_name, params)
        
        if self.is_taproot:
            return self._calculate_taproot_witness_size(
                num_signatures=len(path.required_keys),
                script_len=script_len,
                tree_depth=self.get_tree_depth(),
                extra_data_len=extra_data_len
            )
        else:
            # Check if P2WSH contract uses multi() → CHECKMULTISIG → needs OP_0 dummy
            needs_multisig_dummy = self.p2wsh_uses_checkmultisig()
            
            return self._calculate_p2wsh_witness_size(
                num_signatures=len(path.required_keys),
                script_len=script_len,
                needs_multisig_dummy=needs_multisig_dummy,
                has_branch=self.has_branches(),
                is_if_branch=path.is_if_branch,
                extra_data_len=extra_data_len
            )
    
    def _estimate_script_length(
        self,
        path_name: str,
        params: Dict[str, Any]
    ) -> int:
        """Estimate script length for a path."""
        # Try to build actual script if we have params
        if params:
            try:
                from .builders.unified.generic import build_contract
                
                # Convert params to cacheable tuple
                params_tuple = tuple(sorted(params.items()))
                result = _cached_build_contract(
                    self.contract_name, params_tuple, self.output_type
                )
                
                script_hex = result.get('script_hex', '')
                
                # Get path-specific script for Taproot
                if self.is_taproot and 'leaf_scripts' in result:
                    leaf_idx = self.get_leaf_index(path_name)
                    if leaf_idx is not None:
                        script_hex = result['leaf_scripts'].get(
                            f'leaf_{leaf_idx}', script_hex
                        )
                
                if script_hex:
                    return len(bytes.fromhex(script_hex))
            except Exception:
                pass
        
        # Fallback: estimate based on contract structure
        # Base script size varies by contract type
        base_sizes = {
            'hodl': 35,      # after(locktime) + pk()
            'payment_channel': 80,  # or_i(multi(2,...), and_v(...))
            'escrow': 120,          # or_i(multi(2,...), and_v(..., multi(1,...)))
            'twofactor': 70,        # or_i(and_v(...), and_v(...))
            'data_publishing': 60,  # or_i(and_v(hash,...), and_v(...))
        }
        return base_sizes.get(self.contract_name, 100)
    
    def _get_extra_data_size(
        self,
        path_name: str,
        params: Dict[str, Any]
    ) -> int:
        """Get size of extra witness data (e.g., preimage)."""
        if self.path_requires_preimage(path_name):
            preimage = params.get('data_preimage') or params.get('preimage')
            if preimage:
                if isinstance(preimage, str):
                    return len(bytes.fromhex(preimage))
                elif isinstance(preimage, bytes):
                    return len(preimage)
        return 0
    
    @staticmethod
    def _calculate_taproot_witness_size(
        num_signatures: int,
        script_len: int,
        tree_depth: int,
        extra_data_len: int = 0
    ) -> int:
        """Calculate Taproot script-path witness size."""
        size = 1  # Stack count (varint)
        
        # Signatures (Schnorr, 64 bytes each)
        for _ in range(num_signatures):
            size += 1 + 64  # varint(64) + 64 bytes
        
        # Extra data (e.g., preimage) - pushed before script
        if extra_data_len > 0:
            size += ContractHelper._varint_size(extra_data_len) + extra_data_len
        
        # Script (varint length prefix + script)
        size += ContractHelper._varint_size(script_len) + script_len
        
        # Control block: 1 (version) + 33 (internal_key) + 32*depth
        control_block_len = 1 + 33 + (32 * tree_depth)
        size += ContractHelper._varint_size(control_block_len) + control_block_len
        
        return size
    
    @staticmethod
    def _calculate_p2wsh_witness_size(
        num_signatures: int,
        script_len: int,
        needs_multisig_dummy: bool,
        has_branch: bool,
        is_if_branch: bool,
        extra_data_len: int = 0
    ) -> int:
        """Calculate P2WSH witness size."""
        size = 1  # Stack count (varint)
        
        # CHECKMULTISIG dummy OP_0 (determined by script analysis)
        if needs_multisig_dummy:
            size += 1  # Empty bytes for OP_0
        
        # Signatures (ECDSA DER, typically 71-72 bytes)
        for _ in range(num_signatures):
            size += 1 + 72  # varint(72) + 72 bytes
        
        # Extra data (e.g., preimage)
        if extra_data_len > 0:
            size += ContractHelper._varint_size(extra_data_len) + extra_data_len
        
        # Branch condition (for IF/ELSE scripts)
        if has_branch:
            if is_if_branch:
                size += 1 + 1  # varint(1) + [1]
            else:
                size += 1  # varint(0) + []
        
        # Script (varint length prefix + script)
        size += ContractHelper._varint_size(script_len) + script_len
        
        return size
    
    @staticmethod
    def _varint_size(value: int) -> int:
        """Calculate varint encoding size."""
        if value < 0xfd:
            return 1
        elif value <= 0xffff:
            return 3
        elif value <= 0xffffffff:
            return 5
        else:
            return 9
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def validate_sweep_conditions(
        self,
        path_name: str,
        locktime: int,
        current_height: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if sweep conditions are met for a path.
        
        Args:
            path_name: Spending path name
            locktime: Contract locktime
            current_height: Current blockchain height
        
        Returns:
            (can_sweep: bool, error_message: Optional[str])
        """
        path = self.get_path(path_name)
        
        if path.requires_locktime and current_height < locktime:
            blocks_remaining = locktime - current_height
            return False, (f"Still locked! {blocks_remaining} blocks remaining "
                          f"(current: {current_height}, locktime: {locktime})")
        
        return True, None
    
    def validate_keys(
        self,
        path_name: str,
        provided_keys: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all required keys are provided.
        
        Args:
            path_name: Spending path name
            provided_keys: Dict of key_name -> key (any format)
        
        Returns:
            (valid: bool, missing_keys: List[str])
        """
        required = self.get_required_keys(path_name)
        missing = [k for k in required if k not in provided_keys]
        return len(missing) == 0, missing
    
    # =========================================================================
    # Key Normalization
    # =========================================================================
    
    @staticmethod
    def normalize_key(key: Any) -> bytes:
        """
        Normalize key to bytes.
        
        Handles:
        - bytes: returned as-is
        - hex string: decoded to bytes
        - ECPrivkey: get_secret_bytes()
        
        Args:
            key: Key in any format
        
        Returns:
            Key as bytes
        """
        if isinstance(key, bytes):
            return key
        elif isinstance(key, str):
            return bytes.fromhex(key)
        elif hasattr(key, 'get_secret_bytes'):
            # ECPrivkey
            return key.get_secret_bytes()
        else:
            raise ValueError(f"Cannot normalize key of type {type(key).__name__}")
    
    @staticmethod
    def normalize_pubkey(pubkey: Any) -> bytes:
        """
        Normalize public key to bytes.
        
        Validates length (33 for compressed, 32 for x-only).
        
        Args:
            pubkey: Public key in any format
        
        Returns:
            Public key as bytes
        
        Raises:
            ValueError: If invalid format or length
        """
        if isinstance(pubkey, str):
            pubkey = bytes.fromhex(pubkey)
        
        if not isinstance(pubkey, bytes):
            raise ValueError(f"pubkey must be bytes or hex string, got {type(pubkey).__name__}")
        
        if len(pubkey) == 33:
            # Compressed pubkey
            if pubkey[0] not in (0x02, 0x03):
                raise ValueError("Invalid compressed pubkey prefix")
        elif len(pubkey) == 32:
            # X-only pubkey (Taproot)
            pass
        else:
            raise ValueError(f"Invalid pubkey length: {len(pubkey)}. Expected 32 or 33")
        
        return pubkey


# =========================================================================
# Cached Build Function
# =========================================================================

@lru_cache(maxsize=64)
def _cached_build_contract(
    contract_name: str,
    params_tuple: tuple,
    output_type: str
) -> Dict[str, Any]:
    """
    Cache contract builds for performance.
    
    Used by calculate_witness_size to avoid rebuilding contracts.
    """
    from .builders.unified.generic import build_contract
    params = dict(params_tuple)
    return build_contract(contract_name, params, output_type)


__all__ = ['ContractHelper']

