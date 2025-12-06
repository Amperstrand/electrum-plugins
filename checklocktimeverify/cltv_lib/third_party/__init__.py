"""
Third-party reference implementations.

Contains vendored reference implementations from Bitcoin BIPs:
- bip_0340_reference.py: BIP-340 Schnorr signatures

Note: Bech32m encoding now uses Electrum's built-in segwit_addr module.
"""

from .bip_0340_reference import (
    schnorr_sign,
    schnorr_verify,
    bytes_from_int,
    bytes_from_point,
    point_add,
    point_mul,
    lift_x,
    G,
    n,
    p,
)

__all__ = [
    # BIP-340 Schnorr
    'schnorr_sign',
    'schnorr_verify',
    'bytes_from_int',
    'bytes_from_point',
    'point_add',
    'point_mul',
    'lift_x',
    'G',
    'n',
    'p',
]
