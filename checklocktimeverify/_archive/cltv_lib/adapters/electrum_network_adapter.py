"""
Electrum network operations adapter.

Delegates to electrum.bitcoin and electrum.constants modules
while implementing the NetworkInterface for dependency injection.
"""

from ..interfaces import NetworkInterface
import logging


logger = logging.getLogger(__name__)


class ElectrumNetworkAdapter(NetworkInterface):
    """Adapter for Electrum's network operations."""
    
    def get_constants(self) -> dict:
        """Get network constants."""
        try:
            from electrum.bitcoin import constants as electrum_constants
            return {
                'bitcoin': electrum_constants.bitcoin,
            }
        except Exception as e:
            logger.warning(f"[ADAPTER] Could not get network constants: {e}")
            return {}
    
    def get_genesis_hash(self) -> str:
        """Get network genesis block hash."""
        try:
            from electrum.bitcoin import constants as electrum_constants
            return electrum_constants.bitcoin.GENESIS
        except Exception as e:
            logger.warning(f"[ADAPTER] Could not get genesis hash: {e}")
            return ''
    
    def get_network_name(self) -> str:
        """Get network name (mainnet, testnet, etc.)."""
        try:
            from electrum.bitcoin import constants as electrum_constants
            return electrum_constants.net.NET_NAME
        except Exception as e:
            logger.warning(f"[ADAPTER] Could not get network name: {e}")
            return 'unknown'


__all__ = [
    'ElectrumNetworkAdapter',
]