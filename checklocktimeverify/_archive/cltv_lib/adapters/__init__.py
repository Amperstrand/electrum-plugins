"""
Electrum-agnostic adapters for CLTV core library.

Provides adapter classes that implement the protocol interfaces
and delegate to Electrum's actual implementations.

This allows:
- Testing cltv_lib with mock adapters
- Framework substitution (e.g., using bitcoinlib instead of Electrum)
- Electrum-agnostic core while maintaining compatibility
"""

from .interfaces import CryptoInterface, ScriptInterface, NetworkInterface
from .electrum_crypto_adapter import ElectrumCryptoAdapter
from .electrum_script_adapter import ElectrumScriptAdapter
from .electrum_network_adapter import ElectrumNetworkAdapter


__all__ = [
    # Interfaces
    'CryptoInterface',
    'ScriptInterface',
    'NetworkInterface',
    
    # Adapters
    'ElectrumCryptoAdapter',
    'ElectrumScriptAdapter',
    'ElectrumNetworkAdapter',
]