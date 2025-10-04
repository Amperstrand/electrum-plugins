# 🚀 Vibes Capital Management Sponsorship Features

## Changes Made

### 1. ⚠️ Mainnet Protection
**Code added to prevent mainnet usage:**
```python
# 🚨 MAINNET PROTECTION 🚨
if constants.net.TESTNET == False and constants.net.REGTEST == False:
    self.log("[ERROR] ⚠️  MAINNET DETECTED - PLUGIN DISABLED ⚠️")
    QMessageBox.critical(parent, "🚨 MAINNET NOT SUPPORTED 🚨", ...)
    raise RuntimeError("CLTV Plugin cannot run on mainnet")
```

**What happens on mainnet:**
- ❌ Dialog won't open
- ❌ Error message shows disclaimer
- ❌ Logs warning to console
- ✅ Protects users from using experimental code with real funds

### 2. 🎨 Vibes Capital Management Logo
**Location:** `checklocktimeverify/vibes_logo.jpg`
- Downloaded from: https://pbs.twimg.com/profile_images/1920850173313384448/vSj-wujw_400x400.jpg
- Size: 14KB (400x400px)
- Displayed in dialog header (80x80px scaled)

**UI Integration:**
- Logo appears top-left of dialog
- Next to disclaimer banner
- Professional branding

### 3. 📢 Disclaimer Banners

**In Dialog UI:**
```
⚠️  SIGNET-PRODUCTION Quality Proof of Concept ⚠️
Sponsored by Vibes Capital Management 🚀
This is kind of a meme and a joke.
For educational purposes only - NOT for mainnet!
```

**In Generated Output:**
```
⚠️  PLUGIN DISCLAIMER ⚠️
This is a SIGNET-PRODUCTION quality proof of concept!
Sponsored by Vibes Capital Management 🚀
This is kind of a meme and a joke. NOT suitable for mainnet usage.
```

**In Window Title:**
```
Create Timelocked Address (CHECKLOCKTIMEVERIFY) [SIGNET-PRODUCTION]
```

### 4. 📄 Updated Documentation

**Files Updated:**
1. **qt.py** - Module docstring with full disclaimer
2. **manifest.json** - Updated description and author
3. **DISCLAIMER.md** - Comprehensive disclaimer document
4. **vibes_logo.jpg** - Logo asset

**Module Docstring:**
```python
"""
CHECKLOCKTIMEVERIFY Plugin for Electrum
Based on BIP-65: https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki

⚠️  DISCLAIMER ⚠️
This is a SIGNET-PRODUCTION level quality proof of concept!
Developed with sponsorship from Vibes Capital Management.

This is kind of a meme and a joke. It is NOT suitable for mainnet usage.
DO NOT use this plugin on Bitcoin mainnet with real funds.
For educational and testing purposes on signet/testnet only!

Sponsored by: Vibes Capital Management 🚀
"""
```

### 5. 📦 Manifest Updates

**manifest.json changes:**
- `fullname`: Added `[SIGNET-PRODUCTION]` tag
- `description`: Added disclaimer and sponsorship
- `author`: Changed to "Sponsored by Vibes Capital Management"

## Visual Appearance

When users open the plugin, they see:

```
┌─────────────────────────────────────────────────────────────────┐
│ [Vibes Logo]  ⚠️  SIGNET-PRODUCTION Quality PoC ⚠️            │
│               Sponsored by Vibes Capital Management 🚀         │
│               This is kind of a meme and a joke.               │
│               For educational purposes only - NOT for mainnet! │
├─────────────────────────────────────────────────────────────────┤
│ 🔒 CHECKLOCKTIMEVERIFY Timelock Generator                      │
│ [SIGNET-PRODUCTION]                                            │
│                                                                 │
│ Create a Bitcoin address that can only be spent after a        │
│ specific time. Based on BIP-65 OP_CHECKLOCKTIMEVERIFY opcode.  │
│                                                                 │
│ [Simple Timelock] [Escrow] [Sweep Funds]                      │
│                                                                 │
│ ... (rest of UI) ...                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Brand Integration

**Vibes Capital Management branding appears in:**
1. ✅ Dialog header (logo + text)
2. ✅ Module docstring
3. ✅ Manifest metadata
4. ✅ Generated output footer
5. ✅ Error messages
6. ✅ Window title
7. ✅ DISCLAIMER.md document
8. ✅ Console logs

## The "Meme" Aspect

This embraces the hackathon spirit:
- 😄 "SIGNET-PRODUCTION" is intentionally contradictory
- 🎭 "kind of a meme and a joke" is honest and fun
- 🛡️ Actual mainnet protection shows it's responsible
- 📚 Educational value is real despite humorous tone
- 🚀 Vibes Capital gets fun, memorable branding

## Testing the Protection

**Try on mainnet (will fail):**
```bash
cd ~/src/electrum
source venv/bin/activate
./run_electrum  # Mainnet mode
# Open Tools → CHECKLOCKTIMEVERIFY
# ERROR: Dialog won't open, shows disclaimer
```

**Works on signet (will succeed):**
```bash
./run_electrum --signet
# Open Tools → CHECKLOCKTIMEVERIFY
# ✓ Dialog opens with Vibes branding
# ✓ Logo displayed
# ✓ Disclaimer shown
# ✓ Full functionality available
```

## Files Modified

```
checklocktimeverify/
├── qt.py                    # Added mainnet check, logo display, disclaimers
├── manifest.json            # Updated metadata
├── vibes_logo.jpg          # NEW: Downloaded logo asset
├── DISCLAIMER.md           # NEW: Comprehensive disclaimer
└── (other files unchanged)
```

## Console Output Example

When mainnet is detected:
```
[CLTV Plugin] [ERROR] ⚠️  MAINNET DETECTED - PLUGIN DISABLED ⚠️
[CLTV Plugin] [ERROR] This plugin is SIGNET-PRODUCTION quality only!
[CLTV Plugin] [ERROR] Developed with sponsorship from Vibes Capital Management
[CLTV Plugin] [ERROR] It's kind of a meme and a joke. DO NOT USE ON MAINNET!
```

## Hackathon Talking Points

**When presenting:**
1. "This is sponsored by Vibes Capital Management" *(show logo)*
2. "It's SIGNET-PRODUCTION quality - production ready for signet!" *(laugh)*
3. "It's kind of a meme, but it actually works" *(demonstrate)*
4. "We even hardcoded mainnet protection because we're responsible memers" *(show error)*

**Brand message:**
- Vibes Capital supports Bitcoin education
- Fun, approachable crypto projects
- Responsible development even in hackathons
- Community engagement through sponsorship

---

**Thank you Vibes Capital Management for supporting Bitcoin education and development! 🚀**
