# CHECKLOCKTIMEVERIFY Plugin for Electrum

A demonstration plugin implementing BIP-65 CHECKLOCKTIMEVERIFY functionality for creating time-locked Bitcoin addresses.

## Overview

This plugin allows you to create Bitcoin addresses that can only be spent after a specific block height or timestamp is reached. It implements two script patterns from [BIP-65](https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki):

1. **Simple Timelock**: Single key with timelock
2. **Escrow with Timelock Fallback**: 2-of-2 multisig with escrow fallback after timeout

## Features

- ✅ Create timelocked P2SH addresses
- ✅ Support both block height and timestamp locks
- ✅ Two script types: simple and escrow
- ✅ Visual script builder with validation
- ✅ Generate redeem scripts
- ✅ Integration with Electrum wallet keys
- ✅ Copy address and scripts to clipboard

## Installation

### Development Mode (Recommended for Testing)

1. Clone or copy this plugin to your development directory:
```bash
cd /path/to/electrum-plugins
```

2. Create a symbolic link in your Electrum plugins directory:
```bash
ln -s /path/to/electrum-plugins/checklocktimeverify ~/electrum/electrum/plugins/checklocktimeverify
```

3. Run Electrum:
```bash
cd ~/electrum
./run_electrum
```

4. Enable the plugin:
   - Go to **Tools** → **Plugins**
   - Find **CHECKLOCKTIMEVERIFY Timelock**
   - Check the box to enable it

### Production Mode (ZIP Distribution)

1. Build the plugin zip:
```bash
cd /path/to/electrum
./contrib/make_plugin /path/to/electrum-plugins/checklocktimeverify
```

2. Install the generated zip:
```bash
cp checklocktimeverify-0.0.1.zip ~/.electrum/plugins/
```

3. Restart Electrum and enable the plugin via **Tools** → **Plugins**

## Usage

### Accessing the Plugin

Once enabled, access the plugin via:
**Tools** → **CHECKLOCKTIMEVERIFY Timelock...**

### Tab 1: Simple Timelock

Creates a basic timelocked address with a single key:

**Script:** `<locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG`

**Use Case:** Lock funds until a specific time, only you can spend them.

**Steps:**
1. Choose locktime type (Block Height or Timestamp)
2. Enter the locktime value
3. Provide a public key (or get one from your wallet)
4. Click "Generate Simple Timelock Address"
5. Save the P2SH address and redeem script

**Example:**
- Lock until block 870000 (approximately early 2026)
- Only the owner of the public key can spend after that block

### Tab 2: Escrow with Timelock Fallback

Creates an escrow address with timelock fallback (from BIP-65 example):

**Script:**
```
IF
    <locktime> CHECKLOCKTIMEVERIFY DROP
    <escrow_pubkey> CHECKSIGVERIFY
    1
ELSE
    2
ENDIF
<party1_pubkey> <party2_pubkey> 2 CHECKMULTISIG
```

**Use Case:** Business partners with escrow agent backup.

**Spending Conditions:**
- **Normal:** Both Party 1 AND Party 2 must sign (2-of-2 multisig)
- **After Timeout:** Escrow agent + either party can spend

**Steps:**
1. Choose locktime type and value
2. Enter public keys for Party 1, Party 2, and Escrow Agent
3. Click "Generate Escrow Address with Timelock"
4. All parties save the P2SH address and redeem script

**Example (BIP-65 Alice & Bob scenario):**
- Alice and Bob operate a business together
- Funds normally require both signatures
- After 3 months, their lawyer (Lenny) + either Alice OR Bob can recover funds

## Important Security Notes

### ⚠️ CRITICAL: Save Your Redeem Script

The redeem script is **REQUIRED** to spend the funds. Without it, your funds are **PERMANENTLY LOCKED**. Store it securely!

### Requirements for Spending Timelocked Funds

1. **Redeem Script**: Must have the exact script used to create the address
2. **Private Key(s)**: Must have the private keys for the public key(s) in the script
3. **Transaction nLockTime**: Must be set >= the locktime value
4. **Transaction nSequence**: Must be < 0xffffffff (not 0xffffffff)

### Before the Locktime

Funds sent to a timelocked address **CANNOT** be spent by anyone before the locktime is reached. This is enforced by Bitcoin consensus rules.

### Locktime Types

- **Block Height** (< 500,000,000): Unlocks at specific block
- **Timestamp** (≥ 500,000,000): Unlocks at specific Unix time

