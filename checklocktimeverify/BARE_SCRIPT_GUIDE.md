# Bare Script Transaction Guide

**Feature:** Custom Transaction Builder for Raw Script Outputs  
**Use Case:** Miner Sacrifice (TRUE BIP-65 Example)  
**Status:** Educational / Advanced Users  
**Network:** SIGNET/TESTNET ONLY ⚠️

---

## 📚 What is a Bare Script Transaction?

### Normal Bitcoin Transactions
```
Address: 2N8hwP1WmJrFF5QWABn38y63uYLhnJYJYTF
         ↓
       P2SH wraps the script
         ↓
Script:  <locktime> OP_CLTV OP_DROP OP_TRUE
```

### Bare Script Transaction (This Feature!)
```
No Address!
     ↓
Direct scriptPubKey in transaction output
     ↓
Script:  <locktime> OP_CLTV OP_DROP OP_TRUE
```

**Key Difference:** No address wrapping, script goes directly in `scriptPubKey`

---

## 🎯 Why Would You Want This?

### 1. **TRUE BIP-65 Example**
The BIP-65 specification shows miner sacrifice as:
```
<expiry time> CHECKLOCKTIMEVERIFY DROP OP_TRUE
```

This is a **bare script**, not wrapped in P2SH!

### 2. **Educational Value**
Learn about:
- Low-level transaction building
- `scriptPubKey` vs `redeemScript`
- Standard vs non-standard transactions
- Why P2SH was invented

### 3. **Smaller Transactions**
```
Bare Script:  ~10 bytes in scriptPubKey
P2SH:         22 bytes + redeem script on spend
Taproot:      34 bytes + witness data on spend
```

### 4. **Immediate Visibility**
The script is visible on-chain immediately (not hidden until spend).

---

## ⚠️ Critical Warnings

### Non-Standard Transaction

**Problem:** Most Bitcoin nodes won't relay this!

```python
# Bitcoin Core's IsStandard() check fails because:
if (!scriptPubKey.IsPushOnly())  # Has OP_CLTV, OP_DROP, OP_TRUE
    return false;  # REJECTED!
```

**Impact:**
- May not propagate through network
- Might need direct miner submission
- Could get stuck in mempool
- **Use SIGNET/TESTNET for experimentation**

### Permanently Unrecoverable

After locktime expires:
```
ANYONE can spend = Effectively burned to miners
```

**There is NO private key** that can recover these funds!

---

## 🚀 Step-by-Step Guide

### Step 1: Generate Bare Script

1. Open plugin: `Tools → CheckLockTimeVerify / BIP-65`
2. Go to "Miner Sacrifice" tab
3. Select **"Bare Script"** radio button
4. Set locktime (when coins become claimable)
5. Click "Generate Sacrifice Address (UNRECOVERABLE)"
6. Confirm the warning dialog

**Result:** Script hex displayed, transaction button enabled

### Step 2: Create Transaction

1. Click **"Create Bare Script Transaction →"**
2. Warning dialog appears - read carefully!
3. Enter amount in satoshis (e.g., `10000`)
4. Review script preview
5. Click "Create Transaction"

**Result:** Transaction opens in Electrum's preview window

### Step 3: Review Transaction

In the transaction preview:

1. **Outputs tab:** See the raw scriptPubKey
   ```
   Output #0:
   Value: 10000 sats
   scriptPubKey: 03e2f829b175  ← Your bare script!
   (No address!)
   ```

2. **Details tab:** Check transaction size and fee

3. **Inputs tab:** Verify coin selection

### Step 4: Sign & Broadcast

1. Click "Sign" if wallet has keys
2. Click "Broadcast"
3. **Warning:** May fail with "non-standard transaction"

**If broadcast fails:**
- Expected on mainnet
- May work on signet (smaller network)
- Can try broadcasting directly to a miner
- This demonstrates why P2SH exists!

---

## 🔍 Technical Deep Dive

### Transaction Structure

```python
{
  "version": 2,
  "inputs": [
    {
      # Your wallet's coins
    }
  ],
  "outputs": [
    {
      "value": 10000,
      "scriptPubKey": "03e2f829b175"  ← BARE SCRIPT (no address!)
    },
    {
      # Change output (if any)
    }
  ]
}
```

### The scriptPubKey

```
Hex:  03 e2f829 b1 75 51
      ↓   ↓      ↓  ↓  ↓
      |   |      |  |  OP_TRUE (51)
      |   |      |  OP_DROP (75)
      |   |      OP_CHECKLOCKTIMEVERIFY (b1)
      |   Locktime value (870002 = 0x0e2f82)
      Push 3 bytes (03)
```

### Script Execution (After Locktime)

```
Stack:        []
Execute:      03 e2f829    → [870002]
              b1           → Check locktime (passes after block 870002)
              75           → []
              51           → [true]
Result:       ANYONE CAN SPEND (script always returns true)
```

---

## 💡 Code Example

### How It Works Internally

