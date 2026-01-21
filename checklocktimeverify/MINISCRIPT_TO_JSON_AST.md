# Miniscript to JSON AST Converter

## Overview

We already have the code to convert Miniscript → JSON AST! It's in our Python codebase. We just need to expose it as an API or service.

## Our Existing Implementation

### What We Have

1. **Miniscript Parser**: `cltv_lib/miniscript/compiler.py`
   - `_parse_expr()` - parses Miniscript string into internal AST
   - Handles all Miniscript fragments (pk, multi, after, older, and_v, or_i, etc.)

2. **Visualization AST Converter**: `cltv_lib/miniscript/visualization_ast.py`
   - `create_visualization_ast()` - converts parsed node to VisualizationNode tree
   - Generates human-readable labels
   - Extracts parameters (pubkeys, locktimes, etc.)

3. **Usage in Visualizer**: `dialogs/miniscript_visualizer.py`
   - Already uses both components together
   - Line 164: `parse_miniscript_expr(miniscript, params)`
   - Line 167: `create_visualization_ast(miniscript_node, key_labels=...)`

### The Flow

```python
# 1. Parse Miniscript string
from cltv_lib.miniscript.compiler import _parse_expr as parse_miniscript_expr
miniscript_node = parse_miniscript_expr("or_i(pk(Alice), and_v(after(800000), pk(Bob)))", params)

# 2. Convert to Visualization AST
from cltv_lib.miniscript.visualization_ast import create_visualization_ast
viz_root, nodes_by_id, _ = create_visualization_ast(miniscript_node, key_labels=key_labels)

# 3. Serialize to JSON (we need to add this)
json_ast = serialize_to_json(viz_root, nodes_by_id)
```

## Options for Implementation

### Option 1: Use Our Python Code (Recommended)

**Pros:**
- ✅ We already have it working
- ✅ Handles all our contract types
- ✅ Generates the exact JSON format we need
- ✅ No external dependencies

**Implementation:**
Create a Python service/API that:
1. Accepts Miniscript string + params
2. Parses using our existing code
3. Converts to Visualization AST
4. Serializes to JSON
5. Returns JSON AST

**Code Structure:**
```python
# miniscript_to_json_ast.py
from cltv_lib.miniscript.compiler import _parse_expr as parse_miniscript_expr
from cltv_lib.miniscript.visualization_ast import create_visualization_ast, VisualizationNode, NodeType
import json

def miniscript_to_json_ast(miniscript: str, params: dict, key_labels: dict = None) -> dict:
    """
    Convert Miniscript string to JSON AST.
    
    Args:
        miniscript: Miniscript expression string
        params: Parameter dict (pubkeys, locktimes, etc.)
        key_labels: Optional mapping of pubkey bytes -> human labels
    
    Returns:
        JSON AST in the format expected by the visualizer
    """
    # Parse
    miniscript_node = parse_miniscript_expr(miniscript, params)
    
    # Convert to visualization AST
    viz_root, nodes_by_id, _ = create_visualization_ast(
        miniscript_node,
        key_labels=key_labels or {}
    )
    
    # Serialize to JSON
    return serialize_viz_ast_to_json(viz_root, nodes_by_id)

def serialize_viz_ast_to_json(viz_root: VisualizationNode, nodes_by_id: dict) -> dict:
    """Serialize VisualizationNode tree to JSON."""
    # Convert nodes_by_id to JSON-serializable format
    nodes_dict = {}
    for node_id, node in nodes_by_id.items():
        nodes_dict[node_id] = {
            "id": node.id,
            "type": node.type.value,  # Convert enum to string
            "label": node.label,
            "miniscript": node.miniscript,
            "children": node.children,
            "params": serialize_params(node.params)  # Handle bytes, etc.
        }
    
    return {
        "rootId": viz_root.id,
        "nodes": nodes_dict
    }

def serialize_params(params: dict) -> dict:
    """Convert params to JSON-serializable format."""
    result = {}
    for key, value in params.items():
        if isinstance(value, bytes):
            result[key] = value.hex()
        elif isinstance(value, list):
            result[key] = [v.hex() if isinstance(v, bytes) else v for v in value]
        else:
            result[key] = value
    return result
```

### Option 2: Use bitcoinerlab/miniscript

**Pros:**
- ✅ JavaScript library (can run in browser)
- ✅ Well-tested
- ✅ Has satisfier functionality

**Cons:**
- ❌ Doesn't have visualization AST export
- ❌ Would need to write converter from their AST to our JSON format
- ❌ Different API than our Python code

**What it provides:**
- `compileMiniscript(miniscript)` → Bitcoin Script ASM
- `satisfier(miniscript)` → Witness solutions
- But **not** a visualization AST

