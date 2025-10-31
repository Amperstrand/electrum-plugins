# BIP-65 CHECKLOCKTIMEVERIFY Examples

Reference: [BIP-65](https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki)

This document catalogs all the canonical examples from BIP-65 and tracks their implementation status in this plugin.

---

## Implementation Status Summary

| # | BIP-65 Example | Plugin Tab | Status | Notes |
|---|---------------|------------|---------|-------|
| 1 | Escrow with Backup | Escrow with Timelock Fallback | ✅ DONE | 2-of-2 or 2-of-3 after timeout |
| 2 | Two-Factor Wallets | Two-Factor Wallet | ✅ DONE | Service + user or user alone after timeout |
| 3 | Payment Channels | Payment Channels | ✅ DONE | Same script as #2, different use case |
| 4 | Publishing Data | Data Publishing | ✅ DONE | Hash preimage or refund |
| 5 | Freezing Funds | Simple Timelock | ✅ DONE | Basic CLTV + single sig |

**Progress:** 5/5 examples implemented (100% COMPLETE! 🎉)

---

## Example 1: Escrow with Backup Third-Party

**Status:** ✅ **IMPLEMENTED** (Tab: "Escrow with Timelock Fallback")

**Use Case:** Alice and Bob can spend funds together normally, but after 3 months, their lawyer Lenny can co-sign with one of them if needed.

### Script Structure

**scriptPubKey (locking script):**
```
IF
    <now + 3 months> CHECKLOCKTIMEVERIFY DROP
    <Lenny's pubkey> CHECKSIGVERIFY
    1
ELSE
    2
ENDIF
<Alice's pubkey> <Bob's pubkey> 2 CHECKMULTISIG
```

**Hex Format (example):**
```
63 03[locktime] b1 75 21[Lenny_pubkey] ad 51 67 52 68 21[Alice_pubkey] 21[Bob_pubkey] 52 ae
```

### Spending Paths

**Path 1: Normal spending (before 3 months)**
- Requires: Alice's signature + Bob's signature
- scriptSig: `0 <Alice's signature> <Bob's signature> 0`
- No time restriction

**Path 2: After 3 months (with Lenny)**
- Requires: (Alice OR Bob) + Lenny
- scriptSig: `0 <Alice/Bob's signature> <Lenny's signature> 1`
- Only valid after locktime

### Implementation Notes
- Requires 2-of-2 multisig with conditional 2-of-3 fallback
- Complex IF/ELSE branching
- Could be added in future version as "Escrow Timelock" type

---

## Example 2: Two-Factor Wallets with Timeout Recovery

**Status:** ✅ **IMPLEMENTED** (Tab: "Two-Factor Wallet")

**Use Case:** A user can spend funds without the service after a timeout if the service is unavailable.

### Script Structure

**scriptPubKey:**
```
IF
    <service pubkey> CHECKSIGVERIFY
ELSE
    <expiry time> CHECKLOCKTIMEVERIFY DROP
ENDIF
<user pubkey> CHECKSIG
```

**Hex Format (example):**
```
63 21[service_pubkey] ad 67 03[expiry_time] b1 75 68 21[user_pubkey] ac
```

### Behavior

**Path 1: Normal operation (anytime)**
- Requires: Service signature + User signature
- scriptSig: `<user_sig> <service_sig> 1`
- Service co-signs for security

**Path 2: Backup recovery (after expiry)**
- Requires: User signature only
- scriptSig: `<user_sig> 0`
- Only valid after locktime expires

### Implementation Details

**Plugin Functions:**
- `generate_twofactor_wallet()` - Creates the P2SH address
- `build_twofactor_script()` - Builds the IF/ELSE script

**UI Features:**
- Locktime selection (block height or timestamp)
- User pubkey input (with "Get from Wallet" button)
- Service pubkey input (with "Use Wallet Key" for testing)
- Full technical breakdown with spending paths

---

## Example 3: Payment Channels (Jeremy Spilman Style)

**Status:** ✅ **IMPLEMENTED** (Tab: "Payment Channels")

