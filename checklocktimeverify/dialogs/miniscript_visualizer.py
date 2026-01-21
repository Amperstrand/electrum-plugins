"""
Miniscript Visualizer Dialog

Shows a visual tree representation of a Miniscript spending policy with
interactive simulation capabilities.

Design: Miniscript-first, Tree + Details layout
- Left: Miniscript tree (always visible)
- Right: Tabs (Details, Simulator, Raw, Taproot if applicable)
- Taproot shown as metadata/badge, not core structure
"""

import logging
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTreeWidget,
    QTreeWidgetItem, QGroupBox, QSpinBox, QCheckBox, QTextEdit,
    QPushButton, QScrollArea, QWidget, QSplitter, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QIcon

from electrum.gui.qt.util import (
    WindowModalDialog, Buttons, CloseButton, WWLabel, ColorScheme, MONOSPACE_FONT
)
from electrum.i18n import _

from ..cltv_lib.miniscript.visualization_ast import (
    VisualizationNode, NodeType, create_visualization_ast, evaluate_satisfaction, mark_relevance
)
from ..cltv_lib.miniscript.compiler import _parse_expr as parse_miniscript_expr
from ..cltv_lib.miniscript.node import Node as MiniscriptNode

logger = logging.getLogger(__name__)


@dataclass
class SimulatorState:
    """State for the miniscript simulator."""
    available_signatures: Set[str] = None  # Set of pubkey hex strings
    current_height: int = 0
    confirmation_height: Optional[int] = None  # For relative timelocks
    available_preimages: Dict[str, str] = None  # hash -> preimage hex
    
    def __post_init__(self):
        if self.available_signatures is None:
            self.available_signatures = set()
        if self.available_preimages is None:
            self.available_preimages = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for evaluation."""
        return {
            'available_signatures': self.available_signatures,
            'current_height': self.current_height,
            'confirmation_height': self.confirmation_height,
            'available_preimages': self.available_preimages,
        }


class MiniscriptVisualizerDialog(WindowModalDialog):
    """
    Dialog for visualizing and simulating Miniscript spending conditions.
    
    Layout: Tree + Details
    - Left: Miniscript tree (always visible)
    - Right: Tabs (Details, Simulator, Raw, Taproot if applicable)
    
    Design principles:
    - Miniscript-first: Policy structure is primary
    - Taproot as metadata: Shown via badge and optional tab
    - Works identically for P2WSH and Taproot
    """
    
    def __init__(
        self,
        parent,
        miniscript: str,
        params: Dict[str, Any],
        key_labels: Optional[Dict[bytes, str]] = None,
        address: Optional[str] = None,
        context: str = 'p2wsh',  # 'p2wsh' or 'tapscript'
        taproot_metadata: Optional[Dict[str, Any]] = None,  # Internal key, output key, leaf index, etc.
        contract: Optional[Any] = None  # ContractDefinition for key role lookups
    ):
        """
        Initialize the visualizer dialog.
        
        Args:
            parent: Parent window
            miniscript: Miniscript expression string
            params: Parameter dict (pubkeys, locktimes, etc.)
            key_labels: Optional mapping of pubkey bytes -> human labels
            address: Optional address derived from this script
            context: 'p2wsh' or 'tapscript'
            taproot_metadata: Optional dict with:
                - internal_key: bytes (32-byte x-only)
                - output_key: bytes (32-byte x-only)
                - leaf_index: int
                - leaf_version: int
                - merkle_root: bytes (optional)
        """
        super().__init__(parent, _("Miniscript Spending Conditions"))
        
        self.miniscript = miniscript
        self.params = params
        self.key_labels = key_labels or {}
        self.address = address
        self.context = context
        self.taproot_metadata = taproot_metadata or {}
        self.contract = contract  # Store contract for key role lookups
        
        # Determine script type for badge
        if context == 'tapscript':
            if self.taproot_metadata.get('leaf_index') is not None:
                self.script_type = f"P2TR (script path, leaf {self.taproot_metadata.get('leaf_index')})"
            else:
                self.script_type = "P2TR (script path)"
        else:
            self.script_type = "P2WSH"
        
        # For Taproot: collect all leaves if contract has multiple paths
        self.all_leaves = []  # List of (path_name, miniscript_str, viz_root, nodes_by_id)
        if context == 'tapscript' and contract and contract.taproot_leaves and len(contract.taproot_leaves) > 1:
            # Parse all leaves
            from ..cltv_lib.miniscript import MiniscriptContext
            ms_context = MiniscriptContext.TAPSCRIPT
            for i, leaf_ms in enumerate(contract.taproot_leaves):
                # Find path for this leaf
                path = None
                for p in contract.paths:
                    if p.leaf_index == i:
                        path = p
                        break
                
                try:
                    leaf_node = parse_miniscript_expr(leaf_ms, params)
                    leaf_viz_root, leaf_nodes_by_id, _unused = create_visualization_ast(
                        leaf_node,
                        key_labels=self.key_labels
                    )
                    path_name = path.display_name if path else f"Leaf {i}"
                    self.all_leaves.append((path_name, leaf_ms, leaf_viz_root, leaf_nodes_by_id))
                except Exception as e:
                    logger.error(f"Failed to parse leaf {i}: {e}", exc_info=True)
            
            # Use the first leaf as the primary one (or the one matching current path)
            if self.all_leaves:
                self.viz_root = self.all_leaves[0][2]  # First leaf's viz_root
                self.nodes_by_id = self.all_leaves[0][3]  # First leaf's nodes_by_id
                self.miniscript = self.all_leaves[0][1]  # First leaf's miniscript
                self.miniscript_node = parse_miniscript_expr(self.miniscript, params)
            else:
                self.viz_root = None
                self.nodes_by_id = {}
                self.miniscript_node = None
        else:
            # Single miniscript (P2WSH or single-leaf Taproot)
            try:
                from ..cltv_lib.miniscript import MiniscriptContext
                ms_context = MiniscriptContext.TAPSCRIPT if context == 'tapscript' else MiniscriptContext.P2WSH
                self.miniscript_node = parse_miniscript_expr(miniscript, params)
                
                # Convert to visualization AST
                self.viz_root, self.nodes_by_id, _unused = create_visualization_ast(
                    self.miniscript_node,
                    key_labels=self.key_labels
                )
            except Exception as e:
                logger.error(f"Failed to parse miniscript: {e}", exc_info=True)
                self.viz_root = None
                self.nodes_by_id = {}
                self.miniscript_node = None
        
        # Compile script for Raw tab
        try:
            from ..cltv_lib.miniscript import MiniscriptContext
            ms_context = MiniscriptContext.TAPSCRIPT if context == 'tapscript' else MiniscriptContext.P2WSH
            if self.miniscript_node:
                self.compiled_script = self.miniscript_node.compile(ms_context)
            else:
                self.compiled_script = b''
        except Exception as e:
            logger.error(f"Failed to compile script: {e}", exc_info=True)
            self.compiled_script = b''
        
        # Simulator state
        self.simulator_state = SimulatorState()
        
        # UI components
        self.tree_widget: Optional[QTreeWidget] = None
        self.details_tabs: Optional[QTabWidget] = None
        self.selected_node: Optional[VisualizationNode] = None
        self.signature_checkboxes: Dict[str, QCheckBox] = {}
        self.height_spinbox: Optional[QSpinBox] = None
        self.confirmation_spinbox: Optional[QSpinBox] = None
        self.status_label: Optional[QLabel] = None
        
        self.setMinimumSize(1000, 700)
        self.setup_ui()
    
    def setup_ui(self):
        """Build the dialog UI with Tree + Details layout."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        self.setLayout(main_layout)
        
        # Header with script type badge
        header = self._create_header()
        main_layout.addWidget(header)
        
        # Main splitter: Tree (left) + Details (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Miniscript tree (always visible)
        tree_widget = self._create_tree_panel()
        splitter.addWidget(tree_widget)
        
        # Right: Details tabs
        details_widget = self._create_details_panel()
        splitter.addWidget(details_widget)
        
        # Set splitter proportions (40% tree, 60% details)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([400, 600])
        
        main_layout.addWidget(splitter)
        
        # Close button
        main_layout.addLayout(Buttons(CloseButton(self)))
    
    def _create_header(self) -> QWidget:
        """Create header with script type badge."""
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header.setStyleSheet("background-color: #f0f0f0; padding: 8px;")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        
        # Title
        title = QLabel(_("Miniscript Spending Policy"))
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Script type badge
        badge = QLabel(self.script_type)
        badge.setStyleSheet(
            "background-color: #4a90e2; color: white; "
            "padding: 4px 12px; border-radius: 4px; "
            "font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(badge)
        
        # Address (if available)
        if self.address:
            addr_label = QLabel(self.address)
            addr_label.setFont(QFont(MONOSPACE_FONT))
            addr_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            addr_label.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(addr_label)
        
        header.setLayout(layout)
        return header
    
    def _create_tree_panel(self) -> QWidget:
        """Create left panel with Miniscript tree."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        widget.setLayout(layout)
        
        # Label
        label = QLabel(_("Policy Structure"))
        label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(label)
        
        # Tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel(_("Miniscript Tree"))
        self.tree_widget.setColumnCount(1)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.itemSelectionChanged.connect(self._on_tree_selection_changed)
        
        # Build tree from visualization AST
        # For Taproot with multiple leaves, show all leaves as top-level items
        if self.all_leaves:
            # Multiple leaves: show each as a top-level item
            for path_name, leaf_ms, leaf_viz_root, leaf_nodes_by_id in self.all_leaves:
                # Create a parent item for this path
                path_item = QTreeWidgetItem()
                path_item.setText(0, f"📜 {path_name}")
                path_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No node ID for path header
                path_item.setExpanded(True)
                
                # Add the leaf's tree structure as children
                if leaf_viz_root:
                    leaf_item = self._build_tree_item(leaf_viz_root, path_item, nodes_by_id=leaf_nodes_by_id)
                    # Store leaf data in path_item for later lookup
                    path_item.setData(0, Qt.ItemDataRole.UserRole + 1, (leaf_viz_root, leaf_nodes_by_id))
                
                self.tree_widget.addTopLevelItem(path_item)
        elif self.viz_root:
            # Single miniscript: show as single tree
            root_item = self._build_tree_item(self.viz_root, None)
            self.tree_widget.addTopLevelItem(root_item)
        
        self.tree_widget.expandAll()
        # Select first item by default (but don't trigger selection change yet)
        # The selection will be triggered after details tab is created
        
        layout.addWidget(self.tree_widget)
        
        return widget
    
    def _create_details_panel(self) -> QWidget:
        """Create right panel with tabs (Details, Simulator, Raw, Taproot)."""
        self.details_tabs = QTabWidget()
        
        # Details tab (shows selected node info)
        self.details_tabs.addTab(self._create_details_tab(), _("Details"))
        
        # Simulator tab
        self.details_tabs.addTab(self._create_simulator_tab(), _("Simulator"))
        
        # Raw tab (script hex, witness script, descriptor)
        self.details_tabs.addTab(self._create_raw_tab(), _("Raw"))
        
        # Taproot tab (only if Taproot)
        if self.context == 'tapscript' and self.taproot_metadata:
            self.details_tabs.addTab(self._create_taproot_tab(), _("Taproot"))
        
        return self.details_tabs
    
    def _create_details_tab(self) -> QWidget:
        """Create Details tab showing selected node information."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        widget.setLayout(layout)
        
        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setSpacing(16)
        content.setLayout(content_layout)
        
        # Node info (updated when selection changes)
        # Store as instance variable so _update_details_tab() can access it
        self.node_info_group = QGroupBox(_("Selected Node"))
        self.node_info_layout = QVBoxLayout()
        self.node_info_group.setLayout(self.node_info_layout)
        
        # Default message
        default_label = WWLabel(_("Select a node in the tree to see details"))
        default_label.setWordWrap(True)
        default_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
        self.node_info_layout.addWidget(default_label)
        
        content_layout.addWidget(self.node_info_group)
        content_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return widget
    
    def _create_simulator_tab(self) -> QWidget:
        """Create Simulator tab with interactive controls."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        widget.setLayout(layout)
        
        # Splitter for side-by-side layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout()
        controls_widget.setLayout(controls_layout)
        
        # Block height
        height_group = QGroupBox(_("Block Height"))
        height_layout = QVBoxLayout()
        height_label = QLabel(_("Current block height:"))
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(0)
        self.height_spinbox.setMaximum(10000000)
        self.height_spinbox.setValue(0)
        self.height_spinbox.valueChanged.connect(self._update_simulation)
        height_layout.addWidget(height_label)
        height_layout.addWidget(self.height_spinbox)
        
        # Confirmation height (for relative timelocks)
        conf_label = QLabel(_("Confirmation height (for relative timelocks):"))
        self.confirmation_spinbox = QSpinBox()
        self.confirmation_spinbox.setMinimum(0)
        self.confirmation_spinbox.setMaximum(10000000)
        self.confirmation_spinbox.setValue(0)
        self.confirmation_spinbox.setSpecialValueText(_("Not set"))
        self.confirmation_spinbox.valueChanged.connect(self._update_simulation)
        height_layout.addWidget(conf_label)
        height_layout.addWidget(self.confirmation_spinbox)
        height_group.setLayout(height_layout)
        controls_layout.addWidget(height_group)
        
        # Available signatures
        sigs_group = QGroupBox(_("Available Signatures"))
        sigs_layout = QVBoxLayout()
        
        # Collect all pubkeys from the AST
        pubkeys = set()
        for node in self.nodes_by_id.values():
            if node.type == NodeType.SIGNATURE:
                pubkey = node.params.get('pubkey')
                if pubkey:
                    pubkeys.add(pubkey)
            elif node.type == NodeType.MULTISIG:
                keys = node.params.get('keys', [])
                pubkeys.update(keys)
        
        if pubkeys:
            for pubkey_hex in sorted(pubkeys):
                # Get label
                label = None
                for node in self.nodes_by_id.values():
                    if node.params.get('pubkey') == pubkey_hex:
                        label = node.params.get('pubkey_label') or node.label
                        break
                
                if not label:
                    # Try to find in key_labels
                    try:
                        pubkey_bytes = bytes.fromhex(pubkey_hex)
                        label = self.key_labels.get(pubkey_bytes, pubkey_hex[:16] + "...")
                    except:
                        label = pubkey_hex[:16] + "..."
                
                checkbox = QCheckBox(label)
                checkbox.setObjectName(f"sig_{pubkey_hex}")
                checkbox.stateChanged.connect(self._update_simulation)
                self.signature_checkboxes[pubkey_hex] = checkbox
                sigs_layout.addWidget(checkbox)
        else:
            no_sigs = QLabel(_("No signatures found in this script"))
            no_sigs.setStyleSheet("color: #666; font-style: italic;")
            sigs_layout.addWidget(no_sigs)
        
        sigs_group.setLayout(sigs_layout)
        controls_layout.addWidget(sigs_group)
        
        # Hash preimages (if any hash locks)
        has_hashlocks = any(node.type == NodeType.HASHLOCK for node in self.nodes_by_id.values())
        if has_hashlocks:
            preimage_group = QGroupBox(_("Hash Preimages"))
            preimage_layout = QVBoxLayout()
            # TODO: Add preimage inputs
            preimage_note = QLabel(_("Preimage inputs coming soon"))
            preimage_note.setStyleSheet("color: #666; font-style: italic;")
            preimage_layout.addWidget(preimage_note)
            preimage_group.setLayout(preimage_layout)
            controls_layout.addWidget(preimage_group)
        
        controls_layout.addStretch()
        splitter.addWidget(controls_widget)
        
        # Right: Status and tree
        status_widget = QWidget()
        status_layout = QVBoxLayout()
        status_widget.setLayout(status_layout)
        
        # Status display
        status_group = QGroupBox(_("Spendability Status"))
        status_layout_inner = QVBoxLayout()
        
        self.status_label = QLabel(_("Configure simulation settings above"))
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 14px; padding: 12px;")
        status_layout_inner.addWidget(self.status_label)
        
        # Tree with satisfaction highlighting
        tree_label = QLabel(_("Policy Tree (with satisfaction highlighting):"))
        status_layout_inner.addWidget(tree_label)
        
        self.simulator_tree = QTreeWidget()
        self.simulator_tree.setHeaderLabel(_("Policy Structure"))
        self.simulator_tree.setColumnCount(1)
        self.simulator_tree.setRootIsDecorated(True)
        status_layout_inner.addWidget(self.simulator_tree)
        
        status_group.setLayout(status_layout_inner)
        status_layout.addWidget(status_group)
        
        splitter.addWidget(status_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        
        # Initial simulation update
        self._update_simulation()
        
        return widget
    
    def _create_raw_tab(self) -> QWidget:
        """Create Raw tab with script hex, witness script, descriptor."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        widget.setLayout(layout)
        
        # Miniscript expression
        ms_group = QGroupBox(_("Miniscript Expression"))
        ms_layout = QVBoxLayout()
        ms_text = QTextEdit()
        ms_text.setReadOnly(True)
        ms_text.setFont(QFont(MONOSPACE_FONT))
        ms_text.setPlainText(self.miniscript)
        ms_layout.addWidget(ms_text)
        ms_group.setLayout(ms_layout)
        layout.addWidget(ms_group)
        
        # Compiled script
        script_group = QGroupBox(_("Compiled Bitcoin Script"))
        script_layout = QVBoxLayout()
        script_text = QTextEdit()
        script_text.setReadOnly(True)
        script_text.setFont(QFont(MONOSPACE_FONT))
        script_hex = self.compiled_script.hex() if self.compiled_script else "(failed to compile)"
        script_text.setPlainText(script_hex)
        script_layout.addWidget(script_text)
        script_group.setLayout(script_layout)
        layout.addWidget(script_group)
        
        # Descriptor (if we can construct it)
        # TODO: Add descriptor generation
        
        layout.addStretch()
        return widget
    
    def _create_taproot_tab(self) -> QWidget:
        """Create Taproot tab with metadata (internal key, output key, leaf info)."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        widget.setLayout(layout)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setSpacing(16)
        content.setLayout(content_layout)
        
        # Internal key
        if self.taproot_metadata.get('internal_key'):
            internal_group = QGroupBox(_("Internal Key"))
            internal_layout = QVBoxLayout()
            internal_key = self.taproot_metadata['internal_key']
            if isinstance(internal_key, bytes):
                internal_key_hex = internal_key.hex()
            else:
                internal_key_hex = str(internal_key)
            internal_label = QLabel(internal_key_hex)
            internal_label.setFont(QFont(MONOSPACE_FONT))
            internal_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            internal_layout.addWidget(internal_label)
            internal_group.setLayout(internal_layout)
            content_layout.addWidget(internal_group)
        
        # Output key
        if self.taproot_metadata.get('output_key'):
            output_group = QGroupBox(_("Output Key"))
            output_layout = QVBoxLayout()
            output_key = self.taproot_metadata['output_key']
            if isinstance(output_key, bytes):
                output_key_hex = output_key.hex()
            else:
                output_key_hex = str(output_key)
            output_label = QLabel(output_key_hex)
            output_label.setFont(QFont(MONOSPACE_FONT))
            output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            output_layout.addWidget(output_label)
            output_group.setLayout(output_layout)
            content_layout.addWidget(output_group)
        
        # Leaf info
        leaf_group = QGroupBox(_("Leaf Information"))
        leaf_layout = QVBoxLayout()
        
        if self.taproot_metadata.get('leaf_index') is not None:
            leaf_index_label = QLabel(_("Leaf Index: {}").format(self.taproot_metadata['leaf_index']))
            leaf_layout.addWidget(leaf_index_label)
        
        if self.taproot_metadata.get('leaf_version') is not None:
            leaf_version_label = QLabel(_("Leaf Version: 0x{:02x}").format(self.taproot_metadata['leaf_version']))
            leaf_layout.addWidget(leaf_version_label)
        
        if self.taproot_metadata.get('merkle_root'):
            merkle_label = QLabel(_("Merkle Root:"))
            merkle_label.setStyleSheet("font-weight: bold;")
            leaf_layout.addWidget(merkle_label)
            merkle_value = QLabel(self.taproot_metadata['merkle_root'].hex() if isinstance(self.taproot_metadata['merkle_root'], bytes) else str(self.taproot_metadata['merkle_root']))
            merkle_value.setFont(QFont(MONOSPACE_FONT))
            merkle_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            leaf_layout.addWidget(merkle_value)
        
        leaf_group.setLayout(leaf_layout)
        content_layout.addWidget(leaf_group)
        
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return widget
    
    def _build_tree_item(
        self,
        node: VisualizationNode,
        parent_item: Optional[QTreeWidgetItem],
        nodes_by_id: Optional[Dict[str, VisualizationNode]] = None
    ) -> QTreeWidgetItem:
        """Build a QTreeWidgetItem from a VisualizationNode."""
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem()
        
        # Store node reference in item
        item.setData(0, Qt.ItemDataRole.UserRole, node.id)
        
        # Set text and tooltip
        label = node.label or node.type.value
        icon = self._get_icon_for_type(node.type)
        item.setText(0, f"{icon} {label}")
        
        if node.miniscript:
            item.setToolTip(0, f"Miniscript: {node.miniscript}")
        
        # Use provided nodes_by_id or fall back to self.nodes_by_id
        node_dict = nodes_by_id if nodes_by_id is not None else self.nodes_by_id
        
        # Recursively add children
        for child_id in node.children:
            child_node = node_dict.get(child_id)
            if child_node:
                self._build_tree_item(child_node, item, nodes_by_id=node_dict)
        
        return item
    
    def _get_icon_for_type(self, node_type: NodeType) -> str:
        """Get icon/emoji for node type."""
        icons = {
            NodeType.AND: "🔀",
            NodeType.OR: "🔁",
            NodeType.THRESH: "🔢",
            NodeType.ANDOR: "❓",
            NodeType.SIGNATURE: "🔑",
            NodeType.MULTISIG: "🔐",
            NodeType.TIMELOCK_ABSOLUTE: "⏰",
            NodeType.TIMELOCK_RELATIVE: "⏱️",
            NodeType.HASHLOCK: "#️⃣",
            NodeType.CONSTANT_TRUE: "✅",
            NodeType.CONSTANT_FALSE: "❌",
        }
        return icons.get(node_type, "•")
    
    def _on_tree_selection_changed(self):
        """Handle tree selection change - update Details tab."""
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            self.selected_node = None
            self._update_details_tab()
            return
        
        item = selected_items[0]
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Check if this is a path header (for multi-leaf Taproot)
        leaf_data = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if leaf_data:
            # This is a path header - use the leaf's root node
            leaf_viz_root, leaf_nodes_by_id = leaf_data
            self.selected_node = leaf_viz_root
            # Temporarily switch nodes_by_id for this leaf
            self._temp_nodes_by_id = self.nodes_by_id
            self.nodes_by_id = leaf_nodes_by_id
        elif node_id:
            # Regular node - use current nodes_by_id
            self.selected_node = self.nodes_by_id.get(node_id)
        else:
            self.selected_node = None
        
        self._update_details_tab()
        
        # Restore original nodes_by_id if we switched it
        if hasattr(self, '_temp_nodes_by_id'):
            self.nodes_by_id = self._temp_nodes_by_id
            delattr(self, '_temp_nodes_by_id')
    
    def _update_details_tab(self):
        """Update Details tab with selected node information."""
        # Check if node_info_layout exists (details tab may not be created yet)
        if not hasattr(self, 'node_info_layout') or self.node_info_layout is None:
            return
        
        # Clear existing content
        while self.node_info_layout.count():
            child = self.node_info_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not self.selected_node:
            default_label = WWLabel(_("Select a node in the tree to see details"))
            default_label.setWordWrap(True)
            default_label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
            self.node_info_layout.addWidget(default_label)
            return
        
        node = self.selected_node
        
        # Node type and label
        type_label = QLabel(_("Type: {}").format(node.type.value))
        type_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.node_info_layout.addWidget(type_label)
        
        if node.label:
            label_label = QLabel(_("Label: {}").format(node.label))
            self.node_info_layout.addWidget(label_label)
        
        # Miniscript fragment
        if node.miniscript:
            ms_group = QGroupBox(_("Miniscript Fragment"))
            ms_layout = QVBoxLayout()
            ms_text = QTextEdit()
            ms_text.setReadOnly(True)
            ms_text.setFont(QFont(MONOSPACE_FONT))
            ms_text.setPlainText(node.miniscript)
            ms_layout.addWidget(ms_text)
            ms_group.setLayout(ms_layout)
            self.node_info_layout.addWidget(ms_group)
        
        # Parameters
        if node.params:
            params_group = QGroupBox(_("Parameters"))
            params_layout = QVBoxLayout()
            import json
            params_text = QTextEdit()
            params_text.setReadOnly(True)
            params_text.setFont(QFont(MONOSPACE_FONT))
            params_str = json.dumps(node.params, indent=2, default=str)
            params_text.setPlainText(params_str)
            params_layout.addWidget(params_text)
            params_group.setLayout(params_layout)
            self.node_info_layout.addWidget(params_group)
        
        # Plain language explanation
        explanation = self._get_node_explanation(node)
        if explanation:
            expl_group = QGroupBox(_("Explanation"))
            expl_layout = QVBoxLayout()
            expl_label = WWLabel(explanation)
            expl_label.setWordWrap(True)
            expl_layout.addWidget(expl_label)
            expl_group.setLayout(expl_layout)
            self.node_info_layout.addWidget(expl_group)
        
        self.node_info_layout.addStretch()
    
    def _get_node_explanation(self, node: VisualizationNode) -> str:
        """Get plain language explanation for a node."""
        if node.type == NodeType.AND:
            return _("All child conditions must be satisfied (logical AND).")
        elif node.type == NodeType.OR:
            return _("At least one child condition must be satisfied (logical OR).")
        elif node.type == NodeType.THRESH:
            k = node.params.get('k', 0)
            return _("At least {} of the child conditions must be satisfied.").format(k)
        elif node.type == NodeType.SIGNATURE:
            label = node.params.get('pubkey_label') or node.label
            return _("Requires a valid signature from: {}").format(label)
        elif node.type == NodeType.MULTISIG:
            k = node.params.get('k', 0)
            n = node.params.get('n', 0)
            return _("Requires {} valid signatures out of {} possible keys.").format(k, n)
        elif node.type == NodeType.TIMELOCK_ABSOLUTE:
            locktime = node.params.get('value', 0)
            return _("Can only be spent after block height {}.").format(locktime)
        elif node.type == NodeType.TIMELOCK_RELATIVE:
            blocks = node.params.get('value', 0)
            return _("Can only be spent {} blocks after the transaction was confirmed.").format(blocks)
        elif node.type == NodeType.HASHLOCK:
            return _("Requires knowledge of the preimage to the hash.")
        elif node.type == NodeType.CONSTANT_TRUE:
            return _("Always satisfied (no condition).")
        elif node.type == NodeType.CONSTANT_FALSE:
            return _("Never satisfied (impossible condition).")
        return ""
    
    def _update_simulation(self):
        """Update simulation state and refresh UI."""
        if not self.viz_root:
            return
        
        # Update simulator state from UI
        self.simulator_state.current_height = self.height_spinbox.value() if self.height_spinbox else 0
        conf_height = self.confirmation_spinbox.value() if self.confirmation_spinbox else None
        if conf_height == 0:
            conf_height = None
        self.simulator_state.confirmation_height = conf_height
        
        # Collect available signatures
        available_sigs = set()
        for pubkey_hex, checkbox in self.signature_checkboxes.items():
            if checkbox.isChecked():
                available_sigs.add(pubkey_hex)
        self.simulator_state.available_signatures = available_sigs
        
        # Evaluate satisfaction
        state_dict = self.simulator_state.to_dict()
        is_satisfied = evaluate_satisfaction(self.viz_root, self.nodes_by_id, state_dict)
        
        # Mark relevance
        if is_satisfied:
            mark_relevance(self.viz_root, self.nodes_by_id)
        
        # Update status label
        if is_satisfied:
            self.status_label.setText(
                _("✅ <b>Spendable!</b><br/>"
                  "All required conditions are satisfied. This UTXO can be spent.")
            )
            self.status_label.setStyleSheet("color: green; font-size: 14px; padding: 12px;")
        else:
            self.status_label.setText(
                _("❌ <b>Not yet spendable</b><br/>"
                  "Some required conditions are not satisfied. Check which signatures "
                  "or timelocks are missing.")
            )
            self.status_label.setStyleSheet("color: red; font-size: 14px; padding: 12px;")
        
        # Update simulator tree with satisfaction highlighting
        self._update_simulator_tree()
    
    def _update_simulator_tree(self):
        """Update the simulator tree with satisfaction highlighting."""
        self.simulator_tree.clear()
        
        if not self.viz_root:
            return
        
        root_item = self._build_simulator_tree_item(self.viz_root, None)
        self.simulator_tree.addTopLevelItem(root_item)
        self.simulator_tree.expandAll()
    
    def _build_simulator_tree_item(
        self,
        node: VisualizationNode,
        parent_item: Optional[QTreeWidgetItem]
    ) -> QTreeWidgetItem:
        """Build tree item with satisfaction highlighting."""
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem()
        
        # Build label with satisfaction indicator
        label = node.label or node.type.value
        icon = self._get_icon_for_type(node.type)
        
        if node.satisfied is not None:
            if node.satisfied:
                status_icon = "✅" if node.relevant else "✓"
                color = "green" if node.relevant else "#888"
            else:
                status_icon = "❌" if node.relevant else "✗"
                color = "red" if node.relevant else "#ccc"
            
            full_label = f"{status_icon} {icon} {label}"
        else:
            full_label = f"{icon} {label}"
            color = "#000"
        
        item.setText(0, full_label)
        
        # Set color
        if color:
            item.setForeground(0, QColor(color))
        
        # Tooltip
        tooltip_parts = []
        if node.miniscript:
            tooltip_parts.append(f"Miniscript: {node.miniscript}")
        if node.satisfied is not None:
            tooltip_parts.append(f"Satisfied: {node.satisfied}")
        if node.relevant is not None:
            tooltip_parts.append(f"Relevant: {node.relevant}")
        if tooltip_parts:
            item.setToolTip(0, "\n".join(tooltip_parts))
        
        # Recursively add children
        for child_id in node.children:
            child_node = self.nodes_by_id.get(child_id)
            if child_node:
                self._build_simulator_tree_item(child_node, item)
        
        return item
