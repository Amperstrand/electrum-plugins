# Bare Script Transaction - Lessons Learned

## What We Discovered

### ✅ What Works

1. **Creating bare script transactions in Electrum**: ✅ WORKS
   - `PartialTxOutput(scriptpubkey=<bare_script_bytes>, value=amount)` works perfectly
   - Transaction builds correctly
   - Can be signed successfully
   - PSBT can be completed with witness_utxo data

2. **The automation script works end-to-end**: ✅ COMPLETE
   - Selects UTXOs automatically
   - Builds transaction with bare script
   - Adds proper witness_utxo to PSBT
   - Signs transaction successfully
   - Generates valid raw transaction hex

### ❌ What Doesn't Work

**Networks reject bare script outputs** with error `-26: scriptpubkey`

This is a **network policy rule**, not a consensus rule:
- Bitcoin nodes reject non-standard transactions by default
- Bare scripts are considered non-standard
- This protects against spam and unusual outputs
- Applies to mainnet, testnet, signet, and most nodes

## The Error

```bash
$ bitcoin-cli --signet sendrawtransaction <hex>
error code: -26
error message: scriptpubkey
```

This means: "Your scriptpubkey (output script) is non-standard and I won't relay it"

## Why This Happens

Bitcoin has two types of validation:

1. **Consensus Rules** (hard rules)
   - Transaction must be structurally valid
   - Signatures must be correct
   - Inputs must exist
   - **Our transaction passes all of these** ✅

2. **Policy Rules** (soft rules, per-node)
   - What transactions to relay/accept to mempool
   - Bare scripts fail these rules
   - Nodes reject with `-26` error
   - **Our transaction fails this** ❌

## Solutions

### Solution 1: Use P2SH (Recommended for Production)

Wrap the bare script in P2SH:

```python
from electrum import bitcoin
from electrum.bitcoin import opcodes

# Your timelock script
locktime = 870002
script = bitcoin.construct_script([
    locktime,
    opcodes.OP_CHECKLOCKTIMEVERIFY,
    opcodes.OP_DROP,
    opcodes.OP_TRUE
])

# Wrap in P2SH
script_hash = bitcoin.hash_160(script)
p2sh_scriptpubkey = bitcoin.construct_script([
    opcodes.OP_HASH160,
    script_hash,
    opcodes.OP_EQUAL
])

# This creates a standard P2SH address
address = bitcoin.hash160_to_p2sh(script_hash)
# Example: 2MzQwSSnBHWHqSAqtTVQ6v47XtaisrJa1Vc (testnet)
```

**Benefits**:
- ✅ Accepted by all nodes (standard transaction)
- ✅ Same functionality as bare script
- ✅ Can be broadcast successfully
- ✅ Spending still requires revealing the script

**How to spend P2SH**:
```python
# When spending, provide the script and fulfill its conditions
# The network verifies: HASH160(script) == script_hash
```

### Solution 2: Use SegWit P2WSH (Also Standard)

Even better - use native SegWit:

```python
from electrum import bitcoin
from electrum.bitcoin import opcodes

# Your script
script = bitcoin.construct_script([870002, OP_CLTV, OP_DROP, OP_TRUE])

# Create P2WSH (witness script hash)
script_hash = bitcoin.sha256(script)
p2wsh_scriptpubkey = bitcoin.construct_script([
    opcodes.OP_0,
    script_hash
])

# This creates a bc1q... address (bech32)
```

**Benefits**:
- ✅ Standard transaction (accepted)
- ✅ Lower fees (SegWit discount)
- ✅ Native SegWit address
- ✅ Same timelock functionality

### Solution 3: Regtest with Non-Standard TXs (Testing Only)

For development/testing:

```bash
# Start Bitcoin Core in regtest
bitcoind -regtest -daemon -acceptnonstdtxn=1

# Mine some blocks
bitcoin-cli -regtest generatetoaddress 101 <address>

# Now you can broadcast bare scripts
bitcoin-cli -regtest sendrawtransaction <bare_script_tx_hex>
```

This works because you control the node and enabled `-acceptnonstdtxn=1`.

## Recommendation for Your Plugin

**Change the plugin to use P2SH or P2WSH instead of bare scripts**:

```python
# Current (bare script - doesn't work on network)
output = PartialTxOutput(
    scriptpubkey=bare_script_bytes,  # ❌ Rejected
    value=amount
)

# Recommended (P2SH - works everywhere)
script_hash = bitcoin.hash_160(bare_script_bytes)
p2sh_script = bitcoin.construct_script([
    opcodes.OP_HASH160,
    script_hash,
    opcodes.OP_EQUAL
])
output = PartialTxOutput(
    scriptpubkey=p2sh_script,  # ✅ Accepted
    value=amount
)
```

## What We Learned

1. **Bare script transactions are technically valid** ✅
   - Can be created in Electrum
   - Can be signed
   - Are consensus-valid

2. **But networks won't relay them** ❌
   - Policy rules reject non-standard outputs
   - Error `-26: scriptpubkey`
   - This is intentional spam protection

3. **Use P2SH or P2WSH instead** ✅
   - Standard and accepted everywhere
   - Same functionality
   - Better privacy (script hidden until spent)
   - Lower fees with SegWit (P2WSH)

## Files Created During Testing

1. ✅ `create_bare_tx_auto.sh` - Automated PSBT builder
2. ✅ `add_witness_utxo.py` - Adds witness_utxo to PSBT
3. ✅ `BARE_TX_AUTOMATION_SUCCESS.md` - Documentation
4. ✅ Signed transaction hex in `/tmp/bare_script_tx_SIGNED.hex`
5. ✅ This lessons learned document

## Conclusion

**The automation works perfectly** - we can create, sign, and export bare script transactions using Electrum. However, for real-world use, the plugin should use **P2SH or P2WSH wrapped scripts** instead of bare scripts to ensure transactions are accepted by the network.

The bare script approach taught us how it works, but P2SH/P2WSH is the production solution. 🎯
