"""
UI Generator - Generate dialog components from contract definitions.

This module provides functions to generate UI components (Qt widgets)
directly from ContractDefinition metadata. This ensures the UI always
matches the contract's actual behavior.

Usage:
    from dialogs.ui_generator import generate_status_section, generate_key_section
    
    contract = CONTRACTS['escrow']
    status_group = generate_status_section(contract, params, current_height, balance)
    key_group = generate_key_section(contract, params)
"""

from typing import Dict, Any, Optional, Callable, List

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGroupBox, QWidget, QLabel
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from electrum.i18n import _
from electrum.gui.qt.util import (
    ColorScheme, ButtonsLineEdit, ShowQRLineEdit, MONOSPACE_FONT,
    WWLabel, OkButton
)
from electrum.gui.qt.qrtextedit import ShowQRTextEdit

from ..cltv_lib.contracts import ContractDefinition, SpendingPath, KeyRole, CONTRACTS


def get_contract_for_script_type(script_type: str) -> Optional[ContractDefinition]:
    """
    Get ContractDefinition for a script_type.
    
    Handles mapping from script_type (e.g., 'cltv_escrow_p2wsh') to contract name.
    
    Args:
        script_type: Script type like 'cltv_escrow_p2wsh' or 'cltv_hodl'
    
    Returns:
        ContractDefinition or None if not found
    """
    # Remove 'cltv_' prefix and output type suffix
    name = script_type.replace('cltv_', '')
    name = name.replace('_p2wsh', '').replace('_taproot', '')
    
    # v12.0.0: No legacy mappings - use canonical names from CONTRACTS
    return CONTRACTS.get(name)


def generate_status_section(
    contract: ContractDefinition,
    params: Dict[str, Any],
    current_height: int,
    balance: int,
    sweep_callback: Optional[Callable[[str], None]] = None,
    config: Any = None,
    parent=None
) -> QGroupBox:
    """
    Generate a status section for any contract type.
    
    Dynamically creates:
    - Contract name and description
    - Locktime status (locked/unlocked)
    - Balance display
    - Path-specific sweep buttons
    
    Args:
        contract: ContractDefinition
        params: Address parameters (locktime, pubkeys, etc.)
        current_height: Current blockchain height
        balance: Address balance in satoshis
        sweep_callback: Function to call when sweep button clicked (receives path name)
        config: Electrum config for formatting amounts
    
    Returns:
        QGroupBox with status UI
    """
    group = QGroupBox(_(contract.name))
    layout = QVBoxLayout()
    
    # BIP reference
    if contract.bip_reference:
        bip_label = WWLabel(f"<i>{_(contract.bip_reference)}</i>")
        bip_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(bip_label)
    
    # Short description
    if contract.short_description:
        desc_label = WWLabel(_(contract.short_description))
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
    
    # Locktime status
    locktime = params.get('locktime', 0)
    is_locked = current_height < locktime
    blocks_remaining = max(0, locktime - current_height)
    
    locktime_widget = _create_locktime_status(locktime, current_height, is_locked, blocks_remaining)
    layout.addWidget(locktime_widget)
    
    # Balance
    balance_widget = _create_balance_display(balance, config)
    layout.addWidget(balance_widget)
    
    # Spending path buttons
    spending_label = WWLabel(_("Spending Paths:"))
    layout.addWidget(spending_label)
    
    for path in contract.paths:
        btn = generate_path_button(
            path=path,
            locktime=locktime,
            current_height=current_height,
            balance=balance,
            sweep_callback=sweep_callback,
            parent=parent
        )
        layout.addWidget(btn)
    
    group.setLayout(layout)
    return group


def generate_path_button(
    path: SpendingPath,
    locktime: int,
    current_height: int,
    balance: int,
    sweep_callback: Optional[Callable[[str], None]] = None,
    parent=None
):
    """
    Generate a sweep button for a specific spending path.
    
    Automatically determines availability based on:
    - Balance > 0
    - Locktime requirement satisfied
    
    Args:
        path: SpendingPath definition
        locktime: Script locktime
        current_height: Current blockchain height
        balance: Address balance in satoshis
        sweep_callback: Function to call when clicked (receives path.name)
    
    Returns:
        Configured OkButton
    """
    btn = OkButton(parent, _(path.display_name))
    
    # Determine availability
    is_locked = current_height < locktime
    blocks_remaining = max(0, locktime - current_height)
    
    if balance == 0:
        btn.setEnabled(False)
        btn.setToolTip(_("No funds to sweep"))
        btn.setStyleSheet(_get_disabled_button_style())
    elif path.requires_locktime and is_locked:
        btn.setEnabled(False)
        tooltip = _(f"Available after block {locktime} ({blocks_remaining} blocks remaining)")
        btn.setToolTip(tooltip)
        btn.setStyleSheet(_get_locked_button_style())
    else:
        btn.setEnabled(True)
        tooltip = _(path.description)
        if path.warning:
            tooltip += f"\n\n{path.warning}"
        btn.setToolTip(tooltip)
        btn.setStyleSheet(_get_available_button_style())
        
        # Connect callback
        if sweep_callback:
            btn.clicked.connect(lambda checked, p=path.name: sweep_callback(p))
    
    return btn


