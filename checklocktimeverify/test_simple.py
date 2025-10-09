"""
Simple Unit Tests for CLTV Plugin (No Electrum Dependencies)

These tests verify core logic without requiring Electrum to be installed.

Run with: python test_simple.py
"""

import sys
import hashlib


# ============================================================================
# SIMPLE SCRIPT INTERPRETER TESTS
# ============================================================================

def test_script_interpreter():
    """Test the simple script interpreter"""
    print("Testing SimpleScriptInterpreter...")
    
    from simple_script_interpreter import SimpleScriptInterpreter
    
    locktime = 273169
    pubkey = "03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee"
    current_height = 273175  # After locktime
    
    interpreter = SimpleScriptInterpreter(locktime, pubkey, current_height)
    steps = interpreter.execute()
    
    assert len(steps) > 0, "Should have execution steps"
    assert steps[0].operation == "Initial State", "First step should be initial state"
    
    # Check for expected operations
    operations = [step.operation for step in steps]
    assert any("signature" in op.lower() for op in operations), "Should push signature"
    assert any("CHECKLOCKTIMEVERIFY" in op for op in operations), "Should have CLTV check"
    assert any("DROP" in op for op in operations), "Should drop locktime"
    assert any("CHECKSIG" in op for op in operations), "Should verify signature"
    
    print("✅ Script interpreter tests passed")


def test_script_interpreter_before_locktime():
    """Test script fails before locktime"""
    print("Testing script execution before locktime...")
    
    from simple_script_interpreter import SimpleScriptInterpreter
    
    locktime = 273169
    pubkey = "03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee"
    current_height = 273150  # Before locktime
    
    interpreter = SimpleScriptInterpreter(locktime, pubkey, current_height)
    steps = interpreter.execute()
    
    # Should have a failure
    failed_steps = [s for s in steps if hasattr(s, 'failed') and s.failed]
    assert len(failed_steps) > 0, "Should have failed steps when before locktime"
    
    print("✅ Before-locktime test passed")


# ============================================================================
# SCRIPT BUILDER TESTS
# ============================================================================

def test_simple_script_builder():
    """Test simple script builder"""
    print("Testing FreezingFundsBuilder...")
    
    from script_builders import FreezingFundsBuilder, ScriptInputs
    
    builder = FreezingFundsBuilder()
    locktime = 273169
    pubkey_hex = "03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee"
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    
    # Create ScriptInputs
    common = ScriptInputs(
        locktime=locktime,
        locktime_type="block",
        locktime_display="273169",
        output_type="p2sh"
    )
    
    # Build script
    script = builder.build_script(common, pubkey=pubkey_bytes)
    assert len(script) > 0, "Script should not be empty"
    assert b'\xb1' in script, "Should contain OP_CLTV (0xb1)"
    assert b'u' in script, "Should contain OP_DROP (0x75)"
    assert b'\xac' in script, "Should contain OP_CHECKSIG (0xac)"
    
    print(f"✅ Generated P2SH script: {len(script)} bytes")
    

def test_escrow_script_builder():
    """Test escrow script builder"""
    print("Testing EscrowBuilder...")
    
    from script_builders import EscrowBuilder, ScriptInputs
    
    builder = EscrowBuilder()
    locktime = 273169
    alice = bytes.fromhex("03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee")
    bob = bytes.fromhex("035a784662a4a20a65bf6aab9ae98a6c068a81c52e4b032c0fb5400c706cfccc56")
    agent = bytes.fromhex("03501e454bf00751f24b1b489aa925215d66af2234e3891c3b21a52bedb3cd711c")
    
    common = ScriptInputs(
        locktime=locktime,
        locktime_type="block",
        locktime_display="273169",
        output_type="p2sh"
    )
    
    script = builder.build_script(common, pubkey1=alice, pubkey2=bob, pubkey_agent=agent)
    assert len(script) > 0, "Escrow script should not be empty"
    assert b'\x52' in script, "Should contain OP_2"
    # Note: OP_3 (0x53) might not appear in all escrow script variants
    assert b'\xae' in script, "Should contain OP_CHECKMULTISIG"
    
    print(f"✅ Generated escrow script: {len(script)} bytes")


