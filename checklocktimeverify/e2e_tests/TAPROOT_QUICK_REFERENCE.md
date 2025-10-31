# Taproot Quick Reference - Script-Path Only

**Strategy:** NUMS internal key + script-path spending only. No key aggregation.

---

## 🔑 Key Concepts

### NUMS Point (Internal Key)
```python
# "Nothing Up My Sleeve" point - prevents keypath spending
NUMS_POINT = bytes.fromhex(
    "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
)
# This is H(SHA256("rust-bitcoin NUMS point"))
```

### X-Only Public Keys
```python
# P2WSH uses 33-byte compressed pubkeys
pubkey_compressed = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"

# Taproot uses 32-byte x-only pubkeys (drop first byte)
pubkey_xonly = pubkey_compressed[1:]  # Remove 0x02/0x03 prefix
# Result: "c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
```

---

## 🔧 Tapscript Patterns

### Single-Sig with CLTV
```python
# P2WSH
script_p2wsh = [
    locktime, OP_CLTV, OP_DROP,
    pubkey_compressed,  # 33 bytes
    OP_CHECKSIG
]

# Taproot
script_taproot = [
    locktime, OP_CLTV, OP_DROP,
    pubkey_xonly,  # 32 bytes
    OP_CHECKSIG
]

# Witness: [signature, script, control_block]
```

### 2-of-2 Multisig (NO Key Aggregation)
```python
# P2WSH - Uses OP_CHECKMULTISIG
script_p2wsh = [
    OP_2,
    alice_pubkey_compressed,
    bob_pubkey_compressed,
    OP_2,
    OP_CHECKMULTISIG
]

# Taproot - Uses OP_CHECKSIGADD
script_taproot = [
    alice_pubkey_xonly,
    OP_CHECKSIG,          # Check Alice's sig, push 1 or 0
    bob_pubkey_xonly,
    OP_CHECKSIGADD,       # Check Bob's sig, add to count
    OP_2,                 # Push 2
    OP_EQUAL              # Verify count == 2
]

# Witness: [alice_sig, bob_sig, script, control_block]
```

### Multiple Script Paths (Taptree)
```python
# Example: Data Publishing (2 paths)
script_publisher = [
    OP_HASH160, data_hash, OP_EQUALVERIFY,
    publisher_xonly, OP_CHECKSIG
]

script_refund = [
    locktime, OP_CLTV, OP_DROP,
    buyer_xonly, OP_CHECKSIG
]

# Create taptree
from electrum.bitcoin import TaprootScriptTree
tree = TaprootScriptTree([script_publisher, script_refund])

# Generate address
output_script, tweak, control_blocks = taproot_construct_tree(NUMS_POINT, tree)
```

---

## 📝 Script Builder Template

```python
from electrum import opcodes
from electrum.bitcoin import TaprootScriptTree, taproot_construct_tree
from electrum.segwit_addr import encode_segwit_address

class ExampleTaprootBuilder:
    """
    Example Taproot script builder.
    """
    
    SCRIPT_TYPE = "example_taproot"
    NUMS_POINT = bytes.fromhex(
        "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
    )
    
    def build(self, params):
        """Build Tapscript(s)."""
        locktime = params['locktime']
        pubkey_xonly = bytes.fromhex(params['pubkey_xonly'])
        
        # Build script
        script = bytearray()
        script.append(len(locktime.to_bytes(4, 'little')))
        script.extend(locktime.to_bytes(4, 'little'))
        script.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        script.append(opcodes.OP_DROP)
        script.append(32)  # x-only pubkey is always 32 bytes
        script.extend(pubkey_xonly)
        script.append(opcodes.OP_CHECKSIG)
        
        return bytes(script)
    
    def to_address(self, script_bytes):
        """Convert to bech32m address."""
        tree = TaprootScriptTree([script_bytes])
        output_script, tweak, control_block = taproot_construct_tree(
            self.NUMS_POINT, tree
        )
        
        # For signet: 'tb', version 1
        address = encode_segwit_address('tb', 1, output_script[2:])
        return address
```

---

## 🔓 Sweeper Template

```python
from electrum.transaction import Transaction, PartialTxInput, PartialTxOutput
from electrum.bitcoin import taproot_construct_tree, TaprootScriptTree
from electrum.ecc import ECPrivkey

class ExampleTaprootSweeper:
    """
    Sweep from Taproot script-path.
    """
    
    NUMS_POINT = bytes.fromhex(
        "50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0"
    )
    
    def sweep(self, utxo_info, dest_address, current_height):
        """Create sweep transaction."""
        # Verify locktime
        if current_height < utxo_info['locktime']:
            raise ValueError(f"Locktime not reached")
        
        # Recreate script and control block
        script_bytes = bytes.fromhex(utxo_info['script_hex'])
        tree = TaprootScriptTree([script_bytes])
        output_script, tweak, control_block = taproot_construct_tree(
            self.NUMS_POINT, tree
        )
        
        # Create transaction
        txin = PartialTxInput(
            prevout=f"{utxo_info['txid']}:{utxo_info['vout']}",
            sequence=0xFFFFFFFE
        )
        
        fee_sats = 200
        txout = PartialTxOutput.from_address_and_value(
            dest_address,
            utxo_info['amount_sats'] - fee_sats
        )
        
        tx = Transaction.from_io([txin], [txout], locktime=utxo_info['locktime'])
        
        # Sign with Schnorr
        privkey = ECPrivkey(bytes.fromhex(utxo_info['private_key_hex']))
        sighash = tx.signature_hash_tapscript(
            input_index=0,
            tapscript=script_bytes,
            codesep_pos=None
        )
        sig = privkey.sign_schnorr(sighash)
        
        # Build witness: [sig, script, control_block]
        txin.witness = [sig, script_bytes, control_block]
        
        return tx.serialize()
```

