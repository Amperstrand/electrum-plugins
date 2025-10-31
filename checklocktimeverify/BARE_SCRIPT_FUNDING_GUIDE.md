# Bare Script Funding - Complete Guide

## 🎉 NEW: Plugin Now Creates Bare Script Funding Transactions!

**Problem Solved**: Electrum won't send to bare script outputs (non-standard). Our plugin now handles this automatically!

---

## What We Built

The **Miner Sacrifice** tab now includes a complete bare script workflow:

### Features Added

1. ✅ **Bare Script Address Generation** - Creates `<locktime> CLTV DROP OP_TRUE` script
2. ✅ **Funding Transaction Creator** - Builds raw transaction with bare script output
3. ✅ **Automatic Signing** - Uses your wallet to sign the transaction
4. ✅ **Raw Hex Export** - Shows transaction hex for direct miner submission
5. ✅ **UTXO Selection** - Automatically selects coins from your wallet
6. ✅ **Change Handling** - Creates change output back to your wallet

---

## How to Use (Step-by-Step)

### Step 1: Open Plugin
```
Electrum → Tools → CheckLockTimeVerify → Miner Sacrifice tab
```

### Step 2: Generate Bare Script Address
1. Select **"Bare Script"** output type (default for sacrifice)
2. Set locktime (e.g., `100` blocks in the future)
3. Click **"Generate Sacrifice Address (UNRECOVERABLE)"**
4. Confirm the warning (funds are UNRECOVERABLE!)
5. The target address field auto-fills ✅

### Step 3: Create Funding Transaction
1. Enter amount (e.g., `0.001` BTC)
2. Click **"Create Bare Script Funding Transaction"**
3. Plugin will:
   - Select UTXOs from your wallet
   - Calculate fees (conservative estimate)
   - Create bare script output
   - Add change output (if needed)
   - Sign the transaction
   - Show the result dialog

### Step 4: Submit to Miner

**The dialog shows:**
- ✅ Raw transaction hex
- ✅ Copy button (click to copy hex)
- ⚠️ "Attempt Broadcast" button (will likely fail - expected!)

**Submit to miner:**
```bash
# Copy the hex from the dialog

# Option A: Bitcoin Core (regtest for testing)
bitcoin-cli -regtest sendrawtransaction <hex>
bitcoin-cli -regtest generatetoaddress 1 <address>

# Option B: Signet with custom miner
bitcoin-cli -signet sendrawtransaction <hex>

# Option C: Direct to mining pool
# Contact pool, submit raw hex for custom inclusion
```

---

## Transaction Structure

### What the Plugin Creates

```
Transaction:
  Version: 2
  Inputs:
    [0] Your wallet UTXO (signed with your key)
        - Previous txid: abc123...
        - Output index: 0
        - ScriptSig: <signature> <pubkey>
  
  Outputs:
    [0] Bare Script Output (THE SACRIFICE)
        - Value: 100,000 sats (your amount)
        - ScriptPubKey: 03 a0bb0d b1 75 51
          └─ Decoded: <900000> CHECKLOCKTIMEVERIFY DROP OP_TRUE
    
    [1] Change Output (back to you)
        - Value: 899,800 sats (remaining minus fee)
        - ScriptPubKey: OP_HASH160 <hash> OP_EQUAL (P2SH)
  
  LockTime: 0
```

### Key Point: Bare Script Output

**Normal outputs** (P2SH, P2WPKH):
```
scriptPubKey = OP_HASH160 <hash_of_script> OP_EQUAL
               └─ Script is HASHED and hidden
```

**Bare script output**:
```
scriptPubKey = <locktime> CHECKLOCKTIMEVERIFY DROP OP_TRUE
               └─ Script is DIRECTLY in the output!
```

This is why it's:
- ✅ **Consensus valid** - Bitcoin accepts it
- ❌ **Non-standard** - Nodes won't relay it
- 👁️ **Immediately visible** - Script exposed on-chain

---

## Why This Works

### Transaction Creation Flow

1. **Plugin selects UTXOs** from your wallet
   - Needs enough to cover: amount + fees
   - Selects largest first (simple coin selection)

2. **Creates bare script output**
   - Uses `PartialTxOutput(scriptpubkey=bare_script_bytes, value=amount)`
   - `scriptpubkey` is the ACTUAL script, not a hash!

3. **Adds change output** (if needed)
   - If leftover > 546 sats (dust limit)
   - Sends change back to your wallet

4. **Signs transaction**
   - Uses `wallet.sign_transaction()`
   - Your wallet keys sign the inputs normally
   - Output script doesn't need signing (it's data!)

5. **Exports raw hex**
   - `str(tx)` gives the raw transaction hex
   - Ready for direct submission

### Why Electrum Can't Do This Normally

Electrum's `payto` command only creates **standard** outputs:
- P2PKH
- P2SH
- P2WPKH
- P2WSH
- P2TR

