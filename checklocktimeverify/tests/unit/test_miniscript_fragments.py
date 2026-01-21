"""
Unit tests for Miniscript fragments.

Tests the new fragments added for Trident-style vault support:
- older() - BIP-112 relative timelock (CSV)
- or_b(), or_d(), or_c() - OR combinators
- andor() - Conditional combinator
- wrap_s, wrap_a, wrap_n - Additional wrappers

Reference: Bitcoin Core miniscript.h
"""

import pytest
from electrum.bitcoin import opcodes

# Import from cltv_lib
import sys
sys.path.insert(0, '/Users/macbook/src/electrum')
sys.path.insert(0, '/Users/macbook/src/electrum-plugins/checklocktimeverify')

from cltv_lib.miniscript import compile_miniscript, MiniscriptContext
from cltv_lib.miniscript.node import (
    pk, after, after_drop, older, older_drop,
    and_v, and_b, or_i, or_b, or_d, or_c, andor,
    multi, multi_a, thresh,
    v, c, wrap_s, wrap_a, wrap_n,
)


# Test key (33 bytes compressed)
TEST_KEY = b'\x02' + b'\x11' * 32
TEST_KEY_2 = b'\x02' + b'\x22' * 32
TEST_KEY_3 = b'\x02' + b'\x33' * 32


class TestOlderFragment:
    """Tests for older() - BIP-112 CSV relative timelock."""
    
    def test_older_compiles(self):
        """older(N) should compile to [N] OP_CHECKSEQUENCEVERIFY."""
        script = compile_miniscript('older(144)', {}, MiniscriptContext.P2WSH)
        # 144 = 0x90, pushes as 2 bytes: 0x0190
        # OP_CHECKSEQUENCEVERIFY = 0xb2
        assert script.endswith(bytes([opcodes.OP_CHECKSEQUENCEVERIFY]))
    
    def test_older_drop_compiles(self):
        """older_drop(N) should compile to [N] OP_CSV OP_DROP."""
        script = compile_miniscript('older_drop(144)', {}, MiniscriptContext.P2WSH)
        assert script.endswith(bytes([opcodes.OP_CHECKSEQUENCEVERIFY, opcodes.OP_DROP]))
    
    def test_older_with_and_v(self):
        """older() combined with and_v() for recovery paths."""
        script = compile_miniscript(
            'and_v(older(25920), c:pk(key))',
            {'key': TEST_KEY},
            MiniscriptContext.P2WSH
        )
        # Should contain CSV followed by key and CHECKSIG
        assert bytes([opcodes.OP_CHECKSEQUENCEVERIFY]) in script
        assert bytes([opcodes.OP_CHECKSIG]) in script


class TestOrCombinators:
    """Tests for or_b(), or_d(), or_c() combinators."""
    
    def test_or_b_compiles(self):
        """or_b(X, Y) should compile to [X] [Y] OP_BOOLOR."""
        script = compile_miniscript(
            'or_b(c:pk(a), c:pk(b))',
            {'a': TEST_KEY, 'b': TEST_KEY_2},
            MiniscriptContext.P2WSH
        )
        assert script.endswith(bytes([opcodes.OP_BOOLOR]))
    
    def test_or_d_compiles(self):
        """or_d(X, Y) should compile to [X] OP_IFDUP OP_NOTIF [Y] OP_ENDIF."""
        script = compile_miniscript(
            'or_d(c:pk(a), c:pk(b))',
            {'a': TEST_KEY, 'b': TEST_KEY_2},
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_IFDUP]) in script
        assert bytes([opcodes.OP_NOTIF]) in script
        assert bytes([opcodes.OP_ENDIF]) in script
    
    def test_or_c_compiles(self):
        """or_c(X, Y) should compile to [X] OP_NOTIF [Y] OP_ENDIF."""
        script = compile_miniscript(
            'or_c(c:pk(a), c:pk(b))',
            {'a': TEST_KEY, 'b': TEST_KEY_2},
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_NOTIF]) in script
        assert bytes([opcodes.OP_ENDIF]) in script
        # or_c does NOT have IFDUP (unlike or_d)
        assert bytes([opcodes.OP_IFDUP]) not in script


class TestAndorFragment:
    """Tests for andor(X, Y, Z) - conditional combinator."""
    
    def test_andor_compiles(self):
        """andor(X, Y, Z) should compile to [X] OP_NOTIF [Z] OP_ELSE [Y] OP_ENDIF."""
        script = compile_miniscript(
            'andor(c:pk(a), c:pk(b), c:pk(c))',
            {'a': TEST_KEY, 'b': TEST_KEY_2, 'c': TEST_KEY_3},
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_NOTIF]) in script
        assert bytes([opcodes.OP_ELSE]) in script
        assert bytes([opcodes.OP_ENDIF]) in script
    
    def test_andor_with_timelock(self):
        """andor() with timelock for vault-style policies."""
        # If key1 signs, then key2 must also sign
        # Otherwise after timeout, key3 can sign alone
        script = compile_miniscript(
            'andor(c:pk(key1), c:pk(key2), and_v(older(1000), c:pk(key3)))',
            {'key1': TEST_KEY, 'key2': TEST_KEY_2, 'key3': TEST_KEY_3},
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_CHECKSEQUENCEVERIFY]) in script


