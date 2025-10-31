"""
Script Builders Module - Deterministic CLTV Script Generation

This module provides deterministic script building for all CLTV variants.
Given the same parameters, always produces the same script_hex.

Key principle: params → script_hex (deterministic, bijective)

Usage:
    from script_builders import SimpleCLTVBuilder, EscrowTimeoutBuilder
    
    builder = SimpleCLTVBuilder()
    params = {"locktime": 107332, "pubkey": "0279be66..."}
    script_bytes = builder.build(params)
    script_hex = script_bytes.hex()
"""

from .base import encode_script_number, decode_script_number
from .simple_cltv import SimpleCLTVBuilder
from .escrow_timeout import EscrowTimeoutBuilder

__all__ = [
    'encode_script_number',
    'decode_script_number',
    'SimpleCLTVBuilder',
    'EscrowTimeoutBuilder',
]
