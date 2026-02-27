"""
Typed data models for CLTV Plugin.

Provides dataclasses and TypedDict for common data structures
to improve type safety and reduce dictionary key typos.
"""

from dataclasses import dataclass, field
from typing import TypedDict, List, Dict, Optional, Any
from datetime import datetime
from .constants import StorageVersion, OutputType, Network, LockStatus, SCRIPT_TYPE_PREFIX
from .exceptions import ValidationError


@dataclass
class AddressRecord:
    """Typed model for a CLTV address record.
    
    Replaces dictionary-based storage with type-safe fields.
    """
    
    # Core identification
    address: str
    script_type: str
    output_type: OutputType
    
    # Contract parameters (depends on script_type)
    params: Dict[str, Any]
    
    # Generated data (from regeneration)
    script_hex: Optional[str] = None
    witness_script: Optional[str] = None  # For P2WSH
    taproot_script: Optional[str] = None  # For Taproot
    control_blocks: Optional[List[str]] = None  # For Taproot
    merkle_root: Optional[str] = None  # For Taproot
    
    # Metadata
    created_at: int
    updated_at: Optional[int] = None
    label: Optional[str] = None
    key_source: Optional[str] = None
    
    # Lock status
    lock_status: LockStatus = LockStatus.LOCKED
    current_height: int = 0
    locktime: int = 0
    blocks_remaining: int = 0
    
    def is_taproot(self) -> bool:
        """Check if this is a Taproot address."""
        return self.output_type == OutputType.TAPROOT
    
    def is_p2wsh(self) -> bool:
        """Check if this is a P2WSH address."""
        return self.output_type == OutputType.P2WSH
    
    def is_locked(self, current_height: int) -> bool:
        """Check if address is locked at current height."""
        if not self.locktime:
            return False
        return current_height < self.locktime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage compatibility."""
        return {
            'address': self.address,
            'script_type': self.script_type,
            'output_type': self.output_type.value if isinstance(self.output_type, OutputType) else self.output_type,
            'params': self.params,
            'script_hex': self.script_hex,
            'witness_script': self.witness_script,
            'taproot_script': self.taproot_script,
            'control_blocks': self.control_blocks,
            'merkle_root': self.merkle_root,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'label': self.label,
            'key_source': self.key_source,
        }


@dataclass
class LockStatusInfo:
    """Typed model for lock status computation.
    
    Provides consistent structure for lock status calculations.
    """
    
    locked: bool
    blocks_remaining: int
    current_height: int
    icon_name: Optional[str] = None
    label: str
    tooltip: str
    
    @classmethod
    def from_height(cls, locktime: int, current_height: int) -> 'LockStatusInfo':
        """Create LockStatusInfo from height comparison."""
        locked = current_height < locktime
        blocks_remaining = max(0, locktime - current_height) if locktime else 0
        
        if locked:
            label = LockStatus.LOCKED
            icon_name = "lock.png"
            tooltip = (
                f"CLTV locked until block {locktime:,}.\n"
                f"Current height: {current_height:,}.\n"
                f"Remaining: {blocks_remaining:,} block(s)."
            )
        else:
            label = LockStatus.UNLOCKED
            icon_name = None
            tooltip = (
                f"CLTV unlocked.\n"
                f"Current height: {current_height:,}.\n"
                f"Required locktime was: {locktime:,}."
            )
        
        return LockStatusInfo(
            locked=locked,
            blocks_remaining=blocks_remaining,
            current_height=current_height,
            icon_name=icon_name,
            label=label,
            tooltip=tooltip,
        )


@dataclass
class SweepResult:
    """Typed model for sweep operation results.
    
    Provides consistent structure for sweep operations across all contract types.
    """
    
    success: bool
    txid: Optional[str] = None
    tx_hex: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    broadcast_height: Optional[int] = None
    broadcast_timestamp: Optional[int] = None
    
    # Input/output tracking
    inputs_count: int = 0
    outputs_count: int = 0
    fee_paid: int = 0
    
    # Context
    address_swept: Optional[str] = None
    path_used: Optional[str] = None  # 'cooperative', 'recovery', 'timeout'
    
    @classmethod
    def success_result(cls, txid: str, tx_hex: str = "", 
                     inputs_count: int = 0, outputs_count: int = 0,
                     fee_paid: int = 0, address_swept: str = "",
                     path_used: str = "", broadcast_height: int = 0) -> 'SweepResult':
        """Create successful sweep result."""
        return SweepResult(
            success=True,
            txid=txid,
            tx_hex=tx_hex,
            inputs_count=inputs_count,
            outputs_count=outputs_count,
            fee_paid=fee_paid,
            address_swept=address_swept,
            path_used=path_used,
            broadcast_height=broadcast_height,
            broadcast_timestamp=int(datetime.now().timestamp()),
        )
    
    @classmethod
    def error_result(cls, error_message: str, error_code: str = "") -> 'SweepResult':
        """Create failed sweep result."""
        return SweepResult(
            success=False,
            error_message=error_message,
            error_code=error_code,
        )


@dataclass
class NetworkInfo:
    """Typed model for network information.
    
    Provides consistent structure for network status across plugin.
    """
    
    network_name: Network
    current_height: int
    best_block_hash: Optional[str] = None
    is_connected: bool = True
    server_height: Optional[int] = None
    
    @classmethod
    def offline(cls, network_name: Network = Network.MAINNET) -> 'NetworkInfo':
        """Create offline network info."""
        return NetworkInfo(
            network_name=network_name,
            current_height=0,
            is_connected=False,
        )


@dataclass
class StorageMetadata:
    """Typed model for storage metadata.
    
    Provides consistent structure for wallet database storage.
    """
    
    version: StorageVersion
    plugin_name: str
    address_count: int
    
    @classmethod
    def current(cls) -> 'StorageMetadata':
        """Create metadata for current version."""
        return StorageMetadata(
            version=StorageVersion.CURRENT_STORAGE_VERSION,
            plugin_name="checklocktimeverify",
            address_count=0,
        )


# Helper functions for backward compatibility
def address_record_from_dict(data: Dict[str, Any]) -> AddressRecord:
    """
    Convert dictionary to AddressRecord for backward compatibility.
    
    Args:
        data: Dictionary from storage
        
    Returns:
        AddressRecord instance
        
    Raises:
        ValidationError: If required fields are missing
    """
    # Validate required fields
    if 'address' not in data:
        raise ValidationError("Missing required field: address")
    if 'script_type' not in data:
        raise ValidationError("Missing required field: script_type")
    if 'params' not in data:
        raise ValidationError("Missing required field: params")
    
    # Parse output_type from script_type if not present
    output_type = data.get('output_type')
    if not output_type:
        # Extract from script_type (e.g., 'cltv_escrow_taproot' -> 'taproot')
        script_type = data.get('script_type', '')
        if 'taproot' in script_type.lower():
            output_type = OutputType.TAPROOT
        elif 'p2wsh' in script_type.lower():
            output_type = OutputType.P2WSH
        else:
            output_type = OutputType.P2SH
    
    # Create AddressRecord
    return AddressRecord(
        address=data['address'],
        script_type=data['script_type'],
        output_type=output_type,
        params=data['params'],
        script_hex=data.get('script_hex'),
        witness_script=data.get('witness_script'),
        taproot_script=data.get('taproot_script'),
        control_blocks=data.get('control_blocks'),
        merkle_root=data.get('merkle_root'),
        created_at=data.get('created_at', int(datetime.now().timestamp())),
        updated_at=data.get('updated_at'),
        label=data.get('label'),
        key_source=data.get('key_source'),
        lock_status=LockStatus.LOCKED,
        locktime=data.get('params', {}).get('locktime', 0),
    )


def validate_address_record(record: AddressRecord) -> None:
    """
    Validate an AddressRecord for correctness.
    
    Args:
        record: AddressRecord to validate
        
    Raises:
        ValidationError: If record is invalid
    """
    # Validate address format (basic checks)
    if not record.address or len(record.address) < 10:
        raise ValidationError(f"Invalid address: {record.address}")
    
    # Validate script_type has cltv_ prefix
    if not record.script_type.startswith(SCRIPT_TYPE_PREFIX):
        raise ValidationError(f"Invalid script_type: {record.script_type} (must start with '{SCRIPT_TYPE_PREFIX}')")
    
    # Validate locktime if present
    if record.locktime < 0:
        raise ValidationError(f"Invalid locktime: {record.locktime} (must be >= 0)")
    
    # Validate params is not empty
    if not record.params:
        raise ValidationError("Params dictionary cannot be empty")


__all__ = [
    'AddressRecord',
    'LockStatusInfo',
    'SweepResult',
    'NetworkInfo',
    'StorageMetadata',
    'address_record_from_dict',
    'validate_address_record',
]