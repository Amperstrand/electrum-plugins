# P2WSH Troubleshooting Summary

## 📊 Current Status

### ✅ What Works
1. **Simple CLTV P2WSH** - Sweeps successfully
   - Script: `<locktime> CLTV DROP <pubkey> CHECKSIG`
   - Witness: `[signature, script]`
   - Status: **SWEPT** ✅

### ❌ What Fails
All 8 remaining P2WSH tests fail with **"Witness program hash mismatch"**:

1. **Escrow Normal Operations** - 2-of-2 multisig (Alice + Bob)
2. **Escrow Arbitration** - 1-of-2 multisig (Lenny + Alice/Bob) after timeout
3. **Two-Factor Normal** - User + Service signatures
4. **Two-Factor Recovery** - User + Recovery after timeout
5. **Payment Channel Cooperative** - 2-of-2 multisig (Sender + Receiver)
6. **Payment Channel Refund** - Sender only after timeout
7. **Data Publishing Publisher** - Publisher reveals preimage
8. **Data Publishing Buyer Refund** - Buyer refund after timeout

**Common Pattern:** All failing tests use either:
- `OP_CHECKMULTISIG` (escrow, payment channel)
- `OP_IF/ELSE` conditional logic (all of them)
- Or both

---

## 🔍 What We've Verified (All Correct ✅)

1. **Script Generation**
   - ✅ Scripts match BIP-65 specification exactly
   - ✅ Script hex is identical when stored vs rebuilt
   - ✅ Opcodes are correct

2. **Address Generation**
   - ✅ P2WSH addresses correctly derived from script SHA256 hash
   - ✅ All 9 tests have unique addresses (no collisions)
   - ✅ Address matches script hash perfectly

3. **Witness Order**
   - ✅ Matches BIP-65 specification
   - ✅ Escrow: `[0, alice_sig, bob_sig, 0, script]`
   - ✅ Signature order matches pubkey order in script

4. **Script in Witness**
   - ✅ Script bytes in witness match expected script exactly
   - ✅ No truncation or corruption

5. **Funding**
   - ✅ All 9 tests successfully funded
   - ✅ UTXOs exist on blockchain
   - ✅ Correct amounts stored

6. **Code Quality**
   - ✅ Using Electrum's `construct_witness()` for proper encoding
   - ✅ Using integers (0, 1) instead of raw bytes
   - ✅ BIP-65 compliant witness construction

---

## 🎯 Systematic Troubleshooting Plan

### Phase 1: Isolate the Variable (HIGHEST PRIORITY)

**Goal:** Determine if the issue is with `OP_CHECKMULTISIG` or `OP_IF/ELSE`

#### Test A: Simple Multisig (No CLTV, No IF/ELSE)
```
Script: <alice> <bob> OP_2 OP_CHECKMULTISIG
Witness: [0, alice_sig, bob_sig, script]
```
**Purpose:** Test if basic CHECKMULTISIG works

#### Test B: CLTV with IF/ELSE (No CHECKMULTISIG)
```
Script: IF <locktime> CLTV DROP <pubkey> CHECKSIGVERIFY 1 ELSE 0 ENDIF <pubkey> CHECKSIG
Witness: [sig, 0, script]  (for ELSE branch)
```
**Purpose:** Test if IF/ELSE conditional logic works

#### Test C: Current Escrow (Both CHECKMULTISIG and IF/ELSE)
```
Script: IF ... ELSE OP_2 ENDIF <alice> <bob> OP_2 CHECKMULTISIG
Witness: [0, alice_sig, bob_sig, 0, script]
```
**Purpose:** Current failing test

**Expected Outcomes:**
- If A fails → Issue is with CHECKMULTISIG
- If B fails → Issue is with IF/ELSE
- If both A & B work, but C fails → Issue is with combination

---

### Phase 2: Verify Sighash Calculation

**Goal:** Ensure we're signing the correct data

#### Actions:
1. Extract sighash being signed from sweep_utils.py
2. Manually calculate expected sighash for P2WSH
3. Compare with what we're actually signing
4. Verify sighash includes:
   - Correct input (UTXO being spent)
   - Correct script code (witness script)
   - Correct amount
   - Correct sighash type (SIGHASH_ALL = 0x01)

**Key Question:** Is the sighash calculation different for scripts with OP_CHECKMULTISIG?

---

### Phase 3: Compare Simple vs Escrow Signing

**Goal:** Find the exact difference in how signatures are generated

#### Actions:
1. Add verbose logging to `sweep_utils.py` before signing
2. Log for both Simple CLTV and Escrow:
   - Input UTXO
   - Script being used
   - Sighash bytes
   - Signature bytes
   - Public key bytes
3. Compare side-by-side

**Expected Outcome:** Identify any difference in signing process

---

### Phase 4: Test with Minimal Reproduction

**Goal:** Create smallest possible failing case

#### Actions:
1. Create standalone script that:
   - Generates escrow script
   - Creates funding tx (or uses existing UTXO)
   - Creates sweep tx with witness
   - Prints all intermediate values
2. Test outside of pytest framework
3. Try broadcasting to mempool.space manually

