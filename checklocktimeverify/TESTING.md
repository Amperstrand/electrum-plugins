# Quick Start Guide: Testing the CHECKLOCKTIMEVERIFY Plugin

## Prerequisites

- Electrum installed and running
- Basic understanding of Bitcoin scripts
- This plugin directory

## Installation (5 minutes)

### Step 1: Create Symlink

```bash
# Navigate to Electrum plugins directory
cd ~/electrum/electrum/plugins/

# Create symlink (adjust path as needed)
ln -s /Users/macbook/src/electrum-plugins/checklocktimeverify checklocktimeverify

# Verify symlink
ls -la | grep checklocktimeverify
```

### Step 2: Start Electrum

```bash
cd ~/electrum
./run_electrum
```

### Step 3: Enable Plugin

1. Open Electrum
2. Go to **Tools** → **Plugins**
3. Find **CHECKLOCKTIMEVERIFY Timelock**
4. Check the box to enable
5. Look for **Tools** → **CHECKLOCKTIMEVERIFY Timelock...** menu item

## Quick Test (2 minutes)

### Test 1: Generate Simple Timelock Address

1. Click **Tools** → **CHECKLOCKTIMEVERIFY Timelock...**
2. Stay on "Simple Timelock" tab
3. Select **Block Height**
4. Enter: `900000` (future block)
5. Click **Get Key from Wallet** button
6. Click **Generate Simple Timelock Address**
7. ✅ You should see a P2SH address starting with `3` or `bc1q`
8. Click **Copy Address** to test clipboard functionality

**Expected Output:**
```
P2SH Address (send funds here):
3xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Locktime: 900000
Type: block height

Redeem Script (hex):
03a0bb0db175<pubkey>ac
```

### Test 2: Generate with Timestamp

1. Switch to timestamp mode: Select **Date & Time**
2. Pick a date 30 days in the future
3. Click **Get Key from Wallet**
4. Click **Generate Simple Timelock Address**
5. ✅ Verify timestamp is > 500000000

### Test 3: Generate Escrow Address

1. Switch to **Escrow with Timelock Fallback** tab
2. Set block height: `900000`
3. For testing, you can use the same pubkey for all three parties:
   - Click **Get Key from Wallet (Party 1)**
   - Copy that key to Party 2 and Escrow Agent fields
4. Click **Generate Escrow Address with Timelock**
5. ✅ Verify more complex script is generated

**Expected Output:**
```
Script Type: Escrow with Timelock Fallback

Spending Conditions:
Normal spending: Requires both Party 1 and Party 2 (2-of-2 multisig)
After 900000: Escrow agent + either party can spend
```

## Verify Script Construction

### Simple Timelock Script Breakdown

For locktime `900000` (0x0db8a0 in hex, 0xa0b80d in little-endian):

```
Script Hex: 03a0bb0db175<33-byte-pubkey>ac

Breakdown:
03          - PUSH 3 bytes
a0bb0d      - Locktime value (900000 in little-endian)
b1          - OP_CHECKLOCKTIMEVERIFY (0xb1)
75          - OP_DROP
21          - PUSH 33 bytes (compressed pubkey)
<pubkey>    - 33 bytes of public key
ac          - OP_CHECKSIG
```

### Verify in Console

Open Electrum console (**Tools** → **Console**):

```python
# Get the generated script hex
script_hex = "03a0bb0db175<your_pubkey>ac"

# Decode it
from electrum.bitcoin import hash_160
script_bytes = bytes.fromhex(script_hex)
script_hash = hash_160(script_bytes)
print(f"Script hash: {script_hash.hex()}")

# Verify address
from electrum.bitcoin import hash160_to_p2sh
address = hash160_to_p2sh(script_hash)
print(f"P2SH Address: {address}")
```

## Common Issues & Solutions

### Issue 1: Plugin Not Appearing

**Symptom:** No menu item under Tools

**Solution:**
```bash
# Check if symlink is correct
ls -la ~/electrum/electrum/plugins/ | grep checklocktimeverify

# Check for import errors
cd ~/electrum
./run_electrum 2>&1 | grep -i checklocktimeverify
```

### Issue 2: "Get Key from Wallet" Error

**Symptom:** Button doesn't populate pubkey

