"""
Centralized constants for CLTV Plugin.

Eliminates magic strings and provides single source of truth
for all configuration values, enums, and version identifiers.
"""

from enum import Enum
from typing import Literal


class StorageVersion(str, Enum):
    """Storage format versions for wallet database compatibility."""
    
    V12_0_0 = "12.0.0"


class OutputType(str, Enum):
    """Bitcoin output types for CLTV scripts."""
    
    P2SH = "p2sh"
    P2WSH = "p2wsh"
    TAPROOT = "taproot"
    BARE = "bare"


class Network(str, Enum):
    """Bitcoin network names."""
    
    MAINNET = "mainnet"
    TESTNET = "testnet"
    TESTNET4 = "testnet4"
    SIGNET = "signet"
    REGTEST = "regtest"


class LockStatus(str, Enum):
    """Timelock status strings for UI display."""
    
    LOCKED = "Locked"
    UNLOCKED = "Unlocked"


# Storage version for current implementation
CURRENT_STORAGE_VERSION = StorageVersion.V12_0_0

# Plugin name for storage keys
PLUGIN_NAME = "checklocktimeverify"

# Script type prefix
SCRIPT_TYPE_PREFIX = "cltv_"

# Lock status strings for UI
LOCKED_STATUS = "Locked"
UNLOCKED_STATUS = "Unlocked"

# Output type string constants
OUTPUT_P2WSH = "p2wsh"
OUTPUT_TAPROOT = "taproot"


__all__ = [
    'StorageVersion',
    'OutputType',
    'Network',
    'LockStatus',
    'CURRENT_STORAGE_VERSION',
    'PLUGIN_NAME',
    'SCRIPT_TYPE_PREFIX',
    'LOCKED_STATUS',
    'UNLOCKED_STATUS',
    'OUTPUT_P2WSH',
    'OUTPUT_TAPROOT',
]