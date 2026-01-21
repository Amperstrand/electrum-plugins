"""
Miniscript Visualization AST

Normalized AST representation for UI visualization and simulation.
This is separate from the compilation AST (node.py) - it's optimized
for visualization and human-readable labels.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum


class NodeType(Enum):
    """Node types for visualization."""
    # Combinators
    AND = "and"
    OR = "or"
    THRESH = "thresh"
    ANDOR = "andor"
    
    # Leaf nodes
    SIGNATURE = "signature"
    MULTISIG = "multisig"
    TIMELOCK_ABSOLUTE = "timelock_absolute"
    TIMELOCK_RELATIVE = "timelock_relative"
    HASHLOCK = "hashlock"
    CONSTANT_TRUE = "constant_true"
    CONSTANT_FALSE = "constant_false"


@dataclass
class VisualizationNode:
    """
    Normalized AST node for visualization.
    
    This is a simplified, UI-friendly representation of a miniscript AST.
    It focuses on structure and human-readable labels rather than compilation details.
    """
    id: str  # Unique identifier
    type: NodeType
    label: Optional[str] = None  # Human-readable label for UI
    miniscript: Optional[str] = None  # Miniscript fragment (for tooltip)
    children: List[str] = field(default_factory=list)  # Child node IDs
    params: Dict[str, Any] = field(default_factory=dict)  # Type-specific data
    
    # UI state
    ui: Dict[str, Any] = field(default_factory=dict)  # UI metadata (groupLabel, collapsed, etc.)
    
    # Simulation state (set during evaluation)
    satisfied: Optional[bool] = None  # True if this node is satisfied
    relevant: Optional[bool] = None  # True if this node is relevant to current path
    satisfaction_path: Optional[str] = None  # Which path satisfies this (for OR nodes)


def create_visualization_ast(
    miniscript_node,
    nodes_by_id: Optional[Dict[str, VisualizationNode]] = None,
    node_counter: int = 0,
    key_labels: Optional[Dict[bytes, str]] = None
):
    """
    Convert a miniscript Node to a VisualizationNode tree.
    
    Args:
        miniscript_node: Node from cltv_lib.miniscript.node
        nodes_by_id: Dictionary to populate with all nodes (for lookup)
        node_counter: Counter for generating unique IDs
        key_labels: Optional mapping of pubkey bytes -> human labels
    
    Returns:
        (root VisualizationNode, nodes_by_id dict)
    """
    from .node import Node as MiniscriptNode
    from .fragments import Fragment
    
    if nodes_by_id is None:
        nodes_by_id = {}
    
    if key_labels is None:
        key_labels = {}
    
    node_id = f"node_{node_counter}"
    node_counter += 1
    
    # Determine node type and params
    node_type = None
    label = None
    miniscript_fragment = None
    params = {}
    children = []
    
    fragment = miniscript_node.fragment
    
    # Handle combinators
    if fragment == Fragment.AND_V or fragment == Fragment.AND_B:
        node_type = NodeType.AND
        label = "AND"
        miniscript_fragment = miniscript_node.to_miniscript()
        # Recursively convert children
        for sub in miniscript_node.subs:
            sub_viz, nodes_by_id, node_counter = create_visualization_ast(
                sub, nodes_by_id, node_counter, key_labels
            )
            children.append(sub_viz.id)
    
    elif fragment == Fragment.OR_I or fragment == Fragment.OR_B or fragment == Fragment.OR_D or fragment == Fragment.OR_C:
        node_type = NodeType.OR
        label = "OR"
        miniscript_fragment = miniscript_node.to_miniscript()
        # Recursively convert children
        for sub in miniscript_node.subs:
            sub_viz, nodes_by_id, node_counter = create_visualization_ast(
                sub, nodes_by_id, node_counter, key_labels
            )
            children.append(sub_viz.id)
    
    elif fragment == Fragment.ANDOR:
        node_type = NodeType.ANDOR
        label = "IF-THEN-ELSE"
        miniscript_fragment = miniscript_node.to_miniscript()
        # Recursively convert children (X, Y, Z)
        for sub in miniscript_node.subs:
            sub_viz, nodes_by_id, node_counter = create_visualization_ast(
                sub, nodes_by_id, node_counter, key_labels
            )
            children.append(sub_viz.id)
    
    elif fragment == Fragment.THRESH:
        node_type = NodeType.THRESH
        k = miniscript_node.k or 0
        label = f"THRESH({k})"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['k'] = k
        # Recursively convert children
        for sub in miniscript_node.subs:
            sub_viz, nodes_by_id, node_counter = create_visualization_ast(
                sub, nodes_by_id, node_counter, key_labels
            )
            children.append(sub_viz.id)
    
    # Handle leaf nodes
    elif fragment == Fragment.PK_K:
        node_type = NodeType.SIGNATURE
        pubkey = miniscript_node.key
        if pubkey:
            # Try to get human label
            key_label = key_labels.get(pubkey, pubkey.hex()[:16] + "...")
            label = f"Signature: {key_label}"
        else:
            label = "Signature: (unknown key)"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['pubkey'] = pubkey.hex() if pubkey else None
        params['pubkey_label'] = key_labels.get(pubkey) if pubkey else None
    
    elif fragment == Fragment.MULTI or fragment == Fragment.MULTI_A:
        node_type = NodeType.MULTISIG
        k = miniscript_node.k or 0
        n = len(miniscript_node.keys)
        label = f"{k}-of-{n} Multisig"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['k'] = k
        params['n'] = n
        # Get labels for keys
        key_labels_list = []
        for key in miniscript_node.keys:
            label_text = key_labels.get(key, key.hex()[:16] + "...")
            key_labels_list.append(label_text)
        params['key_labels'] = key_labels_list
        params['keys'] = [k.hex() for k in miniscript_node.keys]
    
    elif fragment == Fragment.AFTER or fragment == Fragment.AFTER_DROP:
        node_type = NodeType.TIMELOCK_ABSOLUTE
        locktime = miniscript_node.k or 0
        label = f"After block {locktime}"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['lockType'] = 'absolute'
        params['value'] = locktime
        params['unit'] = 'height'
    
    elif fragment == Fragment.OLDER or fragment == Fragment.OLDER_DROP:
        node_type = NodeType.TIMELOCK_RELATIVE
        blocks = miniscript_node.k or 0
        label = f"{blocks} blocks after confirmation"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['lockType'] = 'relative'
        params['value'] = blocks
        params['unit'] = 'blocks'
    
    elif fragment == Fragment.HASH160 or fragment == Fragment.HASH160_SIMPLE:
        node_type = NodeType.HASHLOCK
        hash_data = miniscript_node.data
        if hash_data:
            label = f"Hash: {hash_data.hex()[:16]}..."
        else:
            label = "Hash: (unknown)"
        miniscript_fragment = miniscript_node.to_miniscript()
        params['hashType'] = 'hash160'
        params['hash'] = hash_data.hex() if hash_data else None
    
    elif fragment == Fragment.JUST_1:
        node_type = NodeType.CONSTANT_TRUE
        label = "Always true"
        miniscript_fragment = "1"
    
    elif fragment == Fragment.JUST_0:
        node_type = NodeType.CONSTANT_FALSE
        label = "Always false"
        miniscript_fragment = "0"
    
    else:
        # Unknown fragment - create generic node
        node_type = NodeType.SIGNATURE  # Fallback
        label = f"Unknown: {fragment.name}"
        miniscript_fragment = miniscript_node.to_miniscript()
    
    # Handle wrappers (v:, c:, etc.) - these modify the node but don't change structure
    if miniscript_node.wrappers:
        wrapper_text = ':'.join(miniscript_node.wrappers) + ':'
        if miniscript_fragment:
            miniscript_fragment = wrapper_text + miniscript_fragment
    
    # Create visualization node
    viz_node = VisualizationNode(
        id=node_id,
        type=node_type,
        label=label,
        miniscript=miniscript_fragment,
        children=children,
        params=params
    )
    
    nodes_by_id[node_id] = viz_node
    
    return viz_node, nodes_by_id, node_counter


def evaluate_satisfaction(
    node: VisualizationNode,
    nodes_by_id: Dict[str, VisualizationNode],
    simulator_state: Dict[str, Any]
) -> bool:
    """
    Recursively evaluate if a node is satisfied given simulator state.
    
    Args:
        node: VisualizationNode to evaluate
        nodes_by_id: All nodes for lookup
        simulator_state: {
            'available_signatures': Set[str],  # Set of pubkey hex strings
            'current_height': int,
            'confirmation_height': Optional[int],  # For relative timelocks
            'available_preimages': Dict[str, str],  # hash -> preimage hex
        }
    
    Returns:
        True if node is satisfied, False otherwise
    """
    available_sigs = simulator_state.get('available_signatures', set())
    current_height = simulator_state.get('current_height', 0)
    confirmation_height = simulator_state.get('confirmation_height', None)
    available_preimages = simulator_state.get('available_preimages', {})
    
    # Evaluate based on node type
    if node.type == NodeType.AND:
        # All children must be satisfied
        for child_id in node.children:
            child = nodes_by_id.get(child_id)
            if child and not evaluate_satisfaction(child, nodes_by_id, simulator_state):
                node.satisfied = False
                return False
        node.satisfied = True
        return True
    
    elif node.type == NodeType.OR:
        # At least one child must be satisfied
        satisfied_path = None
        for child_id in node.children:
            child = nodes_by_id.get(child_id)
            if child and evaluate_satisfaction(child, nodes_by_id, simulator_state):
                node.satisfied = True
                node.satisfaction_path = child_id
                return True
        node.satisfied = False
        return False
    
    elif node.type == NodeType.ANDOR:
        # IF X THEN Y ELSE Z
        if len(node.children) >= 3:
            x = nodes_by_id.get(node.children[0])
            y = nodes_by_id.get(node.children[1])
            z = nodes_by_id.get(node.children[2])
            
            if x and evaluate_satisfaction(x, nodes_by_id, simulator_state):
                # X is true -> Y must be satisfied
                if y:
                    result = evaluate_satisfaction(y, nodes_by_id, simulator_state)
                    node.satisfied = result
                    if result:
                        node.satisfaction_path = node.children[1]
                    return result
            else:
                # X is false -> Z must be satisfied
                if z:
                    result = evaluate_satisfaction(z, nodes_by_id, simulator_state)
                    node.satisfied = result
                    if result:
                        node.satisfaction_path = node.children[2]
                    return result
        node.satisfied = False
        return False
    
    elif node.type == NodeType.THRESH:
        # K of N children must be satisfied
        k = node.params.get('k', 0)
        satisfied_count = 0
        for child_id in node.children:
            child = nodes_by_id.get(child_id)
            if child and evaluate_satisfaction(child, nodes_by_id, simulator_state):
                satisfied_count += 1
        node.satisfied = satisfied_count >= k
        return node.satisfied
    
    elif node.type == NodeType.SIGNATURE:
        # Check if signature is available
        pubkey_hex = node.params.get('pubkey')
        if pubkey_hex and pubkey_hex in available_sigs:
            node.satisfied = True
            return True
        node.satisfied = False
        return False
    
    elif node.type == NodeType.MULTISIG:
        # Check if enough signatures are available
        k = node.params.get('k', 0)
        keys = node.params.get('keys', [])
        available_count = sum(1 for key_hex in keys if key_hex in available_sigs)
        node.satisfied = available_count >= k
        return node.satisfied
    
    elif node.type == NodeType.TIMELOCK_ABSOLUTE:
        # Check if current height >= locktime
        locktime = node.params.get('value', 0)
        node.satisfied = current_height >= locktime
        return node.satisfied
    
    elif node.type == NodeType.TIMELOCK_RELATIVE:
        # Check if (current_height - confirmation_height) >= blocks
        blocks = node.params.get('value', 0)
        if confirmation_height is not None:
            node.satisfied = (current_height - confirmation_height) >= blocks
        else:
            # No confirmation height -> can't satisfy relative timelock
            node.satisfied = False
        return node.satisfied
    
    elif node.type == NodeType.HASHLOCK:
        # Check if preimage is available
        hash_value = node.params.get('hash')
        if hash_value and hash_value in available_preimages:
            node.satisfied = True
            return True
        node.satisfied = False
        return False
    
    elif node.type == NodeType.CONSTANT_TRUE:
        node.satisfied = True
        return True
    
    elif node.type == NodeType.CONSTANT_FALSE:
        node.satisfied = False
        return False
    
    # Unknown type
    node.satisfied = False
    return False


def mark_relevance(
    node: VisualizationNode,
    nodes_by_id: Dict[str, VisualizationNode],
    satisfied_path: Optional[str] = None
):
    """
    Mark which nodes are relevant to the satisfied path.
    
    For OR nodes, only the satisfied branch is relevant.
    For AND nodes, all children are relevant.
    """
    if satisfied_path and node.satisfaction_path:
        # This is the path that was taken
        node.relevant = True
        # Mark children on this path as relevant
        if node.satisfaction_path in node.children:
            child = nodes_by_id.get(node.satisfaction_path)
            if child:
                child.relevant = True
                mark_relevance(child, nodes_by_id, satisfied_path)
    elif node.type == NodeType.AND:
        # All children are relevant for AND
        node.relevant = True
        for child_id in node.children:
            child = nodes_by_id.get(child_id)
            if child:
                child.relevant = True
                mark_relevance(child, nodes_by_id, satisfied_path)
    elif node.type == NodeType.OR:
        # Only satisfied path is relevant
        if node.satisfaction_path:
            child = nodes_by_id.get(node.satisfaction_path)
            if child:
                child.relevant = True
                mark_relevance(child, nodes_by_id, node.satisfaction_path)
    else:
        # Leaf node
        node.relevant = True

