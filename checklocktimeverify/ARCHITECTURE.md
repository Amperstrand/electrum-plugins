# CHECKLOCKTIMEVERIFY Plugin Architecture

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ELECTRUM WALLET                              │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Tools Menu                                │  │
│  │  • Plugins...                                                 │  │
│  │  • Network...                                                 │  │
│  │  • CHECKLOCKTIMEVERIFY Timelock... ◄── Our Plugin           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                 │                                     │
└─────────────────────────────────┼─────────────────────────────────────┘
                                  │ User clicks
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TimelockDialog (Qt6)                              │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Tab 1: Simple Timelock  │  Tab 2: Escrow w/ Fallback         │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │                                                                 │ │
│  │  ┌─────────────────────┐       ┌──────────────────────────┐   │ │
│  │  │ Locktime Type       │       │  Public Key Input        │   │ │
│  │  │ ○ Block Height      │       │  ┌────────────────────┐  │   │ │
│  │  │ ◉ Date & Time       │       │  │ 02abc123...        │  │   │ │
│  │  └─────────────────────┘       │  └────────────────────┘  │   │ │
│  │                                 │  [Get Key from Wallet]   │   │ │
│  │  ┌─────────────────────┐       └──────────────────────────┘   │ │
│  │  │ 2025-11-15 12:00:00 │                                       │ │
│  │  └─────────────────────┘       [Generate Address]             │ │
│  │                                                                 │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │  Result Display                                                │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │ P2SH Address: 3Abc...xyz                                 │ │ │
│  │  │ Redeem Script: 04deadbeefb175...ac                       │ │ │
│  │  │ [Copy Address]  [Copy Script]                            │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Script Construction Flow

```
User Input
    │
    ├─► Locktime (Block or Timestamp)
    ├─► Public Key(s)
    └─► Script Type Choice
         │
         ▼
┌────────────────────────────────┐
│  build_*_cltv_script()         │
│                                 │
│  1. Push locktime value         │
│  2. Add OP_CHECKLOCKTIMEVERIFY │
│  3. Add OP_DROP                │
│  4. Add signature check(s)     │
│  5. Add multisig (if escrow)   │
└────────────────────────────────┘
         │
         ▼
    Script Bytes
         │
         ▼
┌────────────────────────────────┐
│  script_to_p2sh_address()      │
│                                 │
│  1. SHA256(script)             │
│  2. RIPEMD160(hash)            │
│  3. Add version byte           │
│  4. Encode as Base58Check      │
└────────────────────────────────┘
         │
         ▼
    P2SH Address
    (3... or bc1q...)
```

## Simple Timelock Script Anatomy

```
Locktime: 900000 (block height)
Pubkey: 02abc123...def (33 bytes compressed)

┌─────────────────────────────────────────────────────────────┐
│                    Script Construction                       │
├──────────────┬──────────────────────────────────────────────┤
│ Byte(s)      │ Meaning                                      │
├──────────────┼──────────────────────────────────────────────┤
│ 03           │ PUSH 3 bytes                                 │
│ a0 bb 0d     │ 900000 in little-endian (0x0dbbv0)          │
│ b1           │ OP_CHECKLOCKTIMEVERIFY                       │
│ 75           │ OP_DROP                                      │
│ 21           │ PUSH 33 bytes                                │
│ 02abc...def  │ Public key (33 bytes)                        │
│ ac           │ OP_CHECKSIG                                  │
└──────────────┴──────────────────────────────────────────────┘

Stack Execution (when spending):
┌──────────────────────────────────────────────────────────────┐
│ Initial:    [signature] [pubkey] [script]                    │
│ After push: [signature] [pubkey] [900000]                    │
│ After CLTV: [signature] [pubkey] [900000]  ← Validated!     │
│ After DROP: [signature] [pubkey]                             │
│ After CHECKSIG: [true]                     ← If valid!       │
└──────────────────────────────────────────────────────────────┘

CHECKLOCKTIMEVERIFY validates:
✓ Transaction nLockTime >= 900000
✓ nLockTime type matches (both < 500000000)
✓ Input nSequence < 0xffffffff
✗ Fails otherwise → transaction invalid
```

## Escrow Script Anatomy