**Would need:**
- Parse their internal AST structure
- Convert to our VisualizationNode format
- More work than using our existing code

### Option 3: Use Bitcoin Core

**Pros:**
- ✅ Reference implementation
- ✅ Most complete

**Cons:**
- ❌ C++ code (would need bindings)
- ❌ No visualization AST export
- ❌ Overkill for our needs
- ❌ Would need to write converter

### Option 4: Use bitcoin.sipa.be API

**What it provides:**
- Validation and analysis
- Policy → Miniscript compilation
- Miniscript analysis

**What it doesn't provide:**
- JSON AST export
- Visualization format

**Could use it for:**
- Validation before conversion
- Error checking

## Recommendation

**Use Option 1: Our Python Code**

1. **Create a Python API service** that exposes `miniscript_to_json_ast()`
2. **Add JSON serialization** for VisualizationNode
3. **Optionally validate** with bitcoin.sipa.be first (for error checking)
4. **JavaScript visualizer** calls this API

### Implementation Plan

1. **Create `miniscript_to_json_ast.py`**:
   - Function to convert Miniscript → JSON AST
   - Handles serialization (bytes → hex, enums → strings)

2. **Create API endpoint** (Flask/FastAPI):
   ```python
   @app.post("/api/miniscript-to-ast")
   def convert_miniscript(request):
       miniscript = request.json["miniscript"]
       params = request.json["params"]
       key_labels = request.json.get("keyLabels", {})
       
       # Optional: validate with bitcoin.sipa.be
       # validate_miniscript(miniscript)
       
       # Convert
       json_ast = miniscript_to_json_ast(miniscript, params, key_labels)
       return json_ast
   ```

3. **JavaScript visualizer**:
   - Can accept JSON AST directly (for testing)
   - Or call API to convert Miniscript string

### Why Not Use bitcoinerlab/miniscript?

While [bitcoinerlab/miniscript](https://github.com/bitcoinerlab/miniscript) is a great library, it:
- Focuses on compilation and satisfaction (not visualization)
- Doesn't have a visualization AST format
- Would require writing a converter from their AST to our format
- Our Python code already does exactly what we need

### Why Not Use Bitcoin Core?

Bitcoin Core's Miniscript implementation:
- Is in C++ (would need bindings)
- Focuses on validation and compilation
- Doesn't have visualization AST export
- Is overkill for our needs

## Summary

**Best approach**: Use our existing Python code!

1. ✅ We already have the parser and converter
2. ✅ It generates the exact format we need
3. ✅ Just need to add JSON serialization
4. ✅ Can expose as API for JavaScript visualizer
5. ✅ Can optionally validate with bitcoin.sipa.be first

The "special compiler" is just our existing `create_visualization_ast()` function - it's already a Miniscript-to-visualization-AST compiler!

## Implementation

I've created `miniscript_to_json_ast_service.py` which provides:

```python
from miniscript_to_json_ast_service import miniscript_to_json_ast

# Convert Miniscript to JSON AST
json_ast = miniscript_to_json_ast(
    miniscript="or_i(pk(Alice), pk(Bob))",
    params={"Alice": "02abc...", "Bob": "03def..."},
    key_labels={"02abc...": "Alice", "03def...": "Bob"}
)

# Returns JSON-ready dict that can be sent to JavaScript visualizer
```

### Comparison with Other Tools

| Tool | Purpose | Has Visualization AST? | Our Use Case |
|------|---------|----------------------|--------------|
| **Our Python Code** | Parse + Convert to Visualization AST | ✅ Yes | **Perfect fit** |
| [bitcoinerlab/miniscript](https://github.com/bitcoinerlab/miniscript) | Compile + Satisfier | ❌ No | Would need converter |
| Bitcoin Core | Validation + Compilation | ❌ No | Overkill, C++ bindings needed |
| bitcoin.sipa.be | Validation + Analysis | ❌ No | Good for validation only |

### Why Our Code is Best

1. **Already exists**: We have `parse_miniscript_expr()` and `create_visualization_ast()`
2. **Exact format**: Generates the JSON structure the visualizer expects
3. **No conversion needed**: Direct path from Miniscript → JSON AST
4. **Python**: Easy to expose as API (Flask/FastAPI)
5. **Tested**: Already used in our Electrum plugin visualizer

### Next Steps

1. **Test the service**: Run `python miniscript_to_json_ast_service.py` to see examples
2. **Create API endpoint**: Wrap in Flask/FastAPI for JavaScript to call
3. **Optional validation**: Add bitcoin.sipa.be validation before conversion
4. **JavaScript visualizer**: Consumes JSON AST (can test with static files first)