```python
from electrum.transaction import PartialTxOutput
from electrum.util import bfh

# 1. Create output with RAW SCRIPT (no address!)
script_bytes = bfh("03e2f829b175")  # Your bare script

outputs = [
    PartialTxOutput(
        scriptpubkey=script_bytes,  # Direct script, no address!
        value=10000  # Amount in satoshis
    )
]

# 2. Build transaction
tx = wallet.make_unsigned_transaction(
    coins=wallet.get_spendable_coins(None),
    outputs=outputs,
    fee=None  # Auto-calculate
)

# 3. Show to user
window.show_transaction(tx)
```

### Comparison with P2SH

```python
# P2SH (normal way):
address = "2N8hwP1WmJrFF5QWABn38y63uYLhnJYJYTF"
outputs = [TxOutput.from_address_and_value(address, 10000)]

# Bare Script (this feature!):
script = bfh("03e2f829b175")
outputs = [PartialTxOutput(scriptpubkey=script, value=10000)]
```

---

## 📊 Comparison Table

| Aspect | Bare Script | P2SH | Taproot |
|--------|-------------|------|---------|
| **Address** | None | Yes (2...) | Yes (tb1p...) |
| **Size** | ~10 bytes | 22 bytes | 34 bytes |
| **Standard** | ❌ No | ✅ Yes | ✅ Yes |
| **Relay** | ⚠️ Difficult | ✅ Easy | ✅ Easy |
| **Privacy** | 🔴 Visible | 🟡 Hidden | 🟢 Best |
| **BIP-65** | ✅ TRUE | 🟡 Wrapped | 🟡 Wrapped |
| **Use Case** | Educational | Production | Modern |

---

## 🎓 Educational Insights

### What You Learn

1. **Transaction Building**
   - Not all outputs need addresses
   - `scriptPubKey` is what matters
   - Addresses are just encoding

2. **Standard vs Non-Standard**
   - Bitcoin Core relay policy
   - Why some scripts need wrapping
   - Evolution of P2SH and Taproot

3. **Script Execution**
   - Stack-based execution
   - Time-locked conditions
   - Provably unspendable outputs

4. **Network Behavior**
   - Transaction propagation
   - Mempool acceptance
   - Miner incentives

### Why P2SH Exists

Bare scripts taught us:
```
Problem:  Non-standard scripts don't relay
Solution: Wrap them in a standard script (P2SH)
Result:   Any script can be used via P2SH

This is why P2SH was invented! 🎉
```

---

## 🧪 Testing Checklist

### Before Broadcasting

- [ ] Amount is correct (in satoshis)
- [ ] Locktime is what you intended
- [ ] You're on SIGNET/TESTNET (not mainnet!)
- [ ] You understand funds are unrecoverable
- [ ] You read all warnings

### After Broadcasting

- [ ] Check if transaction propagated
- [ ] Monitor block confirmations
- [ ] Verify script on block explorer
- [ ] Try sweeping after locktime (anyone can!)

### Expected Outcomes

**Signet:** May work (small network, relaxed rules)  
**Testnet:** Might work (more lenient than mainnet)  
**Mainnet:** ❌ DON'T TRY (will fail, policy violation)

---

## 🔧 Troubleshooting

### "Transaction is non-standard"

**Cause:** Bitcoin Core's `IsStandard()` rejected it  
**Fix:** This is expected! Use P2SH instead for production

### "Transaction not propagating"

**Cause:** Nodes rejecting non-standard tx  
**Fix:** Try broadcasting to different node or miner directly

### "Can't create transaction"

**Cause:** Insufficient funds or no spendable coins  
**Fix:** Fund your wallet first

### "Error: scriptpubkey"

**Cause:** Invalid script hex  
**Fix:** Regenerate bare script, don't edit manually

---

## 📚 Further Reading

### BIP-65 Specification
- Section on miner sacrifice
- Script examples
- Use cases

### Electrum Documentation
- `PartialTxOutput` API
- `make_unsigned_transaction()` method
- Transaction serialization

### Bitcoin Script
- Stack-based execution
- Opcode reference
- Script validation rules

---

## ✅ Quick Reference

### Command Sequence
```
1. Miner Sacrifice Tab
2. Select "Bare Script"
3. Set Locktime
4. Generate → Confirm Warning
5. Create Bare Script Transaction →
6. Enter Amount
7. Create Transaction
8. Review in Preview
9. Sign
10. Broadcast (may fail - that's ok!)
```

### Key Files
- `dialogs/miner_sacrifice.py` - Implementation
- `FEATURE_BARE_SCRIPT_TX.md` - Technical details
- This file - User guide

### Logging
All steps logged with `[BARE_TX]` prefix in console.

---

## 🎉 Success Story

**You've created a Bitcoin transaction with a raw script output!**

This is:
- ✅ TRUE BIP-65 example
- ✅ Low-level transaction building
- ✅ Understanding scriptPubKey directly
- ✅ Learning why P2SH exists

**Congratulations!** 🚀

You now understand Bitcoin transactions at a deeper level than most developers!

---

**Created:** October 12, 2025 23:15  
**Feature:** Bare Script Transaction Builder  
**Network:** SIGNET/TESTNET ONLY  
**Safety:** MAXIMUM WARNINGS ⚠️  
**Educational Value:** ⭐⭐⭐⭐⭐