```
Locktime: 900000
Party1: 02aaa...
Party2: 02bbb...
Escrow: 02ccc...

┌────────────────────────────────────────────────────────────────┐
│                    Escrow Script Structure                      │
├──────────────┬─────────────────────────────────────────────────┤
│ Opcode       │ Purpose                                         │
├──────────────┼─────────────────────────────────────────────────┤
│ OP_IF        │ Start conditional                               │
│              │                                                 │
│ [locktime]   │ Push 900000                                     │
│ OP_CLTV      │ Verify time has passed                          │
│ OP_DROP      │ Remove locktime from stack                      │
│ [escrow_key] │ Push escrow agent's pubkey                      │
│ OP_CHECKSIGVERIFY │ Verify escrow signature                   │
│ OP_1         │ Need 1 more signature                           │
│              │                                                 │
│ OP_ELSE      │ Alternative path (normal case)                  │
│              │                                                 │
│ OP_2         │ Need 2 signatures                               │
│              │                                                 │
│ OP_ENDIF     │ End conditional                                 │
│              │                                                 │
│ [party1_key] │ Push party 1 pubkey                             │
│ [party2_key] │ Push party 2 pubkey                             │
│ OP_2         │ 2 pubkeys provided                              │
│ OP_CHECKMULTISIG │ Check M-of-N signatures                    │
└──────────────┴─────────────────────────────────────────────────┘

Spending Paths:

Path 1: BEFORE locktime (OP_ELSE branch)
├─ Requires: Party1 sig + Party2 sig
├─ Script: 0 <sig1> <sig2> 0 [script]
└─ Result: 2-of-2 multisig executes

Path 2: AFTER locktime (OP_IF branch)
├─ Requires: Escrow sig + (Party1 OR Party2) sig
├─ Script: 0 <party_sig> <escrow_sig> 1 [script]
└─ Result: Escrow + 1-of-2 executes
```

## Plugin Class Structure

```
┌────────────────────────────────────────────────────────────┐
│                      Plugin                                 │
│  (Inherits from BasePlugin)                                │
├────────────────────────────────────────────────────────────┤
│  Hooks:                                                     │
│  • load_wallet(wallet, window)                             │
│  • close_wallet(wallet)                                    │
│                                                             │
│  Methods:                                                   │
│  • add_menu_item(window)                                   │
│  • show_timelock_dialog(window)                            │
└────────────────────────────────────────────────────────────┘
                            │
                            │ Creates
                            ▼
┌────────────────────────────────────────────────────────────┐
│                   TimelockDialog                            │
│  (QDialog)                                                  │
├────────────────────────────────────────────────────────────┤
│  UI Setup:                                                  │
│  • create_simple_timelock_tab()                            │
│  • create_escrow_tab()                                     │
│                                                             │
│  Script Building:                                           │
│  • build_simple_cltv_script()                              │
│  • build_escrow_cltv_script()                              │
│  • push_int(), push_bytes()                                │
│  • encode_minimal_int()                                    │
│                                                             │
│  Address Generation:                                        │
│  • script_to_p2sh_address()                                │
│                                                             │
│  Actions:                                                   │
│  • generate_simple_timelock()                              │
│  • generate_escrow_timelock()                              │
│  • get_wallet_pubkey()                                     │
│  • display_results()                                       │
│  • copy_address()                                          │
│  • copy_script()                                           │
└────────────────────────────────────────────────────────────┘
```

## Interaction Sequence

```
User                 Plugin                  Electrum Wallet
 │                     │                            │
 │ Opens wallet        │                            │
 ├────────────────────►│                            │
 │                     │ load_wallet hook           │
 │                     ├───────────────────────────►│
 │                     │                            │
 │                     │ add_menu_item()            │
 │                     │◄───────────────────────────┤
 │                     │                            │
 │ Clicks menu         │                            │
 ├────────────────────►│                            │
 │                     │ show_timelock_dialog()     │
 │                     │                            │
 │ ◄───────────────────┤                            │
 │  [Dialog Opens]     │                            │
 │                     │                            │
 │ Enters locktime     │                            │
 ├────────────────────►│                            │
 │                     │                            │
 │ Clicks "Get Key"    │                            │
 ├────────────────────►│                            │
 │                     │ wallet.get_receiving_address()
 │                     ├───────────────────────────►│
 │                     │ wallet.get_public_key()    │
 │                     │◄───────────────────────────┤
 │ ◄───────────────────┤                            │
 │  [Pubkey displayed] │                            │
 │                     │                            │
 │ Clicks "Generate"   │                            │
 ├────────────────────►│                            │
 │                     │ build_*_cltv_script()      │
 │                     │ script_to_p2sh_address()   │
 │ ◄───────────────────┤                            │
 │  [Results shown]    │                            │
 │                     │                            │
 │ Clicks "Copy"       │                            │
 ├────────────────────►│                            │
 │ ◄───────────────────┤                            │
 │  [Clipboard updated]│                            │
```

## File Dependencies