def generate_key_section(
    contract: ContractDefinition,
    params: Dict[str, Any]
) -> QGroupBox:
    """
    Generate key display section based on contract's key roles.
    
    Args:
        contract: ContractDefinition
        params: Address parameters containing pubkeys
    
    Returns:
        QGroupBox with key displays
    """
    group = QGroupBox(_("Keys"))
    layout = QVBoxLayout()
    
    for role in contract.key_roles:
        # Find the pubkey in params (try various naming conventions)
        pubkey = None
        for key_name in [f'{role.name}_pubkey', role.name, f'{role.name}_key']:
            if key_name in params:
                pubkey = params[key_name]
                break
        
        if pubkey:
            row = QHBoxLayout()
            
            # Icon + label
            label_text = f"{role.icon} {_(role.display_name)}:"
            label = WWLabel(label_text)
            label.setToolTip(_(role.description))
            row.addWidget(label)
            
            # Key display with copy button
            key_edit = ShowQRLineEdit(text=pubkey)
            key_edit.addCopyButton()
            key_edit.setReadOnly(True)
            key_edit.setFont(QFont(MONOSPACE_FONT))
            row.addWidget(key_edit)
            
            layout.addLayout(row)
    
    group.setLayout(layout)
    return group


def generate_miniscript_section(
    contract: ContractDefinition,
    params: Dict[str, Any],
    output_type: str = 'p2wsh',
    config: Any = None
) -> QGroupBox:
    """
    Generate miniscript/descriptor display section.
    
    Shows:
    - Symbolic miniscript (for education)
    - Concrete miniscript (with actual values)
    - Output descriptor
    
    Args:
        contract: ContractDefinition
        params: Address parameters
        output_type: 'p2wsh' or 'taproot'
        config: Electrum config for ShowQRTextEdit
    
    Returns:
        QGroupBox with miniscript displays
    """
    from ..cltv_lib.descriptors import get_miniscript, get_descriptor
    
    group = QGroupBox(_("Miniscript Policy"))
    layout = QVBoxLayout()
    
    script_type = f"cltv_{contract.contract_type.value}"
    
    try:
        # Symbolic (educational)
        symbolic = get_miniscript(script_type, params, 'symbolic')
        symbolic_label = WWLabel(_("Symbolic:"))
        layout.addWidget(symbolic_label)
        symbolic_edit = _create_code_display(symbolic, config)
        symbolic_edit.setStyleSheet("font-size: 11px; background-color: #f5f5ff;")
        layout.addWidget(symbolic_edit)
        
        # Concrete (with actual values)
        concrete = get_miniscript(script_type, params, 'concrete')
        if concrete != symbolic:
            concrete_label = WWLabel(_("Concrete:"))
            layout.addWidget(concrete_label)
            concrete_edit = _create_code_display(concrete, config)
            concrete_edit.setStyleSheet("font-size: 11px; background-color: #e8f5e9;")
            layout.addWidget(concrete_edit)
        
        # Output descriptor
        variant = 'tr' if output_type == 'taproot' else 'wsh'
        descriptor = get_descriptor(script_type, params, variant)
        descriptor_label = WWLabel(_("Output Descriptor:"))
        layout.addWidget(descriptor_label)
        desc_edit = _create_code_display(descriptor, config)
        desc_edit.setStyleSheet("font-size: 10px; background-color: #fff8e1;")
        layout.addWidget(desc_edit)
        
    except Exception as e:
            error_label = WWLabel(f"<i>Could not generate miniscript: {e}</i>")
            layout.addWidget(error_label)
    
    group.setLayout(layout)
    return group


def generate_path_status_list(
    contract: ContractDefinition,
    params: Dict[str, Any],
    current_height: int
) -> QWidget:
    """
    Generate a list showing status of all spending paths.
    
    Shows each path with its availability status:
    - Available now
    - Locked (X blocks remaining)
    
    Args:
        contract: ContractDefinition
        params: Address parameters
        current_height: Current blockchain height
    
    Returns:
        QWidget with path status list
    """
    widget = QWidget()
    layout = QVBoxLayout()
    
    locktime = params.get('locktime', 0)
    is_locked = current_height < locktime
    blocks_remaining = max(0, locktime - current_height)
    
    for path in contract.paths:
        status = _get_path_status(path, locktime, current_height, is_locked, blocks_remaining)
        
        label = QLabel(status['text'])
        label.setStyleSheet(f"color: {status['color']}; font-size: 12px;")
        label.setToolTip(_(path.description))
        layout.addWidget(label)
    
    widget.setLayout(layout)
    return widget


