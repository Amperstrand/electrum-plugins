# Troubleshooting Guide

## 🔴 Common Issues and Solutions

---

## Issue: Address Not Saved to Wallet

### Symptoms
- Generated address shows in UI
- Console doesn't show `[STORAGE] ✓ Saved` message
- Sweep tab is empty
- `diagnose_storage.py` shows no addresses

### Solution
**This was a critical bug - now fixed!**

1. **Make sure you have the latest code**:
   ```bash
   cd ~/src/electrum-plugins
   git pull origin main
   ```

2. **Restart Electrum** (old code may be cached):
   ```bash
   # Kill any running Electrum processes
   pkill -f electrum
   
   # Start fresh
   cd ~/src/electrum
   source venv/bin/activate
   ./run_electrum --testnet4
   ```

3. **Check console logs** when generating:
   - Should see: `[GENERATE] Starting storage save...`
   - Should see: `[STORAGE] ✓ Saved <address>`
   - Should see: `[GENERATE] ✅ Storage save completed`

4. **If still not saving**, check for errors:
   ```python
   # In Electrum Console:
   hasattr(wallet, 'db')  # Should be True
   wallet.db.get_plugin_storage()  # Should not error
   ```

### Root Cause
Before the fix, `generate_*()` functions didn't call `save_timelock_data()`. This has been fixed in all 5 functions.

---

## Issue: Plugin Menu Not Showing

### Symptoms
- Tools menu doesn't have "CLTV Timelock" option
- No plugin UI visible

### Solutions

**1. Check plugin is linked correctly**:
```bash
ls -la ~/.electrum/plugins/checklocktimeverify
# Should show symlink to your plugin directory
```

**2. Re-link if needed**:
```bash
rm ~/.electrum/plugins/checklocktimeverify
ln -s ~/src/electrum-plugins/checklocktimeverify ~/.electrum/plugins/checklocktimeverify
```

**3. Check Electrum found it**:
```python
# In Electrum Console:
plugins = window.gui_object.plugins
for p in plugins:
    print(p.name)
# Should see 'checklocktimeverify' in list
```

**4. Check for load errors**:
```bash
# Start Electrum with debug output
./run_electrum --testnet4 -v 2>&1 | grep -i cltv
```

---

## Issue: Console Not Showing Logs

### Symptoms
- Generate address works but no `[GENERATE]` logs
- Can't see what's happening

### Solution

**1. Open Console** (must be visible):
- View → Show Console
- Keep it open in a tab

**2. Check logging isn't disabled**:
```python
# In Console:
import logging
logger = logging.getLogger()
logger.level  # Should be DEBUG or INFO
```

**3. Manually test logging**:
```python
# In Console:
print("Test message")  # Should appear in console
```

---

## Issue: "Wallet Database Not Available"

### Symptoms
- Error: "Wallet database not available"
- Storage save fails
- Console shows error in `save_timelock_data()`

### Solutions

**1. Check wallet type**:
```python
# In Console:
type(wallet).__name__
# Should be: 'Standard_Wallet' or similar
```

**2. Check wallet has db**:
```python
# In Console:
hasattr(wallet, 'db')  # Should be True
hasattr(wallet, 'storage')  # Should be True
```

**3. Try with a standard wallet**:
- Create new wallet: File → New/Restore
- Choose: Standard wallet
- Import or generate addresses
- Try plugin again

---

## Issue: Sweep Tab Shows Wrong Balance

### Symptoms
- Address has been funded
- Sweep tab shows 0 sats
- Blockchain explorer shows balance

### Solutions

**1. Manual refresh**:
- Click "Refresh Cache" button in Sweep tab
- Wait for network query to complete

**2. Check network connection**:
```python
# In Console:
network.is_connected()  # Should be True
```

**3. Query address manually**:
```python
# In Console:
from electrum import bitcoin
scripthash = bitcoin.address_to_scripthash('YOUR_ADDRESS')
network.listunspent_for_scripthash(scripthash)
# Should show UTXOs if funded
```

**4. Check if address is in storage**:
```bash
cd ~/src/electrum-plugins/checklocktimeverify
python3 diagnose_storage.py
```

---

## Issue: Can't Sweep - "Locktime Not Reached"

### Symptoms
- Funded address in sweep tab
- "Sweep" button disabled or fails
- Error about locktime

### Solutions

**1. Check current block height**:
```python
# In Console:
network.get_local_height()
```

**2. Compare to locktime**:
- Your locktime must be <= current height
- If locktime is in future, must wait

**3. If using timestamp locktime**:
```python
# In Console:
import time
current_time = int(time.time())
print(f"Current: {current_time}, Your locktime: {YOUR_LOCKTIME}")
# Your locktime must be <= current_time
```

---

## Issue: Generated Testnet Address, Got Mainnet Format

### Symptoms
- Expected address starting with `2` (testnet)
- Got address starting with `3` (mainnet)

### Solution