```
checklocktimeverify/
│
├── __init__.py
│   └── (empty - package marker)
│
├── manifest.json
│   ├── name: "checklocktimeverify"
│   ├── fullname: "CHECKLOCKTIMEVERIFY Timelock"
│   ├── available_for: ["qt"]
│   └── version: "0.0.1"
│
└── qt.py
    │
    ├── Imports
    │   ├── PyQt6.QtWidgets (UI components)
    │   ├── PyQt6.QtCore (Date/time)
    │   ├── electrum.plugin (BasePlugin, hook)
    │   ├── electrum.bitcoin (address functions)
    │   └── electrum.transaction (opcodes)
    │
    ├── TimelockDialog class
    │   ├── UI Components (tabs, inputs, buttons)
    │   ├── Script builders
    │   └── Event handlers
    │
    └── Plugin class
        ├── Hooks (load_wallet, close_wallet)
        └── Menu integration
```

## Data Flow

```
                Input Data
                    │
        ┌───────────┼───────────┐
        │           │           │
    Locktime    Pubkey(s)   Script Type
        │           │           │
        └───────────┼───────────┘
                    ▼
            Script Builder
                    │
        ┌───────────┴───────────┐
        │                       │
    Validation            Encoding
    • Type check          • Minimal int
    • Range check         • Push opcodes
    • Format check        • Byte order
        │                       │
        └───────────┬───────────┘
                    ▼
              Script Bytes
                    │
                    ▼
              Hash160
           (SHA256 + RIPEMD160)
                    │
                    ▼
          Base58Check Encoding
                    │
                    ▼
            P2SH Address
           (3... or bc1q...)
                    │
                    ▼
              User Display
```

## Key Algorithms

### 1. Minimal Integer Encoding
```
Input: 900000 (decimal)
     = 0x0DBB80 (hex)
     
Little-endian bytes: 80 BB 0D
Check sign bit: 0x80 & 0x80 = 0x80 (set!)
Add extra byte: 80 BB 0D 00

Final: 04 80 BB 0D 00
       ↑  ↑  ↑  ↑  ↑
       |  |  |  |  └─ Sign byte (positive)
       |  └──┴──┴──── Value bytes
       └───────────── Length (4 bytes)
```

### 2. P2SH Address Generation
```
Script: 03a0bb0db175<pubkey>ac

Step 1: SHA256
script_bytes → SHA256 → hash1

Step 2: RIPEMD160
hash1 → RIPEMD160 → script_hash (20 bytes)

Step 3: Add version
version_byte (0x05) + script_hash → versioned_hash

Step 4: Checksum
SHA256(SHA256(versioned_hash)) → take first 4 bytes

Step 5: Encode
Base58Encode(versioned_hash + checksum) → Address
```

## Security Model

```
┌────────────────────────────────────────────────────────────┐
│                     Security Layers                         │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: Consensus Rules                                  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ • CHECKLOCKTIMEVERIFY opcode validation              │ │
│  │ • nLockTime enforcement                              │ │
│  │ • nSequence requirements                             │ │
│  │ • Block/timestamp type matching                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
│  Layer 2: Script Validation                                │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ • Signature verification                             │ │
│  │ • Public key matching                                │ │
│  │ • Multisig M-of-N checks                            │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
│  Layer 3: User Responsibility                              │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ • Save redeem script (else funds lost!)              │ │
│  │ • Protect private keys                               │ │
│  │ • Verify addresses before sending                    │ │
│  │ • Test on testnet first                              │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

## Comparison: Before vs After Locktime

```
BEFORE Locktime 900000          │  AFTER Locktime 900000
────────────────────────────────┼──────────────────────────────
Current block: 850000           │  Current block: 900050
                                │
Simple Timelock Script:         │  Simple Timelock Script:
  ❌ CANNOT SPEND               │    ✅ CAN SPEND
  CLTV validation fails         │    CLTV validation succeeds
  Consensus rules reject        │    Signature verified
                                │    Transaction valid
                                │
Escrow Script:                  │  Escrow Script:
  ✅ CAN SPEND (ELSE branch)    │    ✅ CAN SPEND (both branches)
  Party1 + Party2 (2-of-2)      │    Option 1: Party1 + Party2
  No timelock check             │    Option 2: Escrow + either
                                │
Network behavior:               │  Network behavior:
  Transaction rejected          │    Transaction accepted
  "non-final" or "CLTV failed"  │    Propagated to mempool
  Not in mempool                │    Included in blocks
  Not mineable                  │    Confirmations accumulate
```

---

*This architecture demonstrates the complete flow from user input to Bitcoin address generation, following BIP-65 specifications.*
