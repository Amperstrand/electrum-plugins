"""
Electrum crypto operations adapter.

Delegates to electrum.crypto and electrum.bitcoin modules
while implementing the CryptoInterface for dependency injection.
"""

from ..interfaces import CryptoInterface
import logging


logger = logging.getLogger(__name__)


class ElectrumCryptoAdapter(CryptoInterface):
    """Adapter for Electrum's crypto operations."""
    
    def sha256(self, data: bytes) -> bytes:
        """Compute SHA256 hash of data."""
        from electrum.crypto import sha256 as electrum_sha256
        return electrum_sha256(data)
    
    def hash160(self, data: bytes) -> bytes:
        """Compute RIPEMD160(SHA256(data)) hash."""
        from electrum.crypto import hash_160 as electrum_hash160
        return electrum_hash160(data)
    
    def sha256d(self, data: bytes) -> bytes:
        """Compute double SHA256 (SHA256(SHA256(data)))."""
        from electrum.crypto import sha256 as electrum_sha256
        return electrum_sha256(electrum_sha256(data))
    
    def ripemd160(self, data: bytes) -> bytes:
        """Compute RIPEMD160 hash."""
        from electrum.crypto import ripemd as electrum_ripemd
        return electrum_ripemd(data)


__all__ = [
    'ElectrumCryptoAdapter',
]