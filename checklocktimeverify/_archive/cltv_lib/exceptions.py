"""
Custom exception hierarchy for CLTV Plugin.

Provides domain-specific exceptions that enable better error handling
and more precise error messages throughout the codebase.
"""

from typing import Optional, Any


class CLTVError(Exception):
    """Base exception for all CLTV plugin errors."""
    pass


class ValidationError(CLTVError):
    """Raised when input validation fails.
    
    Used when parameters, addresses, scripts, or other user input
    is invalid or malformed.
    """
    pass


class StorageError(CLTVError):
    """Raised when storage operations fail.
    
    Used when reading from or writing to wallet database fails,
    when address regeneration fails, or when data corruption is detected.
    """
    pass


class WalletError(CLTVError):
    """Raised when wallet integration operations fail.
    
    Used when wallet methods fail, when wallet is not available,
    or when wallet state is invalid for the requested operation.
    """
    pass


class NetworkError(CLTVError):
    """Raised when network operations fail.
    
    Used when blockchain queries fail, when network is unavailable,
    or when synchronization operations fail.
    """
    pass


class BuildError(CLTVError):
    """Raised when building contracts or addresses fails.
    
    Used when script construction fails, when miniscript compilation fails,
    or when address generation encounters unexpected conditions.
    """
    pass


class SweepError(CLTVError):
    """Raised when sweeping operations fail.
    
    Used when transaction construction fails, when signing fails,
    or when broadcast operations fail.
    """
    pass


class LockedError(CLTVError):
    """Raised when attempting to spend locked funds.
    
    Used when locktime constraints are not yet satisfied and spending
    would violate CLTV conditions.
    """
    pass


__all__ = [
    'CLTVError',
    'ValidationError',
    'StorageError',
    'WalletError',
    'NetworkError',
    'BuildError',
    'SweepError',
    'LockedError',
]