Bare scripts are **non-standard** by design, so Electrum blocks them at the UI level. Our plugin bypasses this by constructing the transaction programmatically!

---

## Testing Strategies

### Strategy 1: Regtest (Best for Development)

**Setup:**
```bash
# Start Bitcoin Core in regtest
bitcoind -regtest -daemon

# Create a wallet
bitcoin-cli -regtest createwallet "test"

# Get an address and mine blocks
ADDR=$(bitcoin-cli -regtest getnewaddress)
bitcoin-cli -regtest generatetoaddress 101 $ADDR
```

**Test the plugin:**
1. Use plugin to create bare script funding tx
2. Copy the raw hex
3. Submit:
```bash
bitcoin-cli -regtest sendrawtransaction <hex>
bitcoin-cli -regtest generatetoaddress 1 $ADDR
```

**Verify:**
```bash
# Get the txid from the output
bitcoin-cli -regtest getrawtransaction <txid> true

# You'll see:
# - "vout": [
#     {
#       "value": 0.001,
#       "scriptPubKey": {
#         "hex": "03a0bb0db17551",  # Your bare script!
#         "type": "nonstandard"
#       }
#     }
#   ]
```

### Strategy 2: Signet with Custom Node

**Challenge**: Signet nodes enforce standardness by default

**Solution**: Run your own signet node with:
```bash
bitcoind -signet -acceptnonstdtxn=1 -daemon
```

Then use the plugin and submit via your node.

### Strategy 3: Direct Miner Submission (Production)

**For mainnet/live networks:**
1. Create transaction with plugin
2. Copy raw hex
3. Contact mining pool
4. Request custom transaction inclusion
5. May require fee negotiation

---

## Error Handling

### "Broadcast Rejected" (Expected!)

When you click **"Attempt Broadcast"** in the plugin:
```
Error: Transaction relay policy violation (non-standard)
```

**This is NORMAL!** The plugin warns you:
- ⚠️ "Will Likely Fail" - on the button
- ⚠️ Red warning in the dialog
- ℹ️ Instructions to submit to miner instead

### "Insufficient Funds"

If you see:
```
Wallet balance: 10,000 sats
Needed: 100,200 sats (amount + estimated fee)
```

**Solutions:**
- Reduce the sacrifice amount
- Add more funds to your wallet
- Wait for pending transactions to confirm

### "No Spendable Coins"

**Causes:**
- Empty wallet
- All coins locked/frozen
- Unconfirmed incoming transactions

**Solution:**
- Fund your wallet first
- Wait for confirmations
- Unfreeze coins if frozen

---

## Understanding Non-Standard Transactions

### Consensus vs Policy

| Rule Type | Bare Scripts | Standard Outputs |
|-----------|--------------|------------------|
| **Consensus Valid** | ✅ Yes | ✅ Yes |
| **Relay Policy** | ❌ Rejected | ✅ Accepted |
| **Can Mine** | ✅ Yes (if miner includes) | ✅ Yes |
| **Will Relay** | ❌ No | ✅ Yes |

### Key Insight

- **Consensus rules** = What miners will accept in blocks
- **Relay policy** = What nodes will forward to each other

Bare scripts violate **relay policy** but not **consensus rules**. So:
- ✅ Miners CAN include them
- ❌ Nodes WON'T relay them
- 🎯 Solution: Submit directly to miner

---

## Example Session

### Complete Walkthrough (Regtest)

```bash
# Terminal 1: Start Bitcoin Core
bitcoind -regtest -daemon
bitcoin-cli -regtest createwallet "test"
ADDR=$(bitcoin-cli -regtest getnewaddress)
bitcoin-cli -regtest generatetoaddress 101 $ADDR

# Terminal 2: Start Electrum
cd ~/src/electrum
source venv/bin/activate
./run_electrum --regtest

# In Electrum:
# 1. Create/open wallet
# 2. Tools → CheckLockTimeVerify
# 3. Miner Sacrifice tab
# 4. Generate bare script address (locktime = 100)
# 5. Enter amount: 0.001
# 6. Click "Create Bare Script Funding Transaction"
# 7. Copy the raw hex from dialog

# Terminal 1: Submit and mine
bitcoin-cli -regtest sendrawtransaction <hex>
# Output: <txid>

bitcoin-cli -regtest generatetoaddress 1 $ADDR
# Block mined!

# Verify the output
bitcoin-cli -regtest getrawtransaction <txid> true
# See your bare script in vout[0].scriptPubKey.hex
```

---

## Technical Details

### Script Bytes Breakdown

**Example bare script**: `03a0bb0db17551`

```
03          - PUSH 3 bytes
a0 bb 0d    - 900000 in little-endian (locktime)
b1          - OP_CHECKLOCKTIMEVERIFY (0xb1)
75          - OP_DROP (0x75)
51          - OP_TRUE (0x51)
```

