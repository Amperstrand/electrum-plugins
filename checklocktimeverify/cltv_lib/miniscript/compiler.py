"""
Miniscript Compiler

Compiles miniscript strings to Bitcoin Script.
Supports both P2WSH and Tapscript contexts.

This module provides two ways to compile:
1. compile_miniscript(string, params, context) - Parse and compile a string
2. Build Node tree manually using factory functions and call .compile()
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from .fragments import MiniscriptContext
from .node import (
    Node, CompiledScript, pk, after, after_drop, older, older_drop,
    hash160, hash160_simple,
    and_v, and_b, or_i, or_b, or_d, or_c, andor,
    multi, multi_a, thresh,
    v, c, wrap_s, wrap_a, wrap_n,
)


class ParseError(Exception):
    """Error parsing miniscript string."""
    pass


def _parse_expr(expr: str, params: Dict[str, Any]) -> Node:
    """
    Parse a miniscript expression into a Node tree.
    
    This is a simple recursive descent parser for our limited subset.
    
    Args:
        expr: Miniscript expression string
        params: Parameter dict with keys and values
        
    Returns:
        Parsed Node tree
    """
    expr = expr.strip()
    
    # Handle wrappers (v:, c:, s:, a:, n:, etc.)
    wrappers = []
    while ':' in expr and expr.index(':') < expr.index('(') if '(' in expr else True:
        if expr.startswith('v:'):
            wrappers.append('v')
            expr = expr[2:]
        elif expr.startswith('c:'):
            wrappers.append('c')
            expr = expr[2:]
        elif expr.startswith('s:'):
            wrappers.append('s')
            expr = expr[2:]
        elif expr.startswith('a:'):
            wrappers.append('a')
            expr = expr[2:]
        elif expr.startswith('n:'):
            wrappers.append('n')
            expr = expr[2:]
        else:
            break
    
    # Parse the main expression
    node = _parse_main_expr(expr, params)
    
    # Apply wrappers (innermost first, so we reverse)
    for wrapper in reversed(wrappers):
        if wrapper == 'v':
            node = v(node)
        elif wrapper == 'c':
            node = c(node)
        elif wrapper == 's':
            node = wrap_s(node)
        elif wrapper == 'a':
            node = wrap_a(node)
        elif wrapper == 'n':
            node = wrap_n(node)
    
    return node


def _parse_main_expr(expr: str, params: Dict[str, Any]) -> Node:
    """Parse the main expression (after wrappers)."""
    
    # pk(key_name) - public key
    if expr.startswith('pk(') and expr.endswith(')'):
        key_name = expr[3:-1]
        key = _get_key(params, key_name)
        return pk(key)
    
    # pk_k(key_name) - explicit pk_k
    if expr.startswith('pk_k(') and expr.endswith(')'):
        key_name = expr[5:-1]
        key = _get_key(params, key_name)
        return pk(key)
    
    # after(n) - timelock (standard miniscript)
    if expr.startswith('after(') and expr.endswith(')'):
        arg = expr[6:-1]
        n = _get_int(params, arg)
        return after(n)
    
    # after_drop(n) - timelock with DROP (BIP-65 style)
    if expr.startswith('after_drop(') and expr.endswith(')'):
        arg = expr[11:-1]
        n = _get_int(params, arg)
        return after_drop(n)
    
    # older(n) - relative timelock (BIP-112 CSV)
    if expr.startswith('older(') and expr.endswith(')'):
        arg = expr[6:-1]
        n = _get_int(params, arg)
        return older(n)
    
    # older_drop(n) - relative timelock with DROP
    if expr.startswith('older_drop(') and expr.endswith(')'):
        arg = expr[11:-1]
        n = _get_int(params, arg)
        return older_drop(n)
    
    # hash160(hash_name) - hash preimage (standard with size check)
    if expr.startswith('hash160(') and expr.endswith(')'):
        hash_name = expr[8:-1]
        data = _get_hash(params, hash_name)
        return hash160(data)
    
    # hash160_simple(hash_name) - hash preimage (no size check, our scripts)
    if expr.startswith('hash160_simple(') and expr.endswith(')'):
        hash_name = expr[15:-1]
        data = _get_hash(params, hash_name)
        return hash160_simple(data)
    
    # and_v(X, Y) - sequential AND
    if expr.startswith('and_v(') and expr.endswith(')'):
        args = _split_args(expr[6:-1])
        if len(args) != 2:
            raise ParseError(f"and_v requires 2 arguments, got {len(args)}")
        return and_v(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # and_b(X, Y) - AND with BOOLAND
    if expr.startswith('and_b(') and expr.endswith(')'):
        args = _split_args(expr[6:-1])
        if len(args) != 2:
            raise ParseError(f"and_b requires 2 arguments, got {len(args)}")
        return and_b(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # or_i(X, Y) - IF/ELSE OR
    if expr.startswith('or_i(') and expr.endswith(')'):
        args = _split_args(expr[5:-1])
        if len(args) != 2:
            raise ParseError(f"or_i requires 2 arguments, got {len(args)}")
        return or_i(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # or_b(X, Y) - BOOLOR
    if expr.startswith('or_b(') and expr.endswith(')'):
        args = _split_args(expr[5:-1])
        if len(args) != 2:
            raise ParseError(f"or_b requires 2 arguments, got {len(args)}")
        return or_b(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # or_d(X, Y) - IFDUP NOTIF
    if expr.startswith('or_d(') and expr.endswith(')'):
        args = _split_args(expr[5:-1])
        if len(args) != 2:
            raise ParseError(f"or_d requires 2 arguments, got {len(args)}")
        return or_d(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # or_c(X, Y) - NOTIF
    if expr.startswith('or_c(') and expr.endswith(')'):
        args = _split_args(expr[5:-1])
        if len(args) != 2:
            raise ParseError(f"or_c requires 2 arguments, got {len(args)}")
        return or_c(_parse_expr(args[0], params), _parse_expr(args[1], params))
    
    # andor(X, Y, Z) - if X then Y else Z
    if expr.startswith('andor(') and expr.endswith(')'):
        args = _split_args(expr[6:-1])
        if len(args) != 3:
            raise ParseError(f"andor requires 3 arguments, got {len(args)}")
        return andor(
            _parse_expr(args[0], params),
            _parse_expr(args[1], params),
            _parse_expr(args[2], params)
        )
    
    # multi(k, key1, key2, ...) - P2WSH multisig
    if expr.startswith('multi(') and expr.endswith(')'):
        args = _split_args(expr[6:-1])
        k = int(args[0])
        keys = [_get_key(params, arg) for arg in args[1:]]
        return multi(k, *keys)
    
    # multi_a(k, key1, key2, ...) - Tapscript multisig
    if expr.startswith('multi_a(') and expr.endswith(')'):
        args = _split_args(expr[8:-1])
        k = int(args[0])
        keys = [_get_key(params, arg) for arg in args[1:]]
        return multi_a(k, *keys)
    
    # thresh(k, X1, X2, ...) - threshold
    if expr.startswith('thresh(') and expr.endswith(')'):
        args = _split_args(expr[7:-1])
        k = int(args[0])
        subs = [_parse_expr(arg, params) for arg in args[1:]]
        return thresh(k, *subs)
    
    raise ParseError(f"Unknown expression: {expr}")


def _split_args(args_str: str) -> list:
    """
    Split comma-separated arguments, respecting nested parentheses.
    
    "X, Y" -> ["X", "Y"]
    "and_v(A,B), C" -> ["and_v(A,B)", "C"]
    """
    args = []
    current = ""
    depth = 0
    
    for char in args_str:
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == ',' and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += char
    
    if current.strip():
        args.append(current.strip())
    
    return args


def _get_key(params: Dict[str, Any], name: str) -> bytes:
    """Get a public key from params by name."""
    # Try direct lookup
    if name in params:
        val = params[name]
        if isinstance(val, bytes):
            return val
        elif isinstance(val, str):
            return bytes.fromhex(val)
    
    # Try with _pubkey suffix
    key_name = f"{name}_pubkey"
    if key_name in params:
        val = params[key_name]
        if isinstance(val, bytes):
            return val
        elif isinstance(val, str):
            return bytes.fromhex(val)
    
    # Try with _pubkey_xonly suffix
    key_name = f"{name}_pubkey_xonly"
    if key_name in params:
        val = params[key_name]
        if isinstance(val, bytes):
            return val
        elif isinstance(val, str):
            return bytes.fromhex(val)
    
    raise ParseError(f"Key not found in params: {name}")


def _get_int(params: Dict[str, Any], name: str) -> int:
    """Get an integer from params or parse directly."""
    # Try as literal integer
    try:
        return int(name)
    except ValueError:
        pass
    
    # Try lookup in params
    if name in params:
        return int(params[name])
    
    raise ParseError(f"Integer not found: {name}")


def _get_hash(params: Dict[str, Any], name: str) -> bytes:
    """Get hash data from params."""
    if name in params:
        val = params[name]
        if isinstance(val, bytes):
            return val
        elif isinstance(val, str):
            return bytes.fromhex(val)
    
    # Try with _hash suffix
    hash_name = f"{name}_hash"
    if hash_name in params:
        val = params[hash_name]
        if isinstance(val, bytes):
            return val
        elif isinstance(val, str):
            return bytes.fromhex(val)
    
    raise ParseError(f"Hash not found in params: {name}")


def compile_miniscript(
    miniscript: str,
    params: Dict[str, Any],
    context: MiniscriptContext = MiniscriptContext.P2WSH
) -> bytes:
    """
    Compile a miniscript string to Bitcoin Script.
    
    For backwards compatibility, returns just the script bytes.
    Use compile_miniscript_with_metadata() to get metadata about the script.
    
    Args:
        miniscript: Miniscript expression string
        params: Parameter dict with keys and values
        context: P2WSH or TAPSCRIPT
    
    Returns:
        Compiled Bitcoin Script bytes
    
    Example:
        >>> compile_miniscript(
        ...     "and_v(v:pk(pubkey), after(100))",
        ...     {'pubkey': bytes.fromhex('02' + '11' * 32)},
        ...     MiniscriptContext.P2WSH
        ... )
    """
    # Parse the miniscript string into a Node tree
    node = _parse_expr(miniscript, params)
    
    # Compile the Node tree to Bitcoin Script
    return node.compile(context)


def compile_miniscript_with_metadata(
    miniscript: str,
    params: Dict[str, Any],
    context: MiniscriptContext = MiniscriptContext.P2WSH
) -> CompiledScript:
    """
    Compile a miniscript string to Bitcoin Script with metadata.
    
    Like Bitcoin Core's miniscript, this tracks fragment properties
    at the AST level so the satisfier knows what witness structure is needed.
    
    Args:
        miniscript: Miniscript expression string
        params: Parameter dict with keys and values
        context: P2WSH or TAPSCRIPT
    
    Returns:
        CompiledScript with:
        - script: bytes - The compiled Bitcoin Script
        - has_checkmultisig: bool - True if script uses OP_CHECKMULTISIG
          (only possible in P2WSH with multi() fragment)
    
    Example:
        >>> result = compile_miniscript_with_metadata(
        ...     "multi(2, alice, bob)",
        ...     {'alice': bytes.fromhex('02...'), 'bob': bytes.fromhex('03...')},
        ...     MiniscriptContext.P2WSH
        ... )
        >>> result.has_checkmultisig
        True  # Witness needs OP_0 dummy
        
        >>> result = compile_miniscript_with_metadata(
        ...     "multi_a(2, alice, bob)",
        ...     {'alice': bytes.fromhex('02...'), 'bob': bytes.fromhex('03...')},
        ...     MiniscriptContext.TAPSCRIPT
        ... )
        >>> result.has_checkmultisig
        False  # Tapscript uses CHECKSIGADD, no dummy needed
    """
    # Parse the miniscript string into a Node tree
    node = _parse_expr(miniscript, params)
    
    # Compile with metadata
    return node.compile_with_metadata(context)


def from_script(script_bytes: bytes, context: MiniscriptContext) -> Optional[Node]:
    """
    Parse a compiled Bitcoin Script back into a miniscript AST.

    THIS IS A FALLBACK MECHANISM FOR FUTURE EXTENSIBILITY - NOT USED IN OUR CURRENT CONTRACTS.

    Why we implemented this (even though we don't need it):
    - Bitcoin Core implements FromScript() for signing arbitrary P2WSH scripts that might be miniscript-compatible
    - It enables our system to potentially handle scripts beyond our known contracts
    - Maintains architectural compatibility with Bitcoin Core's approach
    - Allows future expansion to parse user-provided scripts

    Our current contracts are all known and we determine CHECKMULTISIG needs directly from
    ContractDefinition.miniscript string analysis. We don't need to reverse-engineer scripts.

    Args:
        script_bytes: Compiled Bitcoin Script bytes
        context: P2WSH or TAPSCRIPT context

    Returns:
        Parsed Node if successful, None if script is not valid miniscript

    Note:
        This is a simplified implementation that only handles our supported fragments.
        Full miniscript FromScript support would be much more complex.
    """
    try:
        # Use Electrum's script parser
        from electrum.transaction import script_GetOp

        # Parse script into opcodes
        ops = list(script_GetOp(script_bytes))

        # Try to parse as one of our supported patterns
        return _parse_script_ops(ops, context)

    except Exception:
        return None


def _parse_script_ops(ops: List[Tuple[int, Optional[bytes], int]], context: MiniscriptContext) -> Optional[Node]:
    """
    Parse script opcodes into miniscript Node.

    The type annotation List[Tuple[int, Optional[bytes], int]] represents:
    - int: opcode value
    - Optional[bytes]: pushed data (None for non-push opcodes like CHECKSIG)
    - int: position in script

    This comes from Electrum's script_GetOp() function output.

    NOTE: This FromScript parsing is COMPLEXITY WE DON'T CURRENTLY NEED.
    Our contracts are known, so we determine CHECKMULTISIG needs directly from
    ContractDefinition.miniscript string analysis. We implemented this to match
    Bitcoin Core's FromScript() fallback mechanism, but it's not used for our contracts.
    """
    if not ops:
        return None

    # Handle our supported patterns (reverse of compile_fragment logic)

    # Single key with CHECKSIG: c:pk(key)
    if len(ops) == 2 and ops[1][0] == opcodes.OP_CHECKSIG:
        key = ops[0][1]
        if key and len(key) in (32, 33):  # x-only or compressed
            return Node(fragment=Fragment.PK_K, key=key)

    # Multi-signature patterns
    if _is_multisig_pattern(ops, context):
        return _parse_multisig(ops, context)

    # Timelock patterns
    if _is_timelock_pattern(ops):
        return _parse_timelock(ops)

    # Hash patterns
    if _is_hash_pattern(ops):
        return _parse_hash(ops)

    # Combinator patterns
    return _parse_combinator(ops, context)


def _is_multisig_pattern(ops: List[Tuple[int, Optional[bytes], int]], context: MiniscriptContext) -> bool:
    """Check if ops represent a multisig pattern."""
    if context == MiniscriptContext.TAPSCRIPT:
        # Tapscript: key CHECKSIGADD key CHECKSIGADD ... k OP_NUMEQUAL
        return _is_tapscript_multisig(ops)
    else:
        # P2WSH: k key key ... n OP_CHECKMULTISIG
        return _is_p2wsh_multisig(ops)


def _is_p2wsh_multisig(ops: List[Tuple[int, Optional[bytes], int]]) -> bool:
    """Check P2WSH multisig: OP_0 key key ... n OP_CHECKMULTISIG"""
    if len(ops) < 4 or ops[-1][0] != opcodes.OP_CHECKMULTISIG:
        return False

    # Check OP_0 dummy
    if ops[0][0] != 0:
        return False

    # Check threshold and key count
    threshold = ops[-2][1]
    if not threshold or len(threshold) != 1:
        return False
    k = threshold[0]

    # Should have k keys + threshold + OP_CHECKMULTISIG
    expected_len = k + 2
    if len(ops) != expected_len:
        return False

    # Check all middle ops are keys
    for i in range(1, len(ops) - 2):
        if not ops[i][1] or len(ops[i][1]) != 33:
            return False

    return True


def _is_tapscript_multisig(ops: List[Tuple[int, Optional[bytes], int]]) -> bool:
    """Check Tapscript multisig: key CHECKSIG key CHECKSIGADD ... k OP_NUMEQUAL"""
    if len(ops) < 4 or ops[-1][0] != opcodes.OP_NUMEQUAL:
        return False

    # Check threshold
    threshold = ops[-2][1]
    if not threshold or len(threshold) != 1:
        return False
    k = threshold[0]

    # Pattern: (key CHECKSIGADD)* (key CHECKSIG) k OP_NUMEQUAL
    # Or simplified: alternating keys and CHECKSIG/CHECKSIGADD, then k, OP_NUMEQUAL
    expected_len = 2 * k + 1  # k keys, k sig ops, k threshold, OP_NUMEQUAL
    if len(ops) != expected_len:
        return False

    return True


def _is_timelock_pattern(ops: List[Tuple[int, Optional[bytes], int]]) -> bool:
    """Check timelock patterns."""
    # CLTV OP_DROP (our AFTER_DROP)
    if (len(ops) == 3 and
        ops[1][0] == opcodes.OP_CHECKLOCKTIMEVERIFY and
        ops[2][0] == opcodes.OP_DROP):
        return True

    # Just CLTV (standard AFTER)
    if len(ops) == 2 and ops[1][0] == opcodes.OP_CHECKLOCKTIMEVERIFY:
        return True

    return False


def _is_hash_pattern(ops: List[Tuple[int, Optional[bytes], int]]) -> bool:
    """Check hash patterns."""
    # OP_HASH160 hash OP_EQUALVERIFY (our HASH160_SIMPLE)
    if (len(ops) == 3 and
        ops[0][0] == opcodes.OP_HASH160 and
        ops[2][0] == opcodes.OP_EQUALVERIFY):
        return True

    return False


def _parse_multisig(ops: List[Tuple[int, Optional[bytes], int]], context: MiniscriptContext) -> Optional[Node]:
    """Parse multisig pattern into Node."""
    try:
        if context == MiniscriptContext.TAPSCRIPT:
            return _parse_tapscript_multisig(ops)
        else:
            return _parse_p2wsh_multisig(ops)
    except Exception:
        return None


def _parse_p2wsh_multisig(ops: List[Tuple[int, Optional[bytes], int]]) -> Optional[Node]:
    """Parse P2WSH multisig: OP_0 key key ... n OP_CHECKMULTISIG"""
    if not _is_p2wsh_multisig(ops):
        return None

    k = ops[-2][1][0]
    keys = [ops[i][1] for i in range(1, len(ops) - 2)]

    return Node(fragment=Fragment.MULTI, k=k, keys=keys)


def _parse_tapscript_multisig(ops: List[Tuple[int, Optional[bytes], int]]) -> Optional[Node]:
    """Parse Tapscript multisig: key CHECKSIGADD key CHECKSIGADD ... k OP_NUMEQUAL

    This parses the CHECKSIGADD-based multisig construction that Bitcoin Core
    supports in Tapscript via multi_a(). Despite some confusion about "multisig
    being removed from Taproot", BIP-342 actually added CHECKSIGADD specifically
    for correct multisig constructions in Tapscript.

    See: bitcoin/doc/descriptors.md - multi_a support in tr() descriptors
    See: bitcoin/src/test/miniscript_tests.cpp - multi_a validation tests
    """
    if not _is_tapscript_multisig(ops):
        return None

    k = ops[-2][1][0]
    keys = []

    # Extract keys from alternating pattern
    for i in range(0, len(ops) - 2, 2):
        if ops[i][1]:
            keys.append(ops[i][1])

    return Node(fragment=Fragment.MULTI_A, k=k, keys=keys)


def _parse_timelock(ops: List[Tuple[int, Optional[bytes], int]]) -> Optional[Node]:
    """Parse timelock pattern."""
    if len(ops) == 3 and ops[2][0] == opcodes.OP_DROP:
        # AFTER_DROP: n CLTV DROP
        n = int.from_bytes(ops[0][1], 'little')
        return Node(fragment=Fragment.AFTER_DROP, k=n)
    elif len(ops) == 2:
        # AFTER: n CLTV
        n = int.from_bytes(ops[0][1], 'little')
        return Node(fragment=Fragment.AFTER, k=n)

    return None


def _parse_hash(ops: List[Tuple[int, Optional[bytes], int]]) -> Optional[Node]:
    """Parse hash pattern."""
    if (len(ops) == 3 and ops[0][0] == opcodes.OP_HASH160 and
        ops[2][0] == opcodes.OP_EQUALVERIFY):
        hash_data = ops[1][1]
        return Node(fragment=Fragment.HASH160_SIMPLE, data=hash_data)

    return None


def _parse_combinator(ops: List[Tuple[int, Optional[bytes], int]], context: MiniscriptContext) -> Optional[Node]:
    """Parse combinator patterns (AND_V, OR_I, etc.)."""
    # This is complex - for now return None (not supported)
    # Full implementation would need to recursively parse sub-scripts
    return None


__all__ = ['compile_miniscript', 'compile_miniscript_with_metadata', 'from_script', 'ParseError']

