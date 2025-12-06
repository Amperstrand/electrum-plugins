"""
Path Details Dialog

Shows comprehensive information about a spending path, generated entirely
from the single source of truth (ContractDefinition).

Inspired by mempool.space's Taproot tree visualization, this dialog shows:
- Miniscript (symbolic - with role names)
- Miniscript (concrete - with actual keys)
- For Taproot: Leaf script, control block structure, leaf hash
- Required keys for this path
- Locktime requirements
- Technical details (leaf index, branch type)

All data is derived from ContractDefinition - no hardcoding.
"""

from typing import Dict, Any, Optional
import hashlib

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTextEdit, QGroupBox, QGridLayout, QPushButton, QApplication,
    QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from electrum.i18n import _
from electrum.gui.qt.util import WindowModalDialog, Buttons, CloseButton, WWLabel

from ..cltv_lib.contracts import CONTRACTS, ContractDefinition
from ..cltv_lib.contracts.definitions import SpendingPath
from ..cltv_lib.descriptors import get_miniscript, get_descriptor


class PathDetailsDialog(WindowModalDialog):
    """
    Dialog showing comprehensive details about a spending path.
    
    All information is derived from ContractDefinition - the single source of truth.
    """
    
    def __init__(
        self,
        parent,
        contract: ContractDefinition,
        path: SpendingPath,
        params: Dict[str, Any],
        output_type: str = 'p2wsh',  # 'p2wsh' or 'taproot'
        network: str = 'signet'
    ):
        title = f"{path.display_name} - {_('Details')}"
        super().__init__(parent, title)
        
        self.contract = contract
        self.path = path
        self.params = params
        self.output_type = output_type
        self.network = network
        
        self.setMinimumWidth(600)
        self.setup_ui()
    
    def setup_ui(self):
        """Build the dialog UI."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        self.setLayout(main_layout)
        
        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        content.setLayout(layout)
        
        # Header with path info
        header = self._create_header_section()
        layout.addWidget(header)
        
        # Miniscript section
        miniscript_section = self._create_miniscript_section()
        layout.addWidget(miniscript_section)
        
        # Taproot-specific section (script, control block, leaf hash)
        if self.output_type == 'taproot':
            taproot_section = self._create_taproot_section()
            layout.addWidget(taproot_section)
        
        # P2WSH-specific section (witness script structure)
        if self.output_type == 'p2wsh':
            p2wsh_section = self._create_p2wsh_section()
            layout.addWidget(p2wsh_section)
        
        # Required keys section
        keys_section = self._create_keys_section()
        layout.addWidget(keys_section)
        
        # Technical details section
        tech_section = self._create_technical_section()
        layout.addWidget(tech_section)
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
        
        # Buttons
        main_layout.addLayout(Buttons(CloseButton(self)))
    
    def _create_header_section(self) -> QFrame:
        """Create header with path name and description."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #f0f7ff;
                border: 1px solid #cce0ff;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        frame.setLayout(layout)
        
        # Path icon and name
        title_layout = QHBoxLayout()
        icon_label = QLabel(self.path.icon)
        icon_label.setStyleSheet("font-size: 24px;")
        title_layout.addWidget(icon_label)
        
        name_label = QLabel(f"<b>{self.path.display_name}</b>")
        name_label.setStyleSheet("font-size: 16px;")
        title_layout.addWidget(name_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # Description
        desc_label = WWLabel(self.path.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #555;")
        layout.addWidget(desc_label)
        
        # Locktime requirement
        if self.path.requires_locktime:
            locktime = self.params.get('locktime', 0)
            lock_label = QLabel(f"⏰ {_('Requires locktime')}: {locktime}")
            lock_label.setStyleSheet("color: #d35400; font-weight: bold;")
            layout.addWidget(lock_label)
        else:
            lock_label = QLabel(f"✓ {_('Available anytime')}")
            lock_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            layout.addWidget(lock_label)
        
        return frame
    
    def _create_miniscript_section(self) -> QGroupBox:
        """Create section showing miniscript expressions."""
        group = QGroupBox(_("Miniscript"))
        layout = QVBoxLayout()
        layout.setSpacing(12)
        group.setLayout(layout)
        
        # Build script_type for get_miniscript
        script_type = f"cltv_{self.contract.contract_type.value}_{self.output_type}"
        
        # Symbolic miniscript (with role names)
        symbolic_label = QLabel(_("Symbolic (with role names):"))
        symbolic_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(symbolic_label)
        
        try:
            symbolic_ms = get_miniscript(script_type, self.params, style='symbolic')
        except Exception as e:
            symbolic_ms = f"Error: {e}"
        
        symbolic_text = self._create_copyable_text(symbolic_ms)
        layout.addWidget(symbolic_text)
        
        # Concrete miniscript (with actual keys)
        concrete_label = QLabel(_("Concrete (with actual keys):"))
        concrete_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(concrete_label)
        
        try:
            concrete_ms = get_miniscript(script_type, self.params, style='concrete')
        except Exception as e:
            concrete_ms = f"Error: {e}"
        
        concrete_text = self._create_copyable_text(concrete_ms)
        layout.addWidget(concrete_text)
        
        # Path-specific miniscript (just this branch) - derive from taproot_leaves
        path_ms = self._get_path_miniscript()
        if path_ms:
            path_label = QLabel(_("This path's branch:"))
            path_label.setStyleSheet("font-weight: bold;")
            layout.addWidget(path_label)
            
            # Substitute params into path miniscript
            path_ms_concrete = self._substitute_params(path_ms)
            path_text = self._create_copyable_text(path_ms_concrete)
            layout.addWidget(path_text)
        
        return group
    
    def _get_path_miniscript(self) -> str:
        """Get the miniscript for this specific path from taproot_leaves."""
        # Use taproot_leaves if available
        if self.contract.taproot_leaves and self.path.leaf_index < len(self.contract.taproot_leaves):
            return self.contract.taproot_leaves[self.path.leaf_index]
        return ""
    
    def _create_taproot_section(self) -> QGroupBox:
        """Create Taproot-specific section showing script path spend details.
        
        Inspired by mempool.space's Taproot tree visualization.
        Shows: leaf script, control block structure, leaf hash, tree position.
        """
        group = QGroupBox(_("Taproot Script Path Details"))
        layout = QVBoxLayout()
        layout.setSpacing(12)
        group.setLayout(layout)
        
        # Explanation
        intro = WWLabel(_(
            "When spending via script-path, the witness contains:\n"
            "• Stack elements to satisfy the script\n"
            "• The leaf script (tapscript)\n"
            "• The control block (proves script is in the tree)"
        ))
        intro.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(intro)
        
        # Leaf Script (Tapscript)
        leaf_ms = self._get_path_miniscript()
        if leaf_ms:
            script_label = QLabel(_("Leaf Script (Tapscript):"))
            script_label.setStyleSheet("font-weight: bold;")
            layout.addWidget(script_label)
            
            # Show both symbolic and with values
            leaf_concrete = self._substitute_params(leaf_ms)
            script_text = self._create_copyable_text(leaf_concrete)
            layout.addWidget(script_text)
        
        # Leaf Version
        version_label = QLabel(_("Leaf Version:"))
        version_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(version_label)
        
        version_info = self._create_copyable_text("0xc0 (Tapscript, BIP-342)")
        layout.addWidget(version_info)
        
        # Tree Position
        pos_label = QLabel(_("Tree Position:"))
        pos_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(pos_label)
        
        num_leaves = len(self.contract.taproot_leaves) if self.contract.taproot_leaves else 1
        depth = 0
        if num_leaves > 1:
            import math
            depth = math.ceil(math.log2(num_leaves))
        
        pos_text = f"Leaf {self.path.leaf_index} of {num_leaves} (depth: {depth})"
        pos_info = self._create_copyable_text(pos_text)
        layout.addWidget(pos_info)
        
        # Control Block Structure
        cb_label = QLabel(_("Control Block Structure:"))
        cb_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(cb_label)
        
        cb_structure = (
            "control_byte (1 byte): leaf_version | output_key_parity\n"
            "internal_key (32 bytes): x-only internal pubkey\n"
            f"merkle_path ({depth} × 32 bytes): sibling hashes to root"
        )
        cb_text = self._create_copyable_text(cb_structure)
        layout.addWidget(cb_text)
        
        # Witness Stack Order
        witness_label = QLabel(_("Witness Stack (bottom to top):"))
        witness_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(witness_label)
        
        # Build witness description from required_keys
        witness_items = []
        for key_name in self.path.required_keys:
            key_role = self.contract.get_key_role(key_name)
            display = key_role.display_name if key_role else key_name
            witness_items.append(f"<signature for {display}>")
        
        if self.path.requires_preimage:
            witness_items.append("<preimage>")
        
        witness_items.append("<leaf_script>")
        witness_items.append("<control_block>")
        
        witness_text = "\n".join(f"{i+1}. {item}" for i, item in enumerate(witness_items))
        witness_info = self._create_copyable_text(witness_text)
        layout.addWidget(witness_info)
        
        return group
    
    def _create_p2wsh_section(self) -> QGroupBox:
        """Create P2WSH-specific section showing witness script structure."""
        group = QGroupBox(_("P2WSH Witness Details"))
        layout = QVBoxLayout()
        layout.setSpacing(12)
        group.setLayout(layout)
        
        # Explanation
        intro = WWLabel(_(
            "P2WSH spends require a witness with:\n"
            "• Stack elements to satisfy the script\n"
            "• The witness script (redeem script)"
        ))
        intro.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(intro)
        
        # Branch selection
        branch_label = QLabel(_("Script Branch:"))
        branch_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(branch_label)
        
        if self.path.is_if_branch:
            branch_text = "IF branch (first condition) - push OP_TRUE (0x01) to select"
        else:
            branch_text = "ELSE branch (second condition) - push OP_FALSE (empty) to select"
        
        branch_info = self._create_copyable_text(branch_text)
        layout.addWidget(branch_info)
        
        # CHECKMULTISIG handling
        if self.contract.p2wsh_uses_checkmultisig():
            multi_label = QLabel(_("CHECKMULTISIG Note:"))
            multi_label.setStyleSheet("font-weight: bold; color: #d35400;")
            layout.addWidget(multi_label)
            
            multi_text = (
                "⚠️ This script uses OP_CHECKMULTISIG which has an off-by-one bug.\n"
                "The witness must include a dummy OP_0 (empty element) at the bottom."
            )
            multi_info = self._create_copyable_text(multi_text)
            layout.addWidget(multi_info)
        
        # Witness Stack Order
        witness_label = QLabel(_("Witness Stack (bottom to top):"))
        witness_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(witness_label)
        
        witness_items = []
        
        # Dummy for CHECKMULTISIG
        if self.contract.p2wsh_uses_checkmultisig():
            witness_items.append("<dummy OP_0> (CHECKMULTISIG bug workaround)")
        
        # Signatures
        for key_name in self.path.required_keys:
            key_role = self.contract.get_key_role(key_name)
            display = key_role.display_name if key_role else key_name
            witness_items.append(f"<signature for {display}>")
        
        # Branch selector
        if not self.path.is_if_branch:
            witness_items.append("<empty> (selects ELSE branch)")
        else:
            witness_items.append("<0x01> (selects IF branch)")
        
        # Witness script
        witness_items.append("<witness_script>")
        
        witness_text = "\n".join(f"{i+1}. {item}" for i, item in enumerate(witness_items))
        witness_info = self._create_copyable_text(witness_text)
        layout.addWidget(witness_info)
        
        return group
    
    def _create_keys_section(self) -> QGroupBox:
        """Create section showing required keys for this path."""
        group = QGroupBox(_("Required Keys"))
        layout = QVBoxLayout()
        layout.setSpacing(8)
        group.setLayout(layout)
        
        if not self.path.required_keys:
            no_keys_label = QLabel(_("No keys required for this path"))
            no_keys_label.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(no_keys_label)
            return group
        
        # Grid layout for keys
        grid = QGridLayout()
        grid.setSpacing(8)
        
        for row, key_name in enumerate(self.path.required_keys):
            # Get key role info from contract
            key_role = self.contract.get_key_role(key_name)
            
            # Key icon and name
            icon = key_role.icon if key_role else '🔑'
            display_name = key_role.display_name if key_role else key_name.title()
            
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 16px;")
            grid.addWidget(icon_label, row, 0)
            
            name_label = QLabel(f"<b>{display_name}</b>")
            grid.addWidget(name_label, row, 1)
            
            # Key value (if available in params)
            key_value = self.params.get(key_name, '')
            if isinstance(key_value, bytes):
                key_value = key_value.hex()
            
            if key_value:
                # Truncate long keys for display
                display_value = key_value if len(key_value) <= 20 else f"{key_value[:10]}...{key_value[-10:]}"
                value_label = QLabel(display_value)
                value_label.setStyleSheet("font-family: monospace; color: #555;")
                value_label.setToolTip(key_value)  # Full value on hover
                
                # Copy button
                copy_btn = QPushButton("📋")
                copy_btn.setFixedSize(24, 24)
                copy_btn.setToolTip(_("Copy to clipboard"))
                copy_btn.clicked.connect(lambda checked, v=key_value: self._copy_to_clipboard(v))
                
                grid.addWidget(value_label, row, 2)
                grid.addWidget(copy_btn, row, 3)
            else:
                missing_label = QLabel(_("(not set)"))
                missing_label.setStyleSheet("color: #888; font-style: italic;")
                grid.addWidget(missing_label, row, 2)
        
        layout.addLayout(grid)
        return group
    
    def _create_technical_section(self) -> QGroupBox:
        """Create section with technical details."""
        group = QGroupBox(_("Technical Details"))
        layout = QGridLayout()
        layout.setSpacing(8)
        group.setLayout(layout)
        
        row = 0
        
        # Contract type
        layout.addWidget(QLabel(_("Contract Type:")), row, 0)
        layout.addWidget(QLabel(f"<b>{self.contract.name}</b>"), row, 1)
        row += 1
        
        # Output type
        layout.addWidget(QLabel(_("Output Type:")), row, 0)
        output_display = "Taproot (P2TR)" if self.output_type == 'taproot' else "SegWit v0 (P2WSH)"
        layout.addWidget(QLabel(f"<b>{output_display}</b>"), row, 1)
        row += 1
        
        # Leaf index (for Taproot)
        if self.output_type == 'taproot':
            layout.addWidget(QLabel(_("Taproot Leaf Index:")), row, 0)
            layout.addWidget(QLabel(f"<b>{self.path.leaf_index}</b>"), row, 1)
            row += 1
        
        # P2WSH branch
        if self.output_type == 'p2wsh':
            layout.addWidget(QLabel(_("P2WSH Branch:")), row, 0)
            branch = "IF (first)" if self.path.is_if_branch else "ELSE (second)"
            layout.addWidget(QLabel(f"<b>{branch}</b>"), row, 1)
            row += 1
        
        # Uses CHECKMULTISIG (P2WSH only)
        if self.output_type == 'p2wsh' and self.contract.p2wsh_uses_checkmultisig():
            layout.addWidget(QLabel(_("Uses CHECKMULTISIG:")), row, 0)
            layout.addWidget(QLabel("<b>Yes</b> (dummy OP_0 required)"), row, 1)
            row += 1
        
        # Locktime value
        locktime = self.params.get('locktime', 0)
        layout.addWidget(QLabel(_("Locktime:")), row, 0)
        layout.addWidget(QLabel(f"<b>{locktime}</b>"), row, 1)
        row += 1
        
        # Network
        layout.addWidget(QLabel(_("Network:")), row, 0)
        layout.addWidget(QLabel(f"<b>{self.network}</b>"), row, 1)
        
        return group
    
    def _create_copyable_text(self, text: str) -> QFrame:
        """Create a text display with copy button."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        frame.setLayout(layout)
        
        # Text (monospace, word-wrap)
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(text_label, stretch=1)
        
        # Copy button
        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(28, 28)
        copy_btn.setToolTip(_("Copy to clipboard"))
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(text))
        layout.addWidget(copy_btn)
        
        return frame
    
    def _substitute_params(self, ms: str) -> str:
        """Substitute parameter values into a miniscript string."""
        result = ms
        
        # Substitute locktime
        locktime = self.params.get('locktime')
        if locktime is not None:
            result = result.replace('locktime', str(locktime))
        
        # Substitute keys
        for spec in self.contract.params:
            if spec.param_type == 'pubkey':
                key_value = self.params.get(spec.name)
                if key_value:
                    if isinstance(key_value, bytes):
                        key_value = key_value.hex()
                    result = result.replace(spec.name, key_value)
        
        return result
    
    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)


def show_path_details(
    parent,
    contract_name: str,
    path_name: str,
    params: Dict[str, Any],
    output_type: str = 'p2wsh',
    network: str = 'signet'
) -> None:
    """
    Show path details dialog.
    
    Convenience function to show details for a path.
    
    Args:
        parent: Parent widget
        contract_name: Contract name (e.g., 'escrow', 'hodl')
        path_name: Path name (e.g., 'cooperative', 'refund')
        params: Contract parameters
        output_type: 'p2wsh' or 'taproot'
        network: Network name
    """
    contract = CONTRACTS.get(contract_name)
    if not contract:
        raise ValueError(f"Unknown contract: {contract_name}")
    
    path = contract.get_path(path_name)
    if not path:
        raise ValueError(f"Unknown path '{path_name}' for contract '{contract_name}'")
    
    dialog = PathDetailsDialog(parent, contract, path, params, output_type, network)
    dialog.exec()

