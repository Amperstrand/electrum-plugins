# Cloudflare Worker: Miniscript to JSON AST Converter

## Goal

Create a Cloudflare Worker that converts Bitcoin Miniscript strings to a normalized JSON AST format for visualization. The worker should:

1. Accept Miniscript string + parameters via HTTP POST
2. Parse the Miniscript using [@bitcoinerlab/miniscript](https://github.com/bitcoinerlab/miniscript)
3. Convert the parsed AST to a visualization-friendly JSON format
4. Return the JSON AST

## Architecture

```
HTTP POST Request
  ↓
Cloudflare Worker
  ↓
@bitcoinerlab/miniscript (parse)
  ↓
Convert to Visualization AST
  ↓
JSON Response
```

## Input Format

The worker should accept POST requests with JSON body:

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

## Output Format

The worker should return JSON AST in this format:

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
    "miniscript": "or_i(pk(Alice), and_v(after(800000), pk(Bob)))",
    "context": "p2wsh"
  }
}
```

## Node Types

The visualization AST uses these node types:

```typescript
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

## Implementation Steps

### Step 1: Set Up Cloudflare Worker Project

1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```

2. Create new Worker project:
   ```bash
   wrangler init miniscript-ast-worker
   cd miniscript-ast-worker
   ```

3. Install dependencies:
   ```bash
   npm install @bitcoinerlab/miniscript
   ```

### Step 2: Understand bitcoinerlab/miniscript API

The library provides:
- `compileMiniscript(miniscript)` - compiles to Bitcoin Script
- `satisfier(miniscript)` - generates witnesses

**Important**: The library doesn't expose its internal AST directly. You'll need to:
1. Parse the Miniscript string yourself (simple recursive descent parser)
2. Or extract AST from the library's internal representation (if accessible)
3. Or use the library's compilation output to reconstruct the AST

**Recommended Approach**: Write a simple Miniscript parser that handles the fragments you need, then convert to visualization AST. The library can be used for validation.

### Step 3: Implement Miniscript Parser

Create a parser that handles common Miniscript fragments:

- `pk(key)` → SIGNATURE node
- `multi(k, key1, ...)` → MULTISIG node
- `after(n)` → TIMELOCK_ABSOLUTE node
- `older(n)` → TIMELOCK_RELATIVE node
- `and_v(X, Y)` → AND node
- `or_i(X, Y)` → OR node
- `thresh(k, X, Y, ...)` → THRESH node
- `andor(X, Y, Z)` → ANDOR node
- `sha256(h)`, `hash160(h)`, etc. → HASHLOCK node
- `1` → CONSTANT_TRUE
- `0` → CONSTANT_FALSE

Handle wrappers: `v:`, `c:`, `s:`, `a:`, `n:`, `d:`

### Step 4: Convert to Visualization AST

For each parsed node:
1. Generate unique ID (e.g., "node_0", "node_1", ...)
2. Determine NodeType
3. Extract parameters (pubkeys, locktimes, etc.)
4. Generate human-readable label
5. Recursively process children
6. Store in nodes dictionary

### Step 5: Create Worker Handler

```typescript
// src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    // Handle CORS
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    // Only accept POST
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    try {
      // Parse request body
      const body = await request.json();
      const { miniscript, params, keyLabels, context } = body;

      // Validate input
      if (!miniscript || !params) {
        return new Response(
          JSON.stringify({ error: 'Missing required fields: miniscript, params' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      // Optional: Validate Miniscript using bitcoinerlab/miniscript
      const { compileMiniscript } = require('@bitcoinerlab/miniscript');
      const { issane } = compileMiniscript(miniscript);
      if (!issane) {
        return new Response(
          JSON.stringify({ error: 'Invalid or non-sane Miniscript' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        );
      }

      // Parse and convert to visualization AST
      const jsonAst = miniscriptToJsonAst(miniscript, params, keyLabels || {}, context || 'p2wsh');

      // Return JSON AST
      return new Response(JSON.stringify(jsonAst), {
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    } catch (error) {
      return new Response(
        JSON.stringify({ error: error.message }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }
  },
};
```

### Step 6: Implement Conversion Function

```typescript
function miniscriptToJsonAst(
  miniscript: string,
  params: Record<string, string | number>,
  keyLabels: Record<string, string>,
  context: string
): {
  rootId: string;
  nodes: Record<string, any>;
  metadata: any;
} {
  // Parse Miniscript string into internal AST
  const parsedNode = parseMiniscript(miniscript, params);
  
  // Convert to visualization AST
  const { rootNode, nodesById } = createVisualizationAst(
    parsedNode,
    keyLabels,
    0  // node counter
  );
  
  // Serialize to JSON format
  return {
    rootId: rootNode.id,
    nodes: serializeNodes(nodesById),
    metadata: {
      scriptType: context === 'tapscript' ? 'P2TR' : 'P2WSH',
      miniscript,
      context,
    },
  };
}
```

## Testing

Test with these examples:

1. **Simple OR:**
   ```json
   {
     "miniscript": "or_i(pk(Alice), pk(Bob))",
     "params": {
       "Alice": "02abc123...",
       "Bob": "03def456..."
     }
   }
   ```

2. **AND with timelock:**
   ```json
   {
     "miniscript": "and_v(after(800000), pk(Alice))",
     "params": {
       "Alice": "02abc123..."
     }
   }
   ```

3. **Multisig:**
   ```json
   {
     "miniscript": "multi(2, Alice, Bob, Carol)",
     "params": {
       "Alice": "02abc123...",
       "Bob": "03def456...",
       "Carol": "02ghi789..."
     }
   }
   ```

## Deployment

1. **Login to Cloudflare:**
   ```bash
   wrangler login
   ```

2. **Deploy:**
   ```bash
   wrangler deploy
   ```

3. **Test:**
   ```bash
   curl -X POST https://your-worker.your-subdomain.workers.dev \
     -H "Content-Type: application/json" \
     -d '{"miniscript": "or_i(pk(Alice), pk(Bob))", "params": {"Alice": "02abc...", "Bob": "03def..."}}'
   ```

## Error Handling

Handle these errors gracefully:
- Invalid Miniscript syntax
- Missing parameters
- Unknown fragments
- Malformed input JSON

Return appropriate HTTP status codes:
- 200: Success
- 400: Bad request (invalid input)
- 500: Server error (parsing/conversion failed)

## Performance Considerations

- Cloudflare Workers have CPU time limits
- Keep parsing logic efficient
- Consider caching common Miniscript patterns
- Minimize memory allocation

## Security

- Validate all inputs
- Sanitize Miniscript strings
- Limit request size
- Rate limiting (Cloudflare handles this)

## Documentation

Include:
- API endpoint URL
- Request/response format
- Example requests
- Error codes
- Rate limits

## Deliverables

1. ✅ Working Cloudflare Worker
2. ✅ Miniscript parser (or integration with bitcoinerlab/miniscript)
3. ✅ Visualization AST converter
4. ✅ JSON serialization
5. ✅ Error handling
6. ✅ CORS support
7. ✅ Example requests/responses
8. ✅ README with usage instructions

## Notes

- **bitcoinerlab/miniscript** is primarily for compilation and satisfaction, not AST export
- You may need to write your own parser or extract AST from the library's internals
- Focus on the fragments you actually need (don't need full Miniscript spec)
- The visualization AST format is simpler than full Miniscript - it's optimized for UI

## Alternative: Use Library for Validation Only

If bitcoinerlab/miniscript doesn't expose AST:
1. Write simple parser for your use case
2. Use library's `compileMiniscript()` to validate
3. Convert your parsed AST to visualization format

This gives you:
- ✅ Validation (library ensures Miniscript is valid)
- ✅ Full control over AST format
- ✅ Simpler implementation

Good luck! This will be a powerful service for Miniscript visualization tools.










