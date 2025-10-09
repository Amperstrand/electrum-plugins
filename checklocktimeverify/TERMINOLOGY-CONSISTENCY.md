# BIP-65 Terminology Consistency Verification

## Final Review - Complete Alignment ✅

All code, UI labels, descriptions, and documentation now consistently use BIP-65 terminology.

## Summary of Updates Made

### 1. UI Tab Labels (100% Match)
- ✅ "Freezing Funds"
- ✅ "Escrow"  
- ✅ "Two-Factor Wallets"
- ✅ "Payment Channels"
- ✅ "Trustless Payments for Publishing Data"

### 2. UI Description Headers
**Before:** "BIP-65 Motivation section"  
**After:** "BIP-65 Motivation" or specific subsection names

Updated:
- ✅ Freezing Funds: "(BIP-65 Motivation)"
- ✅ Escrow: "(BIP-65 Motivation)"
- ✅ Two-Factor Wallets: "(BIP-65 Motivation: Non-interactive Time-locked Refunds)"
- ✅ Payment Channels: "(BIP-65 Motivation: Non-interactive Time-locked Refunds)"
- ✅ Trustless Payments for Publishing Data: "(BIP-65 Motivation)"

### 3. Form Labels
**Before:** "Service Pubkey (2FA):"  
**After:** "Service Pubkey:"

Removed informal abbreviation to match BIP-65's formal terminology.

### 4. Code Comments
**Before:** "Normal path: user + 2FA service"  
**After:** "Normal path: user + service"

**Before:** "Recovery path: user + recovery (after timeout)"  
**After:** "Recovery path: user + recovery (after expiry time)"

### 5. Class Docstrings
**Before:**
```python
"""
Two-Factor Wallet

Paths:
1. User + 2FA service (immediate)
2. User + recovery key (after timeout)

Use case: Daily spending requires 2FA, recovery possible after timeout
"""
```

**After:**
```python
"""
Two-Factor Wallets (Non-interactive Time-locked Refunds)

Paths:
1. User + service (immediate)
2. User + recovery key (after timeout)

Use case: Services like GreenAddress with two-factor authentication.
          User can recover funds if service becomes unavailable.
"""
```

### 6. Script Patterns in UI
**Two-Factor Script (now matches BIP-65 exactly):**
```
IF <service> CHECKSIGVERIFY ELSE <expiry time> CLTV DROP ENDIF <user> CHECKSIG
```

This matches BIP-65's exact pattern:
```
IF
    <service pubkey> CHECKSIGVERIFY
ELSE
    <expiry time> CHECKLOCKTIMEVERIFY DROP
ENDIF
<user pubkey> CHECKSIG
```

### 7. Terminology Consistency

| Concept | BIP-65 Term | Our Usage | Status |
|---------|-------------|-----------|--------|
| Time constraint | "expiry time" | "expiry time" | ✅ |
| Locked output | "encumbered output" | "encumbered output" | ✅ |
| Transaction fields | "nLockTime", "nSequence" | "nLockTime", "nSequence" | ✅ |
| Lock types | "lock-by-blockheight", "lock-by-blocktime" | Same | ✅ |
| Threshold | 500,000,000 (LOCKTIME_THRESHOLD) | 500,000,000 | ✅ |
| Character names | Alice, Bob, Lenny | Alice, Bob, Lenny | ✅ |
| Service examples | GreenAddress, PayPub | GreenAddress, PayPub | ✅ |
| Protocol names | Jeremy Spilman | Jeremy Spilman | ✅ |

### 8. Removed Informal Language

❌ Removed:
- "2FA" → Use "service" or "two-factor authentication" spelled out
- "Motivation section" → Use "Motivation" or specific subsection
- Informal parentheticals like "(2FA)" in labels

✅ Kept BIP-65 Terms:
- "timeout" (used in BIP-65)
- "expiry time" (used in BIP-65)
- Both are acceptable per BIP-65

## Key BIP-65 Quotes Now Accurately Reflected

### Freezing Funds
> "In addition to using cold storage, hardware wallets, and P2SH multisig outputs to control funds, now funds can be frozen in UTXOs directly on the blockchain."

✅ Used verbatim in our description

### Escrow  
> "If Alice and Bob jointly operate a business they may want to ensure that all funds are kept in 2-of-2 multisig transaction outputs..."

✅ Character names and scenario match exactly

### Two-Factor Wallets
> "Services like GreenAddress store bitcoins with 2-of-2 multisig scriptPubKey's such that one keypair is controlled by the user, and the other keypair is controlled by the service."

✅ Used verbatim in our description

> "the user is always able to spend their funds without the co-operation of the service by waiting for the expiry time to be reached"

✅ Used verbatim in our description

### Payment Channels
> "Jeremy Spilman style payment channels first setup a deposit controlled by 2-of-2 multisig, tx1, and then adjust a second transaction, tx2, that spends the output of tx1 to payor and payee."

✅ Exact terminology and tx notation preserved

### Trustless Payments for Publishing Data
> "The PayPub protocol makes it possible to pay for information in a trustless way..."

✅ Protocol name and description match

## Code Files Updated

1. **qt.py** - UI descriptions, form labels, log messages
2. **script_builders.py** - Class docstrings, comments, method descriptions
3. **BIP65-TERMINOLOGY.md** - Documentation of alignment

## Verification

Run these checks to verify consistency:

```bash
# Should find no "2FA" in Python code (except in comments explaining)
grep -r "2FA" checklocktimeverify/*.py | grep -v "two-factor" | grep -v "BIP-32"

# Should find "expiry time" in key places
grep -r "expiry time" checklocktimeverify/*.py

# Should find BIP-65 character names
grep -r "Alice.*Bob.*Lenny" checklocktimeverify/*.py

# Should find service names
grep -r "GreenAddress\|PayPub\|Jeremy Spilman" checklocktimeverify/*.py
```

All checks pass ✅

## Conclusion

The plugin now uses **100% consistent terminology with BIP-65**, including:
- Exact section titles
- Character names (Alice, Bob, Lenny)
- Service names (GreenAddress, PayPub, Jeremy Spilman)
- Technical terms (expiry time, encumbered output, nLockTime, nSequence)
- Script patterns (exact match with BIP-65 examples)
- Formal language (no informal abbreviations like "2FA" in UI)

This ensures users learning from the plugin will encounter the same terminology used throughout the Bitcoin ecosystem and in official BIP documentation.

---
*Last verified: October 2025*  
*All files updated and verified for consistency*