**How it works:**
1. Before locktime 900000: CLTV check fails → can't spend
2. After locktime 900000: CLTV check passes → OP_TRUE → anyone can spend!

### UTXO Selection Algorithm

Plugin uses simple **largest-first** strategy:

```python
# Select coins
for coin in sorted(coins, key=lambda c: c.value_sats(), reverse=True):
    if coin.value_sats() >= amount + fee:
        # Found one coin that covers it
        selected = [coin]
        break

# If not, accumulate multiple coins
for coin in sorted(coins, key=lambda c: c.value_sats(), reverse=True):
    selected.append(coin)
    if sum(c.value_sats() for c in selected) >= amount + fee:
        break
```

### Fee Estimation

Currently uses **conservative estimate**:
- 200 sats for typical transaction
- ~1 sat/vbyte × 200 vbytes

**Future enhancement**: Use Electrum's fee estimator

---

## Comparison with Manual Methods

### Before (Manual)

1. ❌ Create raw transaction with Python/bitcoinjs
2. ❌ Manually construct bare script output
3. ❌ Get UTXOs from wallet via RPC
4. ❌ Calculate change manually
5. ❌ Sign with separate tool
6. ❌ Export hex
7. ✅ Submit to miner

**Steps**: 7 (6 manual, 1 final)

### After (Plugin)

1. ✅ Click button
2. ✅ Copy hex
3. ✅ Submit to miner

**Steps**: 3 (all simple!)

---

## Future Enhancements

### Potential Improvements

1. **Custom Fee Selection**
   - Let user choose fee rate
   - Use Electrum's fee estimator

2. **Multiple Outputs**
   - Support multiple bare script outputs
   - Batch sacrifices in one transaction

3. **RBF Support**
   - Allow fee bumping
   - Enable Replace-By-Fee flag

4. **CPFP Support**
   - Child-Pays-For-Parent
   - If stuck, create spending tx with higher fee

5. **Template Transactions**
   - Save common patterns
   - Quick re-use

6. **Miner Integration**
   - Direct API submission to pools
   - Automatic fee negotiation

---

## Security Considerations

### What Could Go Wrong

1. **Losing Funds** ⚠️
   - This is INTENTIONAL for sacrifice!
   - Anyone can spend after locktime
   - No recovery possible

2. **Fee Miscalculation**
   - Conservative estimate (200 sats)
   - May overpay slightly
   - Better than underpaying and getting stuck

3. **Change Output Issues**
   - Dust threshold: 546 sats
   - Change < 546 → becomes fee
   - Plugin logs this clearly

4. **UTXO Selection**
   - Simple algorithm (largest first)
   - May not be optimal for privacy
   - Works correctly for functionality

### Best Practices

✅ **Test on regtest first**  
✅ **Use small amounts**  
✅ **Verify raw hex before submitting**  
✅ **Check locktime is correct**  
✅ **Understand funds are unrecoverable**  

---

## Summary

### What We Achieved

✅ **Solved Electrum Limitation** - Can now create bare script outputs  
✅ **Automated Workflow** - Click buttons instead of manual scripting  
✅ **Proper Transaction Construction** - Handles UTXOs, change, signing  
✅ **Educational** - Shows raw hex, explains non-standard relay  
✅ **Safe** - Multiple warnings, clear instructions  

### Key Takeaways

1. **Bare scripts** = Non-standard = Won't relay normally
2. **Plugin creates** raw transaction hex automatically
3. **Submit directly** to miner for inclusion
4. **Testing** on regtest is easy and safe
5. **Production use** requires miner cooperation

---

## Questions & Troubleshooting

### Q: Why can't I broadcast the transaction?

**A**: Bare scripts are non-standard. Electrum's connected nodes will reject them. This is expected! Submit the raw hex to a miner directly.

### Q: How do I find a miner willing to include it?

**A**: 
- For testing: Use regtest (you control mining)
- For signet: Run your own miner with `-acceptnonstdtxn=1`
- For mainnet: Contact mining pools, may require fee negotiation

### Q: Is this safe to use on mainnet?

**A**: The transaction is valid and safe, BUT:
- ⚠️ Funds are UNRECOVERABLE after locktime
- ⚠️ Relay won't work (need miner)
- ⚠️ This is for SACRIFICE use cases only

### Q: Can I recover the funds before locktime?

**A**: NO! The script is `OP_TRUE` - no keys involved. Anyone can spend after locktime. This is intentional for provable sacrifice.

### Q: What if I make a mistake?

**A**: 
- Before broadcasting: Just don't submit the hex
- After broadcasting: Cannot undo
- Best practice: TEST ON REGTEST FIRST!

---

## Conclusion

The plugin now makes bare script testing straightforward. No more manual transaction crafting - just click buttons and copy hex!

**Remember**: This is for educational and testing purposes. Bare scripts are a special use case (provable sacrifice, timestamping). Always test on regtest first!

🎉 **Happy testing!**