## Technical Details

### Script Encoding

The plugin properly encodes Bitcoin scripts following these rules:
- Integers use minimal encoding
- Locktime values use up to 5 bytes (2^32-1 max)
- Public keys are pushed with length prefix
- Opcodes follow Bitcoin Core implementation

### OP_CHECKLOCKTIMEVERIFY (OP_NOP2)

- Opcode: `0xb1` (177)
- Introduced: BIP-65 (December 2015)
- Soft fork: Activated at block 388,381

### Validation Rules

CHECKLOCKTIMEVERIFY fails if:
1. Stack is empty
2. Top stack item is negative
3. Locktime type mismatch (block vs time)
4. Top stack item > transaction nLockTime
5. Input nSequence is 0xffffffff (finalized)

## Examples

### Example 1: Save for College (18 years)

Lock 1 BTC until your child turns 18 (year 2043):

```
1. Choose "Simple Timelock"
2. Select "Date & Time"
3. Set date: 2043-01-01 00:00:00
4. Get key from wallet
5. Generate address
6. Send 1 BTC to the address
7. Save redeem script in safe place
```

### Example 2: Business Escrow (90 days)

Alice & Bob's business with lawyer Lenny as backup:

```
1. Choose "Escrow with Timelock Fallback"
2. Select "Date & Time"
3. Set date: 90 days from now
4. Party 1: Alice's pubkey
5. Party 2: Bob's pubkey
6. Escrow Agent: Lenny's pubkey
7. Generate address
8. All parties save the redeem script
```

**Normal operation:** Alice + Bob both sign (2-of-2)  
**Emergency (after 90 days):** Lenny + Alice OR Lenny + Bob can recover

### Example 3: Incentive Lock (Block Height)

Lock mining rewards until specific block:

```
1. Choose "Simple Timelock"
2. Select "Block Height"
3. Enter: 900000 (future block)
4. Use miner's pubkey
5. Generate address
```

## Spending Timelocked Funds

Spending timelocked funds requires creating a transaction with:

1. **Input scriptSig**: Signature(s) + redeem script
2. **Transaction nLockTime**: Set to locktime value or later
3. **Input nSequence**: Must be < 0xffffffff (e.g., 0xfffffffe)

**Note:** Electrum's standard transaction builder may need modification to support spending CLTV outputs. This plugin focuses on *creating* timelocked addresses.

## Troubleshooting

### Plugin Not Showing in Menu

1. Verify plugin is enabled: **Tools** → **Plugins**
2. Check console for errors: **Tools** → **Console**
3. Restart Electrum

### Invalid Public Key Error

- Ensure pubkey is in hex format
- Compressed: 33 bytes (66 hex chars), starts with 02 or 03
- Uncompressed: 65 bytes (130 hex chars), starts with 04

### "Get Key from Wallet" Not Working

- Ensure wallet is loaded and has addresses
- Try creating a new receiving address first
- Check that wallet is not watch-only

## Development

### File Structure

```
checklocktimeverify/
├── __init__.py          # Empty (Python package marker)
├── manifest.json        # Plugin metadata
├── qt.py               # Main plugin code
└── README.md           # This file
```

### Key Classes

- `Plugin`: Main plugin class, adds menu items
- `TimelockDialog`: Qt dialog for creating timelocked addresses
- Script builders: `build_simple_cltv_script()`, `build_escrow_cltv_script()`

### Testing

1. Enable plugin in Electrum
2. Open **Tools** → **CHECKLOCKTIMEVERIFY Timelock...**
3. Generate a test address with future block height
4. Verify script hex format
5. Test address generation is deterministic

## References

- **BIP-65**: https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki
- **Bitcoin Script**: https://en.bitcoin.it/wiki/Script
- **Electrum Plugin Guide**: See ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md

## License

MIT License

## Author

Electrum Plugin Demo - Created as an educational example for hackathon participants

## Disclaimer

⚠️ **FOR EDUCATIONAL PURPOSES ONLY**

This is a demonstration plugin. Before using with real funds:
- Thoroughly review and test the code
- Understand Bitcoin script and CHECKLOCKTIMEVERIFY mechanics
- Test on testnet first
- Have the ability to craft custom transactions to spend CLTV outputs
- Keep secure backups of all redeem scripts and private keys

The authors are not responsible for any loss of funds due to misuse of this plugin.
