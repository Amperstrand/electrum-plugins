"""
CLTV Library - Production Bitcoin CLTV Script Generation

Clean, battle-tested library for generating and spending CHECKLOCKTIMEVERIFY
(BIP-65) timelock scripts. Extracted from 20 passing end-to-end tests.

Supports:
- P2WSH (Pay-to-Witness-Script-Hash) - SegWit v0
- Taproot - SegWit v1
- NO P2SH (deprecated and removed)

Features:
- Single source of truth via ContractDefinition
- Generic build_contract() for all contract types
- Unified sweepers for both P2WSH and Taproot
- First-class Miniscript/Descriptor support
- Clean, simple API

Quick Start:
    >>> from cltv_lib.builders.unified import build_contract
    >>> 
    >>> # Build any contract
    >>> result = build_contract('escrow', {
    ...     'locktime': 600000,
    ...     'alice': '02abc...',
    ...     'bob': '03def...',
    ...     'lenny': '02ghi...',
    ... }, output_type='taproot', network='signet')
    >>> 
    >>> print(result['address'])
    'tb1p...'

Script Types (BIP-65 Examples):
    1. hodl - Single-sig timelock
    2. escrow - Three-party arbitration
    3. twofactor - 2FA wallet with recovery
    4. payment_channel - Cooperative close with refund
    5. data_publishing - PayPub contract

For detailed documentation, see CLTV_LIBRARY_API.md
"""

__version__ = '3.2.0'  # Full E2E alignment + version-based storage purge

# ============================================================================
# Core Registry API
# ============================================================================

from .registry import (
    get_config,
    get_builder,
    get_sweeper,
    list_scripts,
    REGISTRY,
    ScriptConfig,
)

# Import build_contract from its actual location
from .builders.unified.generic import build_contract

# ============================================================================
# Address Generation
# ============================================================================

from .address import (
    generate_address,
    generate_p2wsh_address,
    generate_taproot_address,
)

# ============================================================================
# Descriptors (Miniscript + Bitcoin Descriptors)
# ============================================================================

from .descriptors import (
    get_miniscript,
    get_descriptor,
)

# ============================================================================
# Builders (unified - single builder for all contracts)
# ============================================================================

from .builders import (
    # Base classes
    ScriptBuilder,
    BuildError,
    # Unified builder
    UnifiedContractBuilder,
)

# ============================================================================
# Sweepers (unified - handle both P2WSH and Taproot)
# ============================================================================

from .sweepers import (
    # Base classes
    SweeperStrategy,
    SweepError,
    # Generic Sweeper (handles all contract types)
    GenericSweeper,
    sweep_output,
    get_required_keys,
    validate_sweep_conditions,
    build_witness,
    LockedError,
    ValidationError,
)

# ============================================================================
# Contract Helper (unified interface for all contract operations)
# ============================================================================

from .contract_helper import ContractHelper

# ============================================================================
# Signing (Bitcoin Core SignatureData pattern)
# ============================================================================

from .signature_data import SignatureData

# ============================================================================
# Public API
# ============================================================================

__all__ = [
    # Version
    '__version__',
    
    # Core Registry API (most users start here)
    'get_config',
    'get_builder',
    'get_sweeper',
    'list_scripts',
    'REGISTRY',
    'ScriptConfig',
    'build_contract',  # The main entry point
    
    # Address Generation
    'generate_address',
    'generate_p2wsh_address',
    'generate_taproot_address',
    
    # Descriptors (Miniscript + Bitcoin Descriptors)
    'get_miniscript',
    'get_descriptor',
    
    # Builders
    'ScriptBuilder',
    'BuildError',
    'UnifiedContractBuilder',
    
    # Sweepers (generic - handles all contract types)
    'SweeperStrategy',
    'SweepError',
    'GenericSweeper',
    'sweep_output',
    'get_required_keys',
    'validate_sweep_conditions',
    'build_witness',
    'LockedError',
    'ValidationError',
    
    # Contract Helper (unified interface)
    'ContractHelper',
    
    # Signing (Bitcoin Core pattern)
    'SignatureData',
    
    ]