---

## 🔄 P2WSH vs Taproot Conversion

### Single Key
| Aspect | P2WSH | Taproot |
|--------|-------|---------|
| Pubkey | 33 bytes (02/03...) | 32 bytes (x-only) |
| Address | bech32 (`tb1q...`) | bech32m (`tb1p...`) |
| Witness | `[sig, script]` | `[sig, script, control_block]` |
| Signature | ECDSA (70-72 bytes) | Schnorr (64 bytes) |

### Multisig (2-of-2)
| Aspect | P2WSH | Taproot |
|--------|-------|---------|
| Opcode | `OP_CHECKMULTISIG` | `OP_CHECKSIGADD` |
| Script | `OP_2 <A> <B> OP_2 OP_CHECKMULTISIG` | `<A> OP_CHECKSIG <B> OP_CHECKSIGADD OP_2 OP_EQUAL` |
| Witness | `[sig_A, sig_B, script]` | `[sig_A, sig_B, script, control_block]` |

---

## 📦 Test Numbering & Amounts

**Formula:** `amount_sats = 1100 + test_number` for Taproot (1110-1118)

| Test # | Example | Path | Amount |
|--------|---------|------|--------|
| 10 | Simple CLTV | Normal | **1110 sats** |
| 11 | Escrow | Normal | **1111 sats** |
| 12 | Escrow | Arbitration | **1112 sats** |
| 13 | Two-Factor | Normal | **1113 sats** |
| 14 | Two-Factor | Recovery | **1114 sats** |
| 15 | Payment Channel | Cooperative | **1115 sats** |
| 16 | Payment Channel | Refund | **1116 sats** |
| 17 | Data Publishing | Publisher | **1117 sats** |
| 18 | Data Publishing | Buyer Refund | **1118 sats** |

**P2WSH Tests (1-9):** 1001-1009 sats  
**Taproot Tests (10-18):** 1110-1118 sats  
**Benefit:** Amount range + unique-per-test mapping simplifies funding/vout mapping.

---

## ⚠️ Common Mistakes to Avoid

1. **Using compressed pubkeys in Tapscript**
   - ❌ 33 bytes with prefix
   - ✅ 32 bytes, x-only

2. **Forgetting control block in witness**
   - ❌ `[sig, script]`
   - ✅ `[sig, script, control_block]`

3. **Using ECDSA signatures**
   - ❌ `privkey.sign_transaction(...)`
   - ✅ `privkey.sign_schnorr(...)`

4. **Wrong witness order for multisig**
   - ❌ `[sig_B, sig_A, script, control_block]`
   - ✅ `[sig_A, sig_B, script, control_block]` (order matters!)

5. **Chaining CHECKSIGADD without an initial counter**
   - ❌ No `0` (empty) before a chain of CHECKSIGADD ops
   - ✅ Push `b''` (0) as initial counter when you use ONLY CHECKSIGADD (e.g., 3-op chains)

6. **Not using NUMS point**
   - ❌ Random internal key (enables keypath spend)
   - ✅ NUMS point (script-path only)

7. **Non-minimal integers in Tapscript (BIP-342)**
   - ❌ Pushing locktime as a fixed 4-byte little-endian value when a shorter encoding exists
   - ✅ Use minimal script-number encoding for locktime and all integers (strip leading zeros, set sign bit only if needed). Our builders use encode_script_number(locktime).
   - Why: Non-minimal numbers cause non-mandatory-script-verify-flag failures and make UTXOs unspendable.

8. **Wrong control block parity bit (BIP-341)**
   - ❌ Using internal key parity or hard-coded version
   - ✅ Set LSB of control-block first byte from the tweaked output key’s y-parity; version is 0xc0 OR parity.

9. **Mismatched artifacts between funding and spending**
   - ❌ Regenerating script/control block with different rules than were used at funding time
   - ✅ Persist script_hex, control_block, output_script, and output_key; spend using the exact funded artifacts.

---

## 📚 Key References

- **BIP-340:** Schnorr Signatures
- **BIP-341:** Taproot
- **BIP-342:** Tapscript (includes OP_CHECKSIGADD)
- **Electrum:** `bitcoin.py`, `ecc.py`, `transaction.py`

---

## ✅ Checklist for Each Example

- [ ] Create script builder in `script_builders/taproot/`
- [ ] Use x-only pubkeys (32 bytes)
- [ ] Use NUMS point as internal key
- [ ] Generate bech32m address
- [ ] Create sweeper in `sweepers/taproot/`
- [ ] Use Schnorr signatures
- [ ] Include control block in witness
- [ ] Add test function in `test_e2e_full.py`
- [ ] Test: create → fund → sweep
- [ ] Verify test status = SWEPT

**See `TAPROOT_IMPLEMENTATION_PLAN.md` for complete details.**