class TestWrappers:
    """Tests for s:, a:, n: wrappers."""
    
    def test_wrap_s_compiles(self):
        """s: wrapper should add OP_SWAP at start."""
        node = wrap_s(c(pk(TEST_KEY)))
        script = node.compile(MiniscriptContext.P2WSH)
        assert script.startswith(bytes([opcodes.OP_SWAP]))
    
    def test_wrap_a_compiles(self):
        """a: wrapper should use altstack."""
        node = wrap_a(c(pk(TEST_KEY)))
        script = node.compile(MiniscriptContext.P2WSH)
        assert bytes([opcodes.OP_TOALTSTACK]) in script
        assert bytes([opcodes.OP_FROMALTSTACK]) in script
    
    def test_wrap_n_compiles(self):
        """n: wrapper should add OP_0NOTEQUAL at end."""
        node = wrap_n(c(pk(TEST_KEY)))
        script = node.compile(MiniscriptContext.P2WSH)
        assert script.endswith(bytes([opcodes.OP_0NOTEQUAL]))


class TestTridentStyle:
    """Tests for Trident-style vault policies."""
    
    @pytest.fixture
    def trident_keys(self):
        """Create 7 keys for Trident vault."""
        return {
            'C1': b'\x02' + b'\x01' * 32,  # Customer key 1
            'C2': b'\x02' + b'\x02' * 32,  # Customer key 2
            'C3': b'\x02' + b'\x03' * 32,  # Customer key 3
            'A1': b'\x02' + b'\x04' * 32,  # AnchorWatch key 1
            'A2': b'\x02' + b'\x05' * 32,  # AnchorWatch key 2
            'A3': b'\x02' + b'\x06' * 32,  # AnchorWatch key 3
            'R': b'\x02' + b'\x07' * 32,   # Recovery partner
        }
    
    def test_customer_threshold(self, trident_keys):
        """Customer 2-of-3 threshold compiles."""
        script = compile_miniscript(
            'thresh(2, c:pk(C1), c:pk(C2), c:pk(C3))',
            trident_keys,
            MiniscriptContext.P2WSH
        )
        assert len(script) > 0
    
    def test_phase1_immediate(self, trident_keys):
        """Phase 1: Customer 2-of-3 AND AnchorWatch 2-of-3."""
        script = compile_miniscript(
            'and_v(thresh(2, c:pk(C1), c:pk(C2), c:pk(C3)), thresh(2, c:pk(A1), c:pk(A2), c:pk(A3)))',
            trident_keys,
            MiniscriptContext.P2WSH
        )
        # Should be around 218 bytes
        assert 200 < len(script) < 250
    
    def test_phase4_selfcustody(self, trident_keys):
        """Phase 4: After timeout, Customer 2-of-3 only."""
        script = compile_miniscript(
            'and_v(older(54000), thresh(2, c:pk(C1), c:pk(C2), c:pk(C3)))',
            trident_keys,
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_CHECKSEQUENCEVERIFY]) in script
    
    def test_phase3_recovery(self, trident_keys):
        """Phase 3: After timeout, AnchorWatch 2-of-3 + Recovery partner."""
        script = compile_miniscript(
            'and_v(older(47520), and_v(thresh(2, c:pk(A1), c:pk(A2), c:pk(A3)), c:pk(R)))',
            trident_keys,
            MiniscriptContext.P2WSH
        )
        assert bytes([opcodes.OP_CHECKSEQUENCEVERIFY]) in script


class TestTapscriptContext:
    """Tests for Tapscript context with new fragments."""
    
    def test_older_in_tapscript(self):
        """older() works in Tapscript context."""
        script = compile_miniscript(
            'and_v(older(1000), c:pk(key))',
            {'key': TEST_KEY},
            MiniscriptContext.TAPSCRIPT
        )
        # In Tapscript, key is 32 bytes (x-only)
        assert bytes([opcodes.OP_CHECKSEQUENCEVERIFY]) in script
    
    def test_or_combinators_in_tapscript(self):
        """OR combinators work in Tapscript context."""
        script = compile_miniscript(
            'or_d(c:pk(a), c:pk(b))',
            {'a': TEST_KEY, 'b': TEST_KEY_2},
            MiniscriptContext.TAPSCRIPT
        )
        assert bytes([opcodes.OP_IFDUP]) in script


if __name__ == '__main__':
    pytest.main([__file__, '-v'])










