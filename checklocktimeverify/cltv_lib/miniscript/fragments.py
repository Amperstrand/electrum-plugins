"""
Miniscript Fragments - Core compilation logic.

Implements the 11 fragments needed for our 5 CLTV contracts,
following Bitcoin Core's miniscript.h ToScript() logic.

Reference: bitcoin/src/script/miniscript.h lines 768-820
"""

from enum import Enum, auto
from typing import List, Optional, Union
from electrum.bitcoin import construct_script, opcodes

# Import Taproot-specific opcode from dependency-free module
from ..opcodes_ext import OP_CHECKSIGADD


class Fragment(Enum):
    """
    Miniscript fragments.
    
    Based on Bitcoin Core's Fragment enum in miniscript.h.
    Extended to support Trident-style vault contracts with relative timelocks.
    """
    # Leaf fragments (no sub-expressions)
    PK_K = auto()       # [key] - just push the key
    AFTER = auto()      # [n] OP_CHECKLOCKTIMEVERIFY (standard miniscript, absolute)
    AFTER_DROP = auto() # [n] OP_CHECKLOCKTIMEVERIFY OP_DROP (BIP-65 style)
    OLDER = auto()      # [n] OP_CHECKSEQUENCEVERIFY (BIP-112 relative timelock)
    OLDER_DROP = auto() # [n] OP_CHECKSEQUENCEVERIFY OP_DROP (relative, with DROP)
    HASH160 = auto()    # OP_SIZE 32 OP_EQUALVERIFY OP_HASH160 [hash] OP_EQUAL (standard)
    HASH160_SIMPLE = auto()  # OP_HASH160 [hash] OP_EQUALVERIFY (our scripts, no size check)
    JUST_0 = auto()     # OP_0
    JUST_1 = auto()     # OP_1
    
    # Wrapper fragments (modify sub-expression)
    WRAP_C = auto()     # [X] OP_CHECKSIG (or OP_CHECKSIGVERIFY)
    WRAP_V = auto()     # [X] OP_VERIFY (or convert last op to -VERIFY)
    WRAP_S = auto()     # OP_SWAP [X] - swap top two stack elements first
    WRAP_A = auto()     # OP_TOALTSTACK [X] OP_FROMALTSTACK - use altstack
    WRAP_N = auto()     # [X] OP_0NOTEQUAL - convert to boolean
    
    # Combinator fragments (combine sub-expressions)
    AND_V = auto()      # [X] [Y] - sequential AND
    AND_B = auto()      # [X] [Y] OP_BOOLAND
    OR_I = auto()       # OP_IF [X] OP_ELSE [Y] OP_ENDIF
    OR_B = auto()       # [X] [Y] OP_BOOLOR
    OR_D = auto()       # [X] OP_IFDUP OP_NOTIF [Y] OP_ENDIF
    OR_C = auto()       # [X] OP_NOTIF [Y] OP_ENDIF
    ANDOR = auto()      # [X] OP_NOTIF [Z] OP_ELSE [Y] OP_ENDIF
    
    # Multi-signature fragments (context-dependent)
    MULTI = auto()      # [k] [keys...] [n] OP_CHECKMULTISIG (P2WSH only)
    MULTI_A = auto()    # [key0] CS ([keyn] CSA)* [k] NUMEQ (Tapscript only)
    
    # Threshold fragment
    THRESH = auto()     # [X1] ([Xn] OP_ADD)* [k] OP_EQUAL


class MiniscriptContext(Enum):
    """
    Compilation context - determines key format and multisig opcode.
    
    Based on Bitcoin Core's MiniscriptContext enum in miniscript.h.
    """
    P2WSH = "p2wsh"         # 33-byte compressed keys, CHECKMULTISIG
    TAPSCRIPT = "tapscript"  # 32-byte x-only keys, CHECKSIGADD


