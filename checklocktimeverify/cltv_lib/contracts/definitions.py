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

HODL = ContractDefinition(
    contract_type=ContractType.HODL,
    name="HODL",
    description="Time-locked single signature. Funds locked until locktime.",
    miniscript="and_v(after_drop(locktime), c:pk(pubkey))",
    params=[
        ParamSpec("locktime", "Block height when funds unlock"),
        ParamSpec("pubkey", "Owner's public key", test_key_name="hodl"),
    ],
    taproot_leaves=["and_v(after_drop(locktime), c:pk(pubkey))"],
    
    # UI metadata
    bip_reference="BIP-65 Basic Example",
    short_description="Lock funds until a specific block height",
    use_cases=["Long-term savings", "HODL commitment", "Time-delayed inheritance"],
    icon="⏰",
    
    paths=[
        SpendingPath(
            name="sweep",
            display_name="Sweep Funds",
            description="Spend funds after the locktime has passed",
            requires_locktime=True,
            required_keys=["pubkey"],
            is_cooperative=False,
            leaf_index=0,
        ),
    ],
    
    key_roles=[
        KeyRole("pubkey", "Owner", "The key that can spend after locktime", "👤"),
    ],
)


PAYMENT_CHANNEL = ContractDefinition(
    contract_type=ContractType.PAYMENT_CHANNEL,
    name="Payment Channel",
    description="Bi-directional payment channel with timeout refund.",
    miniscript="or_i(multi(2, sender, receiver), and_v(after_drop(locktime), c:pk(sender)))",
    params=[
        ParamSpec("locktime", "Block height after which sender can refund"),
        ParamSpec("sender", "Sender's public key (funds the channel)", param_type="pubkey", test_key_name="sender"),
        ParamSpec("receiver", "Receiver's public key (receives payments)", param_type="pubkey", test_key_name="receiver"),
    ],
    # param_mapping removed in v12.0.0 - storage uses miniscript names directly
    taproot_leaves=[
        "multi_a(2, sender, receiver)",  # Cooperative close - CHECKSIGADD-based multisig (BIP-342)
        "and_v(after_drop(locktime), c:pk(sender))",  # Timeout refund
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #4: Payment Channel",
    short_description="Bi-directional payment channel with refund timeout",
    use_cases=["Micro-payments", "Streaming payments", "Off-chain transactions"],
    icon="💸",
    
    paths=[
        SpendingPath(
            name="cooperative",
            display_name="Cooperative Close",
            description="Both sender and receiver agree to close the channel",
            requires_locktime=False,
            required_keys=["sender", "receiver"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="refund",
            display_name="Sender Refund",
            description="Sender reclaims funds after timeout (receiver unresponsive)",
            requires_locktime=True,
            required_keys=["sender"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("sender", "Sender", "The party funding the channel", "📤"),
        KeyRole("receiver", "Receiver", "The party receiving payments", "📥"),
    ],
)


ESCROW = ContractDefinition(
    contract_type=ContractType.ESCROW,
    name="Escrow with Timeout",
    description="3-party escrow: Alice/Bob 2-of-2, or Lenny arbitration after timeout.",
    miniscript="or_i(multi(2, alice, bob), and_v(after_drop(locktime), and_v(v:c:pk(lenny), multi(1, alice, bob))))",
    params=[
        ParamSpec("locktime", "Block height when arbitration becomes available"),
        ParamSpec("alice", "Alice's public key (party A)", param_type="pubkey", test_key_name="alice"),
        ParamSpec("bob", "Bob's public key (party B)", param_type="pubkey", test_key_name="bob"),
        ParamSpec("lenny", "Lenny's public key (arbiter)", param_type="pubkey", test_key_name="lenny"),
    ],
    # param_mapping removed in v12.0.0 - storage uses miniscript names directly
    taproot_leaves=[
        "multi_a(2, alice, bob)",  # Normal: 2-of-2 CHECKSIGADD-based multisig (BIP-342)
        "and_v(after_drop(locktime), and_v(v:c:pk(lenny), multi_a(1, alice, bob)))",  # Arbitration
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #1: Escrow with Timeout",
    short_description="3-party escrow with arbitration after timeout",
    use_cases=["Marketplace escrow", "Dispute resolution", "Trust-minimized trades"],
    icon="🤝",
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (Alice + Bob)",
            description="Both parties agree on the outcome",
            requires_locktime=False,
            required_keys=["alice", "bob"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="arbitration_alice",
            display_name="Arbitration (Lenny + Alice)",
            description="Arbiter sides with Alice after timeout",
            requires_locktime=True,
            # Stack order: [alice_sig, lenny_sig] (lenny consumed first from top)
            required_keys=["alice", "lenny"],
            is_cooperative=False,
            leaf_index=1,
        ),
        SpendingPath(
            name="arbitration_bob",
            display_name="Arbitration (Lenny + Bob)",
            description="Arbiter sides with Bob after timeout",
            requires_locktime=True,
            # Stack order: [bob_sig, lenny_sig] (lenny consumed first from top)
            required_keys=["bob", "lenny"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("alice", "Alice", "First party (e.g., buyer)", "👤"),
        KeyRole("bob", "Bob", "Second party (e.g., seller)", "👥"),
        KeyRole("lenny", "Lenny", "Neutral arbiter", "⚖️"),
    ],
)


TWOFACTOR = ContractDefinition(
    contract_type=ContractType.TWOFACTOR,
    name="Two-Factor Wallet",
    description="2FA with service co-signer, user-only recovery after timeout.",
    miniscript="or_i(and_v(v:c:pk(service), c:pk(user)), and_v(after_drop(locktime), c:pk(user)))",
    params=[
        ParamSpec("locktime", "Block height when recovery becomes available"),
        ParamSpec("user", "User's public key (your key)", param_type="pubkey", test_key_name="user"),
        ParamSpec("service", "Service's public key (2FA provider)", param_type="pubkey", test_key_name="service"),
    ],
    # param_mapping removed in v12.0.0 - storage uses miniscript names directly
    taproot_leaves=[
        "and_v(v:c:pk(service), c:pk(user))",  # Normal: 2-of-2
        "and_v(after_drop(locktime), c:pk(user))",  # Recovery
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #3: Two-Factor Wallet",
    short_description="2FA spending with emergency recovery after timeout",
    use_cases=["Secure wallet", "Business continuity", "Lost device recovery"],
    icon="🔐",
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (User + Service)",
            description="Both user and 2FA service sign together",
            requires_locktime=False,
            # Stack order: [user_sig, service_sig] (service consumed first from top)
            required_keys=["user", "service"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="recovery",
            display_name="Recovery (User Only)",
            description="User alone after timeout (if service unavailable)",
            requires_locktime=True,
            required_keys=["user"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("user", "User", "Your personal key", "👤"),
        KeyRole("service", "Service", "2FA provider's key", "🏢"),
    ],
)


DATA_PUBLISHING = ContractDefinition(
    contract_type=ContractType.DATA_PUBLISHING,
    name="Data Publishing (PayPub)",
    description="Hash-locked data reveal or buyer refund after timeout.",
    miniscript="or_i(and_v(hash160_simple(data_hash), c:pk(publisher)), and_v(after_drop(locktime), c:pk(buyer)))",
    params=[
        ParamSpec("locktime", "Block height when buyer can refund"),
        ParamSpec("publisher", "Publisher's public key", param_type="pubkey", test_key_name="publisher"),
        ParamSpec("buyer", "Buyer's public key", param_type="pubkey", test_key_name="buyer"),
        ParamSpec("data_hash", "HASH160 of the data (derived from preimage)", param_type="hash160"),
        # data_preimage is special: not in script, but needed for spending
        ParamSpec(
            "data_preimage",
            "The actual data (reveals on-chain when claiming)",
            param_type="preimage",
            required=False,  # Only needed for publisher path
            sensitive=True,  # Should be hidden in UI
        ),
    ],
    # param_mapping removed in v12.0.0 - storage uses miniscript names directly
    taproot_leaves=[
        "and_v(hash160_simple(data_hash), c:pk(publisher))",  # Reveal
        "and_v(after_drop(locktime), c:pk(buyer))",  # Refund
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #5: Data Publishing (PayPub)",
    short_description="Pay for data: Publisher reveals preimage to claim, or buyer refunds",
    use_cases=["Paid data release", "Encryption key sale", "Trustless data exchange"],
    icon="📝",
    
    paths=[
        SpendingPath(
            name="publisher",
            display_name="Claim (Publisher)",
            description="Publisher reveals data preimage to claim payment",
            requires_locktime=False,
            required_keys=["publisher"],
            is_cooperative=True,
            requires_preimage=True,
            warning="⚠️ This will reveal your data on the blockchain permanently!",
            leaf_index=0,
        ),
        SpendingPath(
            name="buyer_refund",
            display_name="Refund (Buyer)",
            description="Buyer reclaims funds if data not revealed by timeout",
            requires_locktime=True,
            required_keys=["buyer"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("publisher", "Publisher", "Sells the data", "📤"),
        KeyRole("buyer", "Buyer", "Pays for the data", "💰"),
    ],
)


# =============================================================================
# TRIDENT VAULT (AnchorWatch-style)
# =============================================================================
# 
# Inspired by AnchorWatch's insured vault model:
# - Multiple customer keys (2-of-3)
# - Multiple service keys (2-of-3)
# - Recovery partner key
# - Timelocked phases for different spending conditions
#
# Uses BIP-112 relative timelocks (older/CSV) for phase transitions.
# This is a simplified 2-phase version; production would have 4 phases.
#
# Reference: https://anchorwatch.com/faq
# =============================================================================

TRIDENT_VAULT = ContractDefinition(
    contract_type=ContractType.TRIDENT_VAULT,
    name="Trident Vault",
    description="AnchorWatch-style insured vault with timelocked recovery phases.",
    # Simplified 2-phase policy:
    # Phase 1 (immediate): Customer 2-of-3 AND Service 2-of-3
    # Phase 2 (after timeout): Customer 2-of-3 alone (self-custody)
    #
    # Full Trident would have 4 phases with recovery partner, but this
    # demonstrates the core pattern using our miniscript compiler.
    #
    # NOTE: Uses 'locktime' as param name for UI compatibility, even though
    # this is a relative timelock (CSV/older). The value represents blocks
    # since the UTXO was confirmed, not an absolute block height.
    miniscript="or_d(and_v(thresh(2, c:pk(C1), c:pk(C2), c:pk(C3)), thresh(2, c:pk(S1), c:pk(S2), c:pk(S3))), and_v(older(locktime), thresh(2, c:pk(C1), c:pk(C2), c:pk(C3))))",
    params=[
        ParamSpec("locktime", "Blocks until self-custody recovery (relative, e.g., 54000 ≈ 1 year)"),
        ParamSpec("C1", "Customer key 1", param_type="pubkey", test_key_name="alice"),
        ParamSpec("C2", "Customer key 2", param_type="pubkey", test_key_name="bob"),
        ParamSpec("C3", "Customer key 3", param_type="pubkey", test_key_name="lenny"),
        ParamSpec("S1", "Service key 1 (e.g., AnchorWatch)", param_type="pubkey", test_key_name="service"),
        ParamSpec("S2", "Service key 2", param_type="pubkey", test_key_name="user"),
        ParamSpec("S3", "Service key 3", param_type="pubkey", test_key_name="publisher"),
    ],
    taproot_leaves=[
        # Leaf 0: Immediate - Customer 2-of-3 AND Service 2-of-3
        # NOTE: For Tapscript, use multi_a() which compiles to OP_CHECKSIGADD
        # (thresh(2, c:pk(...)) compiles to OP_CHECKSIG + OP_ADD which is P2WSH-style)
        "and_v(multi_a(2, C1, C2, C3), multi_a(2, S1, S2, S3))",
        # Leaf 1: Recovery - After timeout, Customer 2-of-3 alone
        "and_v(older(locktime), multi_a(2, C1, C2, C3))",
    ],
    
    # UI metadata
    bip_reference="BIP-112 CSV + Threshold Multisig",
    short_description="Insured vault with timelocked self-custody recovery",
    use_cases=[
        "Institutional custody with insurance",
        "Key recovery without third-party trust after timeout",
        "Collaborative custody with escape hatch",
    ],
    icon="🔱",  # Trident!
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (Customer + Service)",
            description="Both customer (2-of-3) and service (2-of-3) must sign",
            requires_locktime=False,
            # Need 2 customer sigs + 2 service sigs
            # In thresh witness order: C sigs first, then S sigs
            required_keys=["C1", "C2", "S1", "S2"],  # Example: 2 of each
            is_cooperative=True,
            leaf_index=0,
            icon="🤝",
        ),
        SpendingPath(
            name="recovery",
            display_name="Self-Custody Recovery",
            description="After timeout, customer can recover without service",
            requires_locktime=True,
            required_keys=["C1", "C2"],  # Only need 2 customer keys
            is_cooperative=False,
            leaf_index=1,
            icon="🔓",
        ),
    ],
    
    key_roles=[
        KeyRole("C1", "Customer Key 1", "First key in your 2-of-3 set", "👤"),
        KeyRole("C2", "Customer Key 2", "Second key in your 2-of-3 set", "👤"),
        KeyRole("C3", "Customer Key 3", "Third key in your 2-of-3 set", "👤"),
        KeyRole("S1", "Service Key 1", "First key from custody service", "🏢"),
        KeyRole("S2", "Service Key 2", "Second key from custody service", "🏢"),
        KeyRole("S3", "Service Key 3", "Third key from custody service", "🏢"),
    ],
)


# =============================================================================
# REGISTRY
# =============================================================================

CONTRACTS: Dict[str, ContractDefinition] = {
    'hodl': HODL,
    'payment_channel': PAYMENT_CHANNEL,
    'escrow': ESCROW,
    'twofactor': TWOFACTOR,
    'data_publishing': DATA_PUBLISHING,
    # DISABLED: Trident Vault uses relative timelocks (CSV/BIP-112) which require
    # a larger refactoring of the codebase. All other contracts use absolute
    # timelocks (CLTV/BIP-65). See docs/TIMELOCK_REFACTORING_PLAN.md for details.
    # 'trident_vault': TRIDENT_VAULT,
}


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

