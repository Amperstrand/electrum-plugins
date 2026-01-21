# Miniscript Visualizer Architecture - Separated Design

## Proposed Architecture

Instead of having the visualizer parse Miniscript directly, we split it into two components:

1. **Miniscript Compiler/Converter** → Produces normalized JSON AST
2. **Visualizer** → Consumes JSON AST and renders it

This separation provides:
- **Cleaner architecture**: Each component has a single responsibility
- **Easier testing**: Can test compiler and visualizer independently
- **Reusability**: The JSON AST can be used by other tools
- **Validation**: Can use existing Miniscript analyzers (like bitcoin.sipa.be) to validate before conversion
- **Language independence**: The visualizer can be in any language (JS, Python, etc.) as long as it consumes the JSON format

## Component 1: Miniscript Compiler/Converter

### Input
```json
{
  "miniscript": "or_i(pk(Alice), and_v(after(800000), pk(Bob)))",
  "params": {
    "Alice": "02abc123...",
    "Bob": "03def456..."
  },
  "keyLabels": {
    "02abc123...": "Alice (Party A)",
    "03def456...": "Bob (Party B)"
  },
  "context": "p2wsh"  // or "tapscript"
}
```

### Output: Normalized Visualization AST (JSON)
```json
{
  "rootId": "node_0",
  "nodes": {
    "node_0": {
      "id": "node_0",
      "type": "or",
      "label": "OR",
      "miniscript": "or_i(pk(Alice), and_v(after(800000), pk(Bob)))",
      "children": ["node_1", "node_2"],
      "params": {}
    },
    "node_1": {
      "id": "node_1",
      "type": "signature",
      "label": "Signature: Alice (Party A)",
      "miniscript": "pk(Alice)",
      "children": [],
      "params": {
        "pubkey": "02abc123...",
        "pubkeyLabel": "Alice (Party A)"
      }
    },
    "node_2": {
      "id": "node_2",
      "type": "and",
      "label": "AND",
      "miniscript": "and_v(after(800000), pk(Bob))",
      "children": ["node_3", "node_4"],
      "params": {}
    },
    "node_3": {
      "id": "node_3",
      "type": "timelock_absolute",
      "label": "After block 800000",
      "miniscript": "after(800000)",
      "children": [],
      "params": {
        "lockType": "absolute",
        "value": 800000,
        "unit": "height"
      }
    },
    "node_4": {
      "id": "node_4",
      "type": "signature",
      "label": "Signature: Bob (Party B)",
      "miniscript": "pk(Bob)",
      "children": [],
      "params": {
        "pubkey": "03def456...",
        "pubkeyLabel": "Bob (Party B)"
      }
    }
  },
  "metadata": {
    "scriptType": "P2WSH",
    "address": "bc1q...",  // optional
    "compiledScript": "..."  // optional, hex
  }
}
```

### Implementation Options

**Option A: Python Service/API**
- Standalone Python service that exposes an API
- Can use our existing `visualization_ast.py` code
- Returns JSON AST

**Option B: JavaScript Library**
- Pure JS Miniscript parser + converter
- Can run in browser or Node.js
- No backend needed

**Option C: Hybrid**
- Use [bitcoin.sipa.be/miniscript/](https://bitcoin.sipa.be/miniscript/) to validate/analyze
- Our converter takes the validated Miniscript and produces JSON AST
- Visualizer consumes JSON AST

## Component 2: Visualizer

### Input: JSON AST (from Component 1)

The visualizer is now **much simpler**:
- No Miniscript parsing needed
- Just render the tree structure
- Implement simulator evaluation
- Handle UI interactions

### Benefits

1. **Simpler visualizer code**: Just tree rendering + simulation
2. **Language agnostic**: Visualizer can be React, Vue, vanilla JS, etc.
3. **Easy to test**: Can test with static JSON files
4. **Reusable**: Same JSON format can power other tools

## Workflow

```
┌─────────────────┐
│ Miniscript      │
│ String + Params │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validate with   │
│ bitcoin.sipa.be │  (optional)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Compiler/       │
│ Converter       │──→ JSON AST
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Visualizer      │
│ (Tree +         │
│  Simulator)     │
└─────────────────┘
```

## Updated JavaScript Prompt

With this architecture, the JavaScript implementation becomes:

1. **Option 1**: Pure frontend
   - Use a JS Miniscript parser library (or implement simple one)
   - Convert to JSON AST
   - Visualize JSON AST

2. **Option 2**: Backend + Frontend
   - Backend: Python service that converts Miniscript → JSON AST
   - Frontend: Pure visualizer that consumes JSON AST
   - Frontend makes API call to backend

3. **Option 3**: Hybrid
   - Use bitcoin.sipa.be API (if available) or embed their analyzer
   - Our converter produces JSON AST
   - Visualizer consumes JSON AST

## Recommendation

**For the JavaScript implementation**, I'd recommend:

1. **Start with Option 1** (pure frontend):
   - Implement a simple Miniscript parser in JS
   - Convert to JSON AST
   - Visualize JSON AST
   - This makes it fully standalone

2. **Later, add Option 2** (backend):
   - Python service for more complex parsing
   - Can use our existing Python code
   - Frontend calls backend API

This gives you:
- ✅ Standalone JS version (no backend needed)
- ✅ Can later add Python backend for advanced features
- ✅ Same JSON format works for both
- ✅ Can validate with bitcoin.sipa.be before conversion

## JSON Schema

We should define a formal JSON schema for the AST format. This makes it:
- Easy to validate
- Self-documenting
- Language-independent
- Easy to generate from any language

Would you like me to:
1. Create a JSON schema definition?
2. Update the JavaScript prompt to use this separated architecture?
3. Create a Python API service that converts Miniscript → JSON AST?










