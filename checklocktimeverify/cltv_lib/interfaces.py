"""
Electrum-agnostic interfaces for CLTV core library.

Provides protocol definitions that allow cltv_lib to be
tested and used independently of Electrum framework while maintaining
compatibility when Electrum is available.
"""

from typing import Protocol, Union, List, Optional
from abc import ABC, abstractmethod


class CryptoInterface(Protocol):
    """Interface for cryptographic operations (hashing, signing)."""
    
    @abstractmethod
    def sha256(self, data: bytes) -> bytes:
        """Compute SHA256 hash of data."""
        pass
    
    @abstractmethod
    def hash160(self, data: bytes) -> bytes:
        """Compute RIPEMD160(SHA256(data)) hash."""
        pass
    
    @abstractmethod
    def sha256d(self, data: bytes) -> bytes:
        """Compute double SHA256 (SHA256(SHA256(data)))."""
        pass
    
    @abstractmethod
    def ripemd160(self, data: bytes) -> bytes:
        """Compute RIPEMD160 hash."""
        pass


class ScriptInterface(Protocol):
    """Interface for Bitcoin script operations."""
    
    @abstractmethod
    def construct_script(self, ops: List[int], push: bool = False) -> bytes:
        """Construct Bitcoin script from opcodes."""
        pass
    
    @abstractmethod
    def opcodes(self) -> dict:
        """Get available opcodes."""
        pass
    
    @abstractmethod
    def add_number_to_script(self, script: bytes, number: int) -> bytes:
        """Add number to script."""
        pass
    
    @abstractmethod
    def var_int(self, n: int) -> bytes:
        """Convert integer to 4-byte var_int."""
        pass
    
    @abstractmethod
    def script_num_to_bytes(self, n: int) -> bytes:
        """Convert script number to bytes."""
        pass


class NetworkInterface(Protocol):
    """Interface for blockchain network operations."""
    
    @abstractmethod
    def get_constants(self) -> dict:
        """Get network constants."""
        pass
    
    @abstractmethod
    def get_genesis_hash(self) -> str:
        """Get network genesis block hash."""
        pass
    
    @abstractmethod
    def get_network_name(self) -> str:
        """Get network name (mainnet, testnet, etc.)."""
        pass


__all__ = [
    'CryptoInterface',
    'ScriptInterface',
    'NetworkInterface',
]