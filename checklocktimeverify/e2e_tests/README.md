# End-to-End Test Scripts

## Overview

This directory contains **educational end-to-end test scripts** that demonstrate how to create and sweep CLTV (CheckLockTimeVerify) transactions on Bitcoin Testnet4.

Each test consists of two scripts:
1. **FUND script** - Creates and funds a CLTV address
2. **SWEEP script** - Spends the funds after locktime expires

## Purpose

🎓 **Educational**: These scripts are heavily commented and verbose to teach Bitcoin script construction

📝 **Documentation**: All steps are logged to files in `logs/` directory

🔬 **Testing**: Accelerate development by testing with real transactions

💡 **Reference**: See actual transaction hex and signing processes

## Test Scripts

### Test 01: Simple HODL (P2SH)

**01_simple_hodl_p2sh_FUND.py** - Creates a simple time-locked P2SH address
- Script: `<locktime> OP_CLTV OP_DROP <pubkey> OP_CHECKSIG`
- Address Type: P2SH (Pay-to-Script-Hash)
- Network: Testnet4
- Locktime: Block height 1 (immediately spendable for testing)

**01_simple_hodl_p2sh_SWEEP.py** - Sweeps funds from the P2SH address
- Constructs spending transaction
- Signs with legacy signing (SHA256d)
- Builds scriptSig: `<signature> <redeem_script>`
- Sets nSequence and nLockTime correctly

### Test 02: Simple HODL (Taproot) - Coming Soon

**02_simple_hodl_taproot_FUND.py** - Creates a taproot time-locked address
- Script: Same CLTV pattern but with x-only pubkeys
- Address Type: P2TR (Taproot)
- Signing: Schnorr signatures
- Witness: `<signature> <tapscript> <control_block>`

**02_simple_hodl_taproot_SWEEP.py** - Sweeps from taproot

### Test 03: Two-Factor Wallet (P2SH) - Coming Soon

### Test 04: Escrow (P2SH) - Coming Soon

## Usage

### Running a Test

1. **Generate the CLTV address:**
   ```bash
   cd ~/src/electrum-plugins/checklocktimeverify/e2e_tests
   python3 01_simple_hodl_p2sh_FUND.py
   ```

2. **Fund the address:**
   - Option A: Use Electrum GUI to send testnet coins to the generated address
   - Option B: Use testnet4 faucet and update script variables

3. **Update metadata:**
   - After funding, edit `logs/01_simple_hodl_p2sh_metadata.json`
   - Add the `funded_txid` and `funded_vout`

4. **Sweep the funds:**
   ```bash
   python3 01_simple_hodl_p2sh_SWEEP.py
   ```

5. **Check the logs:**
   ```bash
   ls -la logs/
   cat logs/01_simple_hodl_p2sh_FUND_*.log
   cat logs/01_simple_hodl_p2sh_SWEEP_*.log
   ```

## Log Files

All scripts save detailed logs to the `logs/` directory:

- **`*_FUND_*.log`** - Funding script execution logs
- **`*_SWEEP_*.log`** - Sweep script execution logs
- **`*_metadata.json`** - Shared data between FUND and SWEEP scripts
- **`*_signed_*.hex`** - Signed transaction hex (ready to broadcast)

## What You'll Learn

### From FUND Scripts:
- ✅ Bitcoin script opcodes and structure
- ✅ How to build CLTV scripts manually
- ✅ P2SH address generation (script hashing)
- ✅ Taproot address generation (tweak calculation)
- ✅ Metadata needed for spending

### From SWEEP Scripts:
- ✅ Transaction structure (version, inputs, outputs, locktime)
- ✅ Signature preimage construction
- ✅ ECDSA vs Schnorr signing
- ✅ ScriptSig vs Witness stack
- ✅ nSequence and nLockTime interaction
- ✅ Fee calculation

## Educational Features

### Verbose Logging
Every step is logged with:
- 🔧 Step numbers and descriptions
- 📊 Hex dumps of data structures
- 📦 Byte-by-byte transaction breakdown
- ✅ Success/failure indicators
- 💡 Educational notes

