# Miniscript Compiler Comparison

## Overview

This document compares our Python miniscript compiler implementation with Bitcoin Core's C++ implementation and discusses the Rust implementation ecosystem.

## Architecture Comparison

### Our Implementation (Python)

**Location**: `cltv_lib/miniscript/`

**Structure**:
- `compiler.py`: String parsing and compilation entry points
- `fragments.py`: Core fragment compilation logic (ToScript equivalent)
- `node.py`: AST node representation and compilation

**Key Characteristics**:
1. **Simple recursive descent parser** (`_parse_expr`, `_parse_main_expr`)
   - Handles wrappers (`v:`, `c:`, `s:`, `a:`, `n:`) by stripping prefixes
   - Parses fragments by pattern matching function names
   - Supports parameter substitution from a `params` dict

2. **Direct compilation** (`Node.compile()`)
   - Recursively compiles child nodes
   - Applies wrappers in reverse order (innermost first)
   - Tracks `has_checkmultisig` metadata at AST level

3. **Fragment compilation** (`compile_fragment()`)
   - Direct switch statement mapping fragments to script opcodes
   - Context-aware (P2WSH vs TAPSCRIPT)
   - Uses Electrum's `construct_script()` helper

### Bitcoin Core Implementation (C++)

**Location**: `src/script/miniscript.h` and `src/script/miniscript.cpp`

**Structure**:
- `Node<Key>`: Template-based AST node
- `Fragment` enum: All miniscript fragment types
- `Type` system: Rich type system with properties (B, V, K, W, z, o, n, d, u, e, f, s, m, x, g, h, i, j, k)
- `Parse()`: State machine-based parser
- `ToScript()`: TreeEval algorithm for compilation

**Key Characteristics**:

1. **State machine parser** (`Parse()`)
   - Uses `ParseContext` enum and a stack-based parsing approach
   - Tracks script size during parsing to prevent oversized scripts
   - More robust handling of nested expressions and edge cases
   - Supports full miniscript grammar with all fragments

2. **TreeEval algorithm** (`ToScript()`)
   - Non-recursive tree traversal to avoid stack overflow
   - State propagation: tracks whether nodes are followed by `OP_VERIFY`
   - Optimizes `WRAP_V` by converting last opcode to `-VERIFY` form when possible
   - More sophisticated than simple recursive compilation

3. **Rich type system** (`Type`, `CalcType()`)
   - Tracks fragment properties (Base, Verify, Key, Wrapped)
   - Validates type compatibility during construction
   - Enables static analysis of script properties
   - Our implementation doesn't have this - we only track `has_checkmultisig`

4. **FromScript() support**
   - Can parse compiled Bitcoin Script back into miniscript AST
   - Uses pattern matching on opcodes
   - Our implementation has a stub `from_script()` but it's not used

## Detailed Comparison

### Parsing

| Feature | Our Implementation | Bitcoin Core |
|---------|-------------------|--------------|
| **Parser Type** | Recursive descent | State machine with stack |
| **Wrapper Handling** | Strips prefixes, applies in reverse | Integrated into parse state |
| **Parameter Resolution** | Dictionary lookup with fallbacks | Context object (`Ctx`) |
| **Error Handling** | Raises `ParseError` | Returns `std::optional<NodeRef>` |
| **Size Tracking** | None | Tracks script size during parse |
| **Grammar Coverage** | Subset (11 fragments) | Full miniscript grammar |

**Our Parser Example**:
```python
def _parse_expr(expr: str, params: Dict[str, Any]) -> Node:
    # Strip wrappers: "v:c:pk(alice)" -> wrappers=['v','c'], expr="pk(alice)"
    wrappers = []
    while expr.startswith(('v:', 'c:', 's:', 'a:', 'n:')):
        # ... extract wrapper ...
    
    # Parse main expression
    node = _parse_main_expr(expr, params)
    
    # Apply wrappers (innermost first)
    for wrapper in reversed(wrappers):
        node = apply_wrapper(wrapper, node)
```