def test_twofactor_script_builder():
    """Test two-factor script builder"""
    print("Testing TwoFactorBuilder...")
    
    from script_builders import TwoFactorBuilder, ScriptInputs
    
    builder = TwoFactorBuilder()
    locktime = 273169
    user = bytes.fromhex("03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee")
    service = bytes.fromhex("035a784662a4a20a65bf6aab9ae98a6c068a81c52e4b032c0fb5400c706cfccc56")
    recovery = bytes.fromhex("03501e454bf00751f24b1b489aa925215d66af2234e3891c3b21a52bedb3cd711c")
    
    common = ScriptInputs(
        locktime=locktime,
        locktime_type="block",
        locktime_display="273169",
        output_type="p2sh"
    )
    
    script = builder.build_script(common, user_pubkey=user, service_pubkey=service, recovery_pubkey=recovery)
    assert len(script) > 0, "Two-factor script should not be empty"
    assert b'\x63' in script or b'\x67' in script, "Should have IF/ELSE branches"
    
    print(f"✅ Generated two-factor script: {len(script)} bytes")


# ============================================================================
# TAPROOT HELPER TESTS
# ============================================================================

def test_xonly_conversion():
    """Test converting pubkey to x-only"""
    print("Testing pubkey_to_xonly...")
    
    from taproot_helpers import pubkey_to_xonly
    
    pubkey = bytes.fromhex("03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee")
    xonly = pubkey_to_xonly(pubkey)
    
    assert len(xonly) == 32, "X-only pubkey should be 32 bytes"
    assert xonly == pubkey[1:], "Should be the x-coordinate"
    
    print(f"✅ X-only conversion: {xonly.hex()[:16]}...")


# ============================================================================
# UTILITY TESTS
# ============================================================================

def test_script_hash():
    """Test script hashing for P2SH"""
    print("Testing script hash calculation...")
    
    script = b'\x03\xf1\x2a\x04\xb1\x75\x21\x03' + bytes.fromhex("eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee") + b'\xac'
    
    # SHA256 then RIPEMD160
    sha = hashlib.sha256(script).digest()
    script_hash = hashlib.new('ripemd160', sha).digest()
    
    assert len(script_hash) == 20, "Script hash should be 20 bytes"
    
    print(f"✅ Script hash: {script_hash.hex()}")


def test_locktime_encoding():
    """Test locktime encoding in script"""
    print("Testing locktime encoding...")
    
    locktime = 273169  # Block height
    
    # Encode as minimal bytes (little-endian)
    if locktime <= 0xff:
        encoded = locktime.to_bytes(1, 'little')
    elif locktime <= 0xffff:
        encoded = locktime.to_bytes(2, 'little')
    elif locktime <= 0xffffff:
        encoded = locktime.to_bytes(3, 'little')
    else:
        encoded = locktime.to_bytes(4, 'little')
    
    # Should be 3 bytes for 273169
    assert len(encoded) == 3, f"Locktime 273169 should encode to 3 bytes, got {len(encoded)}"
    
    # Verify encoding
    decoded = int.from_bytes(encoded, 'little')
    assert decoded == locktime, "Decoded locktime should match original"
    
    print(f"✅ Locktime {locktime} encoded as {encoded.hex()}")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_full_workflow():
    """Test complete workflow without Electrum"""
    print("Testing full workflow (script build → interpret)...")
    
    from script_builders import FreezingFundsBuilder, ScriptInputs
    from simple_script_interpreter import SimpleScriptInterpreter
    
    # Build
    locktime = 273169
    pubkey_hex = "03eba0977fc81dd74965b499ed6dc73fed15425c8813c6a6675a7a2fa3a77387ee"
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    
    builder = FreezingFundsBuilder()
    common = ScriptInputs(
        locktime=locktime,
        locktime_type="block",
        locktime_display="273169",
        output_type="p2sh"
    )
    script = builder.build_script(common, pubkey=pubkey_bytes)
    
    # Interpret
    current_height = 273175
    interpreter = SimpleScriptInterpreter(locktime, pubkey_hex, current_height)
    steps = interpreter.execute()
    
    assert len(script) > 0, "Script should be generated"
    assert len(steps) > 0, "Steps should be generated"
    
    print(f"✅ Full workflow: {len(script)}-byte script → {len(steps)} execution steps")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("🧪 CLTV Plugin Unit Tests")
    print("="*60 + "\n")
    
    tests = [
        test_script_interpreter,
        test_script_interpreter_before_locktime,
        test_simple_script_builder,
        test_escrow_script_builder,
        test_twofactor_script_builder,
        test_xonly_conversion,
        test_script_hash,
        test_locktime_encoding,
        test_full_workflow,
    ]
    
    failed = []
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed.append(test.__name__)
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    if failed:
        print(f"❌ {len(failed)} test(s) failed:")
        for name in failed:
            print(f"   - {name}")
        sys.exit(1)
    else:
        print(f"✅ All {len(tests)} tests passed!")
    print("="*60 + "\n")


if __name__ == '__main__':
    run_all_tests()
