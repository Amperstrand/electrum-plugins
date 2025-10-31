"""
Unified Registry - Single source of truth for script configurations

This module consolidates builder and sweeper registries into a single
configuration structure, preventing desync and improving maintainability.

Before (Task 3 refactoring):
    - script_builders/registry.py had BUILDERS dict
    - sweepers/registry.py had SWEEPERS dict
    - Risk: Keys could get out of sync

After:
    - Single SCRIPT_REGISTRY with complete configuration
    - Dataclass ensures all fields are present
    - get_builder() and get_sweeper() provide clean API
    - get_format() for format detection
    - get_config() for full configuration access

Design principles:
- DRY: Single definition for each script type
- Type safety: Dataclass with required fields
- Extensibility: Easy to add new script types
- Self-documenting: Description and examples included
"""

from dataclasses import dataclass
from typing import Type, Dict
from script_utils import ScriptFormat

# Import all builders - P2WSH only (Taproot removed - see taproot_tx_builder.py)
from script_builders.simple_cltv import SimpleCLTVBuilder as SimpleCLTVP2WSHBuilder
# from script_builders.simple_cltv_taproot import SimpleCLTVTaprootBuilder  # ARCHIVED
from script_builders.escrow_timeout import EscrowTimeoutBuilder as EscrowTimeoutP2WSHBuilder
# from script_builders.escrow_timeout_taproot import EscrowTimeoutTaprootBuilder  # ARCHIVED
from script_builders.twofactor import TwoFactorBuilder as TwoFactorP2WSHBuilder
# from script_builders.twofactor_taproot import TwoFactorTaprootBuilder  # ARCHIVED
from script_builders.payment_channel import PaymentChannelBuilder as PaymentChannelP2WSHBuilder
# from script_builders.payment_channel_taproot import PaymentChannelTaprootBuilder  # ARCHIVED
from script_builders.data_publishing import DataPublishingBuilder as DataPublishingP2WSHBuilder
# from script_builders.data_publishing_taproot import DataPublishingTaprootBuilder  # ARCHIVED
# from script_builders.miner_sacrifice_p2wsh import MinerSacrificeP2WSHBuilder  # NOT PART OF BIP-65 EXAMPLES
# from script_builders.miner_sacrifice_taproot import MinerSacrificeTaprootBuilder  # ARCHIVED

# Import all sweepers
from sweepers.simple_cltv import SimpleCLTVSweeper
from sweepers.escrow_timeout import EscrowTimeoutSweeper
from sweepers.escrow_dedicated import EscrowDedicatedSweeper  # Dedicated non-DRY version for debugging
from sweepers.twofactor import TwoFactorSweeper
from sweepers.payment_channel import PaymentChannelSweeper
from sweepers.data_publishing import DataPublishingSweeper
# from sweepers.miner_sacrifice import MinerSacrificeSweeper  # NOT PART OF BIP-65 EXAMPLES

# Import Taproot sweepers
from sweepers.taproot.simple_cltv_taproot import SimpleCLTVTaprootSweeper
from sweepers.taproot.twofactor_taproot import TaprootTwoFactorSweeper


@dataclass(frozen=True)
class ScriptConfig:
    """
    Complete configuration for a script type.
    
    Attributes:
        builder_class: Builder class for creating scripts
        sweeper_class: Sweeper class for spending from scripts
        format: Script format (P2SH, P2WSH) - Taproot removed
        description: Human-readable description
        example: Usage example or use case
        
    Example:
        >>> config = SCRIPT_REGISTRY['cltv_simple_p2wsh']
        >>> builder = config.builder_class()
        >>> sweeper = config.sweeper_class()
    """
    builder_class: Type
    sweeper_class: Type
    format: ScriptFormat
    description: str
    example: str


# ============================================================================
# Script Registry - Single Source of Truth
# ============================================================================

