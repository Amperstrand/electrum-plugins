# CLTV Plugin - Hackathon Quick Start 🚀

## What This Plugin Does

Creates Bitcoin addresses with **time locks** using OP_CHECKLOCKTIMEVERIFY (BIP-65).
Funds sent to these addresses **cannot be spent until a specific block height or time**.

## 30-Second Demo

1. **Start Electrum:** `./run_electrum --signet`
2. **Open Plugin:** Tools → CHECKLOCKTIMEVERIFY Timelock...
3. **Open Console:** View → Show Console (to see educational logs)
4. **Generate Address:**
   - Set locktime: 210100 (near current signet block)
   - Click "Generate Simple Timelock Address"
   - **Watch console** - see step-by-step script construction!
5. **Check Results:** Scroll through technical details, miniscript, script breakdown
6. **View Sweep Tab:** See saved addresses and how to claim funds

## Key Features for Demo

### 🎓 Educational Logging
Every action is logged to console with detailed explanations:
```
[CLTV Plugin] [SCRIPT] Step 1: Push locktime value 870000
[CLTV Plugin] [SCRIPT] Step 2: Add OP_CHECKLOCKTIMEVERIFY (0xb1)
[CLTV Plugin] [SCRIPT] Step 3: Add OP_DROP (0x75)
```

### 📊 Technical Details Display
Generated address shows:
- ✅ Miniscript policy
- ✅ Descriptor notation  
- ✅ Annotated hex breakdown
- ✅ Script size and hash
- ✅ Spending instructions

### 💾 Auto-Save
Plugin saves all redeem scripts to:
`~/.electrum/signet/cltv_timelock_data.json`

### 🔄 Sweep Tab
- Lists all your timelocked addresses
- Shows status (Locked / Unlocked ✓)
- Educational sweep messages

## Script Types

### Simple Timelock
```
<locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG
```
Single key, spendable after locktime.

### Escrow with Fallback
```
IF
  <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP
  <agent> OP_CHECKSIGVERIFY
  1
ELSE
  2
ENDIF
<party1> <party2> 2 OP_CHECKMULTISIG
```
- Normal: 2-of-2 multisig (both parties)
- Fallback: After timeout, agent + 1 party

## Hackathon Talking Points

### What You Built
"A Bitcoin plugin that demonstrates BIP-65 OP_CHECKLOCKTIMEVERIFY for creating time-locked addresses with educational logging."

### Technical Highlights
- ✅ Raw Bitcoin Script construction
- ✅ P2SH address generation
- ✅ Minimal integer encoding (little-endian)
- ✅ Miniscript policy notation
- ✅ Educational verbose logging
- ✅ JSON persistence for redeem scripts

### Learning Tool Aspects
- 📚 Shows step-by-step script building
- 📚 Explains transaction requirements (nLockTime, nSequence)
- 📚 Demonstrates scriptSig construction
- 📚 Real BIP-65 compliance

### Why It's Cool
- 🔐 **Time Locks:** Create trust-minimized escrows
- 🎓 **Educational:** Users learn Bitcoin internals
- 🔧 **Practical:** Real scripts on real network (signet)
- 📖 **Transparent:** All steps logged and explained

## Testing Live (If You Have Time)

### Quick Test (5 min)
1. Generate address with locktime = current_block + 5
2. Get signet coins from faucet: https://signetfaucet.com/
3. Send 0.001 tBTC to generated address
4. Check explorer: https://mempool.space/signet/address/YOUR_ADDRESS
5. Show in Sweep tab when locktime passes

### Just Demo (No Sending)
1. Generate address with future locktime
2. Show console logs explaining construction
3. Show technical details (script breakdown)
4. Go to Sweep tab, show educational messages
5. Explain how spending would work

## Console Logs to Highlight

```
[CLTV Plugin] [SCRIPT] Building simple CLTV script step-by-step:
[CLTV Plugin] [SCRIPT] Step 1: Push locktime value 870000
[CLTV Plugin] [SCRIPT]   Encoded as: 0370460d
[CLTV Plugin] [SCRIPT] Step 2: Add OP_CHECKLOCKTIMEVERIFY (0xb1)
[CLTV Plugin] [SCRIPT] Step 3: Add OP_DROP (0x75) - removes locktime from stack
[CLTV Plugin] [SCRIPT] Step 4: Push public key (33 bytes)
[CLTV Plugin] [SCRIPT] Step 5: Add OP_CHECKSIG (0xac)
[CLTV Plugin] [SCRIPT] ✓ Script construction complete: 41 bytes
```

## Questions You Might Get

**Q: What's CHECKLOCKTIMEVERIFY?**
A: Bitcoin opcode (0xb1) from BIP-65 that enforces transaction nLockTime, enabling time-locked contracts.

**Q: Can funds be recovered before locktime?**
A: No! That's the point - trustless time locks. No one can spend until locktime passes.

**Q: Does it actually work?**
A: Yes! The script is BIP-65 compliant. You can verify: send signet coins and try spending before/after locktime.

**Q: What about OP_CHECKSEQUENCEVERIFY?**
A: That's BIP-112 (relative timelocks). This is BIP-65 (absolute timelocks). Different use cases!

**Q: Real use cases?**
A: Escrows, vesting schedules, inheritance plans, Lightning Network HTLCs, atomic swaps.

## File Structure to Show

```
checklocktimeverify/
├── qt.py                           # Main plugin (1200+ lines)
├── manifest.json                   # Plugin metadata
├── README.md                       # Documentation
├── TESTING.md                      # Testing guide
├── ARCHITECTURE.md                 # Technical architecture
├── LOGGING_AND_SWEEP.md           # New logging features
├── HACKATHON_QUICK_START.md       # This file
└── ~/.electrum/signet/
    └── cltv_timelock_data.json    # Auto-saved redeem scripts
```

## Backup Slides (If Demo Fails)

1. Show console logs (pre-captured)
2. Show script breakdown in results
3. Show JSON storage file
4. Walk through code in qt.py
5. Show BIP-65 spec comparison

## Extensions You Could Mention

"If I had more time, I'd add:"
- ✨ Full sweep implementation (UTXO scanning + tx building)
- ✨ Block height lookup from network
- ✨ QR code generation for addresses
- ✨ OP_CSV (relative timelocks) support
- ✨ Multi-sig wizard
- ✨ Export to PSBT for hardware wallets

## The Wow Factor

**Before clicking Generate:**
"Watch the console - it's going to show you exactly how Bitcoin Script works at the opcode level."

**Click Generate**

"See? Step 1: Push the locktime as minimal-encoded bytes. Step 2: OP_CHECKLOCKTIMEVERIFY. This is the actual bytecode being constructed!"

**Scroll through results:**
"And here's the annotated hex breakdown - you can see every opcode. This is what gets hashed to create the P2SH address."

**Go to Sweep tab:**
"And when you want to spend it, the plugin explains the exact transaction structure you need."

Good luck! 🎉
