"""
Miniscript Compiler

Compiles miniscript expressions to Bitcoin Script.
Supports both P2WSH and Tapscript contexts.

Extended to support Trident-style vault contracts with relative timelocks.

Supported Fragments:
- pk(K) - Public key
- after(N) - Absolute timelock (CLTV, BIP-65)
- older(N) - Relative timelock (CSV, BIP-112)
- hash160(H) - Hash preimage
- and_v(X, Y) - AND (sequential)
- and_b(X, Y) - AND with BOOLAND
- or_i(X, Y) - OR (IF/ELSE)
- or_b(X, Y) - OR with BOOLOR
- or_d(X, Y) - OR with IFDUP/NOTIF
- or_c(X, Y) - OR with NOTIF
- andor(X, Y, Z) - If X then Y else Z
- multi(k, K1, K2, ...) - P2WSH multisig
- multi_a(k, K1, K2, ...) - Tapscript multisig
- thresh(k, X1, X2, ...) - Threshold

Wrappers:
- v: - Verify (add OP_VERIFY or use -VERIFY variant)
- c: - Checksig (add OP_CHECKSIG)
- s: - Swap (add OP_SWAP first)
- a: - Altstack (use OP_TOALTSTACK/FROMALTSTACK)
- n: - 0NOTEQUAL (convert to boolean)

Usage:
    >>> from cltv_lib.miniscript import compile_miniscript, MiniscriptContext
    >>> 
    >>> # Simple HODL contract
    >>> script = compile_miniscript(
    ...     "and_v(v:pk(pubkey), after(100))",
    ...     {'pubkey': bytes.fromhex('02...')},
    ...     MiniscriptContext.P2WSH
    ... )
    >>> 
    >>> # Trident-style vault with relative timelock
    >>> script = compile_miniscript(
    ...     "or_d(and_v(v:pk(user), v:pk(service)), and_v(older(25920), v:pk(user)))",
    ...     {'user': user_key, 'service': service_key},
    ...     MiniscriptContext.P2WSH
    ... )

Reference:
- Bitcoin Core: src/script/miniscript.h
- BIP-65: OP_CHECKLOCKTIMEVERIFY (absolute timelock)
- BIP-112: OP_CHECKSEQUENCEVERIFY (relative timelock)
"""

from .fragments import Fragment, MiniscriptContext
from .compiler import compile_miniscript, from_script
from .node import Node, CompiledScript

__all__ = [
    'Fragment',
    'MiniscriptContext',
    'compile_miniscript',
    'from_script',
    'Node',
    'CompiledScript',
]

