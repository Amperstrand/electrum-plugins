"""
Miniscript to JSON AST Converter Service

Converts Miniscript strings to normalized JSON AST for visualization.
Uses our existing Python parser and visualization AST converter.
"""

import json
from typing import Dict, Any, Optional
from electrum.util import BitcoinException
from cltv_lib.miniscript.compiler import _parse_expr as parse_miniscript_expr
from cltv_lib.miniscript.visualization_ast import (
    create_visualization_ast,
    VisualizationNode,
    NodeType
)


def miniscript_to_json_ast(
    miniscript: str,
    params: Dict[str, Any],
    key_labels: Optional[Dict[str, str]] = None,
    context: str = 'p2wsh'
) -> Dict[str, Any]:
    """
    Convert Miniscript string to JSON AST.
    
    This is the "special compiler" - it compiles Miniscript to a visualization AST,
    not to Bitcoin Script. The visualization AST is optimized for UI rendering.
    
    Args:
        miniscript: Miniscript expression string (e.g., "or_i(pk(Alice), pk(Bob))")
        params: Parameter dict mapping names to values
            - Keys: parameter names from miniscript (e.g., "Alice", "Bob")
            - Values: pubkey hex strings, locktime integers, etc.
        key_labels: Optional mapping of pubkey hex strings -> human-readable labels
            - Example: {"02abc123...": "Alice (Party A)"}
        context: 'p2wsh' or 'tapscript' (affects key format)
    
    Returns:
        JSON AST in the format expected by the visualizer:
        {
            "rootId": "node_0",
            "nodes": {
                "node_0": { ... },
                "node_1": { ... },
                ...
            },
            "metadata": {
                "scriptType": "P2WSH",
                "miniscript": "...",
                ...
            }
        }
    
    Example:
        >>> result = miniscript_to_json_ast(
        ...     "or_i(pk(Alice), pk(Bob))",
        ...     {"Alice": "02abc123...", "Bob": "03def456..."},
        ...     key_labels={"02abc123...": "Alice", "03def456...": "Bob"}
        ... )
        >>> print(json.dumps(result, indent=2))
    """
    # Convert key_labels from hex strings to bytes (if needed)
    key_labels_bytes = {}
    if key_labels:
        for hex_key, label in key_labels.items():
            try:
                key_bytes = bytes.fromhex(hex_key)
                key_labels_bytes[key_bytes] = label
            except ValueError:
                # Not a hex string, might already be bytes
                if isinstance(hex_key, bytes):
                    key_labels_bytes[hex_key] = label
    
    # Step 1: Parse Miniscript string into internal AST
    try:
        miniscript_node = parse_miniscript_expr(miniscript, params)
    except Exception as e:
        raise BitcoinException(f"Failed to parse Miniscript: {e}")
    
    # Step 2: Convert to visualization AST
    try:
        viz_root, nodes_by_id, _ = create_visualization_ast(
            miniscript_node,
            key_labels=key_labels_bytes
        )
    except Exception as e:
        raise BitcoinException(f"Failed to create visualization AST: {e}")
    
    # Step 3: Serialize to JSON
    return serialize_viz_ast_to_json(viz_root, nodes_by_id, miniscript, context)


def serialize_viz_ast_to_json(
    viz_root: VisualizationNode,
    nodes_by_id: Dict[str, VisualizationNode],
    miniscript: str,
    context: str
) -> Dict[str, Any]:
    """
    Serialize VisualizationNode tree to JSON-serializable format.
    
    This handles:
    - Converting enums to strings
    - Converting bytes to hex strings
    - Preserving all node relationships
    """
    # Convert nodes_by_id to JSON-serializable format
    nodes_dict = {}
    for node_id, node in nodes_by_id.items():
        nodes_dict[node_id] = {
            "id": node.id,
            "type": node.type.value,  # Convert NodeType enum to string
            "label": node.label,
            "miniscript": node.miniscript,
            "children": node.children,
            "params": serialize_params(node.params)  # Handle bytes, etc.
        }
    
    # Determine script type
    script_type = "P2TR" if context == 'tapscript' else "P2WSH"
    
    return {
        "rootId": viz_root.id,
        "nodes": nodes_dict,
        "metadata": {
            "scriptType": script_type,
            "miniscript": miniscript,
            "context": context
        }
    }


def serialize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert params dict to JSON-serializable format.
    
    Handles:
    - bytes → hex strings
    - Lists of bytes → lists of hex strings
    - Other types pass through
    """
    result = {}
    for key, value in params.items():
        if isinstance(value, bytes):
            result[key] = value.hex()
        elif isinstance(value, list):
            # Handle lists that might contain bytes
            result[key] = [
                v.hex() if isinstance(v, bytes) else v
                for v in value
            ]
        elif isinstance(value, dict):
            # Recursively serialize nested dicts
            result[key] = serialize_params(value)
        else:
            result[key] = value
    return result


# Example usage and testing
if __name__ == "__main__":
    # Example 1: Simple OR
    result = miniscript_to_json_ast(
        "or_i(pk(Alice), pk(Bob))",
        {
            "Alice": "02abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "Bob": "03def4567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        },
        key_labels={
            "02abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab": "Alice (Party A)",
            "03def4567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef": "Bob (Party B)"
        }
    )
    
    print("Example 1: Simple OR")
    print(json.dumps(result, indent=2))
    print("\n" + "="*80 + "\n")
    
    # Example 2: AND with timelock
    result2 = miniscript_to_json_ast(
        "and_v(after(800000), pk(Alice))",
        {
            "Alice": "02abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"
        },
        key_labels={
            "02abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab": "Alice"
        }
    )
    
    print("Example 2: AND with timelock")
    print(json.dumps(result2, indent=2))










