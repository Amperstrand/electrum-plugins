# Quick Start Guide - CLTV Plugin

## 📦 Installation

1. **Clone the plugin**
   ```bash
   cd ~/src
   git clone https://github.com/Amperstrand/electrum-plugins.git
   ```

2. **Install Electrum** (if not already installed)
   ```bash
   cd ~/src
   git clone https://github.com/spesmilo/electrum.git
   cd electrum
   python3 -m venv venv
   source venv/bin/activate
   pip install -e .
   ```

3. **Link the plugin**
   ```bash
   # Electrum looks for plugins in ~/.electrum/plugins/
   mkdir -p ~/.electrum/plugins
   ln -s ~/src/electrum-plugins/checklocktimeverify ~/.electrum/plugins/checklocktimeverify
   ```

---

## 🚀 First Run

### 1. Start Electrum with Plugin

```bash
cd ~/src/electrum
source venv/bin/activate
./run_electrum --testnet4
```

### 2. Open Console (IMPORTANT!)

- **View → Show Console** (keep it open to see logs)

### 3. Access Plugin

- **Tools → CLTV Timelock** (menu should appear)

---

## 🎯 Generate Your First Address

### Freezing Funds (Simplest Type)

1. **Open tab**: Tools → CLTV Timelock → Freezing Funds
2. **Set locktime**: Enter block height (current + 10 blocks)
3. **Load pubkey**: Click "Load from Wallet" 
4. **Choose type**: P2SH (Signet) ✓ (start with this)
5. **Click**: "Generate Address"

### ✅ What You Should See

**In Console** (critical - shows save working):
```
================================================================================
[GENERATE] Starting storage save for simple timelock address
================================================================================
[GENERATE] Address: 2N...
[GENERATE] Script type: simple
[GENERATE] Calling save_timelock_data()...
[STORAGE] ✓ Saved 2N...
[GENERATE] ✅ Storage save completed
================================================================================
```

**In Results Panel**:
- Address displayed
- Script hex shown
- Copy buttons available

**In Sweep Tab**:
- Address appears in table (might need to switch tabs to refresh)
- Balance shows 0 sats (until funded)

---

## 💰 Fund and Sweep

### 1. Fund the Address

```bash
# Get signet coins from faucet
# https://signetfaucet.com/

# Or use testnet4 faucet
# Send to the address you generated
```

### 2. Wait for Confirmation

- Watch balance update automatically in Sweep tab (Electrum monitors addresses automatically)

### 3. Wait for Locktime

- Locktime must pass before you can sweep
- Check current block height in console

### 4. Sweep Back to Wallet

- Click "Sweep All" button in Sweep tab
- Transaction will be built and broadcast
- Coins return to your wallet

---

## 🔍 Verify Everything is Working

### Test 1: Storage Saved?

```bash
cd ~/src/electrum-plugins/checklocktimeverify
python3 diagnose_storage.py
```

Expected:
```
✓ plugin_storage exists with 1 plugin(s)
✓ Address 2N... found in v3.1.0 structure
```

### Test 2: Logs Showing?

In Electrum Console, you should see:
- `[GENERATE]` logs when generating
- `[STORAGE]` logs when saving
- `[SWEEP]` logs when sweeping

### Test 3: Sweep Tab Populated?

- Tools → CLTV Timelock → Sweep Tab
- Should show generated addresses
- Balances update automatically when new blocks arrive or wallet state changes

---

## 🎓 Try Other Script Types

Once freezing funds works, try:

### Escrow (3-of-3 with timeout)
- Requires 3 pubkeys (party1, party2, agent)
- Normal: All 3 must sign
- Timeout: 2-of-2 after locktime

### Two-Factor (2-of-2 with recovery)
- Requires 3 pubkeys (user, service, recovery)
- Normal: User + Service
- Recovery: User + Recovery after timeout

### Payment Channel (bidirectional)
- Requires 2 pubkeys (sender, receiver)
- Normal: Both sign
- Refund: Sender only after timeout

### Data Publishing (conditional payment)
- Requires data hash + 2 pubkeys
- Publisher proves data preimage
- Buyer can refund after timeout

---

## 📚 Next Steps

1. ✅ **Generate addresses** - Done!
2. ✅ **Verify storage** - Check with diagnose_storage.py
3. 💰 **Fund address** - Use faucet
4. ⏰ **Wait for locktime** - Monitor blocks
5. 🔄 **Sweep coins** - Test redemption
6. 🎯 **Try Taproot** - Generate with Taproot option

---

## 🆘 Problems?

See `TROUBLESHOOTING.md` for common issues and solutions.

---

## 📖 Documentation

- `DESIGN_PATTERNS.md` - Architecture and patterns
- `STORAGE_FIX_APPLIED.md` - Recent fix details
- `TEST_STORAGE_AND_SWEEP.md` - Comprehensive testing guide
- `CAN_PLUGINS_ADD_COINS.md` - Plugin limitations explained
- `TAPROOT_FEASIBILITY.md` - Taproot implementation details

---

## 🎉 You're Ready!

Start with a simple freezing funds address on testnet4, verify it saves correctly, fund it, and sweep it back. Once that works, you understand the full workflow!

**Happy timelocking! 🔒⏰**
