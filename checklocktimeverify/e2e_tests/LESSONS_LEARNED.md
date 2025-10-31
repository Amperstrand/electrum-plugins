# 🎓 LESSONS LEARNED - BIP-65 CLTV Implementation

## 📋 Critical Lessons from P2WSH Testing

### 1. ⚠️ **HASH ALGORITHM BUG - Data Publishing Example**

**Issue**: Data publishing publisher path was unspendable due to wrong hash opcode

**Root Cause**:
- **BIP-65 Spec (line 155)**: `HASH160 <Hash160(encryption key)> EQUALVERIFY`
- **Our Implementation**: `OP_SHA256 <data_hash> EQUALVERIFY` ❌

**The Bug**:
```
BIP-65 uses:    HASH160  = RIPEMD160(SHA256(x))  [20 bytes output]
We implemented: OP_SHA256 = SHA256(x)             [32 bytes output]
```

**Impact**:
- Script expects 20-byte HASH160 output
- We provide 32-byte SHA256 hash
- `OP_EQUALVERIFY` fails because lengths don't match
- Publisher path becomes unspendable

**Resolution**:
1. Change `OP_SHA256` (0xa8) to `OP_HASH160` (0xa9) in script builder
2. Change `data_hash` generation from `hashlib.sha256()` to `hash160()` (RIPEMD160(SHA256(x)))
3. Update hash from 32 bytes (64 hex chars) to 20 bytes (40 hex chars)

**Lesson**: **Always verify exact opcodes against BIP spec!** Don't assume similar-sounding operations are equivalent.

---

### 2. ✅ **Locktime Must Match Exactly**

**Issue**: "Witness program hash mismatch" errors when locktime differs between funding and sweeping

**Resolution**:
- Use **exact same locktime** value for funding and sweeping
- Store locktime during funding: `funding_locktime = 108088`
- Use stored locktime for sweeping: `script_params['locktime'] = funding_locktime`

**Lesson**: **Script parameters must be 100% consistent** throughout the UTXO lifecycle.

---

### 3. ✅ **Sweeper Constructor Compatibility**

**Issue**: `SimpleCLTVSweeper() takes no arguments` when registry passes kwargs

**Resolution**:
```python
def __init__(self, **kwargs):
    """Accept kwargs for registry compatibility"""
    pass  # Simple CLTV has no path variants
```

**Lesson**: **All sweepers must accept `**kwargs`** even if they don't use them, for registry compatibility.

---

### 4. ✅ **Example-Specific Logic Required**

**Issue**: Generic sweeping doesn't work - each BIP-65 example has unique requirements

**BIP-65 Examples Have Different Structures**:
1. **Simple CLTV**: 1 path, 1 signature, no variants
2. **Escrow**: 2 paths (normal/arbitration), different signers
3. **Two-Factor**: 2 paths (normal/recovery), user key always required
4. **Payment Channel**: 2 paths (cooperative/refund), 2-of-2 or timeout
5. **Data Publishing**: 2 paths (publisher/buyer), **preimage required for publisher only**

**Lesson**: **Don't over-generalize!** Each example needs tailored logic.

---

### 5. ✅ **Variant-Specific Parameters**

**Issue**: Used same `data_preimage` for both publisher and buyer_refund paths

**Resolution**:
- Each variant gets its own parameters
- Publisher: `"Hello, World! This is the data to be published for publisher"`
- Buyer: `"Hello, World! This is the data to be published for buyer_refund"`
- This creates different script hashes → different addresses

**Lesson**: **Path variants with same script structure still need unique identifiers** for testing.

---

### 6. ✅ **Electrum nLockTime Serialization Bug**

**Issue**: `PartialTransaction.locktime` property not serialized to raw transaction bytes

**Workaround**:
```python
# Manually fix nLockTime in raw transaction
tx_bytes = bytes.fromhex(tx_hex)
correct_locktime_bytes = locktime.to_bytes(4, 'little')
tx_bytes_fixed = tx_bytes[:-4] + correct_locktime_bytes
tx_hex = tx_bytes_fixed.hex()
```

**Lesson**: **Test end-to-end with actual blockchain**, don't just trust library behavior.

---

### 7. ✅ **UTXO Vout Mapping**

**Issue**: `bad-txns-inputs-missingorspent` when vout indices were wrong

**Resolution**:
- Use unique amounts (1000, 1001, 1002 sats) for each test
- Query transaction after funding to map vout correctly
- Or use `paytomany` and query to get actual vout mapping

**Lesson**: **Never assume vout order** - always query and verify.

---

### 8. ✅ **Mempool Chain Limits**

**Issue**: `too-long-mempool-chain` prevented sequential testing

**Resolution**:
- Use batch funding (`paytomany`) to create all UTXOs in single transaction
- Wait for mempool to clear before new batch
- Or use confirmed UTXOs without unconfirmed parents

**Lesson**: **Testnet has limitations** - design tests to work within constraints.

---

### 9. ✅ **Compressed vs X-Only Pubkeys**

**Issue**: Mixed up 33-byte compressed and 32-byte x-only pubkeys

**Resolution**:
- **P2WSH**: Always use 33-byte compressed pubkeys
- **Taproot**: Always use 32-byte x-only pubkeys (remove first byte)
- Keep them separate and labeled clearly

**Lesson**: **Label your pubkey formats explicitly** to avoid confusion.

---

### 10. ✅ **Test State Management**

**Issue**: Old test state caused conflicts and confusion

**Resolution**:
- Wipe `test_state.json` when starting fresh
- Document current test state clearly
- Use unique addresses for each test run

**Lesson**: **Clean state = clean debugging**. Don't mix old and new test data.

---

## 📊 Success Metrics

### P2WSH Testing Results:
- **8 out of 9 paths working** (88.9% before hash fix)
- **9 out of 9 paths expected** (100% after hash fix)
- **All 5 BIP-65 examples tested**
- **8 successful on-chain sweeps** on testnet4

### Key Fixes Applied:
1. ✅ Sweeper constructor compatibility
2. ✅ Locktime consistency
3. ✅ Example-specific logic
4. ✅ Variant-specific parameters
5. ✅ nLockTime serialization workaround
6. ✅ UTXO vout mapping
7. ✅ Mempool chain handling
8. ✅ Pubkey format separation
9. 🔧 **Hash algorithm fix (pending)**

---

## 🎯 Key Takeaways

1. **Read the spec carefully** - Don't assume, verify exact opcodes
2. **Test end-to-end early** - Catch integration issues sooner
3. **Keep it simple** - Example-specific logic beats over-engineering
4. **Document as you go** - Future you will thank you
5. **One thing at a time** - Fix systematically, don't rush

---

**Date**: October 27, 2025
**Status**: P2WSH testing complete (minus hash fix)
**Next**: Fix HASH160 bug, re-test data publishing, then Taproot

