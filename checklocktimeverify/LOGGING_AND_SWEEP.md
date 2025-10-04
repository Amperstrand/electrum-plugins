# CLTV Plugin - Logging & Sweep Features

## 🎓 Educational Logging System

The plugin now includes comprehensive logging to help users understand how CHECKLOCKTIMEVERIFY works.

### Where to See Logs

**Electrum Console:**
- Go to: `View → Show Console`
- All plugin activity is logged with `[CLTV Plugin]` prefix
- Educational messages explain each step

### What Gets Logged

#### Address Generation:
```
[CLTV Plugin] [INIT] CLTV Plugin initialized
[CLTV Plugin] [INIT] Storage file: ~/.electrum/signet/cltv_timelock_data.json
[CLTV Plugin] [GENERATE] Starting simple timelock address generation
[CLTV Plugin] [GENERATE] Locktime type: Block height = 870000
[CLTV Plugin] [GENERATE] Public key: 037f47cefaf4be34ad440aeaaf2589cd...
[CLTV Plugin] [GENERATE] Pubkey validated: 33 bytes (compressed)
[CLTV Plugin] [SCRIPT] Building simple CLTV script step-by-step:
[CLTV Plugin] [SCRIPT] Step 1: Push locktime value 870000
[CLTV Plugin] [SCRIPT]   Encoded as: 0370460d
[CLTV Plugin] [SCRIPT] Step 2: Add OP_CHECKLOCKTIMEVERIFY (0xb1)
[CLTV Plugin] [SCRIPT] Step 3: Add OP_DROP (0x75) - removes locktime from stack
[CLTV Plugin] [SCRIPT] Step 4: Push public key (33 bytes)
[CLTV Plugin] [SCRIPT]   Push opcode: 0x21
[CLTV Plugin] [SCRIPT] Step 5: Add OP_CHECKSIG (0xac)
[CLTV Plugin] [SCRIPT] ✓ Script construction complete: 41 bytes
[CLTV Plugin] [GENERATE] Script built: 0370460db17521037f47cefaf4be34...
[CLTV Plugin] [GENERATE] Script size: 41 bytes
[CLTV Plugin] [GENERATE] Creating P2SH address from script hash
[CLTV Plugin] [GENERATE] ✓ P2SH Address generated: 2NEyY5gMq1SNcyZRRsNrBpVCdEMjxLMYkHU
[CLTV Plugin] [STORAGE] Saved timelock data to ~/.electrum/signet/cltv_timelock_data.json
[CLTV Plugin] [STORAGE] Entry: 2NEyY5gMq1SNcyZRRsNrBpVCdEMjxLMYkHU
[CLTV Plugin] [GENERATE] Timelock data saved for future sweeping
```

## 💾 Auto-Save Feature

### What Gets Saved
When you generate a timelock address, the plugin automatically saves:
- P2SH address
- Redeem script (hex)
- Locktime value
- Locktime type (block height or timestamp)
- Public key
- Script type (simple or escrow)
- Creation timestamp

### Storage Location
**File:** `~/.electrum/signet/cltv_timelock_data.json` (or mainnet/testnet equivalent)

**Format:**
```json
[
  {
    "address": "2NEyY5gMq1SNcyZRRsNrBpVCdEMjxLMYkHU",
    "script_hex": "0370460db17521037f47cefaf4be34ad440aeaaf2589cd877885e97de188c0bf22c886f80388cc4fac",
    "locktime": 870000,
    "locktime_type": "block height",
    "pubkey": "037f47cefaf4be34ad440aeaaf2589cd877885e97de188c0bf22c886f80388cc4f",
    "script_type": "simple",
    "created": "2025-10-04T12:30:00.000000"
  }
]
```

## 🔄 Sweep Functionality

### Three Tabs in Plugin Dialog

#### Tab 1: Simple Timelock
- Generate simple `<locktime> CLTV DROP <pubkey> CHECKSIG` addresses
- Auto-saves redeem script

#### Tab 2: Escrow with Timelock
- Generate escrow multisig with timelock fallback
- Auto-saves redeem script

#### Tab 3: Sweep Locked Funds (NEW!)
- View all your timelocked addresses
- Check locktime status (Locked / Unlocked ✓)
- Sweep funds back to wallet

### Sweep Tab Features

**Auto-Loaded Timelocks:**
- Table shows all addresses you've created
- Columns: Address | Locktime | Type | Status | Balance | Action
- Click "Sweep" button to claim funds

**Manual Sweep:**
- Paste any CLTV redeem script (if you have it from elsewhere)
- Plugin auto-extracts locktime from script
- Attempts sweep operation

### Educational Sweep Process

Currently, the sweep function is **educational** - it shows you:
1. How to find UTXOs at the address
2. Required transaction structure:
   - `nLockTime` must equal locktime value
   - `nSequence` must be `0xfffffffe` (not finalized)
3. How scriptSig should be constructed
4. Signing requirements

**Full implementation would require:**
- UTXO scanning from Electrum network
- Transaction building with proper fields
- Automatic signing with wallet keys
- Broadcasting to Bitcoin network

## 🎯 For Hackathon Purposes

This is a **learning tool** that demonstrates:

✅ **Script Construction:**
- Step-by-step opcode assembly
- Proper Bitcoin Script encoding
- P2SH address generation

✅ **Transaction Requirements:**
- nLockTime field usage
- nSequence field for CLTV
- scriptSig format

✅ **User Education:**
- Verbose logging explains every step
- Shows how timelocks work
- Demonstrates BIP-65 compliance

✅ **Data Management:**
- Auto-save for convenience
- JSON storage for portability
- Easy recovery of redeem scripts

## 🧪 Testing Workflow

1. **Generate Address:**
   - Open Tools → CHECKLOCKTIMEVERIFY Timelock
   - Set locktime (use low value like block 210100 for testing on signet)
   - Click "Generate Simple Timelock Address"
   - **Check console logs** to see step-by-step process

2. **Send Coins:**
   - Send signet coins to generated address
   - Plugin automatically saved redeem script

3. **Check Sweep Tab:**
   - Go to "Sweep Locked Funds" tab
   - Click "Refresh List"
   - See your address with status

4. **Learn About Spending:**
   - Click "Sweep" button
   - Read educational message about how to spend
   - Check console logs for detailed process

## 📚 Learning Objectives

After using this plugin, users will understand:
- How OP_CHECKLOCKTIMEVERIFY works at the bytecode level
- Bitcoin Script construction and P2SH
- Transaction nLockTime and nSequence fields
- Why you need the redeem script to spend P2SH outputs
- BIP-65 timelock mechanics

## 🔧 Console Commands for Debugging

In Electrum console, you can check the storage file:
```python
import json
with open(os.path.expanduser('~/.electrum/signet/cltv_timelock_data.json')) as f:
    print(json.dumps(json.load(f), indent=2))
```

## ⚠️ Important Notes

1. **Save Your Wallet Backup:**
   - You need the private key for the pubkey in the script
   - If you lose your wallet, you can't spend the locked funds

2. **Keep Redeem Script:**
   - Plugin auto-saves, but keep a backup
   - You MUST have the redeem script to spend P2SH outputs

3. **Test on Signet:**
   - Use worthless signet coins for testing
   - Don't test on mainnet until fully verified

4. **Locktime Must Pass:**
   - Funds are truly locked until locktime
   - No backdoor or emergency recovery

Happy learning! 🎓