**Solution:**
- Ensure wallet has addresses: **Receive** tab → **New Address**
- Try manually pasting a pubkey in hex format
- Check wallet type (watch-only wallets may not work)

### Issue 3: Invalid Public Key

**Symptom:** Error when generating address

**Solution:**
```python
# Test pubkey format in console
pubkey = "02abc123..."  # Your pubkey
assert len(bytes.fromhex(pubkey)) in (33, 65), "Invalid length"
print("✅ Pubkey is valid")
```

### Issue 4: Script Generation Fails

**Symptom:** Exception when clicking generate

**Solution:**
- Check Electrum console for full traceback
- Verify all inputs are filled
- Ensure locktime is positive integer
- Check that you're using correct Electrum version (4.0+)

## Advanced Testing

### Test Script Decoding

```python
from electrum.transaction import opcodes

# Your generated script
script_hex = "03a0bb0db175<pubkey>ac"
script_bytes = bytes.fromhex(script_hex)

# Manual decode
i = 0
print("Script opcodes:")
while i < len(script_bytes):
    opcode = script_bytes[i]
    if opcode <= opcodes.OP_PUSHDATA4:
        # It's a data push
        if opcode < opcodes.OP_PUSHDATA1:
            length = opcode
            i += 1
            data = script_bytes[i:i+length]
            print(f"PUSH {length} bytes: {data.hex()}")
            i += length
        else:
            # Handle PUSHDATA1/2/4
            i += 1
    else:
        # It's an opcode
        opcode_name = [k for k, v in vars(opcodes).items() if v == opcode]
        print(f"OP: {opcode_name[0] if opcode_name else hex(opcode)}")
        i += 1
```

### Test Different Locktime Values

```python
# Block heights
test_cases = [
    500000,    # Past block (should work but immediately spendable)
    850000,    # Current-ish block
    900000,    # Future block
    1000000,   # Far future block
]

# Timestamps
import time
test_timestamps = [
    int(time.time()) + 86400,      # 1 day
    int(time.time()) + 2592000,    # 30 days
    int(time.time()) + 31536000,   # 1 year
]
```

## Next Steps

1. ✅ Plugin installed and working
2. ✅ Can generate simple timelock addresses
3. ✅ Can generate escrow addresses
4. ✅ Understand script structure

### To Actually Use (TESTNET FIRST!)

1. **Switch to Testnet:**
   ```bash
   ./run_electrum --testnet
   ```

2. **Generate testnet address with plugin**

3. **Send testnet coins** to the address

4. **Wait for locktime** (use short locktime for testing!)

5. **Craft spending transaction:**
   - Set nLockTime to locktime value
   - Set nSequence to 0xfffffffe
   - Include redeem script in scriptSig
   - Sign with corresponding private key

**Note:** Spending CLTV outputs requires custom transaction construction, which is beyond this plugin's current scope.

## Debugging

### Enable Debug Output

In `qt.py`, add print statements:

```python
def generate_simple_timelock(self):
    print(f"[CLTV] Generating simple timelock")
    print(f"[CLTV] Locktime: {locktime}")
    print(f"[CLTV] Pubkey: {pubkey_hex}")
    print(f"[CLTV] Script: {script}")
    # ... rest of function
```

Run Electrum from terminal to see output:
```bash
cd ~/electrum
./run_electrum 2>&1 | grep CLTV
```

## Success Criteria

✅ Plugin loads without errors  
✅ Menu item appears in Tools  
✅ Dialog opens and displays tabs  
✅ Can generate simple timelock address  
✅ Can generate escrow address  
✅ Can copy address to clipboard  
✅ Can copy redeem script  
✅ Script hex is valid Bitcoin script  
✅ P2SH address is valid format  

## Resources

- **BIP-65 Spec:** https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki
- **Bitcoin Script Wiki:** https://en.bitcoin.it/wiki/Script
- **Electrum Docs:** https://electrum.readthedocs.io/
- **Full Plugin Guide:** See `ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md`

## Getting Help

If you encounter issues:

1. Check the console output
2. Verify all prerequisites are met
3. Review the script hex output
4. Test on testnet first
5. Consult BIP-65 specification

Happy testing! 🚀