**Bitcoin Core Parser**:
```cpp
// Uses ParseContext stack and state machine
std::vector<std::tuple<ParseContext, int64_t, int64_t>> to_parse;
to_parse.emplace_back(ParseContext::WRAPPED_EXPR, -1, -1);

while (!to_parse.empty()) {
    auto [cur_context, n, k] = to_parse.back();
    to_parse.pop_back();
    
    switch (cur_context) {
        case ParseContext::WRAPPED_EXPR:
            // Handle wrappers by pushing new contexts
        case ParseContext::EXPR:
            // Parse fragments
    }
}
```

### Compilation

| Feature | Our Implementation | Bitcoin Core |
|---------|-------------------|--------------|
| **Algorithm** | Recursive compilation | TreeEval (non-recursive) |
| **State Tracking** | None | Tracks "followed-by-VERIFY" state |
| **Optimization** | None | Converts opcodes to -VERIFY form |
| **Metadata** | `has_checkmultisig` only | Full type system with properties |
| **Context Handling** | `MiniscriptContext` enum | Template-based `Ctx` object |

**Our Compilation**:
```python
def compile_with_metadata(self, context: MiniscriptContext) -> CompiledScript:
    # Recursively compile children
    compiled_subs = [sub.compile_with_metadata(context) for sub in self.subs]
    
    # Compile this node
    result = compile_fragment(self.fragment, context, subs=compiled_subs, ...)
    
    # Apply wrappers
    for wrapper in reversed(self.wrappers):
        result = apply_wrapper(wrapper, result)
    
    return CompiledScript(script=result, has_checkmultisig=has_checkmultisig)
```

**Bitcoin Core Compilation**:
```cpp
CScript ToScript(const Ctx& ctx) const {
    // TreeEval: non-recursive tree traversal
    auto downfn = [](bool verify, const Node& node, size_t index) {
        // Propagate "followed-by-VERIFY" state down the tree
        if (node.fragment == Fragment::WRAP_V) return true;
        // ...
    };
    
    auto upfn = [&ctx](bool verify, const Node& node, std::span<CScript> subs) -> CScript {
        // Compile node, using verify state to optimize opcodes
        switch (node.fragment) {
            case Fragment::WRAP_C:
                return BuildScript(subs[0], verify ? OP_CHECKSIGVERIFY : OP_CHECKSIG);
            // ...
        }
    };
    
    return TreeEval<CScript>(false, downfn, upfn);
}
```

### Fragment Support

| Fragment | Our Implementation | Bitcoin Core | Notes |
|----------|-------------------|--------------|-------|
| `pk_k` | ✅ | ✅ | Public key |
| `after` | ✅ | ✅ | CLTV (absolute timelock) |
| `after_drop` | ✅ | ❌ | Our extension (BIP-65 style with DROP) |
| `older` | ✅ | ✅ | CSV (relative timelock) |
| `older_drop` | ✅ | ❌ | Our extension (CSV with DROP) |
| `hash160` | ✅ | ✅ | Standard (with size check) |
| `hash160_simple` | ✅ | ❌ | Our extension (no size check) |
| `and_v` | ✅ | ✅ | Sequential AND |
| `and_b` | ✅ | ✅ | AND with BOOLAND |
| `or_i` | ✅ | ✅ | IF/ELSE OR |
| `or_b` | ✅ | ✅ | BOOLOR |
| `or_d` | ✅ | ✅ | IFDUP NOTIF |
| `or_c` | ✅ | ✅ | NOTIF |
| `andor` | ✅ | ✅ | If-then-else |
| `multi` | ✅ | ✅ | P2WSH multisig |
| `multi_a` | ✅ | ✅ | Tapscript multisig |
| `thresh` | ✅ | ✅ | Threshold |
| `pk_h` | ❌ | ✅ | Hash-based pubkey |
| `sha256` | ❌ | ✅ | SHA256 hash |
| `hash256` | ❌ | ✅ | HASH256 hash |
| `ripemd160` | ❌ | ✅ | RIPEMD160 hash |
| `wrap_d` | ❌ | ✅ | DUP IF wrapper |
| `wrap_j` | ❌ | ✅ | SIZE 0NOTEQUAL IF wrapper |

**Our Extensions**:
- `after_drop`: BIP-65 style CLTV with DROP (matches our existing scripts)
- `older_drop`: CSV with DROP (for consistency)
- `hash160_simple`: Hash without size check (matches our data publishing scripts)

### Type System

**Bitcoin Core**:
- Rich type system with 19 properties
- Validates type compatibility
- Enables static analysis
- Tracks timelock information (g, h, i, j, k properties)

