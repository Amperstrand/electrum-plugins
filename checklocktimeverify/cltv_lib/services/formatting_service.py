"""
Formatting service for CLTV Plugin.

Provides centralized formatting functions for display, UI components,
and data presentation throughout the plugin.
"""

from typing import Optional, Tuple, Any
import logging

from .models import LockStatusInfo, LockStatus, OutputType
from .constants import LOCKED_STATUS, UNLOCKED_STATUS


logger = logging.getLogger(__name__)


class FormattingService:
    """
    Centralized service for all formatting operations.
    
    Handles:
    - Lock status computation and display
    - Amount formatting with optional fiat
    - Date/time formatting
    - Network status display
    """
    
    def __init__(self):
        """Initialize formatting service."""
        pass  # Could inject formatter configuration here
    
    def compute_lock_status(
        self,
        locktime: int,
        current_height: int
    ) -> LockStatusInfo:
        """
        Compute lock status information for CLTV address.
        
        Args:
            locktime: The CLTV locktime (block height or timestamp)
            current_height: Current blockchain height
            
        Returns:
            LockStatusInfo with lock details and formatted strings
        """
        locked = current_height < locktime
        blocks_remaining = max(0, locktime - current_height) if locktime else 0
        
        if locked:
            label = LOCKED_STATUS
            icon_name = "lock.png"
            tooltip = (
                f"CLTV locked until block {locktime:,}.\n"
                f"Current height: {current_height:,}.\n"
                f"Remaining: {blocks_remaining:,} block(s)."
            )
        else:
            label = UNLOCKED_STATUS
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
    
    def format_amount_with_fiat(
        self,
        amount_sat: int,
        fx_rate: Optional[float] = None,
        add_separator: bool = True,
        max_decimals: int = 8
    ) -> str:
        """
        Format Bitcoin amount with optional fiat conversion.
        
        Args:
            amount_sat: Amount in satoshis
            fx_rate: Fiat exchange rate (optional)
            add_separator: Add thousands separator (default: True)
            max_decimals: Maximum decimal places (default: 8)
            
        Returns:
            Formatted amount string (e.g., "0.00123456 BTC" or "0.00123456 BTC (≈ $45.50)")
        """
        # Format Bitcoin amount
        btc_str = self._format_btc_amount(amount_sat, max_decimals)
        
        # Add fiat if rate provided
        if fx_rate is not None:
            fiat_value = amount_sat * fx_rate / 100_000_000
            fiat_str = f" {fiat_value:.2f} USD"
            return f"{btc_str} (≈ {fiat_str})"
        else:
            return btc_str
    
    def _format_btc_amount(
        self,
        amount_sat: int,
        max_decimals: int = 8
    ) -> str:
        """
        Format satoshis to BTC with appropriate precision.
        
        Args:
            amount_sat: Amount in satoshis
            max_decimals: Maximum decimal places
            
        Returns:
            Formatted BTC string
        """
        btc = amount_sat / 100_000_000
        
        # Determine precision based on amount
        if btc < 0.00000001:
            precision = max_decimals
        elif btc < 0.000001:
            precision = max(2, max_decimals)
        elif btc < 0.00001:
            precision = max(3, max_decimals)
        elif btc < 0.001:
            precision = max(4, max_decimals)
        elif btc < 0.1:
            precision = max(5, max_decimals)
        else:
            precision = max(6, max_decimals)
        
        # Format with thousands separator
        format_str = "{:,." + f".{precision}f" if precision > 0 else "{:,d}"
        
        if add_separator:
            return f"{format_str} BTC"
        else:
            return f"{format_str} BTC"
    
    def format_network_status(
        self,
        network_name: str,
        is_connected: bool = True,
        current_height: int = 0,
        best_block_hash: Optional[str] = None,
        server_height: Optional[int] = None,
    ) -> str:
        """
        Format network status information for display.
        
        Args:
            network_name: Name of the network
            is_connected: Connection status
            current_height: Current blockchain height
            best_block_hash: Latest block hash
            server_height: Server-reported height
            
        Returns:
            Formatted status string
        """
        status_parts = [network_name.title()]
        
        if not is_connected:
            status_parts.append("(disconnected)")
        
        status_parts.append(f"@ {current_height:,}")
        
        if best_block_hash:
            status_parts.append(f"block: {best_block_hash[:12]}...")
        
        if server_height and server_height != current_height:
            status_parts.append(f"server: {server_height:,}")
        
        return " | ".join(status_parts)
    
    def format_timestamp(self, timestamp: int) -> str:
        """
        Format Unix timestamp to human-readable string.
        
        Args:
            timestamp: Unix timestamp
            
        Returns:
            Human-readable datetime string
        """
        from datetime import datetime
        
        dt = datetime.fromtimestamp(timestamp)
        
        # Format based on age
        now = datetime.now()
        delta = now - dt
        
        if delta.days > 365:
            return dt.strftime("%Y-%m-%d")
        elif delta.days > 0:
            return dt.strftime("%b %d, %Y")
        elif delta.seconds > 3600:
            return dt.strftime("%b %d, %H:%M")
        else:
            return dt.strftime("%H:%M")
    
    def format_bytes(self, size_bytes: int) -> str:
        """
        Format byte count to human-readable string.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string (e.g., "1.5 KB")
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            size_bytes /= 1024
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            else:
                size_bytes /= 1024
        
        return f"{size_bytes:.2f} B"
    
    def format_script_type(self, script_type: str) -> Tuple[str, str]:
        """
        Parse and format script type for display.
        
        Args:
            script_type: Script type identifier (e.g., 'cltv_escrow_taproot')
            
        Returns:
            Tuple of (contract_name, output_type)
        """
        # Remove prefix
        base = script_type.replace('cltv_', '')
        
        # Extract output type
        if 'taproot' in base:
            output = 'Taproot'
        elif 'p2wsh' in base:
            output = 'P2WSH'
        elif 'p2sh' in base:
            output = 'P2SH'
        else:
            output = 'Unknown'
        
        # Extract contract name
        contract = base.split('_')[0] if '_' in base else base
        
        return (contract, output)
    
    def truncate_address(self, address: str, max_length: int = 20) -> str:
        """
        Truncate address string for display.
        
        Args:
            address: Full address string
            max_length: Maximum length (default: 20)
            
        Returns:
            Truncated address with ellipsis
        """
        if len(address) <= max_length:
            return address
        
        return address[:max_length] + "..."


__all__ = [
    'FormattingService',
]