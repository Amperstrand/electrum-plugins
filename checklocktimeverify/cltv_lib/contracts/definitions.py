"""
Contract Definitions - Single Source of Truth

Each contract is defined once with its Miniscript expression and parameter schema.
The same definition generates both P2WSH and Taproot scripts.

This module serves as the single source of truth for:
- Miniscript expressions
- Parameter specifications
- Spending paths (with locktime requirements)
- Key roles (with descriptions for UI)
- BIP-65 references and documentation

The UI can be generated directly from these definitions.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Literal
from enum import Enum

from ..miniscript import compile_miniscript, MiniscriptContext, CompiledScript
from ..miniscript.compiler import compile_miniscript


class ContractType(Enum):
    """Contract types supported by the plugin."""
    HODL = "hodl"
    PAYMENT_CHANNEL = "payment_channel"
    ESCROW = "escrow"
    TWOFACTOR = "twofactor"
    DATA_PUBLISHING = "data_publishing"
    TRIDENT_VAULT = "trident_vault"
    DECAYING_MULTISIG = "decaying_multisig"


@dataclass
class ParamSpec:
    """
    Parameter specification for a contract.
    
    This is the single source of truth for parameter metadata used by:
    - UI dialogs (form generation, test key buttons)
    - Tests (loading test keys)
    - Validation
    
    Args:
        name: Parameter name (e.g., 'locktime', 'alice')
        description: Human-readable description
        param_type: Type for validation ('pubkey', 'locktime', 'hash160', 'preimage')
                   Defaults to name if not specified.
        test_key_name: Name in test_keys.py for UI "Test Key" buttons
    """
    name: str
    description: str
    param_type: Optional[str] = None  # Defaults to name if None
    required: bool = True
    sensitive: bool = False  # True for data that should be hidden (e.g., preimage)
    derivable_from: Optional[str] = None  # e.g., 'data_hash' derivable from 'data_preimage'
    test_key_name: Optional[str] = None  # Name in test_keys.py (e.g., 'hodl', 'alice')
    
    def __post_init__(self):
        """Set param_type to name if not specified."""
        if self.param_type is None:
            self.param_type = self.name


@dataclass
class SpendingPath:
    """
    A spending path (branch) of a contract.
    
    CURRENT IMPLEMENTATION (practical compromise):
    - leaf_index: Manually specified, maps to taproot_leaves[i]
    - required_keys: Manually specified, in witness stack order
    
    AUTOMATICALLY DERIVED:
    - is_if_branch: Computed from leaf_index (leaf_index=0 → IF, else ELSE)
    - CHECKMULTISIG dummy: Detected from compiled script bytes (0xae/0xaf opcodes)
    
    FUTURE IMPLEMENTATION (like Minsc):
    - Parse the miniscript expression to extract the AST
    - Identify branches from or_i/or_d/thresh nodes
    - Infer required_keys from pk() nodes in each branch
    - Compute leaf_index from policy tree position
    - This would reduce SpendingPath to just: name, display_name, description
    - See: https://min.sc for reference implementation
    
    REQUIRED_KEYS ORDER (for now, manually specified):
    Must match WITNESS STACK order (bottom to top). Later script operations
    consume from stack TOP, so their keys should be LAST in required_keys.
    Example: CHECKSIGVERIFY(lenny) then CHECKMULTISIG(alice)
      -> required_keys=['alice', 'lenny'] (lenny consumed first from top)
    """
    name: str                    # Internal name: 'normal', 'refund', 'arbitration_alice'
    display_name: str            # UI button text: 'Cooperative Close (Sender+Receiver)'
    description: str             # Tooltip: 'Both parties agree to close the channel'
    requires_locktime: bool      # Does this path need CLTV to be satisfied?
    required_keys: List[str]     # Keys in WITNESS STACK order (bottom to top)
    is_cooperative: bool = True  # True = immediate (no timelock check), False = after locktime
    warning: Optional[str] = None  # Special warnings (e.g., data reveal)
    
    # For data publishing: special handling
    requires_preimage: bool = False  # Publisher path needs preimage
    
    # Taproot leaf index - also used to derive P2WSH branch
    # For or_i(X, Y): leaf_index=0 → first sub-expr (IF), leaf_index=1 → second (ELSE)
    leaf_index: int = 0
    
    # UI metadata for this path
    # Default icon keeps backwards compatibility for older definitions
    icon: str = "🔀"
    
    @property
    def is_if_branch(self) -> bool:
        """Derive P2WSH branch from leaf_index. leaf_index=0 → IF, otherwise ELSE."""
        return self.leaf_index == 0


@dataclass
class KeyRole:
    """
    Defines a key's role in the contract.
    
    Used to generate UI labels and help text.
    """
    name: str                    # Internal name: 'alice', 'sender', 'publisher'
    display_name: str            # UI label: 'Alice (Party A)'
    description: str             # Help text: 'The first party to the escrow'
    icon: str = '🔑'             # Icon for UI


@dataclass
class ContractDefinition:
    """
    Complete definition of a CLTV contract.
    
    This is the SINGLE SOURCE OF TRUTH for each contract type.
    The UI, e2e tests, builders, and sweepers all derive from this.
    
    Attributes:
        contract_type: The type of contract
        name: Human-readable name
        description: What the contract does
        miniscript: The Miniscript expression (with parameter placeholders)
        params: List of parameter specifications
        param_mapping: Maps user-friendly param names to miniscript placeholders
        
        # NEW: For UI generation
        bip_reference: BIP-65 example reference
        short_description: One-liner for lists
        use_cases: Example use cases
        paths: Spending paths with all metadata
        key_roles: Key descriptions for UI
        icon: Contract icon for lists
    """
    contract_type: ContractType
    name: str
    description: str
    miniscript: str
    params: List[ParamSpec]
    param_mapping: Dict[str, str] = field(default_factory=dict)
    
    # For Taproot: which paths go in which leaves
    taproot_leaves: Optional[List[str]] = None
    
    # NEW: UI metadata
    bip_reference: str = ''
    short_description: str = ''
    use_cases: List[str] = field(default_factory=list)
    icon: str = '📜'
    
    # NEW: Spending paths (for UI buttons and sweep logic)
    paths: List[SpendingPath] = field(default_factory=list)
    
    # NEW: Key roles (for UI labels)
    key_roles: List[KeyRole] = field(default_factory=list)
    
    def get_path(self, path_name: str) -> Optional[SpendingPath]:
        """Get a spending path by name."""
        for path in self.paths:
            if path.name == path_name:
                return path
        return None
    
    def get_key_role(self, key_name: str) -> Optional[KeyRole]:
        """Get a key role by name."""
        for role in self.key_roles:
            if role.name == key_name:
                return role
        return None
    
    def p2wsh_uses_checkmultisig(self) -> bool:
        """
        Check if the P2WSH version of this contract uses OP_CHECKMULTISIG.
        
        This determines whether the witness needs a dummy OP_0 element.
        
        Bitcoin's CHECKMULTISIG opcode has an off-by-one bug that pops an extra
        element from the stack. Witnesses must include a dummy element (OP_0).
        
        NOTE: Taproot/Tapscript does NOT have this issue - CHECKMULTISIG is
        disabled in Tapscript and replaced with CHECKSIGADD (multi_a).
        See BIP-342 and Bitcoin Core interpreter.cpp line 1107.
        
        Returns:
            True if P2WSH miniscript contains multi() (not multi_a)
        """
        # Simple string check: does miniscript contain "multi(" but not "multi_a("?
        # This works because:
        # - multi(k, keys...) compiles to OP_CHECKMULTISIG in P2WSH
        # - multi_a(k, keys...) compiles to CHECKSIGADD in Tapscript (not used in P2WSH)
        import re
        # Match "multi(" but not "multi_a("
        return bool(re.search(r'multi\s*\(', self.miniscript) and 
                   not re.search(r'multi_a\s*\(', self.miniscript))
    
    def get_path_leaf_index(self, path_name: str) -> Optional[int]:
        """Get the Taproot leaf index for a spending path."""
        path = self.get_path(path_name)
        return path.leaf_index if path else None
    
    def get_path_is_if_branch(self, path_name: str) -> bool:
        """Check if a spending path uses the IF branch in P2WSH."""
        path = self.get_path(path_name)
        return path.is_if_branch if path else True
    
    def has_branches(self) -> bool:
        """Check if this contract has IF/ELSE branches in P2WSH."""
        # Contracts with multiple paths have branches
        return len(self.paths) > 1
    
    def get_required_param_names(self) -> List[str]:
        """Get list of required parameter names."""
        return [spec.name for spec in self.params if spec.required]
    
    def get_miniscript(self, style: str = 'symbolic') -> str:
        """
        Get the Miniscript expression.
        
        Args:
            style: 'symbolic' for placeholders, 'concrete' for actual values
        
        Returns:
            Miniscript expression string
        """
        return self.miniscript
    
    def compile(
        self,
        params: Dict[str, Any],
        context: str = 'p2wsh'
    ) -> bytes:
        """
        Compile the contract to Bitcoin Script.
        
        Args:
            params: Parameter values (pubkeys as bytes, locktime as int, etc.)
            context: 'p2wsh' or 'tapscript'
        
        Returns:
            Compiled Bitcoin Script bytes
        """
        # Map parameters if needed
        mapped_params = {}
        for key, value in params.items():
            mapped_key = self.param_mapping.get(key, key)
            mapped_params[mapped_key] = value

        # Select context
        ms_context = (
            MiniscriptContext.TAPSCRIPT if context == 'tapscript'
            else MiniscriptContext.P2WSH
        )

        return compile_miniscript(self.miniscript, mapped_params, ms_context)



# =============================================================================
# CONTRACT DEFINITIONS
# =============================================================================
# 
# Contracts are dynamically loaded from individual files in this directory.
# Each contract file should define a ContractDefinition instance with a name
# matching the pattern: <CONTRACT_NAME> = ContractDefinition(...)
#
# The registry automatically discovers and loads all contracts.
# =============================================================================

import importlib
import pkgutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Contracts to exclude from auto-loading
EXCLUDED_CONTRACTS = {
    'trident_vault',  # Uses relative timelocks (CSV/BIP-112), not CLTV
}

def _discover_contracts() -> Dict[str, ContractDefinition]:
    """
    Dynamically discover and load all contract definitions from this package.
    
    Scans the contracts directory for Python files and imports ContractDefinition
    instances that match the pattern: <CONTRACT_NAME> = ContractDefinition(...)
    
    Returns:
        Dictionary mapping contract names to ContractDefinition instances
    """
    contracts = {}
    package_path = Path(__file__).parent
    
    # Get all Python files in the contracts directory
    for module_info in pkgutil.iter_modules([str(package_path)]):
        module_name = module_info.name
        
        # Skip non-contract files
        if module_name in ('__init__', 'definitions'):
            continue
        
        # Skip excluded contracts
        if module_name in EXCLUDED_CONTRACTS:
            logger.debug(f"Skipping excluded contract: {module_name}")
            continue
        
        try:
            # Import the module using absolute import path
            full_module_path = f'{__package__}.{module_name}'
            module = importlib.import_module(full_module_path)
            
            # Look for ContractDefinition instances (uppercase constants)
            for attr_name in dir(module):
                if attr_name.startswith('_'):
                    continue
                
                attr = getattr(module, attr_name)
                if isinstance(attr, ContractDefinition):
                    # Use contract_type value as the key
                    contract_name = attr.contract_type.value
                    contracts[contract_name] = attr
                    logger.debug(f"Loaded contract: {contract_name} from {module_name}")
                    break
            else:
                logger.warning(f"No ContractDefinition found in {module_name}")
                
        except Exception as e:
            logger.error(f"Failed to load contract from {module_name}: {e}", exc_info=True)
    
    return contracts


# Dynamically load all contracts
CONTRACTS: Dict[str, ContractDefinition] = _discover_contracts()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def build_contract_script(
    contract_name: str,
    params: Dict[str, Any],
    context: str = 'p2wsh'
) -> bytes:
    """
    Build a contract script from its definition.

    Args:
        contract_name: One of 'hodl', 'payment_channel', etc.
        params: Parameter values
        context: 'p2wsh' or 'tapscript'
        use_descriptors: If True, use Electrum descriptors instead of direct miniscript

    Returns:
        Compiled Bitcoin Script bytes

    Example:
        >>> script = build_contract_script(
        ...     'hodl',
        ...     {'locktime': 100, 'pubkey': pubkey_bytes},
        ...     context='p2wsh',
        ...     use_descriptors=True  # Use Electrum descriptor parsing
        ... )
    """
    if contract_name not in CONTRACTS:
        raise ValueError(f"Unknown contract: {contract_name}")

    return CONTRACTS[contract_name].compile(params, context)


def get_contract_miniscript(
    contract_name: str,
    style: str = 'symbolic'
) -> str:
    """
    Get the Miniscript expression for a contract.
    
    Args:
        contract_name: Contract name
        style: 'symbolic' or 'concrete'
    
    Returns:
        Miniscript expression string
    """
    if contract_name not in CONTRACTS:
        raise ValueError(f"Unknown contract: {contract_name}")
    
    return CONTRACTS[contract_name].get_miniscript(style)


def get_taproot_leaves(contract_name: str) -> List[str]:
    """
    Get the Taproot leaf scripts for a contract.
    
    Args:
        contract_name: Contract name
    
    Returns:
        List of Miniscript expressions for each leaf
    """
    if contract_name not in CONTRACTS:
        raise ValueError(f"Unknown contract: {contract_name}")
    
    contract = CONTRACTS[contract_name]
    if contract.taproot_leaves:
        return contract.taproot_leaves
    else:
        # Single-leaf: use the main miniscript
        return [contract.miniscript]