**Use Case:** Create refundable micropayment channels for instant off-chain payments with timeout refund protection.

### Script Structure

**scriptPubKey:**
```
IF
    <counterparty pubkey> CHECKSIGVERIFY
ELSE
    <refund time> CHECKLOCKTIMEVERIFY DROP
ENDIF
<user pubkey> CHECKSIG
```

**Hex Format:**
```
63 21[counterparty_pubkey] ad 67 03[refund_time] b1 75 68 21[user_pubkey] ac
```

### Behavior

**Path 1: Normal channel close (anytime)**
- Requires: Counterparty signature + User signature
- Both parties agree to close

**Path 2: Force-close/refund (after timeout)**
- Requires: User signature only
- Protects user if counterparty disappears

### Implementation Details

**Plugin Functions:**
- `generate_payment_channel()` - Creates the P2SH address
- `build_twofactor_script()` - Reuses two-factor script (identical structure)

**UI Features:**
- Locktime selection (block height or timestamp)
- Sender pubkey input (gets refund after timeout)
- Receiver pubkey input (receives payment with sender's signature)
- Full technical breakdown with both spending paths

**Key Points:**
- Same script structure as Two-Factor Wallets
- Different use case: payment flow instead of 2FA
- Used in early Lightning Network designs
- Sender provides signed payment updates off-chain
- Enables trustless payment channels

---

## Example 4: Trustless Payments for Publishing Data

**Status:** ✅ **IMPLEMENTED** (Tab: "Data Publishing")

**Use Case:** Pay for data/secrets with trustless delivery - publisher must reveal preimage to claim payment, or buyer gets refund.

### Script Structure

**scriptPubKey:**
```
IF
    HASH160 <Hash160(encryption key)> EQUALVERIFY
    <publisher pubkey> CHECKSIG
ELSE
    <expiry time> CHECKLOCKTIMEVERIFY DROP
    <buyer pubkey> CHECKSIG
ENDIF
```

**Hex Format:**
```
63 a9 14[hash160_of_key] 88 21[publisher_pubkey] ac 67 03[expiry_time] b1 75 21[buyer_pubkey] ac 68
```

### Behavior

**Path 1: Publisher reveals data (anytime)**
- Requires: Hash preimage + Publisher signature
- scriptSig: `<publisher_sig> <encryption_key> 1`
- Publisher proves they released the data

**Path 2: Buyer refund (after expiry)**
- Requires: Buyer signature only
- scriptSig: `<buyer_sig> 0`
- Buyer gets refund if data not released

### Implementation Details

**Plugin Functions:**
- `generate_datapub_contract()` - Creates the P2SH address
- `build_datapub_script()` - Builds IF/ELSE with HASH160 check
- `generate_data_hash()` - Helper to hash data and generate commitment

**UI Features:**
- Data hash input (SHA256)
- Helper to generate hash from plaintext data
- Publisher pubkey input (knows the secret)
- Buyer pubkey input (gets refund if data not published)
- Locktime selection for refund timeout
- Full technical breakdown with hash preimage requirements

**Script Structure (Actual Implementation):**
```
IF
    HASH160 <hash160_of_data> EQUALVERIFY
    <publisher_pubkey> CHECKSIG
ELSE
    <refund_time> CHECKLOCKTIMEVERIFY DROP
    <buyer_pubkey> CHECKSIG
ENDIF
```

**Security Notes:**
- Uses HASH160 (RIPEMD160 of SHA256) for standard Bitcoin practice
- Preimage becomes PUBLIC when published to blockchain
- Suitable for selling encryption keys, secrets, or data
- Atomic swap of data for payment

---

## Example 5: Freezing Funds (Simple Timelock)

**Status:** ✅ **IMPLEMENTED** (Primary feature of this plugin!)

**Use Case:** A straightforward way to lock funds until a specific time.

### Script Structure

**scriptPubKey:**
```
<expiry time> CHECKLOCKTIMEVERIFY DROP
DUP HASH160 <pubKeyHash> EQUALVERIFY CHECKSIG
```

**Hex Format:**
```
03[locktime] b1 75 76 a9 14[pubkey_hash] 88 ac
```

**Example (Block 272394):**
```
030a2804 b1 75 21 037f47cefaf4be34ad440aeaaf2589cd877885e97de188c0bf22c886f80388cc4f ac
```

### Behavior

**Single Spending Path (after locktime only):**
- Requires: Owner signature
- scriptSig: `<signature> <redeem_script>`
- Transaction nLockTime must be >= locktime
- Transaction nSequence must be < 0xffffffff

### Implementation Details

**✅ Implemented Features:**
- Create timelock address with block height or timestamp
- P2SH wrapping for standard address format
- Auto-saves redeem script for recovery
- Sweep functionality to reclaim funds after locktime
- Manual signing for P2SH CLTV inputs
- Auto-refresh on new blocks
- Real-time status updates (⏳ LOCKED / ✅ READY TO SWEEP)

**Plugin UI Locations:**
- Create tab: "Simple Timelock (Freeze Funds)"
- Sweep tab: Auto-detects and lists all timelocked addresses
- Manual sweep: Paste redeem script to recover

**Script Generation:**
```python
# Locktime bytes (3-4 bytes, little-endian)
locktime_bytes = locktime.to_bytes((locktime.bit_length() + 7) // 8, 'little')

# Build script: <locktime> CLTV DROP <pubkey> CHECKSIG
script = (
    bytes([len(locktime_bytes)]) + locktime_bytes +  # Push locktime
    b'\xb1' +  # OP_CHECKLOCKTIMEVERIFY
    b'\x75' +  # OP_DROP
    bytes([len(pubkey_bytes)]) + pubkey_bytes +  # Push pubkey
    b'\xac'   # OP_CHECKSIG
)
```

---

## Implementation Summary

| Example | Status | Complexity | Plugin Support |
|---------|--------|------------|----------------|
| 1. Escrow with Backup | ⚠️ Not Implemented | High (multisig + conditional) | Future feature |
| 2. Two-Factor Wallets | ⚠️ Not Implemented | Medium (requires service) | Could add |
| 3. Payment Channels | ⚠️ Not Implemented | High (channel state) | Out of scope |
| 4. Data Publishing | ⚠️ Not Implemented | Medium (hash preimage) | Could add |
| 5. Simple Timelock | ✅ **IMPLEMENTED** | Low (single sig) | **Full support** |

---

## Roadmap for Additional Examples

### Priority 1: Two-Factor Wallets (Example 2)
- **Effort:** Medium
- **Value:** High (useful backup recovery)
- **Requirements:** 
  - Add IF/ELSE branching to script builder
  - Add second pubkey input
  - Modify sweep to support both paths

### Priority 2: Escrow (Example 1)
- **Effort:** High
- **Value:** Medium (specialized use case)
- **Requirements:**
  - Full multisig support
  - Complex conditional logic
  - Multiple signature collection

### Priority 3: Data Publishing (Example 4)
- **Effort:** Medium
- **Value:** Low (niche use case)
- **Requirements:**
  - Hash preimage input
  - Conditional spending logic

---

## Testing Notes

**Current Implementation (Example 5):**
- ✅ Tested on signet with real funds
- ✅ Block height timelocks working
- ✅ Timestamp timelocks working
- ✅ Sweep functionality working
- ✅ Manual signing for P2SH inputs
- ✅ Auto-refresh on new blocks

**Test Addresses Created:**
- Multiple timelocks created and swept successfully
- Redeem scripts properly saved and loaded
- P2SH address generation verified
- Script hash calculation confirmed

---

## References

- **BIP-65 Specification:** https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki
- **Bitcoin Wiki:** https://en.bitcoin.it/wiki/Timelock
- **Optech Topics:** https://bitcoinops.org/en/topics/timelocks/
- **Script Reference:** https://en.bitcoin.it/wiki/Script

---

**Plugin Development Status:** SIGNET-PRODUCTION Quality  
**Sponsored by:** Vibes Capital Management 🚀  
**Network:** Signet/Testnet only (NOT for mainnet!)

