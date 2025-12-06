"""
Miniscript AST Node

Represents a parsed miniscript expression as a tree of nodes.
Each node can compile itself to Bitcoin Script.

Like Bitcoin Core's miniscript.h, we track fragment properties during
compilation so the satisfier knows what witness structure is needed.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union, NamedTuple
from .fragments import Fragment, MiniscriptContext, compile_fragment


class CompiledScript(NamedTuple):
    """
    Result of compiling a miniscript node.
    
    Like Bitcoin Core, we track metadata alongside the compiled script
    so the satisfier knows what witness structure is needed.
    
    Attributes:
        script: The compiled Bitcoin Script bytes
        has_checkmultisig: True if the script contains OP_CHECKMULTISIG.
                          This is only possible in P2WSH context (Fragment::MULTI).
                          Tapscript uses CHECKSIGADD instead (Fragment::MULTI_A).
                          When True, witness needs a dummy OP_0 element due to
                          Bitcoin's CHECKMULTISIG off-by-one bug.
    """
    script: bytes
    has_checkmultisig: bool = False


@dataclass
class Node:
    """
    AST node for a miniscript expression.
    
    Mirrors Bitcoin Core's Node class in miniscript.h.
    
    Attributes:
        fragment: The fragment type
        k: Integer parameter (locktime, threshold)
        key: Single public key
        keys: List of public keys (for multi)
        data: Hash data
        subs: Child nodes
    """
    fragment: Fragment
    k: Optional[int] = None
    key: Optional[bytes] = None
    keys: List[bytes] = field(default_factory=list)
    data: Optional[bytes] = None
    subs: List['Node'] = field(default_factory=list)
    
    # Wrappers applied to this node (v:, c:, etc.)
    wrappers: str = ""
    
    def compile(self, context: MiniscriptContext) -> bytes:
        """
        Compile this node to Bitcoin Script.
        
        For backwards compatibility, returns just the script bytes.
        Use compile_with_metadata() to get full CompiledScript with metadata.
        
        Args:
            context: P2WSH or TAPSCRIPT
            
        Returns:
            Compiled Bitcoin Script bytes
        """
        return self.compile_with_metadata(context).script
    
    def compile_with_metadata(self, context: MiniscriptContext) -> CompiledScript:
        """
        Compile this node to Bitcoin Script with metadata.
        
        Like Bitcoin Core's miniscript, we track whether the script
        contains CHECKMULTISIG at the AST level, not by scanning bytes.
        
        Args:
            context: P2WSH or TAPSCRIPT
            
        Returns:
            CompiledScript with script bytes and metadata
        """
        # Track if this subtree contains CHECKMULTISIG
        # Only Fragment::MULTI in P2WSH context produces CHECKMULTISIG
        has_checkmultisig = False
        
        # Special case: v:c:pk_k should use CHECKSIGVERIFY directly
        # Check if this is WRAP_V containing WRAP_C
        if (self.fragment == Fragment.WRAP_V and 
            len(self.subs) == 1 and 
            self.subs[0].fragment == Fragment.WRAP_C):
            # Compile the inner node (skip WRAP_C, we'll add CHECKSIGVERIFY)
            inner = self.subs[0].subs[0] if self.subs[0].subs else None
            if inner:
                inner_result = inner.compile_with_metadata(context)
                has_checkmultisig = inner_result.has_checkmultisig
                # Add CHECKSIGVERIFY instead of CHECKSIG + VERIFY
                script = compile_fragment(Fragment.WRAP_C, context, subs=[inner_result.script], verify=True)
                return CompiledScript(script=script, has_checkmultisig=has_checkmultisig)
        
        # First compile all children and collect metadata
        compiled_subs = []
        for sub in self.subs:
            sub_result = sub.compile_with_metadata(context)
            compiled_subs.append(sub_result.script)
            # Propagate has_checkmultisig from children
            has_checkmultisig = has_checkmultisig or sub_result.has_checkmultisig
        
        # Check if THIS node uses CHECKMULTISIG
        # Only Fragment::MULTI in P2WSH context uses OP_CHECKMULTISIG
        # Fragment::MULTI_A in Tapscript uses CHECKSIGADD (no dummy needed)
        if self.fragment == Fragment.MULTI and context == MiniscriptContext.P2WSH:
            has_checkmultisig = True
        
        # Compile this node
        result = compile_fragment(
            self.fragment,
            context,
            key=self.key,
            keys=self.keys,
            k=self.k,
            data=self.data,
            subs=compiled_subs if compiled_subs else None,
        )
        
        # Apply wrappers in reverse order (innermost first)
        for wrapper in reversed(self.wrappers):
            if wrapper == 'v':
                result = compile_fragment(Fragment.WRAP_V, context, subs=[result])
            elif wrapper == 'c':
                result = compile_fragment(Fragment.WRAP_C, context, subs=[result])
            # Add more wrappers as needed
        
        return CompiledScript(script=result, has_checkmultisig=has_checkmultisig)
    
    def to_miniscript(self) -> str:
        """
        Convert back to miniscript string (for debugging).
        
        Returns:
            Miniscript string representation
        """
        # Build prefix from wrappers
        prefix = ':'.join(self.wrappers) + ':' if self.wrappers else ''
        
        if self.fragment == Fragment.PK_K:
            return f"{prefix}pk({self.key.hex() if self.key else 'KEY'})"
        
        elif self.fragment == Fragment.AFTER:
            return f"{prefix}after({self.k})"
        
        elif self.fragment == Fragment.AFTER_DROP:
            return f"{prefix}after_drop({self.k})"
        
        elif self.fragment == Fragment.OLDER:
            return f"{prefix}older({self.k})"
        
        elif self.fragment == Fragment.OLDER_DROP:
            return f"{prefix}older_drop({self.k})"
        
        elif self.fragment == Fragment.HASH160:
            return f"{prefix}hash160({self.data.hex() if self.data else 'HASH'})"
        
        elif self.fragment == Fragment.JUST_0:
            return "0"
        
        elif self.fragment == Fragment.JUST_1:
            return "1"
        
        elif self.fragment == Fragment.AND_V:
            return f"{prefix}and_v({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.AND_B:
            return f"{prefix}and_b({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.OR_I:
            return f"{prefix}or_i({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.OR_B:
            return f"{prefix}or_b({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.OR_D:
            return f"{prefix}or_d({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.OR_C:
            return f"{prefix}or_c({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()})"
        
        elif self.fragment == Fragment.ANDOR:
            return f"{prefix}andor({self.subs[0].to_miniscript()},{self.subs[1].to_miniscript()},{self.subs[2].to_miniscript()})"
        
        elif self.fragment == Fragment.WRAP_S:
            return f"s:{self.subs[0].to_miniscript()}"
        
        elif self.fragment == Fragment.WRAP_A:
            return f"a:{self.subs[0].to_miniscript()}"
        
        elif self.fragment == Fragment.WRAP_N:
            return f"n:{self.subs[0].to_miniscript()}"
        
        elif self.fragment == Fragment.MULTI:
            keys_str = ','.join(k.hex() for k in self.keys)
            return f"{prefix}multi({self.k},{keys_str})"
        
        elif self.fragment == Fragment.MULTI_A:
            keys_str = ','.join(k.hex() for k in self.keys)
            return f"{prefix}multi_a({self.k},{keys_str})"
        
        elif self.fragment == Fragment.THRESH:
            subs_str = ','.join(s.to_miniscript() for s in self.subs)
            return f"{prefix}thresh({self.k},{subs_str})"
        
        elif self.fragment == Fragment.WRAP_C:
            return f"c:{self.subs[0].to_miniscript()}"
        
        elif self.fragment == Fragment.WRAP_V:
            return f"v:{self.subs[0].to_miniscript()}"
        
        return f"<{self.fragment.name}>"


# === Factory functions for building nodes ===

def pk(key: bytes) -> Node:
    """Create a pk(K) node."""
    return Node(fragment=Fragment.PK_K, key=key)


def after(n: int) -> Node:
    """Create an after(N) node (standard miniscript, no DROP)."""
    return Node(fragment=Fragment.AFTER, k=n)


def after_drop(n: int) -> Node:
    """Create an after_drop(N) node (BIP-65 style with DROP)."""
    return Node(fragment=Fragment.AFTER_DROP, k=n)


def older(n: int) -> Node:
    """Create an older(N) node (BIP-112 CSV relative timelock)."""
    return Node(fragment=Fragment.OLDER, k=n)


def older_drop(n: int) -> Node:
    """Create an older_drop(N) node (BIP-112 style with DROP)."""
    return Node(fragment=Fragment.OLDER_DROP, k=n)


def hash160(data: bytes) -> Node:
    """Create a hash160(H) node (standard miniscript with size check)."""
    return Node(fragment=Fragment.HASH160, data=data)


def hash160_simple(data: bytes) -> Node:
    """Create a hash160_simple(H) node (no size check, our scripts)."""
    return Node(fragment=Fragment.HASH160_SIMPLE, data=data)


def and_v(x: Node, y: Node) -> Node:
    """Create an and_v(X, Y) node."""
    return Node(fragment=Fragment.AND_V, subs=[x, y])


def and_b(x: Node, y: Node) -> Node:
    """Create an and_b(X, Y) node."""
    return Node(fragment=Fragment.AND_B, subs=[x, y])


def or_i(x: Node, y: Node) -> Node:
    """Create an or_i(X, Y) node."""
    return Node(fragment=Fragment.OR_I, subs=[x, y])


def or_b(x: Node, y: Node) -> Node:
    """Create an or_b(X, Y) node (X OR Y using BOOLOR)."""
    return Node(fragment=Fragment.OR_B, subs=[x, y])


def or_d(x: Node, y: Node) -> Node:
    """Create an or_d(X, Y) node (X IFDUP NOTIF Y ENDIF)."""
    return Node(fragment=Fragment.OR_D, subs=[x, y])


def or_c(x: Node, y: Node) -> Node:
    """Create an or_c(X, Y) node (X NOTIF Y ENDIF)."""
    return Node(fragment=Fragment.OR_C, subs=[x, y])


def andor(x: Node, y: Node, z: Node) -> Node:
    """Create an andor(X, Y, Z) node (if X then Y else Z)."""
    return Node(fragment=Fragment.ANDOR, subs=[x, y, z])


def wrap_s(x: Node) -> Node:
    """Apply s: wrapper (SWAP first)."""
    return Node(fragment=Fragment.WRAP_S, subs=[x])


def wrap_a(x: Node) -> Node:
    """Apply a: wrapper (use altstack)."""
    return Node(fragment=Fragment.WRAP_A, subs=[x])


def wrap_n(x: Node) -> Node:
    """Apply n: wrapper (0NOTEQUAL)."""
    return Node(fragment=Fragment.WRAP_N, subs=[x])


def multi(k: int, *keys: bytes) -> Node:
    """Create a multi(k, K1, K2, ...) node."""
    return Node(fragment=Fragment.MULTI, k=k, keys=list(keys))


def multi_a(k: int, *keys: bytes) -> Node:
    """Create a multi_a(k, K1, K2, ...) node."""
    return Node(fragment=Fragment.MULTI_A, k=k, keys=list(keys))


def thresh(k: int, *subs: Node) -> Node:
    """Create a thresh(k, X1, X2, ...) node."""
    return Node(fragment=Fragment.THRESH, k=k, subs=list(subs))


def v(x: Node) -> Node:
    """Apply v: wrapper."""
    return Node(fragment=Fragment.WRAP_V, subs=[x])


def c(x: Node) -> Node:
    """Apply c: wrapper (CHECKSIG)."""
    return Node(fragment=Fragment.WRAP_C, subs=[x])


__all__ = [
    'Node',
    'CompiledScript',
    # Factory functions
    'pk', 'after', 'after_drop', 'older', 'older_drop',
    'hash160', 'hash160_simple',
    'and_v', 'and_b', 
    'or_i', 'or_b', 'or_d', 'or_c', 'andor',
    'multi', 'multi_a', 'thresh',
    'v', 'c', 'wrap_s', 'wrap_a', 'wrap_n',
]