SCRIPT_REGISTRY = {
    # ========================================================================
    # Simple CLTV - Basic time-locked outputs
    # ========================================================================
    'cltv_simple_p2wsh': ScriptConfig(
        builder_class=SimpleCLTVP2WSHBuilder,
        sweeper_class=SimpleCLTVSweeper,
        format=ScriptFormat.P2WSH,
        description='Simple CLTV time-locked script (P2WSH)',
        example='Basic time lock - funds locked until block height (SegWit)'
    ),
    
    'cltv_simple_taproot': ScriptConfig(
        builder_class=None,  # Uses custom escrow_taproot builder
        sweeper_class=SimpleCLTVTaprootSweeper,
        format="taproot",
        description='Simple CLTV time-locked script (Taproot)',
        example='Basic time lock with Schnorr signatures (Taproot)'
    ),
    
    # ========================================================================
    # Escrow with Timeout - BIP-65 Example #1
    # ========================================================================
    'cltv_escrow_p2wsh': ScriptConfig(
        builder_class=EscrowTimeoutP2WSHBuilder,
        sweeper_class=EscrowDedicatedSweeper,  # Using dedicated sweeper for debugging
        format=ScriptFormat.P2WSH,
        description='Escrow with timeout (P2WSH)',
        example='2-of-2 cooperation or 1-of-2 refund after timeout (SegWit)'
    ),
    
    # ARCHIVED: 'cltv_escrow_taproot'
    
    # ========================================================================
    # Two-Factor Wallet - BIP-65 Example #3
    # ========================================================================
    'cltv_twofactor_p2wsh': ScriptConfig(
        builder_class=TwoFactorP2WSHBuilder,
        sweeper_class=TwoFactorSweeper,
        format=ScriptFormat.P2WSH,
        description='Two-factor wallet with recovery (P2WSH)',
        example='User+Service normal or User+Recovery after timeout (SegWit)'
    ),
    
    'cltv_twofactor_taproot': ScriptConfig(
        builder_class=None,  # Uses custom builder
        sweeper_class=TaprootTwoFactorSweeper,
        format="taproot",
        description='Two-factor wallet with recovery (Taproot)',
        example='User+Service normal or User+Recovery after timeout (Taproot)'
    ),
    
    # ========================================================================
    # Payment Channel - BIP-65 Example #4
    # ========================================================================
    'cltv_payment_channel_p2wsh': ScriptConfig(
        builder_class=PaymentChannelP2WSHBuilder,
        sweeper_class=PaymentChannelSweeper,
        format=ScriptFormat.P2WSH,
        description='Payment channel with refund (P2WSH)',
        example='Sender+Receiver cooperative or Sender refund after timeout (SegWit)'
    ),
    
    # ARCHIVED: 'cltv_payment_channel_taproot'
    
    # ========================================================================
    # Data Publishing - BIP-65 Example #5
    # ========================================================================
    'cltv_data_publishing_p2wsh': ScriptConfig(
        builder_class=DataPublishingP2WSHBuilder,
        sweeper_class=DataPublishingSweeper,
        format=ScriptFormat.P2WSH,
        description='Data publishing contract (PayPub) (P2WSH)',
        example='Publisher reveals preimage or Buyer refunds after timeout (SegWit)'
    ),
    
    # ARCHIVED: 'cltv_data_publishing_taproot'
}


# ============================================================================
# Registry API
# ============================================================================

def get_builder(script_type: str):
    """
    Get builder instance for script type.
    
    Args:
        script_type: Script type identifier (e.g., 'cltv_simple_hodl')
    
    Returns:
        Builder instance
    
    Raises:
        ValueError: If script_type is unknown
    
    Example:
        >>> builder = get_builder('cltv_simple_hodl')
        >>> script_hex = builder.build(params)
    """
    if script_type not in SCRIPT_REGISTRY:
        raise ValueError(
            f"Unknown script type: '{script_type}'\n"
            f"Valid types:\n" +
            '\n'.join(f"  - {t}" for t in SCRIPT_REGISTRY.keys())
        )
    
    return SCRIPT_REGISTRY[script_type].builder_class()


def get_sweeper(script_type: str, **kwargs):
    """
    Get sweeper instance for script type.
    
    Args:
        script_type: Script type identifier (e.g., 'cltv_simple_hodl')
        **kwargs: Additional arguments passed to sweeper constructor
                 (e.g., use_refund_path=True for escrow sweepers)
    
    Returns:
        Sweeper instance
    
    Raises:
        ValueError: If script_type is unknown
    
    Examples:
        >>> sweeper = get_sweeper('cltv_simple_hodl')
        >>> escrow_coop = get_sweeper('cltv_escrow_timeout', use_refund_path=False)
        >>> escrow_refund = get_sweeper('cltv_escrow_timeout', use_refund_path=True, refund_signer='alice')
    """
    if script_type not in SCRIPT_REGISTRY:
        raise ValueError(
            f"Unknown script type: '{script_type}'\n"
            f"Valid types:\n" +
            '\n'.join(f"  - {t}" for t in SCRIPT_REGISTRY.keys())
        )
    
    sweeper_class = SCRIPT_REGISTRY[script_type].sweeper_class
    return sweeper_class(**kwargs)


