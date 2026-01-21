# Miniscript Visualizer & Simulator - Explanation

## Overview

The Miniscript Visualizer is a tool that helps users understand Bitcoin spending policies by:
1. **Visualizing** the policy structure as an interactive tree
2. **Simulating** whether the script is spendable under different conditions

## Architecture

### 1. Visualization AST (Abstract Syntax Tree)

The visualizer converts a Miniscript expression into a normalized AST optimized for UI display:

```
Miniscript: "or_i(pk(Alice), and_v(after(800000), pk(Bob)))"
         ↓
Visualization AST:
  - OR node (root)
    ├─ SIGNATURE node (Alice)
    └─ AND node
        ├─ TIMELOCK_ABSOLUTE node (block 800000)
        └─ SIGNATURE node (Bob)
```

Each node contains:
- **Type**: What kind of condition (signature, timelock, combinator, etc.)
- **Label**: Human-readable description
- **Miniscript fragment**: The actual Miniscript code for this node
- **Parameters**: Type-specific data (pubkeys, locktimes, etc.)
- **Children**: References to child nodes

### 2. Tree Visualization

The tree is displayed in the left panel:
- **Icons** indicate node types (🔑 signature, ⏰ timelock, 📦 combinator)
- **Labels** show human-readable descriptions
- **Color coding** shows satisfaction state (green=satisfied, red=unsatisfied, gray=irrelevant)
- **Tooltips** show the Miniscript fragment on hover
- **Expandable/collapsible** for navigation

### 3. Simulator

The simulator allows users to test spending conditions:

**Inputs:**
- Current block height
- Confirmation height (for relative timelocks)
- Available signatures (checkboxes per pubkey)
- Hash preimages (for hash locks)

**Algorithm:**
1. Recursively evaluate each node based on simulator state
2. Mark nodes as satisfied/unsatisfied
3. Mark which nodes are "relevant" to the satisfied path
4. Update tree colors accordingly
5. Display status: "✅ Spendable" or "❌ Not yet spendable"

**Evaluation Rules:**
- **AND**: All children must be satisfied
- **OR**: At least one child must be satisfied
- **THRESH(k)**: At least k children must be satisfied
- **SIGNATURE**: Pubkey must be in available signatures
- **MULTISIG(k, keys)**: At least k keys must have signatures
- **TIMELOCK_ABSOLUTE**: current_height >= locktime
- **TIMELOCK_RELATIVE**: (current_height - confirmation_height) >= blocks
- **HASHLOCK**: Preimage must be available

### 4. Details Panel

When a node is selected in the tree, the Details tab shows:
- Node type
- Human-readable label
- Miniscript fragment
- Parameters (formatted)
- Plain language explanation

## Example Flow

1. **User opens visualizer** with Miniscript: `or_i(pk(Alice), and_v(after(800000), pk(Bob)))`
2. **Tree displays** showing OR with two branches
3. **User configures simulator:**
   - Current height: 800001
   - Available signatures: [Bob]
4. **Simulator evaluates:**
   - OR node: Check both branches
   - Left branch (Alice): ❌ No signature
   - Right branch (AND): Check both children
     - Timelock: ✅ 800001 >= 800000
     - Bob signature: ✅ Available
   - Result: ✅ Spendable via right branch
5. **Tree updates** with colors:
   - OR: Green
   - AND: Green
   - Timelock: Green
   - Bob signature: Green
   - Alice signature: Gray (not relevant)

## Key Features

1. **Miniscript-first design**: The policy structure is the primary focus
2. **Interactive simulation**: Test different scenarios in real-time
3. **Visual feedback**: Color coding makes satisfaction state clear
4. **Human-readable**: Labels and explanations make it accessible
5. **Taproot support**: Shows all leaves for multi-leaf Taproot scripts

## Use Cases

- **Understanding complex scripts**: See the structure at a glance
- **Testing spending conditions**: Verify if a script is spendable
- **Debugging**: Identify why a script isn't spendable
- **Education**: Learn how Miniscript policies work