# =============================================================================
# Private Helper Functions
# =============================================================================

def _create_locktime_status(
    locktime: int,
    current_height: int,
    is_locked: bool,
    blocks_remaining: int
):
    """Create locktime status label."""
    if is_locked:
        text = f"Locked until block {locktime} ({blocks_remaining} blocks remaining)"
        color = ColorScheme.RED.as_color().name()
    else:
        text = f"Unlocked (locktime {locktime} passed)"
        color = ColorScheme.GREEN.as_color().name()
    
    label = WWLabel(text)
    label.setStyleSheet(f"color: {color}; font-weight: bold;")
    return label


def _create_balance_display(balance: int, config: Any = None):
    """Create balance display label - handles zero cleanly (avoids '0. sat' issue)."""
    if balance > 0:
        if config and hasattr(config, 'format_amount_and_units'):
            balance_text = config.format_amount_and_units(balance)
        else:
            balance_text = f"{balance:,} sat"
        text = f"Balance: {balance_text}"
        color = ColorScheme.GREEN.as_color().name()
    else:
        # Clean zero display (avoid Electrum's "0." format issue)
        base_unit = config.get_base_unit() if config and hasattr(config, 'get_base_unit') else 'sat'
        text = f"Balance: 0 {base_unit} (unfunded)"
        color = ColorScheme.GRAY.as_color().name()
    
    label = WWLabel(text)
    label.setStyleSheet(f"color: {color};")
    return label


def _create_code_display(text: str, config: Any = None) -> ShowQRTextEdit:
    """Create a code display widget."""
    edit = ShowQRTextEdit(text=text, config=config)
    edit.addCopyButton()
    edit.setReadOnly(True)
    edit.setMaximumHeight(80)
    edit.setFont(QFont(MONOSPACE_FONT))
    return edit


def _get_path_status(
    path: SpendingPath,
    locktime: int,
    current_height: int,
    is_locked: bool,
    blocks_remaining: int
) -> Dict[str, str]:
    """Get status text and color for a path."""
    if not path.requires_locktime:
        return {
            'text': f"{_(path.display_name)}: {_(path.description)}",
            'color': ColorScheme.GREEN.as_color().name()
        }
    elif is_locked:
        return {
            'text': f"{_(path.display_name)}: {_('after block')} {locktime} ({blocks_remaining} {_('blocks remaining')})",
            'color': ColorScheme.RED.as_color().name()
        }
    else:
        return {
            'text': f"{_(path.display_name)}: {_('available now')}",
            'color': ColorScheme.GREEN.as_color().name()
        }


def _get_disabled_button_style() -> str:
    """Button style for disabled (no balance)."""
    return """
        QPushButton {
            background-color: #e0e0e0;
            color: #888;
            border: 1px solid #ccc;
            padding: 8px 16px;
            border-radius: 4px;
        }
    """


def _get_locked_button_style() -> str:
    """Button style for locked paths."""
    return """
        QPushButton {
            background-color: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
            padding: 8px 16px;
            border-radius: 4px;
        }
    """


def _get_available_button_style() -> str:
    """Button style for available paths."""
    return """
        QPushButton {
            background-color: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
            padding: 8px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #c8e6c9;
        }
    """


# =============================================================================
# Data Publishing Special Handling
# =============================================================================

def compute_hash160(data: bytes) -> bytes:
    """
    Compute HASH160 (RIPEMD160(SHA256(data))) as per BIP-65.
    
    Args:
        data: The data bytes
    
    Returns:
        20-byte HASH160 result
    """
    from electrum.crypto import hash_160
    return hash_160(data)


def get_data_hash_from_preimage(preimage: str) -> str:
    """
    Derive data_hash from data_preimage.
    
    The preimage can be:
    - Hex string (if all hex characters)
    - UTF-8 string (otherwise)
    
    Args:
        preimage: The data preimage (hex or UTF-8 string)
    
    Returns:
        HASH160 as hex string (40 characters)
    """
    # Determine if preimage is hex or UTF-8
    if len(preimage) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in preimage):
        data_bytes = bytes.fromhex(preimage)
    else:
        data_bytes = preimage.encode('utf-8')
    
    return compute_hash160(data_bytes).hex()


__all__ = [
    'get_contract_for_script_type',
    'generate_status_section',
    'generate_path_button',
    'generate_key_section',
    'generate_miniscript_section',
    'generate_path_status_list',
    'compute_hash160',
    'get_data_hash_from_preimage',
]

