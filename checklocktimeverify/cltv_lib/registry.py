"""
CLTV Script Registry - Single Source of Truth

Central configuration for all supported CLTV script types.
All metadata derived from ContractDefinition - no duplication.

CANONICAL SCRIPT ID FORMAT:
    cltv_{contract_name}_{output_type}
    
    Examples:
    - cltv_hodl_p2wsh
    - cltv_hodl_taproot
    - cltv_escrow_p2wsh
    - cltv_escrow_taproot

NO ALIASES - only canonical names are supported.

Usage:
    >>> from cltv_lib.registry import get_config, get_script_id
    >>> 
    >>> # Get canonical script_id
    >>> script_id = get_script_id('hodl', 'p2wsh')  # 'cltv_hodl_p2wsh'
    >>> 
    >>> # Get config
    >>> config = get_config('cltv_hodl_p2wsh')
"""

from dataclasses import dataclass
from typing import Literal, Optional, List

from .contracts import CONTRACTS

OutputType = Literal['p2wsh', 'taproot']


@dataclass(frozen=True)
class ScriptConfig:
    """
    Configuration for a CLTV script type.
    
    All metadata derived from ContractDefinition.
    """
    script_id: str
    contract_name: str
    output_type: OutputType
    
    @property
    def miniscript(self) -> str:
        """Get miniscript from ContractDefinition (single source of truth)."""
        contract = CONTRACTS.get(self.contract_name)
        return contract.miniscript if contract else ''
    
    @property
    def description(self) -> str:
        """Get description from ContractDefinition."""
        contract = CONTRACTS.get(self.contract_name)
        output_suffix = ' (Taproot)' if self.output_type == 'taproot' else ' (P2WSH)'
        return (contract.description if contract else '') + output_suffix
    
    @property
    def contract(self):
        """Get the ContractDefinition."""
        return CONTRACTS.get(self.contract_name)


def get_script_id(contract_name: str, output_type: OutputType) -> str:
    """
    Generate canonical script_id from contract_name and output_type.
    
    This is the SINGLE SOURCE OF TRUTH for script_id format.
    
    Args:
        contract_name: Contract name (e.g., 'hodl', 'escrow')
        output_type: 'p2wsh' or 'taproot'
    
    Returns:
        Canonical script_id (e.g., 'cltv_hodl_p2wsh')
    
    Example:
        >>> get_script_id('hodl', 'p2wsh')
        'cltv_hodl_p2wsh'
        >>> get_script_id('escrow', 'taproot')
        'cltv_escrow_taproot'
    """
    return f"cltv_{contract_name}_{output_type}"


def parse_script_id(script_id: str) -> tuple:
    """
    Parse script_id into contract_name and output_type.
    
    Args:
        script_id: Canonical script_id (e.g., 'cltv_hodl_p2wsh')
    
    Returns:
        Tuple of (contract_name, output_type)
    
    Raises:
        ValueError: If script_id format is invalid
    """
    if not script_id.startswith('cltv_'):
        raise ValueError(f"Invalid script_id format: {script_id}")
    
    # Remove 'cltv_' prefix
    rest = script_id[5:]
    
    # Extract output_type from end
    if rest.endswith('_p2wsh'):
        output_type = 'p2wsh'
        contract_name = rest[:-6]
    elif rest.endswith('_taproot'):
        output_type = 'taproot'
        contract_name = rest[:-8]
    else:
        raise ValueError(f"Invalid script_id format: {script_id}")
    
    return contract_name, output_type


# ============================================================================
# Registry - Generated from CONTRACTS
# ============================================================================

def _build_registry() -> dict:
    """Build registry from ContractDefinition (single source of truth)."""
    registry = {}
    
    for contract_name, contract in CONTRACTS.items():
        # P2WSH variant
        p2wsh_id = get_script_id(contract_name, 'p2wsh')
        registry[p2wsh_id] = ScriptConfig(
            script_id=p2wsh_id,
            contract_name=contract_name,
            output_type='p2wsh'
        )
        
        # Taproot variant
        taproot_id = get_script_id(contract_name, 'taproot')
        registry[taproot_id] = ScriptConfig(
            script_id=taproot_id,
            contract_name=contract_name,
            output_type='taproot'
        )
    
    return registry


REGISTRY = _build_registry()


# ============================================================================
# Public API
# ============================================================================

def get_config(script_id: str) -> ScriptConfig:
    """
    Get configuration for a script ID.
    
    Args:
        script_id: Canonical script identifier (e.g., 'cltv_hodl_p2wsh')
    
    Returns:
        ScriptConfig for the script
    
    Raises:
        ValueError: If script_id is not found
    """
    if script_id not in REGISTRY:
        available = list(REGISTRY.keys())
        raise ValueError(
            f"Unknown script_id: {script_id}. "
            f"Available: {available}"
        )
    return REGISTRY[script_id]


def list_scripts(output_type: OutputType = None) -> List[str]:
    """
    List all available script IDs.
    
    Args:
        output_type: Filter by output type ('p2wsh' or 'taproot')
    
    Returns:
        List of script IDs
    """
    if output_type:
        return [
            sid for sid, config in REGISTRY.items()
            if config.output_type == output_type
        ]
    return list(REGISTRY.keys())


def get_builder(script_id: str, network: str = 'signet'):
    """
    Get a builder wrapper for a script type.
    
    Args:
        script_id: Script identifier
        network: Network name
    
    Returns:
        BuilderWrapper that can build addresses
    """
    config = get_config(script_id)
    
    from .builders.unified.generic import build_contract
    
    class BuilderWrapper:
        def __init__(self, contract_name, output_type, network):
            self.contract_name = contract_name
            self.output_type = output_type
            self.network = network
        
        def build(self, params: dict) -> dict:
            return build_contract(self.contract_name, params, self.output_type, self.network)
    
    return BuilderWrapper(config.contract_name, config.output_type, network)


def get_sweeper(script_id: str, path: str = None, **kwargs):
    """
    Get a sweeper for a script type.

    Args:
        script_id: Script identifier
        path: Spending path name
        **kwargs: Additional sweeper arguments

    Returns:
        GenericSweeper instance
    """
    from .sweepers.generic import GenericSweeper

    return GenericSweeper(
        script_id,  # script_type (positional)
        path=path,
        **kwargs
    )


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'ScriptConfig',
    'OutputType',
    'REGISTRY',
    'get_script_id',
    'parse_script_id',
    'get_config',
    'get_builder',
    'get_sweeper',
    'list_scripts',
]