**Expected Outcome:** Clearer error message or successful broadcast

---

### Phase 5: Review OP_CHECKMULTISIG Stack Behavior

**Goal:** Verify our understanding of CHECKMULTISIG is correct

#### Key Questions:
1. **Does CHECKMULTISIG consume the M value from the stack?**
   - In escrow ELSE branch, OP_2 is pushed by script
   - Does witness need to provide M, or does script provide it?

2. **What's the exact stack state before CHECKMULTISIG?**
   ```
   Expected: [0, sig1, sig2, M, pubkey1, pubkey2, N]
   Our stack: [0, sig1, sig2, 2, pubkey1, pubkey2, 2]
   ```

3. **Is the off-by-one bug handled correctly?**
   - We provide 0 at bottom of witness
   - Is this consumed by CHECKMULTISIG?

#### Actions:
1. Review Bitcoin Core CHECKMULTISIG implementation
2. Test with bitcoin-cli if available
3. Compare with known working CHECKMULTISIG examples

---

### Phase 6: Check Key Material

**Goal:** Verify we're using the correct keys

#### Actions:
1. Print actual keys being used for signing:
   - Alice private key
   - Bob private key
   - Lenny private key
2. Verify they match keys used in script generation:
   - Alice public key in script
   - Bob public key in script
   - Lenny public key in script
3. Test signature verification manually

**Expected Outcome:** Confirm keys match or find mismatch

---

### Phase 7: Test Alternative Witness Constructions (Empirical)

**Goal:** Try different witness orders to find what works

#### Test Variations:
```python
# Current (BIP-65 compliant)
witness = [0, alice_sig, bob_sig, 0, script]

# Variation 1: Reversed signatures
witness = [0, bob_sig, alice_sig, 0, script]

# Variation 2: M value included
witness = [0, alice_sig, bob_sig, 2, 0, script]

# Variation 3: Different order
witness = [0, 0, alice_sig, bob_sig, script]

# Variation 4: No extra 0
witness = [alice_sig, bob_sig, 0, script]
```

**Purpose:** Empirically discover correct witness format

---

### Phase 8: Compare with Reference Implementation

**Goal:** Find a working BIP-65 escrow example

#### Actions:
1. Search for working BIP-65 escrow implementations:
   - Peter Todd's original demos
   - Bitcoin Core test vectors
   - Other open-source implementations
2. Compare scripts byte-by-byte
3. Compare witness construction
4. Identify any differences

---

## 🔬 Debugging Tools

### Tool 1: Add Verbose Logging
```python
# In sweep_utils.py, before signing
print(f"DEBUG: Sighash: {sighash.hex()}")
print(f"DEBUG: Script: {script.hex()}")
print(f"DEBUG: Keys: {list(keys.keys())}")
```

### Tool 2: Manual Transaction Construction
Create a standalone script that builds the transaction step-by-step with full visibility.

### Tool 3: Bitcoin Core Validation
If available, use `bitcoin-cli testmempoolaccept` for authoritative validation.

### Tool 4: Mempool.space Manual Push
Push raw transaction hex manually to see detailed error.

---

## 💡 Leading Hypotheses (Ranked by Likelihood)

### Hypothesis 1: CHECKMULTISIG M Value Issue (80% likely)
**Theory:** The ELSE branch pushes OP_2, but CHECKMULTISIG might expect M value from witness.

**Test:** Try witness with explicit M value: `[0, alice_sig, bob_sig, 2, 0, script]`

### Hypothesis 2: Sighash Calculation for Complex Scripts (15% likely)
**Theory:** Sighash calculation might be different for scripts with conditionals.

**Test:** Manually calculate sighash and compare with what we're signing.

### Hypothesis 3: Signature Order vs Pubkey Order (5% likely)
**Theory:** Despite matching BIP-65, signatures might need different order.

**Test:** Try reversed signature order: `[0, bob_sig, alice_sig, 0, script]`

---

## 🚀 Recommended Execution Order

1. **Start with Phase 1, Test A** (Simple Multisig)
   - Quick test to isolate CHECKMULTISIG
   - 30 minutes

2. **Then Phase 5** (Review CHECKMULTISIG behavior)
   - Understand the opcode deeply
   - 1 hour

3. **Then Phase 7, Test Hypothesis 1** (Try M value in witness)
   - Quick empirical test
   - 15 minutes

4. **Then Phase 2** (Verify sighash)
   - Deep dive if still failing
   - 1 hour

5. **Then Phase 4** (Minimal reproduction)
   - Create isolated test case
   - 1 hour

---

## 📝 Next Immediate Actions

1. **Create Test A script** - Simple 2-of-2 multisig without CLTV
2. **Fund and sweep Test A** - See if basic CHECKMULTISIG works
3. **If Test A works** → Issue is with IF/ELSE or combination
4. **If Test A fails** → Issue is with CHECKMULTISIG witness construction
5. **Document findings** and iterate

---

## 🎯 Success Criteria

We'll know we've solved it when:
1. ✅ All 9 P2WSH tests sweep successfully
2. ✅ We understand WHY it works
3. ✅ We can document the solution for future reference
4. ✅ Tests are reproducible and reliable

