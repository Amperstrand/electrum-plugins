# -*- coding: utf-8 -*-
"""
CLTV Contracts List Widget

Main tab content for CLTV time-locked contracts.
Follows Electrum's ChannelsList pattern for consistent UI/UX.

Architecture:
    - Inherits from MyTreeView (Electrum's standard list widget)
    - Displays all CLTV contracts with columns for type, address, locktime, balance, status
    - Provides toolbar with Create/Sweep actions
    - Supports double-click to open contract details
    - Context menu for contract-specific actions
    - Search/filter functionality built-in
"""

import enum
import time
from typing import TYPE_CHECKING, Dict, Optional, Sequence

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QAbstractItemView
from PyQt6.QtGui import QFont, QStandardItem, QBrush

from electrum.i18n import _
from electrum.wallet import Abstract_Wallet

from electrum.gui.qt.util import (
    WindowModalDialog, Buttons, OkButton, EnterButton, 
    MONOSPACE_FONT, ColorScheme, read_QIcon
)
from electrum.gui.qt.my_treeview import MyTreeView
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from electrum.gui.qt.main_window import ElectrumWindow


# Custom role for storing contract address in items
ROLE_CONTRACT_ADDRESS = Qt.ItemDataRole.UserRole


class CLTVList(MyTreeView):
    """
    Main CLTV contracts list widget.
    
    Displays all time-locked contracts with their status, balance, and locktime.
    Follows Electrum's ChannelsList pattern for consistency.
    
    Features:
        - Sortable columns (Type, Address, Label, Locktime, Balance, Status)
        - Double-click opens contract detail dialog
        - Right-click context menu for actions (Sweep, Details, Copy, Delete)
        - Toolbar with Create Contract and summary stats
        - Search/filter by address, type, or label
        - Real-time updates via signals
    """
    
    # Signals for cross-component updates
    update_rows = QtCore.pyqtSignal(Abstract_Wallet)
    update_single_row = QtCore.pyqtSignal(Abstract_Wallet, str)  # wallet, address
    
    class Columns(MyTreeView.BaseColumnsEnum):
        TYPE = enum.auto()           # Contract type (Simple HODL, Escrow, etc.)
        OUTPUT = enum.auto()         # P2WSH or Taproot
        ADDRESS = enum.auto()        # Bitcoin address (truncated)
        LABEL = enum.auto()          # User label
        LOCKTIME = enum.auto()       # Block height or timestamp
        LOCK_STATUS = enum.auto()    # Locked/Unlocked
        BALANCE = enum.auto()        # Current balance in sats
        UTXOS = enum.auto()          # Number of UTXOs
    
    headers = {
        Columns.TYPE: _('Contract'),
        Columns.OUTPUT: _('Type'),
        Columns.ADDRESS: _('Address'),
        Columns.LABEL: _('Label'),
        Columns.LOCKTIME: _('Locktime'),
        Columns.LOCK_STATUS: _('Status'),
        Columns.BALANCE: _('Balance'),
        Columns.UTXOS: _('UTXOs'),
    }
    
    # Columns to search/filter on
    filter_columns = [
        Columns.TYPE,
        Columns.ADDRESS,
        Columns.LABEL,
        Columns.LOCK_STATUS,
    ]
    
    _default_item_bg_brush = None  # type: Optional[QBrush]
    
    def __init__(self, main_window: 'ElectrumWindow', plugin):
        super().__init__(
            main_window=main_window,
            stretch_column=self.Columns.ADDRESS,
            editable_columns=[self.Columns.LABEL],  # Allow label editing
        )
        self.plugin = plugin
        self.setModel(QtGui.QStandardItemModel(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.update_rows.connect(self.do_update_rows)
        self.update_single_row.connect(self.do_update_single_row)
        # Don't store wallet - always get it from main_window to avoid stale references
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
    
    def get_toolbar_buttons(self):
        """Return toolbar buttons for the CLTV tab (Electrum pattern)."""
        from electrum.gui.qt.util import EnterButton
        
        def create_contract():
            """Open contract creation dialog."""
            from .unified_creation_dialog import UnifiedCreationDialog
            dialog = UnifiedCreationDialog(self.main_window, self.plugin)
            if dialog.exec():
                # Refresh list if address was created
                self.update_rows.emit(self.wallet)
        
 create_btn = EnterButton(_(" Create Contract"), create_contract)
        create_btn.setToolTip(_("Create a new time-locked contract"))
        
        return [create_btn]
    
    def format_fields(self, addr_data: dict) -> Dict['CLTVList.Columns', str]:
        """
        Format address data into column display values.
        
        Args:
            addr_data: Dictionary with address information from plugin storage
            
        Returns:
            Dict mapping column enum to display string
        """
        address = addr_data.get('address', '')
        script_type = addr_data.get('script_type', '')
        params = addr_data.get('params', {})
        label = addr_data.get('label', '')
        
        # Parse contract type and output type from script_type
        # e.g., "cltv_hodl_p2wsh" -> ("Simple HODL", "P2WSH")
        contract_name, output_type = self._parse_script_type(script_type)
        
        # Get locktime from params
        # Check if locktime key exists (not just if value is truthy, since 0 is valid)
        if 'locktime' in params:
            locktime = params.get('locktime')
            # Handle None case
            if locktime is None:
                locktime_str = 'N/A'
            else:
                locktime_str = str(locktime)
        else:
            locktime = 0
            locktime_str = 'N/A'
        
        # Determine lock status
        current_height = self.wallet.adb.get_local_height()
        # Check if locktime exists and is not None, and current_height is available
        if 'locktime' in params and params.get('locktime') is not None and current_height:
            locktime_value = params.get('locktime')
            if current_height >= locktime_value:
 lock_status = _(' Unlocked')
            else:
                blocks_remaining = locktime_value - current_height
 lock_status = _(' Locked') + f' ({blocks_remaining})'
        else:
            lock_status = _('Unknown')
        
        # Get balance from Electrum's native wallet cache
        c, u, x = self.wallet.get_addr_balance(address)
        balance_sats = c + u + x
        if balance_sats > 0:
            balance_str = self.main_window.format_amount(balance_sats) if self.main_window else f'{balance_sats:,}'
        else:
            balance_str = '0'
        
        # Get UTXO count directly from Electrum's ADB
        utxos = self.wallet.adb.get_addr_utxo(address) if hasattr(self.wallet, 'adb') else {}
        utxo_count = len(utxos) if utxos else 0
        utxo_str = str(utxo_count)
        
        # Truncate address for display
        addr_display = address[:12] + '...' + address[-8:] if len(address) > 24 else address
        
        return {
            self.Columns.TYPE: contract_name,
            self.Columns.OUTPUT: output_type,
            self.Columns.ADDRESS: addr_display,
            self.Columns.LABEL: label,
            self.Columns.LOCKTIME: locktime_str,
            self.Columns.LOCK_STATUS: lock_status,
            self.Columns.BALANCE: balance_str,
            self.Columns.UTXOS: utxo_str,
        }
    
    def _parse_script_type(self, script_type: str) -> tuple:
        """
        Parse script_type into human-readable contract name and output type.
        
        SINGLE SOURCE OF TRUTH: Uses ContractDefinition for display names.
        
        Args:
            script_type: e.g., "cltv_hodl_p2wsh", "cltv_escrow_taproot"
            
        Returns:
            Tuple of (contract_name, output_type)
        """
        from ..cltv_lib.contracts import CONTRACTS
        
        # Extract parts from script_type
        parts = script_type.replace('cltv_', '').split('_')
        
        # Determine output type
        if 'taproot' in parts:
            output_type = 'Taproot'
            parts = [p for p in parts if p != 'taproot']
        elif 'p2wsh' in parts:
            output_type = 'P2WSH'
            parts = [p for p in parts if p != 'p2wsh']
        else:
            output_type = 'Unknown'
        
        # Reconstruct contract key and get name from ContractDefinition
        contract_key = '_'.join(parts)
        
        # v12.0.0: No legacy mappings - use canonical names from CONTRACTS
        contract = CONTRACTS.get(contract_key)
        contract_name = contract.name if contract else contract_key.replace('_', ' ').title()
        
        return contract_name, output_type
    
    
    
    def on_double_click(self, idx):
        """Handle double-click on row - open contract details dialog."""
        address = idx.sibling(idx.row(), self.Columns.ADDRESS).data(ROLE_CONTRACT_ADDRESS)
        if address:
            self._show_contract_details(address)
    
    def _show_contract_details(self, address: str):
        """Open the contract details dialog for an address."""
        from .cltv_address_dialog import CLTVAddressDialog
        
        # Find address data from plugin cache
        addr_data = None
        if self.plugin:
            try:
                all_addresses = self.plugin.load_all_addresses(self.wallet, use_cache=True)
                for data in all_addresses:
                    if data.get('address') == address:
                        addr_data = data
                        break
            except Exception as e:
                logger.error(f"[CLTVList] Error loading address data: {e}")
        
        if not addr_data:
            logger.warning(f"[CLTVList] Address data not found for {address[:20]}...")
            return
        
        try:
            dlg = CLTVAddressDialog(
                parent=self.main_window,
                plugin=self.plugin,
                address=address,
                addr_data=addr_data
            )
            dlg.exec()
        except Exception as e:
            logger.error(f"[CLTVList] Error opening dialog: {e}")
    
    def create_menu(self, position):
        """Create right-click context menu."""
        menu = QMenu()
        menu.setSeparatorsCollapsible(True)
        
        selected = self.selected_in_column(self.Columns.ADDRESS)
        if not selected:
            menu.exec(self.viewport().mapToGlobal(position))
            return
        
        if len(selected) > 1:
            # Multi-select: only show bulk actions
            menu.addAction(_("Copy Addresses"), lambda: self._copy_selected_addresses(selected))
            menu.exec(self.viewport().mapToGlobal(position))
            return
        
        idx = self.indexAt(position)
        if not idx.isValid():
            return
        
        item = self.model().itemFromIndex(idx)
        if not item:
            return
        
        address = idx.sibling(idx.row(), self.Columns.ADDRESS).data(ROLE_CONTRACT_ADDRESS)
        if not address:
            return
        
        # Find address data for status checks
        addr_data = None
        if self.plugin:
            try:
                all_addresses = self.plugin.load_all_addresses(self.wallet, use_cache=True)
                for data in all_addresses:
                    if data.get('address') == address:
                        addr_data = data
                        break
            except Exception as e:
                logger.error(f"[CLTVList] Error loading address data: {e}")
        
        params = addr_data.get('params', {}) if addr_data else {}
        locktime = params.get('locktime', 0)
        current_height = self.wallet.adb.get_local_height()
        c, u, x = self.wallet.get_addr_balance(address)
        balance = c + u + x
        is_unlocked = not locktime or current_height >= locktime
        
        # Details action (always available)
        menu.addAction(_("Details..."), lambda: self._show_contract_details(address))
        
        # Sweep action (if unlocked and has balance)
        if balance > 0 and is_unlocked:
            menu.addAction(_("Sweep Funds..."), lambda: self._show_contract_details(address))
        elif balance > 0 and not is_unlocked:
            blocks_remaining = locktime - current_height
            sweep_action = menu.addAction(_("Sweep Funds..."))
            sweep_action.setEnabled(False)
            sweep_action.setToolTip(_("Locked for {} more blocks").format(blocks_remaining))
        
        menu.addSeparator()
        
        # Copy submenu
        cc = self.add_copy_menu(menu, idx)
        cc.addAction(_("Full Address"), lambda: self.place_text_on_clipboard(
            address, title=_("Address")))
        if addr_data:
            script_type = addr_data.get('script_type', '')
            cc.addAction(_("Script Type"), lambda: self.place_text_on_clipboard(
                script_type, title=_("Script Type")))
        
        # Status info
        menu.addSeparator()
        if balance > 0:
            balance_str = self.main_window.format_amount(balance)
            base_unit = self.main_window.base_unit()
 status_action = menu.addAction(f" {balance_str} {base_unit}")
            status_action.setEnabled(False)
        
        if locktime:
            if is_unlocked:
 lock_action = menu.addAction(_(" Unlocked"))
            else:
                blocks_remaining = locktime - current_height
 lock_action = menu.addAction(_(" Locked ({} blocks)").format(blocks_remaining))
            lock_action.setEnabled(False)
        
        # Delete action
        menu.addSeparator()
        menu.addAction(_("Delete..."), lambda: self._delete_contract(address))
        
        menu.exec(self.viewport().mapToGlobal(position))
    
    def _copy_selected_addresses(self, selected):
        """Copy selected addresses to clipboard."""
        addresses = []
        for idx in selected:
            addr = idx.sibling(idx.row(), self.Columns.ADDRESS).data(ROLE_CONTRACT_ADDRESS)
            if addr:
                addresses.append(addr)
        self.place_text_on_clipboard('\n'.join(addresses), title=_("Addresses"))
    
    def _delete_contract(self, address: str):
        """Delete a contract from storage."""
        if self.main_window.question(
            _('Are you sure you want to delete this contract?') + '\n\n' +
            _('This will remove the address from your CLTV list. The address itself remains valid on the blockchain.')
        ):
            try:
                self.plugin.remove_address(self.wallet, address)
                self.update_rows.emit(self.wallet)
            except Exception as e:
                logger.error(f"[CLTVList] Error deleting contract: {e}")
    
    @QtCore.pyqtSlot(Abstract_Wallet, str)
    def do_update_single_row(self, wallet: Abstract_Wallet, address: str):
        """Update a single row in the list, or add it if it's new."""
        # Get current wallet from main_window
        current_wallet = self.wallet
        if not current_wallet or wallet != current_wallet:
            return
        
        # Find address data from plugin cache (most up-to-date)
        addr_data = None
        if self.plugin:
            try:
                # Get from plugin's cache (which was just updated)
                all_addresses = self.plugin.load_all_addresses(wallet, use_cache=True)
                for data in all_addresses:
                    if data.get('address') == address:
                        addr_data = data
                        break
            except Exception as e:
                logger.error(f"[CLTVList] Error loading address data: {e}")
        
        if not addr_data:
            # Address not found - do full refresh to be safe
            self.do_update_rows(wallet)
            return
        
        # Check if row already exists
        existing_row = None
        for row in range(self.model().rowCount()):
            item = self.model().item(row, self.Columns.ADDRESS)
            if item and item.data(ROLE_CONTRACT_ADDRESS) == address:
                existing_row = row
                break
        
        if existing_row is not None:
            # Update existing row
            for column, v in self.format_fields(addr_data).items():
                item = self.model().item(existing_row, column)
                if item:
                    item.setData(v, Qt.ItemDataRole.DisplayRole)
            
            # Update styling
            items = [self.model().item(existing_row, column) for column in self.Columns]
            self._update_row_styling(addr_data, items)
        else:
            # New address - add it to the list
            # Add new row
            field_map = self.format_fields(addr_data)
            items = [QStandardItem(field_map[col]) for col in sorted(field_map)]
            self.set_editability(items)
            
            if self._default_item_bg_brush is None:
                self._default_item_bg_brush = items[self.Columns.ADDRESS].background()
            
            # Store full address in item data
            items[self.Columns.ADDRESS].setData(addr_data.get('address'), ROLE_CONTRACT_ADDRESS)
            
            # Apply monospace font
            items[self.Columns.ADDRESS].setFont(QFont(MONOSPACE_FONT))
            items[self.Columns.BALANCE].setFont(QFont(MONOSPACE_FONT))
            items[self.Columns.LOCKTIME].setFont(QFont(MONOSPACE_FONT))
            
            # Apply styling
            self._update_row_styling(addr_data, items)
            
            self.model().insertRow(0, items)
            self.update_summary_label()
    
    @property
    def wallet(self):
        """Get current wallet from main_window (always fresh, never stale)."""
        if self.main_window and hasattr(self.main_window, 'wallet'):
            return self.main_window.wallet
        return None
    
    @QtCore.pyqtSlot(Abstract_Wallet)
    def do_update_rows(self, wallet):
        """Update all rows in the list.
        
        Note: We don't check wallet identity because hooks only fire for the relevant wallet.
        We always use self.wallet (property) which gets the current wallet from main_window.
        """
        # Get current wallet from main_window (property ensures it's always fresh)
        current_wallet = self.wallet
        if not current_wallet:
            logger.debug("[CLTVList] do_update_rows: no wallet available")
            return
        
        logger.debug(f"[CLTVList] do_update_rows: refreshing list for wallet {id(current_wallet)}")
        
        self.model().clear()
        self.update_headers(self.headers)
        self.set_visibility_of_columns()
        
        # Load addresses from plugin (uses plugin's cache)
        try:
            addresses = self.plugin.load_all_addresses(current_wallet, use_cache=True)
        except Exception as e:
            logger.error(f"[CLTVList] Error loading addresses: {e}")
            addresses = []
        
        self.update_summary_label(addresses)
        
        for addr_data in addresses:
            field_map = self.format_fields(addr_data)
            items = [QStandardItem(field_map[col]) for col in sorted(field_map)]
            self.set_editability(items)
            
            if self._default_item_bg_brush is None:
                self._default_item_bg_brush = items[self.Columns.ADDRESS].background()
            
            # Store full address in item data
            items[self.Columns.ADDRESS].setData(addr_data.get('address'), ROLE_CONTRACT_ADDRESS)
            
            # Apply monospace font to address and balance
            items[self.Columns.ADDRESS].setFont(QFont(MONOSPACE_FONT))
            items[self.Columns.BALANCE].setFont(QFont(MONOSPACE_FONT))
            items[self.Columns.LOCKTIME].setFont(QFont(MONOSPACE_FONT))
            
            # Apply styling based on status
            self._update_row_styling(addr_data, items)
            
            self.model().insertRow(0, items)
        
        # Sort by locktime descending (newest first)
        self.sortByColumn(self.Columns.LOCKTIME, Qt.SortOrder.DescendingOrder)
    
    def _update_row_styling(self, addr_data: dict, items: Sequence[QStandardItem]):
        """Apply visual styling to row based on contract state."""
        assert self._default_item_bg_brush is not None
        
        params = addr_data.get('params', {})
        locktime = params.get('locktime', 0)
        current_height = self.wallet.adb.get_local_height()
        c, u, x = self.wallet.get_addr_balance(addr_data.get('address', ''))
        balance = c + u + x
        
        # Highlight locked contracts with balance
        status_item = items[self.Columns.LOCK_STATUS]
        balance_item = items[self.Columns.BALANCE]
        
        if balance > 0:
            if locktime and current_height and current_height < locktime:
                # Locked with funds - orange background
                status_item.setBackground(ColorScheme.YELLOW.as_color(True))
                status_item.setToolTip(_("Contract is locked and has funds"))
            else:
                # Unlocked with funds - green background (ready to sweep)
                status_item.setBackground(ColorScheme.GREEN.as_color(True))
                status_item.setToolTip(_("Contract is unlocked - funds can be swept"))
            
            balance_item.setBackground(ColorScheme.GREEN.as_color(True))
        else:
            # No funds
            status_item.setBackground(self._default_item_bg_brush)
            balance_item.setBackground(self._default_item_bg_brush)
    
    def update_summary_label(self, addresses=None):
        """Update the summary label in toolbar."""
        if not hasattr(self, 'summary_label'):
            return
        
        # Get addresses from plugin if not provided
        if addresses is None:
            try:
                addresses = self.plugin.load_all_addresses(self.wallet, use_cache=True) if self.plugin else []
            except Exception:
                addresses = []
        
        total_contracts = len(addresses)
        total_balance = sum(
            sum(self.wallet.get_addr_balance(d.get('address', ''))) 
            for d in addresses
        )
        
        msg = _('Contracts') + f': {total_contracts}'
        if total_balance > 0:
            balance_str = self.main_window.format_amount(total_balance)
            base_unit = self.main_window.base_unit()
            msg += f' | ' + _('Total') + f': {balance_str} {base_unit}'
        
        self.summary_label.setText(msg)
    
    def create_toolbar(self, config):
        """Create toolbar with actions and summary.
        
        Toolbar layout (left to right):
        - Summary label (contract count + total balance)
        - Stretch spacer
        - Create Contract button
        - Sweep All button (if any unlocked with funds)
        - Settings menu button
        """
        toolbar, menu = self.create_toolbar_with_menu('')
        self.summary_label = toolbar.itemAt(0).widget()
        
        # Settings menu items
        menu.addAction(_('Show Unfunded Addresses...'), lambda: self._show_unfunded())
        menu.addSeparator()
        menu.addAction(_('Settings...'), lambda: self._show_settings())
        menu.addSeparator()
        
        # Version info in menu
        try:
            from ..cltv_lib.version_info import get_version_string
            version_str = get_version_string()
 version_action = menu.addAction(f" {version_str}")
            version_action.setEnabled(False)  # Just display, not clickable
        except Exception:
            pass
        
        # Create Contract button (primary action)
        self.create_button = EnterButton(_('Create Contract'), self._show_create_dialog)
        toolbar.insertWidget(2, self.create_button)
        
        # Sweep All button (secondary action for batch operations)
        self.sweep_all_button = EnterButton(_('Sweep All'), self._sweep_all_unlocked)
        self.sweep_all_button.setToolTip(_('Sweep all unlocked contracts with funds'))
        toolbar.insertWidget(3, self.sweep_all_button)
        
        return toolbar
    
    def _sweep_all_unlocked(self):
        """Sweep all unlocked contracts that have funds."""
        # Find all sweepable contracts
        sweepable = []
        current_height = self.wallet.adb.get_local_height()
        
        # Get addresses from plugin cache
        try:
            addresses = self.plugin.load_all_addresses(self.wallet, use_cache=True) if self.plugin else []
        except Exception:
            addresses = []
        
        for addr_data in addresses:
            address = addr_data.get('address', '')
            params = addr_data.get('params', {})
            locktime = params.get('locktime', 0)
            c, u, x = self.wallet.get_addr_balance(address)
            balance = c + u + x
            
            # Check if unlocked and has funds
            if balance > 0 and (not locktime or current_height >= locktime):
                sweepable.append({
                    'address': address,
                    'balance': balance,
                    'data': addr_data
                })
        
        if not sweepable:
            self.main_window.show_message(_('No unlocked contracts with funds to sweep.'))
            return
        
        # Show confirmation dialog
        total_sats = sum(s['balance'] for s in sweepable)
        balance_str = self.main_window.format_amount(total_sats)
        base_unit = self.main_window.base_unit()
        
        msg = _('Found {} unlocked contracts with funds:').format(len(sweepable))
        msg += f'\n\n{_("Total")}: {balance_str} {base_unit}'
        msg += f'\n\n{_("Open each contract to sweep individually?")}'
        
        if self.main_window.question(msg):
            # Open first sweepable contract's detail dialog
            if sweepable:
                self._show_contract_details(sweepable[0]['address'])
    
    def _show_create_dialog(self):
        """Show the unified contract creation dialog."""
        from .unified_creation_dialog import UnifiedCreationDialog
        dialog = UnifiedCreationDialog(self.main_window, self.plugin)
        if dialog.exec():
            # Refresh list after creation
            self.update_rows.emit(self.wallet)
    
    def _show_unfunded(self):
        """Show unfunded addresses dialog."""
        from electrum.gui.qt.util import (
            WindowModalDialog, WWLabel, MONOSPACE_FONT, CopyButton, CloseButton, Buttons
        )
        from PyQt6.QtWidgets import QTextEdit, QVBoxLayout
        from PyQt6.QtGui import QFont
        from electrum.i18n import _
        
        wallet = self.wallet
        if not wallet:
            self.main_window.show_error("No wallet available")
            return
        
        try:
            # Get all CLTV addresses
            addresses = self.plugin.load_all_addresses(wallet)
            if not addresses:
                self.main_window.show_message(
                    _("No CLTV addresses found.\n\nCreate some addresses first using the menu options above."),
                    title=_("No Addresses")
                )
                return
            
            # Separate funded and unfunded
            funded = []
            unfunded = []
            
            for addr_data in addresses:
                addr = addr_data['address']
                script_type = addr_data.get('script_type', 'unknown')
                c, u, x = wallet.get_addr_balance(addr)
                balance = c + u + x
                
                if balance > 0:
                    funded.append((addr, script_type, balance))
                else:
                    unfunded.append((addr, script_type))
            
            # Create dialog
            dialog = WindowModalDialog(self.main_window, _("CLTV Addresses - Pay to Many Helper"))
            dialog.setMinimumWidth(800)
            dialog.setMinimumHeight(600)
            
            layout = QVBoxLayout()
            dialog.setLayout(layout)
            
            # Instructions
            if unfunded:
                instructions = WWLabel(
                    _("Found {count} unfunded CLTV addresses.\n\n"
                      "To fund them:\n"
                      "1. Click 'Copy to Clipboard' below\n"
                      "2. Go to Send tab\n"
                      "3. Click 'Pay to Many' button\n"
                      "4. Paste (Cmd+V)\n"
                      "5. Set fee and send").format(count=len(unfunded))
                )
            else:
                instructions = WWLabel(
                    _("All {count} CLTV addresses are funded!\n\n"
                      "Balance summary shown below.").format(count=len(addresses))
                )
            layout.addWidget(instructions)
            
            # Text area with Pay-to-Many format
            text_area = QTextEdit()
            text_area.setReadOnly(True)
            text_area.setFont(QFont(MONOSPACE_FONT))
            
            # Build Pay-to-Many format: address, amount
            if unfunded:
                # Get current unit from config (BTC, mBTC, bits, sat)
                base_unit = self.plugin.config.get_base_unit() if self.plugin.config else 'BTC'
                
                # Convert 1000 sats to current unit
                amount_sats = 1000
                if base_unit == 'BTC':
                    amount_str = "0.00001"
                elif base_unit == 'mBTC':
                    amount_str = "0.01"
                elif base_unit == 'bits' or base_unit == 'uBTC':
                    amount_str = "10"
                elif base_unit == 'sat':
                    amount_str = "1000"
                else:
                    amount_str = "0.00001"  # Fallback to BTC
                
                lines = []
                for addr, script_type in unfunded:
                    lines.append(f"{addr}, {amount_str}")
                
                text_content = "\n".join(lines)
                text_area.setPlainText(text_content)
                
                # Add summary at bottom
                text_area.append(f"\n# Total: {len(unfunded)} addresses × {amount_str} {base_unit} = {len(unfunded) * amount_sats:,} sats")
            else:
                # Show funded addresses summary
                lines = ["# All addresses are funded:\n"]
                for addr, script_type, balance in funded:
                    lines.append(f"{addr[:30]}...  {balance:,} sats  ({script_type})")
                text_area.setPlainText("\n".join(lines))
            
            layout.addWidget(text_area)
            
            # Buttons
            buttons = []
            if unfunded:
                copy_btn = CopyButton(lambda: text_area.toPlainText(), dialog)
                buttons.append(copy_btn)
            
            close_btn = CloseButton(dialog)
            buttons.append(close_btn)
            
            layout.addLayout(Buttons(*buttons))
            
            dialog.exec()
            
        except Exception as e:
            logger.error(f"[UNFUNDED] Error: {e}")
            self.main_window.show_error(_("Error showing unfunded addresses:\n{e}").format(e=e))
    
    def _show_settings(self):
        """Show plugin settings dialog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton
        from electrum.i18n import _
        
        widget = self.plugin.settings_widget(self.main_window)
        d = QDialog(self.main_window)
        d.setWindowTitle(_("CLTV Settings"))
        layout = QVBoxLayout(d)
        layout.addWidget(widget)
        btn_close = QPushButton(_("Close"))
        btn_close.clicked.connect(d.accept)
        layout.addWidget(btn_close)
        d.setLayout(layout)
        d.exec()
    
    def set_visibility_of_columns(self):
        """Set which columns are visible by default."""
        def set_visible(col: int, b: bool):
            self.showColumn(col) if b else self.hideColumn(col)
        
        # All columns visible by default
        for col in self.Columns:
            set_visible(col, True)
    
    def on_edited(self, idx, edit_key, *, text: str) -> None:
        """Handle label editing."""
        # Get address from the row
        address = idx.sibling(idx.row(), self.Columns.ADDRESS).data(ROLE_CONTRACT_ADDRESS)
        if address and text is not None:
            try:
                self.plugin.set_address_label(self.wallet, address, text)
                # Invalidate plugin cache to force refresh on next load
                self.plugin.invalidate_address_cache(self.wallet)
            except Exception as e:
                logger.error(f"[CLTVList] Error setting label: {e}")