def get_format(script_type: str) -> ScriptFormat:
    """
    Get script format for script type.
    
    Args:
        script_type: Script type identifier
    
    Returns:
        ScriptFormat enum
    
    Raises:
        ValueError: If script_type is unknown
    
    Example:
        >>> fmt = get_format('cltv_simple_hodl')
        >>> assert fmt == ScriptFormat.P2SH
    """
    if script_type not in SCRIPT_REGISTRY:
        raise ValueError(f"Unknown script type: '{script_type}'")
    
    return SCRIPT_REGISTRY[script_type].format


def get_config(script_type: str) -> ScriptConfig:
    """
    Get complete configuration for script type.
    
    Args:
        script_type: Script type identifier
    
    Returns:
        ScriptConfig dataclass
    
    Raises:
        ValueError: If script_type is unknown
    
    Example:
        >>> config = get_config('cltv_simple_hodl')
        >>> print(config.description)
        >>> print(config.example)
    """
    if script_type not in SCRIPT_REGISTRY:
        raise ValueError(f"Unknown script type: '{script_type}'")
    
    return SCRIPT_REGISTRY[script_type]


def list_script_types() -> list[str]:
    """
    Get list of all available script types.
    
    Returns:
        List of script type identifiers
    
    Example:
        >>> types = list_script_types()
        >>> print(f"Available: {', '.join(types)}")
    """
    return list(SCRIPT_REGISTRY.keys())


def list_formats() -> list[ScriptFormat]:
    """
    Get list of all available formats.
    
    Returns:
        List of ScriptFormat enums
    
    Example:
        >>> formats = list_formats()
        >>> assert ScriptFormat.P2SH in formats
    """
    return list(set(config.format for config in SCRIPT_REGISTRY.values()))


# ============================================================================
# Convenience Functions (for backward compatibility with tests)
# ============================================================================

def build_script(script_type: str, params: dict) -> str:
    """
    Build script from type and parameters (deterministic).
    
    This is a convenience wrapper around get_builder() for tests.
    
    Args:
        script_type: Script type identifier
        params: Type-specific parameters
    
    Returns:
        Hex-encoded script
    
    Example:
        >>> params = {"locktime": 107332, "pubkey": "0279be66..."}
        >>> script_hex = build_script("cltv_simple_hodl", params)
    """
    builder = get_builder(script_type)
    script_bytes = builder.build(params)
    return script_bytes.hex()


def verify_script(script_type: str, params: dict, expected_hex: str) -> bool:
    """
    Verify that script_hex matches what we'd build from params.
    
    Args:
        script_type: Script type identifier
        params: Parameters to build from
        expected_hex: Expected script hex
    
    Returns:
        True if script matches, False otherwise
    """
    try:
        rebuilt_hex = build_script(script_type, params)
        return rebuilt_hex.lower() == expected_hex.lower()
    except Exception:
        return False


# ============================================================================
# Registry Validation
# ============================================================================

def validate_registry():
    """
    Validate registry configuration for consistency.
    
    Checks:
        - All required fields are present
        - Builder and sweeper classes are valid
        - No duplicate keys
        - All formats are supported
    
    Raises:
        AssertionError: If validation fails
    
    This is called automatically on import to catch configuration errors early.
    """
    # Check all entries have required fields
    for script_type, config in SCRIPT_REGISTRY.items():
        # Builder can be None for Taproot (uses custom builders)
        if config.format != "taproot":
            assert config.builder_class is not None, f"Missing builder for {script_type}"
        assert config.sweeper_class is not None, f"Missing sweeper for {script_type}"
        assert config.format is not None, f"Missing format for {script_type}"
        assert config.description, f"Missing description for {script_type}"
        assert config.example, f"Missing example for {script_type}"
    
    # Check all formats are represented
    formats = set(config.format for config in SCRIPT_REGISTRY.values())
    expected_formats = {ScriptFormat.P2WSH, "taproot"}
    assert formats.issubset(expected_formats), f"Unexpected formats: {formats - expected_formats}"
    
    print(f"✓ Registry validated: {len(SCRIPT_REGISTRY)} script types, {len(formats)} formats")


# Validate on import
validate_registry()
