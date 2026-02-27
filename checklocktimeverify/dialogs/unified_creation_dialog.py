"""
Unified Contract Creation Dialog

Creates addresses for any contract type by generating UI from ContractDefinition.
This is the Phase 4 implementation that replaces 5 separate creation dialogs.

Usage:
    dialog = UnifiedCreationDialog(parent, plugin, 'escrow')
    dialog.exec()

Or with contract selector:
    dialog = UnifiedCreationDialog(parent, plugin)  # Shows contract picker
    dialog.exec()
"""

from typing import Optional, Dict, Any, List

from electrum.crypto import hash_160

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QLabel, QLineEdit, QGroupBox, QTextEdit, QPushButton,
    QComboBox, QRadioButton, QButtonGroup
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from electrum import constants
from electrum.i18n import _
from electrum.gui.qt.util import (
    WWLabel, EnterButton, Buttons, MONOSPACE_FONT, 
    CloseButton, OkButton, WindowModalDialog, HelpLabel, ColorScheme
)
from electrum.gui.qt.locktimeedit import LockTimeEdit
from electrum.gui.qt.qrtextedit import ShowQRTextEdit
from electrum.bitcoin import bfh
import logging

logger = logging.getLogger(__name__)

from ..cltv_lib.contracts import (
    ContractDefinition, ContractType, ParamSpec, CONTRACTS
)
from ..cltv_lib.registry import get_builder
from ..cltv_lib.address import generate_address
from ..test_keys import get_test_pubkey