def _to_xonly(key: bytes) -> bytes:
    """Convert 33-byte compressed key to 32-byte x-only."""
    if len(key) == 33:
        return key[1:]
    elif len(key) == 32:
        return key
    else:
        raise ValueError(f"Invalid key length: {len(key)}")


def _context_key(key: bytes, context: MiniscriptContext) -> bytes:
    """Get key in appropriate format for context."""
    if context == MiniscriptContext.TAPSCRIPT:
        return _to_xonly(key)
    else:
        # P2WSH needs 33-byte compressed
        if len(key) == 32:
            raise ValueError("P2WSH requires 33-byte compressed keys")
        return key


def compile_fragment(
    fragment: Fragment,
    context: MiniscriptContext,
    *,
    key: Optional[bytes] = None,
    keys: Optional[List[bytes]] = None,
    k: Optional[int] = None,
    data: Optional[bytes] = None,
    subs: Optional[List[bytes]] = None,
    verify: bool = False,
) -> bytes:
    """
    Compile a single fragment to Bitcoin Script.
    
    Follows Bitcoin Core's miniscript.h ToScript() logic exactly.
    
    Args:
        fragment: The fragment type to compile
        context: P2WSH or TAPSCRIPT context
        key: Single public key (for PK_K)
        keys: List of public keys (for MULTI, MULTI_A)
        k: Integer parameter (locktime for AFTER, threshold for MULTI)
        data: Hash data (for HASH160)
        subs: Compiled sub-expressions (for wrappers and combinators)
        verify: Whether to use -VERIFY variants
    
    Returns:
        Compiled Bitcoin Script bytes
    
    Reference: Bitcoin Core miniscript.h lines 768-820
    """
    is_tapscript = context == MiniscriptContext.TAPSCRIPT
    
    # === Leaf Fragments ===
    
    if fragment == Fragment.PK_K:
        # case Fragment::PK_K: return BuildScript(ctx.ToPKBytes(node.keys[0]));
        return construct_script([_context_key(key, context)])
    
    elif fragment == Fragment.AFTER:
        # case Fragment::AFTER: return BuildScript(node.k, OP_CHECKLOCKTIMEVERIFY);
        # Standard miniscript - no DROP
        return construct_script([k, opcodes.OP_CHECKLOCKTIMEVERIFY])
    
    elif fragment == Fragment.AFTER_DROP:
        # BIP-65 style: [n] CLTV DROP
        # This is what our existing CLTV scripts use
        return construct_script([k, opcodes.OP_CHECKLOCKTIMEVERIFY, opcodes.OP_DROP])
    
    elif fragment == Fragment.OLDER:
        # case Fragment::OLDER: return BuildScript(node.k, OP_CHECKSEQUENCEVERIFY);
        # BIP-112 relative timelock (CSV) - standard miniscript, no DROP
        return construct_script([k, opcodes.OP_CHECKSEQUENCEVERIFY])
    
    elif fragment == Fragment.OLDER_DROP:
        # BIP-112 style with DROP: [n] CSV DROP
        # Relative timelock variant matching our CLTV style
        return construct_script([k, opcodes.OP_CHECKSEQUENCEVERIFY, opcodes.OP_DROP])
    
    elif fragment == Fragment.HASH160:
        # case Fragment::HASH160: return BuildScript(OP_SIZE, 32, OP_EQUALVERIFY, 
        #                                            OP_HASH160, node.data, 
        #                                            verify ? OP_EQUALVERIFY : OP_EQUAL);
        # Standard miniscript with size check
        return construct_script([
            opcodes.OP_SIZE, 32, opcodes.OP_EQUALVERIFY,
            opcodes.OP_HASH160, data,
            opcodes.OP_EQUALVERIFY if verify else opcodes.OP_EQUAL
        ])
    
    elif fragment == Fragment.HASH160_SIMPLE:
        # Simpler form without size check: OP_HASH160 <hash> OP_EQUALVERIFY
        # This is what our existing data publishing scripts use
        return construct_script([
            opcodes.OP_HASH160, data, opcodes.OP_EQUALVERIFY
        ])
    
    elif fragment == Fragment.JUST_0:
        # case Fragment::JUST_0: return BuildScript(OP_0);
        return construct_script([opcodes.OP_0])
    
    elif fragment == Fragment.JUST_1:
        # case Fragment::JUST_1: return BuildScript(OP_1);
        return construct_script([opcodes.OP_1])
    
    # === Wrapper Fragments ===
    # Note: For wrappers and combinators, we directly concatenate bytes
    # because construct_script would add push opcodes for byte data
    
    elif fragment == Fragment.WRAP_C:
        # case Fragment::WRAP_C: return BuildScript(subs[0], verify ? OP_CHECKSIGVERIFY : OP_CHECKSIG);
        op = bytes([opcodes.OP_CHECKSIGVERIFY if verify else opcodes.OP_CHECKSIG])
        return subs[0] + op
    
    elif fragment == Fragment.WRAP_V:
        # case Fragment::WRAP_V: return BuildScript(subs[0], OP_VERIFY);
        return subs[0] + bytes([opcodes.OP_VERIFY])
    
    elif fragment == Fragment.WRAP_S:
        # case Fragment::WRAP_S: return BuildScript(OP_SWAP, subs[0]);
        return bytes([opcodes.OP_SWAP]) + subs[0]
    
    elif fragment == Fragment.WRAP_A:
        # case Fragment::WRAP_A: return BuildScript(OP_TOALTSTACK, subs[0], OP_FROMALTSTACK);
        return (bytes([opcodes.OP_TOALTSTACK]) + subs[0] + 
                bytes([opcodes.OP_FROMALTSTACK]))
    
    elif fragment == Fragment.WRAP_N:
        # case Fragment::WRAP_N: return BuildScript(subs[0], OP_0NOTEQUAL);
        return subs[0] + bytes([opcodes.OP_0NOTEQUAL])
    
    # === Combinator Fragments ===
    # Direct concatenation of sub-scripts
    
    elif fragment == Fragment.AND_V:
        # case Fragment::AND_V: return BuildScript(subs[0], subs[1]);
        return subs[0] + subs[1]
    
    elif fragment == Fragment.AND_B:
        # case Fragment::AND_B: return BuildScript(subs[0], subs[1], OP_BOOLAND);
        return subs[0] + subs[1] + bytes([opcodes.OP_BOOLAND])
    
    elif fragment == Fragment.OR_I:
        # case Fragment::OR_I: return BuildScript(OP_IF, subs[0], OP_ELSE, subs[1], OP_ENDIF);
        return (bytes([opcodes.OP_IF]) + subs[0] + 
                bytes([opcodes.OP_ELSE]) + subs[1] + 
                bytes([opcodes.OP_ENDIF]))
    
    elif fragment == Fragment.OR_B:
        # case Fragment::OR_B: return BuildScript(subs[0], subs[1], OP_BOOLOR);
        return subs[0] + subs[1] + bytes([opcodes.OP_BOOLOR])
    
    elif fragment == Fragment.OR_D:
        # case Fragment::OR_D: return BuildScript(subs[0], OP_IFDUP, OP_NOTIF, subs[1], OP_ENDIF);
        return (subs[0] + bytes([opcodes.OP_IFDUP, opcodes.OP_NOTIF]) + 
                subs[1] + bytes([opcodes.OP_ENDIF]))
    
    elif fragment == Fragment.OR_C:
        # case Fragment::OR_C: return BuildScript(subs[0], OP_NOTIF, subs[1], OP_ENDIF);
        return (subs[0] + bytes([opcodes.OP_NOTIF]) + 
                subs[1] + bytes([opcodes.OP_ENDIF]))
    
    elif fragment == Fragment.ANDOR:
        # case Fragment::ANDOR: return BuildScript(subs[0], OP_NOTIF, subs[2], OP_ELSE, subs[1], OP_ENDIF);
        # andor(X, Y, Z) = if X then Y else Z
        return (subs[0] + bytes([opcodes.OP_NOTIF]) + 
                subs[2] + bytes([opcodes.OP_ELSE]) + 
                subs[1] + bytes([opcodes.OP_ENDIF]))
    
    # === Multi-signature Fragments ===
    
    elif fragment == Fragment.MULTI:
        # case Fragment::MULTI: (P2WSH only)
        #   CScript script = BuildScript(node.k);
        #   for (key in keys) script = BuildScript(script, ctx.ToPKBytes(key));
        #   return BuildScript(script, node.keys.size(), OP_CHECKMULTISIG);
        if is_tapscript:
            raise ValueError("MULTI fragment only available in P2WSH context")
        
        script_parts = [k]
        for key in keys:
            script_parts.append(_context_key(key, context))
        script_parts.extend([len(keys), opcodes.OP_CHECKMULTISIG])
        return construct_script(script_parts)
    
    elif fragment == Fragment.MULTI_A:
        # MULTI_A: Tapscript multisig using CHECKSIGADD (BIP-342)
        #
        # IMPORTANT: This IS supported by Bitcoin Core! Despite some confusion,
        # BIP-342 added CHECKSIGADD specifically for multisig constructions in Tapscript.
        # Bitcoin Core's miniscript library supports multi_a() and their descriptor
        # language includes multi_a() for Taproot multisig.
        #
        # See: bitcoin/doc/descriptors.md - "multi_a(k,KEY_1,KEY_2,...,KEY_N) (only inside tr)"
        # See: bitcoin/src/test/miniscript_tests.cpp - extensive multi_a tests
        #
        # case Fragment::MULTI_A: (Tapscript only)
        #   CScript script = BuildScript(ctx.ToPKBytes(*keys.begin()), OP_CHECKSIG);
        #   for (key in keys[1:]) script = BuildScript(script, ctx.ToPKBytes(key), OP_CHECKSIGADD);
        #   return BuildScript(script, node.k, OP_NUMEQUAL);
        if not is_tapscript:
            raise ValueError("MULTI_A fragment only available in Tapscript context")
        
        # Build script manually because construct_script treats OP_CHECKSIGADD (0xba)
        # as data to push, not as an opcode
        result = b''
        
        # First key with CHECKSIG: <xonly_key> OP_CHECKSIG
        first_key = _context_key(keys[0], context)
        result += bytes([len(first_key)]) + first_key + bytes([opcodes.OP_CHECKSIG])
        
        # Remaining keys with CHECKSIGADD: <xonly_key> OP_CHECKSIGADD
        for key in keys[1:]:
            xonly_key = _context_key(key, context)
            result += bytes([len(xonly_key)]) + xonly_key + bytes([OP_CHECKSIGADD])
        
        # Threshold check: k OP_NUMEQUAL
        # For small k (1-16), use OP_1 through OP_16
        if 1 <= k <= 16:
            result += bytes([opcodes.OP_1 + k - 1, opcodes.OP_NUMEQUAL])
        else:
            # For larger k, push as data (but this is unusual for multi_a)
            result += construct_script([k, opcodes.OP_NUMEQUAL])
        
        return result
    
    # === Threshold Fragment ===
    
    elif fragment == Fragment.THRESH:
        # case Fragment::THRESH:
        #   CScript script = subs[0];
        #   for (i = 1..n) script = BuildScript(script, subs[i], OP_ADD);
        #   return BuildScript(script, node.k, verify ? OP_EQUALVERIFY : OP_EQUAL);
        result = subs[0]
        for sub in subs[1:]:
            result = result + sub + bytes([opcodes.OP_ADD])
        # Add threshold check
        eq_op = opcodes.OP_EQUALVERIFY if verify else opcodes.OP_EQUAL
        result = result + construct_script([k, eq_op])
        return result
    
    else:
        raise ValueError(f"Unknown fragment: {fragment}")


__all__ = ['Fragment', 'MiniscriptContext', 'compile_fragment']

