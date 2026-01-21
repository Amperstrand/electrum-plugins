# JavaScript Miniscript Visualizer & Simulator - Implementation Prompt

## Overview

You are building a JavaScript web application that visualizes and simulates Bitcoin Miniscript spending policies. This tool helps users understand complex Bitcoin scripts by showing them as interactive tree structures and allowing them to simulate spending conditions.

## Architecture: Two-Component Design

This implementation uses a **separated architecture**:

1. **Miniscript Compiler/Converter**: Parses Miniscript string → produces normalized JSON AST
2. **Visualizer**: Consumes JSON AST → renders tree + simulator

This separation makes the code cleaner, easier to test, and allows the visualizer to work with any language that produces the JSON format.

### Why Separate?

- **Validation**: Can use [bitcoin.sipa.be/miniscript/](https://bitcoin.sipa.be/miniscript/) to validate Miniscript before conversion
- **Reusability**: The JSON AST can be used by other tools
- **Simplicity**: Visualizer doesn't need to parse Miniscript, just render JSON
- **Testing**: Can test compiler and visualizer independently

## Core Concepts

### What is Miniscript?

Miniscript is a language for writing Bitcoin scripts in a structured, analyzable way. It uses fragments like:
- `pk(key)` - requires signature from key
- `multi(k, key1, key2, ...)` - requires k-of-n signatures
- `after(locktime)` - requires block height >= locktime
- `older(blocks)` - requires N blocks after confirmation
- `hash160(hash)` - requires preimage that hashes to hash
- `and_v(X, Y)` - both X and Y must be satisfied
- `or_i(X, Y)` - either X or Y must be satisfied
- `thresh(k, X, Y, Z, ...)` - at least k of the conditions must be satisfied

### What You're Building

A single-page web application with:
1. **Tree Visualization**: Shows the Miniscript policy as an interactive tree
2. **Simulator**: Allows users to test if a script is spendable under different conditions
3. **Details Panel**: Shows information about selected nodes

## Input Format

Your application can accept Miniscript in two ways:

### Option 1: Direct Miniscript Input (Full Implementation)
```javascript
{
  miniscript: "or_i(pk(Alice), and_v(after(800000), pk(Bob)))",
  params: {
    "Alice": "02abc123...",  // Pubkey hex string
    "Bob": "03def456...",     // Pubkey hex string
  },
  keyLabels: {  // Optional: human-readable labels
    "02abc123...": "Alice (Party A)",
    "03def456...": "Bob (Party B)"
  }
}
```

### Option 2: Pre-compiled JSON AST (Simpler Visualizer)
```javascript
{
  rootId: "node_0",
  nodes: {
    "node_0": { /* ... */ },
    "node_1": { /* ... */ },
    // ... more nodes
  },
  metadata: {
    scriptType: "P2WSH",
    address: "bc1q...",  // optional
    compiledScript: "..."  // optional
  }
}
```

**Recommendation**: Start with Option 2 (JSON AST input) for the visualizer. You can add Option 1 later by implementing a Miniscript parser, or by calling a backend API that converts Miniscript → JSON AST.

## Data Model: Visualization AST

You need to convert the Miniscript string into a normalized AST (Abstract Syntax Tree) for visualization. Each node in the tree has this structure:

```typescript
interface VisualizationNode {
  id: string;                    // Unique identifier (e.g., "node_0", "node_1")
  type: NodeType;                 // See NodeType enum below
  label: string | null;            // Human-readable label for UI
  miniscript: string | null;       // Miniscript fragment (for tooltip)
  children: string[];             // Array of child node IDs
  params: Record<string, any>;    // Type-specific data (see below)
  
  // UI state (set during simulation)
  satisfied?: boolean | null;     // True if this node is satisfied
  relevant?: boolean | null;       // True if this node is relevant to current path
  satisfactionPath?: string | null; // Which child path satisfies this (for OR nodes)
}

enum NodeType {
  // Combinators
  AND = "and",
  OR = "or",
  THRESH = "thresh",
  ANDOR = "andor",  // IF-THEN-ELSE
  
  // Leaf nodes
  SIGNATURE = "signature",
  MULTISIG = "multisig",
  TIMELOCK_ABSOLUTE = "timelock_absolute",
  TIMELOCK_RELATIVE = "timelock_relative",
  HASHLOCK = "hashlock",
  CONSTANT_TRUE = "constant_true",
  CONSTANT_FALSE = "constant_false"
}
```

### Node Type-Specific Parameters

Different node types have different `params`:

**SIGNATURE:**
```javascript
{
  pubkey: "02abc123...",           // Pubkey hex string
  pubkeyLabel: "Alice (Party A)"   // Human-readable label
}
```

**MULTISIG:**
```javascript
{
  k: 2,                            // Required signatures
  n: 3,                            // Total keys
  keys: ["02abc...", "03def...", "02ghi..."],  // Array of pubkey hex strings
  keyLabels: ["Alice", "Bob", "Carol"]  // Human-readable labels
}
```

**TIMELOCK_ABSOLUTE:**
```javascript
{
  lockType: "absolute",
  value: 800000,                   // Block height
  unit: "height"
}
```

**TIMELOCK_RELATIVE:**
```javascript
{
  lockType: "relative",
  value: 144,                      // Number of blocks
  unit: "blocks"
}
```

**HASHLOCK:**
```javascript
{
  hashType: "hash160",
  hash: "abcd1234..."              // Hash hex string
}
```

**THRESH:**
```javascript
{
  k: 2                             // At least k children must be satisfied
}
```

## Component 1: Miniscript Compiler/Converter (Optional)

If you want to accept Miniscript strings directly, you need to parse and convert them to JSON AST.

### Option A: Use Existing Parser
- Use a JavaScript Miniscript parser library if available
- Or call a backend API that does the conversion

### Option B: Simple Parser (For Common Cases)
For a simple implementation, you can write a basic recursive descent parser that handles:
- `pk(key)` → SIGNATURE node
- `multi(k, key1, ...)` → MULTISIG node
- `after(n)` → TIMELOCK_ABSOLUTE node
- `older(n)` → TIMELOCK_RELATIVE node
- `and_v(X, Y)` → AND node
- `or_i(X, Y)` → OR node
- `thresh(k, X, Y, ...)` → THRESH node

### Option C: Validate First
Before parsing, you can validate the Miniscript using [bitcoin.sipa.be/miniscript/](https://bitcoin.sipa.be/miniscript/) to ensure it's valid.

### Conversion Algorithm
1. **Parse the Miniscript expression** into an AST
2. **Convert each node** to a VisualizationNode:
   - Generate unique IDs (e.g., "node_0", "node_1", ...)
   - Determine the NodeType based on the fragment
   - Extract parameters (pubkeys, locktimes, etc.)
   - Recursively convert children
   - Generate human-readable labels
3. **Output JSON AST** in the format specified below

### JSON AST Format

The compiler/converter should output a normalized JSON AST in this format:

```javascript
{
  rootId: "node_0",  // ID of the root node
  nodes: {  // Map of all nodes by ID
    "node_0": {
      id: "node_0",
      type: "or",  // NodeType enum value
      label: "OR",  // Human-readable label
      miniscript: "or_i(pk(Alice), and_v(after(800000), pk(Bob)))",  // Miniscript fragment
      children: ["node_1", "node_2"],  // Array of child node IDs
      params: {}  // Type-specific parameters (see below)
    },
    "node_1": {
      id: "node_1",
      type: "signature",
      label: "Signature: Alice (Party A)",
      miniscript: "pk(Alice)",
      children: [],
      params: {
        pubkey: "02abc123...",
        pubkeyLabel: "Alice (Party A)"
      }
    },
    "node_2": {
      id: "node_2",
      type: "and",
      label: "AND",
      miniscript: "and_v(after(800000), pk(Bob))",
      children: ["node_3", "node_4"],
      params: {}
    },
    "node_3": {
      id: "node_3",
      type: "timelock_absolute",
      label: "After block 800000",
      miniscript: "after(800000)",
      children: [],
      params: {
        lockType: "absolute",
        value: 800000,
        unit: "height"
      }
    },
    "node_4": {
      id: "node_4",
      type: "signature",
      label: "Signature: Bob (Party B)",
      miniscript: "pk(Bob)",
      children: [],
      params: {
        pubkey: "03def456...",
        pubkeyLabel: "Bob (Party B)"
      }
    }
  },
  metadata: {  // Optional metadata
    scriptType: "P2WSH",  // or "P2TR"
    address: "bc1q...",  // Optional: derived address
    compiledScript: "..."  // Optional: compiled Bitcoin Script (hex)
  }
}
```

**Note**: The visualizer should work with this JSON format directly. You can start by hardcoding example JSON ASTs for testing, then add the compiler later.

## UI Layout

Create a responsive web page with this layout:

```
┌─────────────────────────────────────────────────────────────┐
│  Miniscript Spending Policy                                  │
│  [Badge: P2WSH or P2TR]                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────┐  ┌─────────────────────────────┐ │
│  │                      │  │  [Tabs: Details | Simulator] │ │
│  │  Policy Structure    │  │                             │ │
│  │  (Tree View)         │  │  [Tab Content]              │ │
│  │                      │  │                             │ │
│  │  📜 OR               │  │                             │ │
│  │   ├─ 🔑 Signature:   │  │                             │ │
│  │   │   Alice          │  │                             │ │
│  │   └─ 📦 AND          │  │                             │ │
│  │      ├─ ⏰ After     │  │                             │ │
│  │      │   block 800k  │  │                             │ │
│  │      └─ 🔑 Signature:│  │                             │ │
│  │          Bob         │  │                             │ │
│  │                      │  │                             │ │
│  └──────────────────────┘  └─────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Left Panel: Policy Tree

- Use a tree widget (e.g., a collapsible HTML tree, or a library like `react-tree-view`)
- Show each node with:
  - An icon based on type (🔑 for signature, ⏰ for timelock, 📦 for combinators)
  - The node's label
  - Color coding:
    - **Green**: Node is satisfied and relevant
    - **Red**: Node is required but not satisfied
    - **Gray**: Node is not relevant to current path
    - **Default**: No simulation state yet
- Make nodes expandable/collapsible
- Show tooltip with Miniscript fragment on hover

### Right Panel: Tabs

#### Details Tab
- Shows information about the currently selected node:
  - Type
  - Label
  - Miniscript fragment
  - Parameters (formatted JSON)
  - Plain language explanation

#### Simulator Tab
- **Inputs:**
  - Current block height (number input)
  - Confirmation height (number input, optional, for relative timelocks)
  - Available signatures (checkboxes, one per pubkey found in the script)
  - Hash preimages (text inputs, one per hash lock)
- **Output:**
  - Status message: "✅ Spendable via path X" or "❌ Not yet spendable"
  - The tree view updates with color coding based on satisfaction

## Simulation Algorithm

The simulator evaluates whether the script is spendable given the current state. Here's the recursive evaluation function:

```javascript
function evaluateSatisfaction(node, nodesById, simulatorState) {
  const {
    availableSignatures,  // Set of pubkey hex strings
    currentHeight,        // Current block height
    confirmationHeight,  // Optional: confirmation height for relative timelocks
    availablePreimages   // Map: hash -> preimage hex
  } = simulatorState;
  
  switch (node.type) {
    case "and":
      // All children must be satisfied
      for (const childId of node.children) {
        const child = nodesById[childId];
        if (!evaluateSatisfaction(child, nodesById, simulatorState)) {
          node.satisfied = false;
          return false;
        }
      }
      node.satisfied = true;
      return true;
      
    case "or":
      // At least one child must be satisfied
      for (const childId of node.children) {
        const child = nodesById[childId];
        if (evaluateSatisfaction(child, nodesById, simulatorState)) {
          node.satisfied = true;
          node.satisfactionPath = childId;  // Track which path was taken
          return true;
        }
      }
      node.satisfied = false;
      return false;
      
    case "thresh":
      // At least k children must be satisfied
      const k = node.params.k;
      let satisfiedCount = 0;
      for (const childId of node.children) {
        const child = nodesById[childId];
        if (evaluateSatisfaction(child, nodesById, simulatorState)) {
          satisfiedCount++;
        }
      }
      node.satisfied = satisfiedCount >= k;
      return node.satisfied;
      
    case "signature":
      // Check if signature is available
      const pubkey = node.params.pubkey;
      node.satisfied = availableSignatures.has(pubkey);
      return node.satisfied;
      
    case "multisig":
      // Check if enough signatures are available
      const requiredK = node.params.k;
      const keys = node.params.keys;
      const availableCount = keys.filter(k => availableSignatures.has(k)).length;
      node.satisfied = availableCount >= requiredK;
      return node.satisfied;
      
    case "timelock_absolute":
      // Check if current height >= locktime
      const locktime = node.params.value;
      node.satisfied = currentHeight >= locktime;
      return node.satisfied;
      
    case "timelock_relative":
      // Check if (currentHeight - confirmationHeight) >= blocks
      const blocks = node.params.value;
      if (confirmationHeight !== null && confirmationHeight !== undefined) {
        node.satisfied = (currentHeight - confirmationHeight) >= blocks;
      } else {
        node.satisfied = false;  // Can't satisfy without confirmation height
      }
      return node.satisfied;
      
    case "hashlock":
      // Check if preimage is available
      const hash = node.params.hash;
      node.satisfied = hash in availablePreimages;
      return node.satisfied;
      
    case "constant_true":
      node.satisfied = true;
      return true;
      
    case "constant_false":
      node.satisfied = false;
      return false;
      
    default:
      node.satisfied = false;
      return false;
  }
}
```

### Marking Relevance

After evaluation, mark which nodes are "relevant" to the satisfied path:

```javascript
function markRelevance(node, nodesById, satisfiedPath) {
  if (node.satisfied) {
    node.relevant = true;
    
    if (node.type === "or" && node.satisfactionPath) {
      // Only the satisfied branch is relevant
      const satisfiedChild = nodesById[node.satisfactionPath];
      if (satisfiedChild) {
        satisfiedChild.relevant = true;
        markRelevance(satisfiedChild, nodesById, satisfiedPath);
      }
    } else if (node.type === "and") {
      // All children are relevant
      for (const childId of node.children) {
        const child = nodesById[childId];
        if (child) {
          child.relevant = true;
          markRelevance(child, nodesById, satisfiedPath);
        }
      }
    }
  } else {
    node.relevant = false;
  }
}
```

## Implementation Steps

### Phase 1: Visualizer (Start Here)

1. **Set up the project**
   - Use React, Vue, or vanilla JavaScript
   - Include a tree visualization library (or build your own)

2. **Build the tree visualization**
   - Accept JSON AST as input (hardcode examples for testing)
   - Render the tree with icons and labels
   - Make it interactive (expand/collapse, selection)
   - Add tooltips with Miniscript fragments

3. **Implement the simulator**
   - Create UI inputs for simulation state
   - Implement evaluation algorithm (works on JSON AST)
   - Update tree colors based on satisfaction
   - Show status message

4. **Add details panel**
   - Show selected node information
   - Format parameters nicely
   - Add plain language explanations

### Phase 2: Compiler/Converter (Optional)

5. **Implement Miniscript parsing** (if you want direct Miniscript input)
   - Parse the Miniscript string into an AST
   - Convert to JSON AST format
   - Generate human-readable labels
   - Or: Call a backend API that does this conversion

6. **Integration**
   - Connect compiler output to visualizer input
   - Add validation using [bitcoin.sipa.be/miniscript/](https://bitcoin.sipa.be/miniscript/) if possible

**Recommendation**: Start with Phase 1 (visualizer only) using hardcoded JSON AST examples. This lets you focus on the UI and simulation logic first. Add Phase 2 (compiler) later.

## Example Miniscript Expressions

Test your implementation with these:

1. **Simple OR:**
   ```
   or_i(pk(Alice), pk(Bob))
   ```

2. **AND with timelock:**
   ```
   and_v(after(800000), pk(Alice))
   ```

3. **Multisig:**
   ```
   multi(2, Alice, Bob, Carol)
   ```

4. **Complex:**
   ```
   or_i(
     pk(Alice),
     and_v(
       after(800000),
       multi(2, Bob, Carol)
     )
   )
   ```

5. **Threshold:**
   ```
   thresh(2, pk(Alice), pk(Bob), pk(Carol))
   ```

## Styling Guidelines

- Use a clean, modern design
- Color coding:
  - Green (#4CAF50): Satisfied and relevant
  - Red (#F44336): Required but not satisfied
  - Gray (#9E9E9E): Not relevant
  - Default: No state
- Icons:
  - 🔑 or 🔐: Signature
  - ⏰ or 🕐: Timelock
  - 📦 or 🔗: Combinator (AND/OR/THRESH)
  - 🔢: Multisig
  - 🔒: Hashlock
- Make it responsive (works on mobile and desktop)

## Deliverables

1. A working web application (HTML + JS, or React/Vue component)
2. It should accept Miniscript input and display the tree
3. The simulator should work correctly for all node types
4. The UI should be intuitive and visually appealing
5. Include example Miniscript expressions for testing

## Notes

- **Start simple**: Begin with the visualizer that accepts JSON AST. Add Miniscript parsing later.
- **Validation**: Consider using [bitcoin.sipa.be/miniscript/](https://bitcoin.sipa.be/miniscript/) to validate Miniscript before conversion
- **You don't need to compile Miniscript to Bitcoin Script** (that's handled elsewhere)
- **Focus on visualization and simulation only**
- **The tree should be read-only** (users can't edit the policy)
- **Support both P2WSH and Taproot contexts** (but you can treat them the same for visualization)

## Example JSON AST Files for Testing

Create example JSON files like `example1.json`, `example2.json` with different Miniscript policies. This lets you test the visualizer without implementing the parser first.

Good luck! This is a powerful tool for understanding Bitcoin spending policies.