### Example Log Output:
```
================================================================================
STEP 2: BUILD SIMPLE CLTV SCRIPT
================================================================================

Script pattern: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG

🔧 Building script:
  [1] Push 2 byte(s): 5704
      Value: 1111 (block height)
  [2] OP_CHECKLOCKTIMEVERIFY (0xb1)
      Validates: tx.nLockTime >= 1111
  [3] OP_DROP (0x75)
      Removes locktime from stack
  [4] Push 33 bytes: 03895f2e...
      Public key (compressed)
  [5] OP_CHECKSIG (0xac)
      Validates signature against pubkey

✅ Complete Script (redeem script):
  Hex:    025704b17521...ac
  Length: 37 bytes
```

### Hardcoded Test Keys
Scripts use deterministic test keys for reproducibility:
```python
TEST_PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"
```

⚠️ **Never use these keys with real funds!**

## Testing Workflow

```
┌─────────────────┐
│  FUND Script    │  Generates address, builds script, outputs metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Send Testnet   │  Manually fund via Electrum or faucet
│  Coins          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Update         │  Add funded_txid and funded_vout to metadata.json
│  Metadata       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SWEEP Script   │  Loads metadata, builds & signs transaction, broadcasts
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Verify on      │  Check mempool.space/testnet4 for confirmation
│  Block Explorer │
└─────────────────┘
```

## Requirements

- Python 3.8+
- Electrum installed at `/Applications/Electrum.app/Contents/MacOS`
- Plugin code at `~/src/electrum-plugins`
- Testnet4 coins (from faucet or existing wallet)

## Testnet4 Faucets

Get free testnet coins:
- https://mempool.space/testnet4/faucet
- https://testnet-faucet.com/btc-testnet4/

## File Structure

```
e2e_tests/
├── README.md                           # This file
├── 01_simple_hodl_p2sh_FUND.py        # Test 01: Funding script
├── 01_simple_hodl_p2sh_SWEEP.py       # Test 01: Sweep script
├── 02_simple_hodl_taproot_FUND.py     # Test 02: Taproot funding (coming soon)
├── 02_simple_hodl_taproot_SWEEP.py    # Test 02: Taproot sweep (coming soon)
└── logs/
    ├── 01_simple_hodl_p2sh_FUND_20251018_*.log
    ├── 01_simple_hodl_p2sh_SWEEP_20251018_*.log
    ├── 01_simple_hodl_p2sh_metadata.json
    └── 01_simple_hodl_p2sh_signed_*.hex
```

## Tips

### Quick Test Loop
```bash
# 1. Fund
python3 01_simple_hodl_p2sh_FUND.py

# 2. Get testnet coins
open "https://mempool.space/testnet4/faucet"

# 3. Update metadata with TXID
vim logs/01_simple_hodl_p2sh_metadata.json

# 4. Sweep
python3 01_simple_hodl_p2sh_SWEEP.py

# 5. View logs
tail -f logs/01_simple_hodl_p2sh_SWEEP_*.log
```

### Testing Different Locktimes

Edit the `LOCKTIME` variable in FUND scripts:
```python
LOCKTIME = 1           # Block height 1 (immediate)
LOCKTIME = 1000000     # Block height 1M (far future)
LOCKTIME = 1730419200  # Unix timestamp (Oct 31, 2024)
```

### Broadcasting Options

1. **Electrum Console:**
   ```python
   broadcast(transaction_hex)
   ```

2. **Mempool.space:**
   ```
   https://mempool.space/testnet4/tx/push
   ```

3. **Bitcoin CLI:**
   ```bash
   bitcoin-cli -testnet4 sendrawtransaction <hex>
   ```

## Troubleshooting

### "Metadata file not found"
Run the FUND script first before the SWEEP script.

### "No funded TXID in metadata"
After funding, update `logs/*_metadata.json` with the TXID and VOUT.

### "Non-final transaction"
Check that nLockTime is set correctly and current block height >= locktime.

### "Script failed verification"
Check that:
- Signature is valid
- ScriptSig includes both signature and redeem script
- Redeem script hash matches P2SH address

## Contributing

Want to add more test cases? Follow this pattern:

1. Create `XX_name_type_FUND.py` and `XX_name_type_SWEEP.py`
2. Use verbose logging with emojis
3. Save metadata to `logs/XX_name_type_metadata.json`
4. Document in this README

## License

Educational use - Part of the CheckLockTimeVerify Electrum Plugin

## Questions?

Check the main plugin documentation:
- `/checklocktimeverify/LESSONS_LEARNED.md`
- `/checklocktimeverify/README.md`