**Check network mode**:
```python
# In Console:
from electrum import constants
constants.net.NET_NAME  # Should be 'testnet4' or 'signet'
```

**Restart with correct network**:
```bash
# For testnet4:
./run_electrum --testnet4

# For signet:
./run_electrum --signet
```

---

## Issue: Taproot Address Generation Fails

### Symptoms
- P2SH works fine
- Selecting "Taproot" causes error
- Console shows import errors

### Solutions

**1. Check Electrum version**:
```python
# In Console:
from electrum import version
version.ELECTRUM_VERSION
# Should be >= 4.3.0 for Taproot support
```

**2. Check Taproot imports**:
```python
# In Console:
from electrum.bitcoin import taproot_construct_tree_from_script
from electrum.crypto import sha256
# Should not error
```

**3. Try with signet** (better Taproot support):
```bash
./run_electrum --signet
```

---

## Issue: "Two-Factor Generation Failed"

### Symptoms
- Escrow works
- Payment Channel works
- Two-Factor fails with error

### Solution

**Two-Factor requires 3 keys**:
- User pubkey
- Service pubkey  
- **Recovery pubkey** ← Often forgotten!

Make sure all 3 fields are filled.

---

## Issue: Sweep Creates Invalid Transaction

### Symptoms
- Sweep button works
- Transaction created
- Broadcast fails with "script failed"

### Possible Causes

**1. Wrong nSequence**:
- CLTV requires `nSequence = 0xfffffffe`
- Check redemption code sets this

**2. Missing locktime**:
- Transaction `nLockTime` must be >= script locktime
- Check tx builder sets this

**3. Wrong script format**:
- Redeem script must match exactly
- Check script_hex from storage

### Debug
```python
# In Console:
timelocks = load_timelock_data()
print(timelocks[0])  # Check stored data
```

---

## Issue: UTXO Already Spent

### Symptoms
- Had balance, now shows 0
- Sweep tab shows "spent"
- Didn't manually sweep

### Explanation

**This is normal if**:
- You already swept it
- You used a redemption script
- You tested with the UTXO

**To verify**:
```bash
# Check transaction on explorer
# e.g., https://mempool.space/testnet4/address/YOUR_ADDRESS
```

**Generate a new address** and fund it for testing.

---

## Issue: Plugin Crashes on Startup

### Symptoms
- Electrum starts but immediately closes
- Or shows error dialog
- Console shows Python traceback

### Solutions

**1. Check Python version**:
```bash
python3 --version
# Should be >= 3.8
```

**2. Check dependencies**:
```bash
cd ~/src/electrum
source venv/bin/activate
pip install -e .  # Reinstall Electrum
```

**3. Check for syntax errors**:
```bash
cd ~/src/electrum-plugins/checklocktimeverify
python3 -m py_compile qt.py
# Should not error
```

**4. Start with verbose logging**:
```bash
./run_electrum --testnet4 -v 2>&1 | grep -i error
```

---

## Issue: Permission Denied on wallet.db

### Symptoms
- Can't save to wallet
- Error about permissions
- Storage save fails

### Solution

**Check wallet file permissions**:
```bash
ls -la ~/.electrum/testnet4/wallets/default_wallet
# Should be owned by you, writable
```

**Fix permissions**:
```bash
chmod 600 ~/.electrum/testnet4/wallets/default_wallet
```

---

## 🔍 Debug Commands

### Check Plugin Status
```python
# In Console:
window.gui_object.plugins.get('checklocktimeverify')
```

### Check Wallet Storage
```bash
cd ~/src/electrum-plugins/checklocktimeverify
python3 diagnose_storage.py
```

### Check Generated Address Validity
```python
# In Console:
from electrum import bitcoin
bitcoin.is_address('YOUR_ADDRESS')  # Should be True
```

### Manual UTXO Query
```python
# In Console:
from electrum import bitcoin
sh = bitcoin.address_to_scripthash('YOUR_ADDRESS')
utxos = network.listunspent_for_scripthash(sh)
print(utxos)
```

---

## 📞 Still Having Issues?

1. **Check the logs**:
   ```bash
   tail -f /tmp/electrum_sweep_test.log
   ```

2. **Run diagnostic**:
   ```bash
   python3 diagnose_storage.py > /tmp/storage_diag.txt
   ```

3. **Check documentation**:
   - `STORAGE_FIX_APPLIED.md` - Recent fixes
   - `DESIGN_PATTERNS.md` - Architecture
   - `TEST_STORAGE_AND_SWEEP.md` - Testing guide

4. **Create minimal test case**:
   ```bash
   cd tests
   python3 test_storage_integration.py
   ```

---

## ✅ Most Common Solution

**90% of issues are solved by**:
1. Make sure you have latest code
2. Restart Electrum completely
3. Open Console and check for logs
4. Run `diagnose_storage.py`

**Remember**: The storage bug fix is critical. If you generated addresses before October 15, 2025, they weren't saved and need to be manually added or re-generated.