**Our Implementation**:
- Minimal: only tracks `has_checkmultisig`
- No type validation
- No static analysis
- Sufficient for our use case (known contracts)

### Context Handling

**Our Implementation**:
```python
class MiniscriptContext(Enum):
    P2WSH = "p2wsh"
    TAPSCRIPT = "tapscript"

def _context_key(key: bytes, context: MiniscriptContext) -> bytes:
    if context == MiniscriptContext.TAPSCRIPT:
        return _to_xonly(key)  # 32 bytes
    else:
        return key  # 33 bytes compressed
```

**Bitcoin Core**:
```cpp
enum class MiniscriptContext {
    P2WSH,
    TAPSCRIPT,
};

template<typename Ctx>
CScript ToScript(const Ctx& ctx) const {
    // ctx.ToPKBytes(key) handles key format conversion
    // ctx.MsContext() returns the context
}
```

Both implementations handle context correctly, but Bitcoin Core uses templates for more flexibility.

## Rust Implementation

The Rust miniscript ecosystem is primarily maintained by the `rust-miniscript` crate (https://github.com/rust-bitcoin/rust-miniscript).

**Key Characteristics**:
1. **Full miniscript support**: Implements the complete miniscript grammar
2. **Type system**: Similar to Bitcoin Core's type system
3. **Policy language**: High-level policy → miniscript compilation
4. **Descriptor support**: Integration with output descriptors
5. **Widely used**: Used by many Rust Bitcoin projects

**Comparison with Our Implementation**:
- **More complete**: Supports all miniscript fragments
- **Type system**: Rich type checking like Bitcoin Core
- **Policy compilation**: Can compile high-level policies to miniscript
- **Our advantage**: Simpler, focused on our specific use case

## Strengths and Weaknesses

### Our Implementation

**Strengths**:
1. **Simplicity**: Easy to understand and modify
2. **Focused**: Only implements what we need
3. **Python**: Integrates well with Electrum
4. **Extensions**: Supports our custom fragments (`after_drop`, `hash160_simple`)
5. **Sufficient**: Works perfectly for our 5 contract types

**Weaknesses**:
1. **Limited grammar**: Only 11 fragments vs full miniscript
2. **No type system**: Can't validate script properties statically
3. **Simple parser**: May not handle all edge cases
4. **No policy language**: Can't compile high-level policies
5. **Recursive compilation**: Could stack overflow on very deep trees (unlikely in practice)

### Bitcoin Core Implementation

**Strengths**:
1. **Complete**: Full miniscript grammar support
2. **Robust**: State machine parser handles all edge cases
3. **Type system**: Rich type checking and validation
4. **Optimized**: TreeEval avoids stack overflow
5. **FromScript**: Can parse scripts back to miniscript
6. **Well-tested**: Extensive test suite

**Weaknesses**:
1. **Complexity**: Much more code, harder to understand
2. **C++**: More verbose than Python
3. **Overkill**: For our use case, it's more than we need

## Use Case Fit

**Our Implementation is Perfect For**:
- CLTV plugin with 5 known contract types
- Simple, maintainable codebase
- Python/Electrum integration
- Custom fragments matching our existing scripts

**Bitcoin Core's Implementation is Better For**:
- Full miniscript support
- Policy language compilation
- Static analysis and validation
- Parsing arbitrary miniscript scripts
- Production wallet software

## Conclusion

Our miniscript compiler is a **focused, simplified implementation** that perfectly serves our needs. While Bitcoin Core's implementation is more complete and robust, it's also significantly more complex. For our use case (5 known contract types in an Electrum plugin), our implementation strikes the right balance between functionality and simplicity.

**Key Takeaways**:
1. Our parser is simpler but sufficient for our needs
2. Our compilation is recursive but works fine for our contract depth
3. We support custom fragments that match our existing scripts
4. We don't need the full type system - `has_checkmultisig` is enough
5. Bitcoin Core's TreeEval is more sophisticated but overkill for us

**When to Consider Upgrading**:
- If we need to support arbitrary user-provided miniscripts
- If we need policy language compilation
- If we need static analysis of script properties
- If we encounter edge cases our parser can't handle

For now, our implementation is the right choice for the CLTV plugin.










