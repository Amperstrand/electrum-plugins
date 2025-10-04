# 🚀 Quick Installation Guide

## Option 1: Automatic Installation (Easiest)

### Step 1: Run the installer script
```bash
cd /Users/macbook/src/electrum-plugins/checklocktimeverify
./install.sh
```

That's it! The script will:
- ✅ Check if Electrum is installed
- ✅ Create a symlink to the plugin
- ✅ Show you next steps

---

## Option 2: Manual Installation

### Step 1: Check if you have Electrum
```bash
ls ~/electrum
```

If you don't have it:
```bash
git clone https://github.com/spesmilo/electrum.git ~/electrum
cd ~/electrum
python3 -m pip install --user -e .
```

### Step 2: Create symlink to plugin
```bash
cd ~/electrum/electrum/plugins/
ln -s /Users/macbook/src/electrum-plugins/checklocktimeverify checklocktimeverify
```

### Step 3: Verify symlink
```bash
ls -la ~/electrum/electrum/plugins/ | grep checklocktimeverify
```

You should see:
```
checklocktimeverify -> /Users/macbook/src/electrum-plugins/checklocktimeverify
```

---

## Step 4: Run Electrum

```bash
cd ~/electrum
./run_electrum
```

---

## Step 5: Enable the Plugin

1. In Electrum, go to **Tools** → **Plugins**
2. Find **CHECKLOCKTIMEVERIFY Timelock** in the list
3. Check the checkbox to enable it
4. You should see a checkmark ✅

---

## Step 6: Use the Plugin

1. Go to **Tools** → **CHECKLOCKTIMEVERIFY Timelock...**
2. A dialog will open with two tabs
3. Try generating a simple timelock address!

---

## Quick Test (2 minutes)

Once the plugin is enabled:

1. **Tools** → **CHECKLOCKTIMEVERIFY Timelock...**
2. Stay on "Simple Timelock" tab
3. Select **Block Height**
4. Enter: `900000`
5. Click **Get Key from Wallet**
6. Click **Generate Simple Timelock Address**
7. ✅ You should see a P2SH address!

---

## Troubleshooting

### Plugin doesn't appear in menu
```bash
# Check if symlink exists
ls -la ~/electrum/electrum/plugins/checklocktimeverify

# Check Electrum console for errors
cd ~/electrum
./run_electrum 2>&1 | grep -i checklocktimeverify
```

### Import errors
Make sure you have PyQt6:
```bash
pip install PyQt6
```

### "Get Key from Wallet" doesn't work
- Make sure you have a wallet loaded
- Try creating a receiving address first
- Use the Receive tab to generate an address

---

## Current Status Check

Run this to verify everything:
```bash
# 1. Check plugin files exist
ls /Users/macbook/src/electrum-plugins/checklocktimeverify/

# 2. Check Electrum exists
ls ~/electrum/

# 3. Check if symlink is created
ls -la ~/electrum/electrum/plugins/ | grep checklocktimeverify

# 4. Count plugin files
ls /Users/macbook/src/electrum-plugins/checklocktimeverify/ | wc -l
```

Should show: 13 files (including install.sh and INSTALL.md)

---

## What's Next?

After installation:
- 📖 Read **README.md** for usage guide
- 🧪 Follow **TESTING.md** for detailed tests
- 🏗️ Check **ARCHITECTURE.md** to understand how it works
- 💡 Run **examples.py** to see script breakdowns

---

## One-Line Install

If you have Electrum at `~/electrum`:

```bash
cd ~/electrum/electrum/plugins/ && ln -s /Users/macbook/src/electrum-plugins/checklocktimeverify checklocktimeverify && cd ~/electrum && ./run_electrum
```

Then enable in: **Tools → Plugins → CHECKLOCKTIMEVERIFY Timelock**

---

## Uninstall

To remove the plugin:
```bash
rm ~/electrum/electrum/plugins/checklocktimeverify
```

Then restart Electrum.

---

**Need help?** See TESTING.md for detailed troubleshooting!