class UnifiedCreationDialog(WindowModalDialog):
    """
    Unified contract creation dialog.
    
    Generates UI dynamically from ContractDefinition metadata.
    Supports all contract types with a single dialog class.
    
    Features:
    - Contract type selector (if not specified)
    - P2WSH/Taproot selector
    - Form inputs generated from ParamSpec
    - Data publishing special handling (preimage → hash)
    - Automatic test key loading
    """
    
    def __init__(self, parent, plugin, contract_name: str = None):
        """
        Initialize creation dialog.
        
        Args:
            parent: Parent widget (main window)
            plugin: Plugin instance
            contract_name: Contract to create (None = show selector)
        """
        self.parent = parent
        self.plugin = plugin
        self.wallet = parent.wallet if hasattr(parent, 'wallet') else None
        self.network = parent.network if hasattr(parent, 'network') else None
        self.config = getattr(plugin, 'config', None) or getattr(parent, 'config', None)
        
        # Contract selection
        self.contract_name = contract_name
        self.contract: Optional[ContractDefinition] = None
        if contract_name:
            self.contract = CONTRACTS.get(contract_name)
        
        # UI elements
        self.contract_combo: Optional[QComboBox] = None
        self.witness_version_group: Optional[QButtonGroup] = None
        self.p2wsh_radio: Optional[QRadioButton] = None
        self.taproot_radio: Optional[QRadioButton] = None
        self.locktime_edit: Optional[LockTimeEdit] = None  # For backwards compatibility (single locktime)
        self.locktime_edits: Dict[str, LockTimeEdit] = {}  # For multiple locktime parameters
        self.param_inputs: Dict[str, QWidget] = {}
        self.data_input: Optional[QTextEdit] = None
        self.data_hash_display: Optional[QLineEdit] = None
        
        # Determine title
        title = self.contract.name if self.contract else _("Create CLTV Contract")
        
        WindowModalDialog.__init__(self, parent, title)
        self.setMinimumWidth(650)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Contract selector (if no contract specified)
        if not self.contract:
            self._add_contract_selector(layout)
        
        # Description section
        self.desc_label = WWLabel("")
        layout.addWidget(self.desc_label)
        self._update_description()
        
        # Form section
        self.form_group = QGroupBox(_("Parameters"))
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(8)
        self.form_group.setLayout(self.form_layout)
        layout.addWidget(self.form_group)
        
        # Build form for current contract
        if self.contract:
            self._build_form_inputs()
        
        # Create button
        self.create_btn = EnterButton(_("Create Address"), self.on_create_address)
        if not self.contract:
            self.create_btn.setEnabled(False)
        layout.addWidget(self.create_btn)
        
        # Results section (hidden initially)
        self.results_group = QGroupBox(_("Generated Address"))
        self.results_group.setVisible(False)
        results_layout = QVBoxLayout()
        
        self.address_label = WWLabel(_("Address:"))
        results_layout.addWidget(self.address_label)
        
        self.address_display = ShowQRTextEdit(config=self.config)
        self.address_display.setMaximumHeight(100)
        results_layout.addWidget(self.address_display)
        
        self.script_label = WWLabel(_("Witness Script (hex):"))
        results_layout.addWidget(self.script_label)
        
        self.script_display = QTextEdit()
        self.script_display.setReadOnly(True)
        self.script_display.setMaximumHeight(80)
        self.script_display.setFont(QFont(MONOSPACE_FONT))
        results_layout.addWidget(self.script_display)
        
        self.results_group.setLayout(results_layout)
        layout.addWidget(self.results_group)
        
        # Close button
        layout.addLayout(Buttons(CloseButton(self)))
    
    def _add_contract_selector(self, layout: QVBoxLayout):
        """Add contract type selector."""
        selector_group = QGroupBox(_("Contract Type"))
        selector_layout = QHBoxLayout()
        
        self.contract_combo = QComboBox()
        self.contract_combo.addItem(_("-- Select Contract Type --"), None)
        
        # Add all contracts with icons
        for name, contract in CONTRACTS.items():
            display = f"{contract.icon} {contract.name}"
            self.contract_combo.addItem(display, name)
        
        self.contract_combo.currentIndexChanged.connect(self._on_contract_changed)
        selector_layout.addWidget(self.contract_combo)
        
        selector_group.setLayout(selector_layout)
        layout.addWidget(selector_group)
    
    def _on_contract_changed(self, index: int):
        """Handle contract selection change."""
        contract_name = self.contract_combo.itemData(index)
        
        if contract_name:
            self.contract_name = contract_name
            self.contract = CONTRACTS.get(contract_name)
            self._update_description()
            self._rebuild_form()
            self.create_btn.setEnabled(True)
        else:
            self.contract = None
            self.desc_label.setText("")
            self._clear_form()
            self.create_btn.setEnabled(False)
    
    def _update_description(self):
        """Update description based on current contract."""
        if not self.contract:
            self.desc_label.setText("")
            return
        
        html = f"<b>{self.contract.icon} {self.contract.name}</b><br/><br/>"
        
        if self.contract.bip_reference:
            html += f"<i>{self.contract.bip_reference}</i><br/><br/>"
        
        html += f"{self.contract.description}<br/><br/>"
        
        if self.contract.short_description:
            html += f"<b>Summary:</b> {self.contract.short_description}<br/><br/>"
        
        # Use cases
        if self.contract.use_cases:
            html += "<b>Use Cases:</b><br/>"
            for use_case in self.contract.use_cases:
                html += f"• {use_case}<br/>"
            html += "<br/>"
        
        # Spending paths
        html += "<b>Spending Paths:</b><br/>"
        for path in self.contract.paths:
            locktime_note = " (after locktime)" if path.requires_locktime else " (anytime)"
            html += f"• <b>{path.display_name}</b>{locktime_note}<br/>"
        
        self.desc_label.setText(html)
    
    def _clear_form(self):
        """Clear all form inputs."""
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.param_inputs.clear()
        self.locktime_edit = None
        self.locktime_edits.clear()
        self.witness_version_group = None
        self.p2wsh_radio = None
        self.taproot_radio = None
        self.data_input = None
        self.data_hash_display = None
    
    def _rebuild_form(self):
        """Rebuild form inputs for current contract."""
        self._clear_form()
        if self.contract:
            self._build_form_inputs()
    
    def _build_form_inputs(self):
        """Build form inputs from contract's ParamSpec list."""
        if not self.contract:
            return
        
        # Witness version selector (always first)
        self._add_witness_version_selector()
        
        # Generate inputs from ParamSpec
        for param in self.contract.params:
            if param.param_type == 'locktime':
                self._add_locktime_input(param)
            elif param.param_type == 'pubkey':
                self._add_pubkey_input(param)
            elif param.param_type == 'hash160':
                # For data publishing, show data input instead of hash input
                if self.contract.contract_type == ContractType.DATA_PUBLISHING:
                    self._add_data_input(param)
                else:
                    self._add_hash_input(param)
            elif param.param_type == 'preimage':
                # Preimage is handled by data input above
                pass
    
    def _add_witness_version_selector(self):
        """Add P2WSH/Taproot selector."""
        group_box = QGroupBox(_("Address Type"))
        group_layout = QVBoxLayout()
        
        self.p2wsh_radio = QRadioButton(_("P2WSH (SegWit v0) - Standard, widely supported"))
        self.taproot_radio = QRadioButton(_("Taproot (SegWit v1) - Smaller, more private"))
        
        self.p2wsh_radio.setChecked(True)
        
        self.witness_version_group = QButtonGroup()
        self.witness_version_group.addButton(self.p2wsh_radio, 0)
        self.witness_version_group.addButton(self.taproot_radio, 1)
        
        group_layout.addWidget(self.p2wsh_radio)
        group_layout.addWidget(self.taproot_radio)
        
        note = QLabel(
            "<small><i>Taproot (tb1p...) uses Schnorr signatures and is more "
            "efficient than P2WSH (tb1q...). Both are equally secure.</i></small>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; padding: 5px;")
        group_layout.addWidget(note)
        
        group_box.setLayout(group_layout)
        self.form_layout.addRow(group_box)
    
    def _add_locktime_input(self, param: ParamSpec):
        """Add locktime input widget."""
        default_locktime = self._get_default_locktime()
        locktime_edit = LockTimeEdit(self)
        locktime_edit.set_locktime(default_locktime)
        locktime_edit.setToolTip(_(param.description))
        
        # Store in dict for multiple locktimes, and also set single for backwards compatibility
        self.locktime_edits[param.name] = locktime_edit
        if self.locktime_edit is None:
            # First locktime: also set for backwards compatibility
            self.locktime_edit = locktime_edit
        
        # Use param name as label (e.g., "Locktime (60 months)" or just "Locktime")
        if param.name == 'locktime':
            label = _("Locktime")
        else:
            # Extract meaningful part from name (e.g., "locktime_60m" -> "Locktime (60 months)")
            label = param.name.replace('locktime_', '').replace('_', ' ').title()
            if '60m' in param.name.lower():
                label = _("Locktime (60 months)")
            elif '66m' in param.name.lower():
                label = _("Locktime (66 months)")
            else:
                label = param.description or param.name
        
        self.form_layout.addRow(label + ":", locktime_edit)
    
    def _add_pubkey_input(self, param: ParamSpec):
        """Add pubkey input with test key button."""
        # Find matching key role for better label
        role = self.contract.get_key_role(param.name)
        label = role.display_name if role else param.name.replace('_', ' ').title()
        
        # Use test_key_name from ParamSpec (single source of truth)
        test_key_name = param.test_key_name
        
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        
        pubkey_input = QLineEdit()
        pubkey_input.setFont(QFont(MONOSPACE_FONT))
        pubkey_input.setPlaceholderText(_(f"{label} public key (33 bytes hex)"))
        pubkey_input.setToolTip(_(param.description))
        row_layout.addWidget(pubkey_input, stretch=1)
        
        # Test key button (only if test_key_name is defined)
        if test_key_name:
            test_btn = QPushButton(_("Test Key"))
            test_btn.setToolTip(_(f"Load '{test_key_name}' demo key for testing"))
            test_btn.clicked.connect(lambda checked, n=param.name, t=test_key_name: self._load_test_key(n, t))
            row_layout.addWidget(test_btn, stretch=0)
        
        # Icon from key role
        icon = role.icon if role else ""
        label_text = f"{icon} {label}"
        
        self.form_layout.addRow(label_text + ":", row)
        self.param_inputs[param.name] = pubkey_input
    
    def _add_hash_input(self, param: ParamSpec):
        """Add hash input (for non-data-publishing contracts)."""
        hash_input = QLineEdit()
        hash_input.setFont(QFont(MONOSPACE_FONT))
        hash_input.setPlaceholderText(_("HASH160 (20 bytes / 40 hex chars)"))
        hash_input.setToolTip(_(param.description))
        
        self.form_layout.addRow(_(param.description) + ":", hash_input)
        self.param_inputs[param.name] = hash_input
    
    def _add_data_input(self, param: ParamSpec):
        """Add data input with automatic hash generation (for data publishing)."""
        data_widget = QWidget()
        data_layout = QVBoxLayout()
        data_layout.setContentsMargins(0, 0, 0, 0)
        data_layout.setSpacing(8)
        
        # Data text input
        self.data_input = QTextEdit()
        self.data_input.setMaximumHeight(100)
        self.data_input.setPlaceholderText(
            _("Enter data to publish (e.g., 'Secret information')\n"
              "HASH160 will be generated automatically")
        )
        self.data_input.textChanged.connect(self._update_data_hash)
        data_layout.addWidget(self.data_input)
        
        # Hash display
        hash_row = QHBoxLayout()
        hash_row.addWidget(QLabel(_("Data Hash (HASH160):")))
        
        self.data_hash_display = QLineEdit()
        self.data_hash_display.setReadOnly(True)
        self.data_hash_display.setFont(QFont(MONOSPACE_FONT))
        self.data_hash_display.setPlaceholderText(_("Hash will appear here (20 bytes / 40 hex chars)"))
        hash_row.addWidget(self.data_hash_display, 1)
        
        data_layout.addLayout(hash_row)
        
        # Warning
        warning = QLabel(
            "<small><font color='#c62828'> When publisher claims, "
            "the data becomes PUBLIC on the blockchain!</font></small>"
        )
        warning.setWordWrap(True)
        data_layout.addWidget(warning)
        
        data_widget.setLayout(data_layout)
        self.form_layout.addRow(_(" Data to Publish:"), data_widget)
    
    def _update_data_hash(self):
        """Update data hash display when data changes."""
        if not self.data_input or not self.data_hash_display:
            return
        
        data_text = self.data_input.toPlainText()
        if not data_text:
            self.data_hash_display.setText("")
            self.data_hash_display.setStyleSheet("")
            return
        
        # Compute HASH160 using Electrum native function
        data_bytes = data_text.encode('utf-8')
        data_hash = hash_160(data_bytes)
        
        self.data_hash_display.setText(data_hash.hex())
        self.data_hash_display.setStyleSheet(f"background-color: {ColorScheme.GREEN.as_color().name()};")
    
    def _load_test_key(self, input_name: str, test_key_name: str):
        """Load test key into pubkey input."""
        try:
            pubkey = get_test_pubkey(test_key_name)
            if input_name in self.param_inputs:
                self.param_inputs[input_name].setText(pubkey)
        except Exception as e:
            self.show_error(_("Failed to load test key: ") + str(e))
    
    def _get_default_locktime(self) -> int:
        """Get default locktime (current height + 3)."""
        try:
            return self.plugin.get_default_locktime(self.wallet, offset_blocks=3)
        except Exception:
            return 1003
    
    def _get_witness_version(self) -> int:
        """Get selected witness version (0=P2WSH, 1=Taproot)."""
        if self.taproot_radio and self.taproot_radio.isChecked():
            return 1
        return 0
    
    def collect_params(self) -> Dict[str, Any]:
        """Collect parameters from form inputs."""
        params = {}
        
        # Collect all locktime parameters
        if self.locktime_edits:
            # Multiple locktimes: collect all
            for param_name, locktime_edit in self.locktime_edits.items():
                params[param_name] = locktime_edit.get_locktime()
            # Also set 'locktime' for backwards compatibility (use first one)
            if 'locktime' not in params and self.locktime_edit:
                params['locktime'] = self.locktime_edit.get_locktime()
        elif self.locktime_edit:
            # Single locktime: backwards compatibility
            params['locktime'] = self.locktime_edit.get_locktime()
        
        # Pubkeys and other params
        for name, widget in self.param_inputs.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
                if value:
                    params[name] = value
        
        # Data publishing special handling
        if self.contract.contract_type == ContractType.DATA_PUBLISHING:
            if self.data_input:
                data_text = self.data_input.toPlainText()
                if data_text:
                    # Store both preimage and hash
                    data_bytes = data_text.encode('utf-8')
                    params['data_preimage'] = data_bytes.hex()
                    
                    # Use Electrum native hash_160 (RIPEMD160(SHA256(x)))
                    data_hash = hash_160(data_bytes)
                    params['data_hash'] = data_hash.hex()
        
        # NOTE: param_mapping is NOT needed here because:
        # - Form inputs use param.name directly (e.g., 'alice', not 'alice_pubkey')
        # - param_mapping is only for backwards compatibility when LOADING old stored addresses
        # - That compatibility is handled in address_regenerator.py and generic.py
        
        return params
    
    def on_create_address(self):
        """Handle create address button click."""
        if not self.contract:
            self.show_error(_("Please select a contract type"))
            return
        
        try:
            params = self.collect_params()
            witness_version = self._get_witness_version()
            
            # Detect network
            network_type = 'signet' if constants.net.GENESIS.startswith('00000008819873') else 'testnet'
            
            # Build address based on contract type and witness version
            addr_info = self._build_address(params, witness_version, network_type)
            
            # Determine script type
            output_type = 'taproot' if witness_version == 1 else 'p2wsh'
            script_type = f"cltv_{self.contract.contract_type.value}_{output_type}"
            
            # Display results
            self._display_results(addr_info, witness_version)
            
            # Save to storage
            self._save_to_storage(addr_info, params, script_type, witness_version)
            
            # Success message
            addr_type_name = "Taproot" if witness_version == 1 else "P2WSH"
            self.show_message(
                _(f"{addr_type_name} address created successfully!") + "\n\n" +
                _("Address: ") + addr_info['address']
            )
            
        except Exception as e:
            # Critical error - log with full traceback and show to user
            logger.error(f"[CLTV] CRITICAL: Failed to create address: {e}")
            import traceback
            logger.error(f"[CLTV] Traceback:\n{traceback.format_exc()}")
            self.show_error(_("Failed to create address: ") + str(e))
            # Exception is logged and shown to user - no need to re-raise in GUI context
    
    def _build_address(self, params: Dict[str, Any], witness_version: int, network_type: str) -> Dict[str, Any]:
        """
        Build address using generic UnifiedContractBuilder.
        
        This is now a single line - all contract-specific logic is in ContractDefinition!
        """
        from ..cltv_lib.builders.unified.generic import build_contract
        
        output_type = 'taproot' if witness_version == 1 else 'p2wsh'
        contract_name = self.contract.contract_type.value
        
        return build_contract(
            contract_name=contract_name,
            params=params,
            output_type=output_type,
            network=network_type
        )
    
    def _display_results(self, addr_info: Dict[str, Any], witness_version: int):
        """Display generated address."""
        self.results_group.setVisible(True)
        
        address = addr_info['address']
        addr_type = 'Taproot' if witness_version == 1 else 'P2WSH'
        script_label = 'Tapscript (hex):' if witness_version == 1 else 'Witness Script (hex):'
        
        self.address_label.setText(_(f"Address ({addr_type}):"))
        self.script_label.setText(_(script_label))
        self.address_display.setText(address)
        self.address_display.repaint()
        
        script_hex = addr_info.get('script_hex', '')
        self.script_display.setPlainText(script_hex)
    
    def _save_to_storage(self, addr_info: Dict[str, Any], params: Dict[str, Any], 
                        script_type: str, witness_version: int):
        """Save address to plugin storage.
        
        Raises:
            RuntimeError: If plugin is not available
            ValueError: If required parameters are missing
            RuntimeError: If storage write fails
        """
        if not self.plugin:
            raise RuntimeError("Plugin not available - cannot save address")
        
        logger.info(f"[CLTV] Saving address: {addr_info['address']}")
        logger.info(f"[CLTV] Script type: {script_type}")
        
        # Prepare storage data
        storage_data = {
            'script_hex': addr_info['script_hex'],
            'script_type': script_type,
            'witness_version': witness_version,
            'params': params,
            'output_type': 'taproot' if witness_version == 1 else 'p2wsh',
        }
        
        # Add Taproot-specific fields
        if witness_version == 1:
            if 'internal_key' in addr_info:
                storage_data['internal_key'] = addr_info['internal_key']
            if 'output_key' in addr_info:
                storage_data['output_key'] = addr_info['output_key']
            if 'control_block' in addr_info:
                storage_data['control_block'] = addr_info['control_block']
        
        # save_timelock_data now raises exceptions instead of returning False
        self.plugin.save_timelock_data(
            address=addr_info['address'],
            wallet=self.wallet,
            **storage_data
        )
        
        logger.info(f"[CLTV] Address saved successfully")
        
        # UI will refresh automatically via Electrum's hooks when address is detected


__all__ = ['UnifiedCreationDialog']

