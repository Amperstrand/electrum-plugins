"""CLTV Address Detail Dialog

Electrum-aligned detailed view for a CLTV timelock address.

Follows Electrum's standard pattern:
- Uses Electrum wrapper classes (WindowModalDialog, WWLabel, ColorScheme, etc.)
- Uses direct PyQt imports for basic layouts (QVBoxLayout, QFrame, etc.)
- This matches Electrum's own utxo_list.py, address_dialog.py, etc.

Sections:
    - Address (QR)
    - Locktime status & balance
    - Coins (both spent and unspent)
    - Spending paths
    - Key information
    - Transaction history (HistoryList filtered to address)
    - Sweep Funds action
"""

# PyQt6 for basic layouts and widgets (standard Electrum pattern)
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QAbstractItemView, QMenu
)
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt
import enum

from electrum.i18n import _
from electrum import constants
from electrum.gui.qt.util import (
    WindowModalDialog, Buttons, CloseButton, CopyButton,
    ButtonsLineEdit, ShowQRLineEdit, ColorScheme, qt_event_listener, QtEventListener,
    ButtonsTextEdit, MONOSPACE_FONT, WWLabel, HelpLabel, OkButton,
    RichLabel, AmountLabel
)
from electrum.gui.qt.history_list import HistoryList, HistoryModel
from electrum.gui.qt.qrtextedit import ShowQRTextEdit
from electrum.gui.qt.my_treeview import MyTreeView, MySortModel
import logging

logger = logging.getLogger(__name__)

# Transaction building imports (used by _build_*_tx methods)
from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput, TxOutpoint
from electrum.crypto import sha256d
import electrum_ecc as ecc
from ..test_keys import get_test_privkey
from ..cltv_lib.fee_calculator import FeeCalculator
from ..cltv_lib.registry import get_sweeper, get_config, REGISTRY
from ..cltv_lib.contracts import CONTRACTS, ContractDefinition, SpendingPath
from .ui_generator import (
    get_contract_for_script_type,
)
from .path_details_dialog import PathDetailsDialog



# NOTE: SWEEPER_CONFIG has been removed.
# All sweeper/path configuration is now derived from ContractDefinition (single source of truth).
# See cltv_lib/contracts/definitions.py for the canonical contract metadata.


class CLTVCoinList(MyTreeView):
    """
    Coin list widget for a specific CLTV address.
    
    Shows both unspent (UTXOs) and spent coins, similar to Electrum's Coins tab.
    Uses Electrum's native formatting and styling.
    """
    
    class Columns(MyTreeView.BaseColumnsEnum):
        OUTPOINT = enum.auto()
        AMOUNT = enum.auto()
        HEIGHT = enum.auto()
        STATUS = enum.auto()
    
    headers = {
        Columns.OUTPOINT: _('Outpoint'),
        Columns.AMOUNT: _('Amount'),
        Columns.HEIGHT: _('Height'),
        Columns.STATUS: _('Status'),
    }
    filter_columns = [Columns.OUTPOINT]
    stretch_column = Columns.OUTPOINT
    
    ROLE_PREVOUT_STR = Qt.ItemDataRole.UserRole + 1000
    ROLE_SORT_ORDER = Qt.ItemDataRole.UserRole + 1001
    key_role = ROLE_PREVOUT_STR
    
    def __init__(self, main_window, coins: list, plugin=None):
        """
        Args:
            main_window: Electrum main window for formatting
            coins: List of coin dicts with 'spent' field
            plugin: Plugin instance for logging
        """
        super().__init__(
            main_window=main_window,
            stretch_column=self.stretch_column,
        )
        self.plugin = plugin
        self._coins = coins or []
        
        self.std_model = QStandardItemModel(self)
        self.proxy = MySortModel(self, sort_role=self.ROLE_SORT_ORDER)
        self.proxy.setSourceModel(self.std_model)
        self.setModel(self.proxy)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)
        
        # Set compact height
        self.setMaximumHeight(180)
        
        # Populate
        self._populate()
    
    def _populate(self):
        """Populate the list with coins (both spent and unspent)."""
        self.proxy.setDynamicSortFilter(False)
        self.std_model.clear()
        self.update_headers(self.__class__.headers)
        
        for idx, coin in enumerate(self._coins):
            txid = coin.get('tx_hash', coin.get('txid', ''))
            vout = coin.get('tx_pos', coin.get('vout', 0))
            value = coin.get('value', 0)
            height = coin.get('height', 0)
            is_spent = coin.get('spent', False)
            
            # Format outpoint like Electrum's Coins tab: txid:vout (truncated)
            outpoint_full = f"{txid}:{vout}"
            outpoint_display = f"{txid[:12]}…{txid[-6:]}:{vout}"
            
            # Format amount using Electrum's formatter
            if self.main_window:
                amount_str = self.main_window.format_amount(value, whitespaces=True)
            else:
                amount_str = f"{value:,} sat"
            
            # Height display
            if height > 0:
                height_str = str(height)
            else:
                height_str = _("Unconfirmed")
            
            # Status display
            status_str = _("Spent") if is_spent else _("Unspent")
            
            labels = [""] * len(self.Columns)
            labels[self.Columns.OUTPOINT] = outpoint_display
            labels[self.Columns.AMOUNT] = amount_str
            labels[self.Columns.HEIGHT] = height_str
            labels[self.Columns.STATUS] = status_str
            
            coin_items = [QStandardItem(x) for x in labels]
            self.set_editability(coin_items)
            
            # Store full outpoint for clipboard/actions
            coin_items[self.Columns.OUTPOINT].setData(outpoint_full, self.ROLE_PREVOUT_STR)
            coin_items[self.Columns.OUTPOINT].setData(idx, self.ROLE_SORT_ORDER)
            
            # Monospace font for all columns
            for item in coin_items:
                item.setFont(QFont(MONOSPACE_FONT))
            
            # Gray out spent coins
            if is_spent:
                for item in coin_items:
                    item.setForeground(ColorScheme.GRAY.as_color())
            
            self.std_model.insertRow(idx, coin_items)
        
        self.proxy.setDynamicSortFilter(True)
        self.sortByColumn(self.Columns.HEIGHT, Qt.SortOrder.DescendingOrder)
    
    def create_menu(self, position):
        """Context menu for coin actions."""
        menu = QMenu()
        
        # Get selected items
        selected = self.selected_in_column(self.Columns.OUTPOINT)
        if not selected:
            return
        
        # Copy outpoint
        if len(selected) == 1:
            outpoint = selected[0].data(self.ROLE_PREVOUT_STR)
            menu.addAction(_("Copy Outpoint"), lambda: self.place_text_on_clipboard(outpoint))
        
        menu.exec(self.viewport().mapToGlobal(position))


# Alias for backward compatibility
CLTVUTXOList = CLTVCoinList


class CLTVAddressHistoryModel(HistoryModel):
    """History model filtered to a specific address."""
    
    def __init__(self, window, address):
        super().__init__(window)
        self.address = address
    
    def get_domain(self):
        """Return single address domain."""
        return [self.address]
    
    def should_include_lightning_payments(self) -> bool:
        """CLTV addresses don't support Lightning."""
        return False


class CLTVAddressDialog(WindowModalDialog, QtEventListener):
    """
    Detailed view for a CLTV timelock address.
    
    Shows all address information including scripts, keys, and transaction history.
    Matches Electrum's AddressDialog pattern but with CLTV-specific features.
    """
    
    def _get_script_id(self) -> str:
        """
        Determine script_id from script_type and output_type.
        
        Uses registry.get_script_id() as single source of truth.
        
        Returns:
            script_id like 'cltv_hodl_p2wsh' or 'cltv_escrow_taproot'
        """
        script_type = self.addr_data.get('script_type', 'cltv_hodl')
        output_type = self.addr_data.get('output_type', 'p2wsh')
        
        # Use parse_script_type for consistent parsing
        from ..cltv_lib.address_regenerator import parse_script_type
        from ..cltv_lib.registry import get_script_id
        
        contract_name, stored_output_type = parse_script_type(script_type)
        
        # Use stored output_type if available, otherwise use the parsed one
        # (storage may have output_type separately for legacy compatibility)
        actual_output_type = output_type if output_type != 'p2wsh' else stored_output_type
        
        # Use registry as single source of truth
        return get_script_id(contract_name, actual_output_type)
    
    def __init__(self, parent, plugin, address: str, addr_data: dict):
        """
        Initialize CLTV address dialog.
        
        Args:
            parent: Main window (ElectrumWindow) - this IS the main window
            plugin: Plugin instance
            address: Bitcoin address
            addr_data: Address data dictionary
        """
        WindowModalDialog.__init__(self, parent, _("CLTV Address Details"))
        
        # Parent IS the main window in Electrum
        self.window = parent
        self.plugin = plugin
        self.address = address
        self.addr_data = addr_data
        
        # Get config, network from parent (main window)
        # Wallet is accessed via property to always get fresh reference
        self.config = getattr(plugin, 'config', None) or getattr(parent, 'config', None)
        self.network = getattr(parent, 'network', None)
        
        # No dialog-level UTXO cache - we rely on Electrum's wallet.adb which already caches
        
        # Initialize UI elements that will be created later
        self.coin_list = None
        
        self.setMinimumWidth(850)  # Increased for better card layout
        
        # Set height dynamically - use 90% of screen height (leave space for title bar)
        try:
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_height = screen.availableGeometry().height()
                # Use 90% of available screen height (leaves room for window decorations)
                dialog_height = int(screen_height * 0.9)
                self.setMinimumHeight(min(dialog_height, 750))  # At least 750, but scale up on larger screens
                self.resize(850, dialog_height)
        except Exception:
            # Fallback if screen detection fails
            self.setMinimumHeight(750)
        
        self.setup_ui()
        
        # Register address with wallet for UTXO tracking (especially important for Taproot)
        if self.wallet:
            try:
                self.plugin._register_single_address_with_wallet(self.wallet, self.address)
            except Exception as e:
                logger.debug(f"[DIALOG] Failed to register address: {e}")
        
        # Register for Qt event callbacks (QtEventListener pattern)
        self.register_callbacks()
    
    @property
    def wallet(self):
        """Get current wallet from parent (main window) - always fresh, never stale."""
        if self.window and hasattr(self.window, 'wallet'):
            return self.window.wallet
        return None
    
    def _format_locktime_status(self, locktime: int, is_locked: bool, blocks_remaining: int = 0) -> dict:
        """
        Format locktime status display text and color.
        Helper method to reduce code duplication (Phase 4 improvement).

        Args:
            locktime: The locktime value (block height or unix timestamp)
            is_locked: Whether the timelock is currently locked
            blocks_remaining: Blocks until unlock (only for block height locktime)

        Returns:
            dict: {'text': status_text, 'color': status_color} for display
        """
        # Ensure _() is available locally (avoid scope issues during dialog initialization)
        from electrum.i18n import _
        from datetime import datetime

        # Determine if locktime is block height or timestamp (BIP-65 convention: < 500M = block)
        if locktime < 500000000:
            # Block height locktime
            if is_locked:
                status_text = f"🔒 {_('Unlocks at block')} <b>{locktime}</b> ({blocks_remaining} {_('blocks remaining')})"
                status_color = ColorScheme.RED.as_color()
            else:
                status_text = f"🔓 {_('Unlocked at block')} <b>{locktime}</b> — {_('Can be spent')}"
                status_color = ColorScheme.GREEN.as_color()
        else:
            # Unix timestamp locktime
            unlock_time = datetime.fromtimestamp(locktime).strftime('%Y-%m-%d %H:%M:%S')
            if is_locked:
                status_text = f"🔒 {_('Unlocks at')} <b>{unlock_time}</b> UTC"
                status_color = ColorScheme.RED.as_color()
            else:
                status_text = f"🔓 {_('Unlocked at')} <b>{unlock_time}</b> UTC — {_('Can be spent')}"
                status_color = ColorScheme.GREEN.as_color()

        return {'text': status_text, 'color': status_color}
    
    
    def add_horizontal_separator(self, layout):
        """Add a horizontal line separator to layout.
        
        Args:
            layout: QVBoxLayout to add separator to.
        """
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
    
    def add_section_header(self, layout, text: str):
        """Add a bold section header to layout.

        Args:
            layout: QVBoxLayout to add header to.
            text: Header text (will be translated and bolded).
        """
        # Use Electrum's WWLabel for word-wrapping capability
        from electrum.i18n import _
        header = WWLabel(f"<b>{_(text)}:</b>")
        layout.addWidget(header)
    
    def format_pubkey_abbrev(self, pubkey: str, style: str = "standard") -> str:
        """Format pubkey with standard abbreviation.
        
        Args:
            pubkey: Full pubkey hex string
            style: "short" (16 chars), "standard" (8+8), "long" (32 chars)
        
        Returns:
            Abbreviated pubkey or "N/A" if empty
        """
        if not pubkey or pubkey == 'N/A':
            return "N/A"
        
        if style == "short":
            return f"{pubkey[:16]}..."
        elif style == "long":
            return f"{pubkey[:32]}..."
        else:  # standard
            return f"{pubkey[:8]}...{pubkey[-8:]}"
    
    def add_pubkey_list(self, layout, pubkeys: dict, style: str = "standard"):
        """Add a list of labeled pubkeys with monospace styling.
        
        Args:
            layout: QVBoxLayout to add list to
            pubkeys: Dict of {label: pubkey_hex}
            style: Abbreviation style to use
        """
        lines = []
        for label, pubkey in pubkeys.items():
            abbrev = self.format_pubkey_abbrev(pubkey, style)
            lines.append(f"{_(label)}: {abbrev}")
        
        label = WWLabel("\n".join(lines))
        label.setFont(QFont(MONOSPACE_FONT))
        label.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(label)
    
    def add_locktime_path(self, layout, path_name: str, description: str, 
                          locktime: int, current_height: int, always_available: bool = False):
        """Add a spending path with locktime status.
        
        Args:
            layout: QVBoxLayout to add path to
            path_name: Name of the spending path (e.g., "Normal Operations", "Arbitration")
            description: Description of required signers (e.g., "Alice + Bob (anytime)")
            locktime: Block height when path becomes available
            current_height: Current blockchain height
            always_available: If True, path is always available (green checkmark)
        """
        if always_available:
            # Path always available
            text = f"✅ {_(path_name)}: {_(description)}"
            color = ColorScheme.GREEN.as_color().name()
        else:
            # Path availability depends on locktime
            is_locked = current_height < locktime
            blocks_remaining = max(0, locktime - current_height)
            
            if is_locked:
                text = f"🔒 {_(path_name)}: {_(description)} {_('after block')} {locktime} ({blocks_remaining} {_('blocks remaining')})"
                color = ColorScheme.RED.as_color().name()
            else:
                text = f"🔓 {_(path_name)}: {_(description)} {_('available now')}"
                color = ColorScheme.GREEN.as_color().name()
        
        label = WWLabel(text)
        label.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(label)
    
    def add_colored_field(self, layout, text: str, color: str = '#888'):
        """Add a field with colored styling (replacement for inline HTML).
        
        Args:
            layout: Layout to add label to
            text: Text to display (can include bold tags)
            color: Hex color code (default gray)
        """
        label = WWLabel(text)
        label.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(label)
    
    def has_utxos(self) -> bool:
        """Check if address has any UTXOs (confirmed or unconfirmed).
        
        Uses Electrum's wallet.adb which already caches and updates automatically.
        
        Returns:
            True if address has at least one UTXO, False otherwise
        """
        try:
            if hasattr(self.wallet, 'adb'):
                utxos = self.wallet.adb.get_addr_utxo(self.address)
                return len(utxos) > 0 if utxos else False
            return False
        except Exception:
            return False
    
    def create_action_button(self, text: str, tooltip_available: str, tooltip_no_funds: str,
                            tooltip_locked: str, on_click, has_funds: bool = True,
                            is_available: bool = True, blocks_remaining: int = 0):
        """Create an action button with conditional enable state and tooltip.
        
        Args:
            text: Button label
            tooltip_available: Tooltip when button is enabled
            tooltip_no_funds: Tooltip when no funds available
            tooltip_locked: Tooltip when funds exist but locktime not reached
            on_click: Function to call when button clicked
            has_funds: Whether address has UTXOs
            is_available: Whether locktime condition is met (True for always-available paths)
            blocks_remaining: Number of blocks until locktime (for locked tooltip)
        
        Returns:
            Configured QPushButton
        """
        btn = OkButton(self, _(text))
        can_execute = has_funds and is_available
        btn.setEnabled(can_execute)
        
        if not has_funds:
            btn.setToolTip(_(tooltip_no_funds))
        elif not is_available:
            btn.setToolTip(_(tooltip_locked) + f" ({blocks_remaining} {_('blocks')})")
        else:
            btn.setToolTip(_(tooltip_available))
        
        btn.clicked.connect(on_click)
        return btn
    
    def _validate_sweep_prerequisites(self, path_name: str, **kwargs) -> bool:
        """Validate prerequisites before building sweep transaction.
        
        Args:
            path_name: Human-readable path name for error messages
            **kwargs: May contain 'requires_locktime', 'locktime', etc.
        
        Returns:
            True if all prerequisites met, False otherwise (shows error)
        """
        # Check balance using UTXO cache (stateless - no _balance field)
        result = self._get_utxos_and_balance()
        if not result['success'] or result['balance'] <= 0:
            self.show_error(
                f"{path_name}:\n\n" +
                _("Address has no balance (0 sats). Cannot sweep empty address.")
            )
            return False
        
        # Check locktime if applicable
        if kwargs.get('requires_locktime'):
            locktime = kwargs.get('locktime') or self.get_locktime()
            current_height = self.wallet.adb.get_local_height() if hasattr(self.wallet, 'adb') else 0
            
            if current_height < locktime:
                blocks_remaining = locktime - current_height
                self.show_error(
                    f"{path_name}:\n\n" +
                    f"{_('Timelock not yet reached')}.\n" +
                    f"{_('Current block')}: {current_height}\n" +
                    f"{_('Required block')}: {locktime}\n" +
                    f"{_('Blocks remaining')}: {blocks_remaining}"
                )
                return False
        
        return True
    
    def get_params(self):
        """
        Get script parameters from addr_data using ContractDefinition (single source of truth).
        
        Only supports v3.1+ nested format {'params': {...}}.
        Returns params dict, logs warnings for broken addresses.
        """
        from ..cltv_lib.registry import parse_script_id
        from ..cltv_lib.contracts import CONTRACTS
        
        script_type = self.addr_data.get('script_type', '')
        
        # Parse script_type to get contract_name
        try:
            contract_name, _ = parse_script_id(script_type)
        except ValueError:
            logger.warning(f"[WARNING] ⚠️  Unknown script type: {script_type}")
            return {}
        
        # Get contract definition (single source of truth)
        contract = CONTRACTS.get(contract_name)
        if not contract:
            logger.warning(f"[WARNING] ⚠️  Unknown contract: {contract_name}")
            return {}
        
        # Extract parameters (v12.0.0 format: nested params dict)
        if 'params' not in self.addr_data or not isinstance(self.addr_data['params'], dict):
            return {}
        
        params = self.addr_data['params'].copy()
        
        # Validate required parameters using ContractDefinition
        required_params = contract.get_required_param_names()
        missing = [p for p in required_params if params.get(p) is None]
        
        if missing:
            logger.warning(f"[WARNING] ⚠️  Broken address: {self.address[:20]}...")
            logger.warning(f"[WARNING] ⚠️  Missing required parameters: {', '.join(missing)}")
            logger.warning(f"[WARNING] ⚠️  Cannot sweep - address must be recreated")
        
        return params
    
    def get_locktime(self):
        """Get locktime value from params. Returns 0 if not found."""
        params = self.get_params()
        return params.get('locktime', 0)
    
    def _get_utxos_and_balance(self):
        """
        Get UTXOs and balance for the address with validation.
        
        Uses Electrum's wallet.adb which already caches and updates automatically.
        
        Returns:
            dict: {'success': bool, 'utxos': list, 'balance': int, 'error': str}
        """
        try:
            # Get balance directly from Electrum
            c, u, x = self.wallet.get_addr_balance(self.address)
            balance = c + u + x
            
            # Get UTXOs directly from Electrum's ADB
            utxos = []
            if balance > 0 and hasattr(self.wallet, 'adb'):
                wallet_utxos = self.wallet.adb.get_addr_utxo(self.address)
                if wallet_utxos:
                    for outpoint, utxo in wallet_utxos.items():
                        txid = outpoint.txid.hex() if hasattr(outpoint.txid, 'hex') else str(outpoint.txid)
                        vout = outpoint.out_idx
                        value = utxo._trusted_value_sats if hasattr(utxo, '_trusted_value_sats') else 0
                        height = utxo.block_height if hasattr(utxo, 'block_height') else 0
                        
                        utxos.append({
                            'tx_hash': txid,
                            'txid': txid,
                            'tx_pos': vout,
                            'vout': vout,
                            'value': value,
                            'height': height
                        })
            
            if not utxos:
                return {'success': False, 'utxos': [], 'balance': 0, 'error': 'No UTXOs found'}
            
            return {'success': True, 'utxos': utxos, 'balance': balance, 'error': None}
        except Exception as e:
            return {'success': False, 'utxos': [], 'balance': 0, 'error': str(e)}
    
    def _get_all_coins(self, **kwargs):
        """
        Get all coins (both spent and unspent) for the address.
        
        Queries address history to find all outputs received, then checks
        if each is spent or unspent.
        
        Returns:
            dict: {'success': bool, 'coins': list, 'unspent_count': int, 'spent_count': int}
        """
        try:
            coins = []
            
            # First get unspent coins (UTXOs) from Electrum's cache
            utxos = []
            if hasattr(self.wallet, 'adb'):
                wallet_utxos = self.wallet.adb.get_addr_utxo(self.address)
                if wallet_utxos:
                    for outpoint, utxo in wallet_utxos.items():
                        txid = outpoint.txid.hex() if hasattr(outpoint.txid, 'hex') else str(outpoint.txid)
                        vout = outpoint.out_idx
                        value = utxo._trusted_value_sats if hasattr(utxo, '_trusted_value_sats') else 0
                        height = utxo.block_height if hasattr(utxo, 'block_height') else 0
                        
                        utxos.append({
                            'tx_hash': txid,
                            'txid': txid,
                            'tx_pos': vout,
                            'vout': vout,
                            'value': value,
                            'height': height
                        })
            
            # Mark UTXOs as unspent
            for utxo in utxos:
                utxo['spent'] = False
                coins.append(utxo)
            
            # Now get address history to find spent coins
            try:
                if hasattr(self.wallet, 'adb') and hasattr(self.wallet.adb, 'get_address_history'):
                    history = self.wallet.adb.get_address_history(self.address)
                    
                    # Track which outpoints we already have (from UTXOs)
                    known_outpoints = set()
                    for utxo in utxos:
                        txid = utxo.get('tx_hash', utxo.get('txid', ''))
                        vout = utxo.get('tx_pos', utxo.get('vout', 0))
                        known_outpoints.add(f"{txid}:{vout}")
                    
                    # History is a dict: {tx_hash: TxMinedInfo}
                    # Iterate over keys (tx_hashes)
                    history_items = history.items() if isinstance(history, dict) else history
                    for item in history_items:
                        try:
                            # Handle dict format: (tx_hash, tx_mined_info)
                            if isinstance(item, tuple) and len(item) == 2:
                                tx_hash, tx_info = item
                                # tx_info might be TxMinedInfo object
                                height = getattr(tx_info, 'height', 0) if hasattr(tx_info, 'height') else 0
                                if callable(getattr(tx_info, 'height', None)):
                                    height = tx_info.height()
                            else:
                                tx_hash = str(item)
                                height = 0
                            
                            tx = self.wallet.db.get_transaction(tx_hash)
                            if tx:
                                for vout, txout in enumerate(tx.outputs()):
                                    if txout.address == self.address:
                                        outpoint = f"{tx_hash}:{vout}"
                                        if outpoint not in known_outpoints:
                                            # This is a spent coin
                                            coins.append({
                                                'tx_hash': tx_hash,
                                                'txid': tx_hash,
                                                'tx_pos': vout,
                                                'vout': vout,
                                                'value': txout.value,
                                                'height': height if isinstance(height, int) else 0,
                                                'spent': True
                                            })
                        except Exception:
                            pass  # Skip transactions we can't parse
            except Exception as e:
                logger.error(f"[COINS] Error getting history: {e}")
            
            # Sort by height (newest first)
            coins.sort(key=lambda c: c.get('height', 0), reverse=True)
            
            unspent_count = sum(1 for c in coins if not c.get('spent', False))
            spent_count = sum(1 for c in coins if c.get('spent', False))
            
            return {
                'success': True,
                'coins': coins,
                'unspent_count': unspent_count,
                'spent_count': spent_count
            }
        except Exception as e:
            return {'success': False, 'utxos': [], 'balance': 0, 'error': str(e)}
    
    def get_dynamic_fee_rate(self) -> int:
        """
        Get dynamic fee rate from Electrum's fee estimator.
        
        Returns:
            int: Fee rate in sat/vbyte (minimum 1 sat/vbyte for relay)
        """
        if not self.config:
            return 1  # Conservative fallback
        
        try:
            # estimate_fee() typically returns fee in sat/kB
            fee_rate = self.config.estimate_fee(2)  # 2-block confirmation target
            
            # Convert to sat/byte if needed
            if fee_rate > 1000:  # Likely sat/kB
                fee_rate = fee_rate / 1000
            
            # Ensure MINIMUM 1 sat/vbyte for relay (Bitcoin network requirement)
            # Signet/testnet may return lower estimates, but nodes reject < 1 sat/vbyte
            fee_rate_int = max(1, int(fee_rate))
            
            logger.info(f"[FEE] Dynamic fee rate: {fee_rate_int} sat/vbyte (from estimate: {fee_rate})")
            return fee_rate_int
        
        except (AttributeError, TypeError):
            # Fallback if estimate_fee not available
            try:
                fee_kb = self.config.fee_per_kb()
                fee_rate_int = max(1, int(fee_kb / 1000))
                logger.info(f"[FEE] Fee rate from fee_per_kb: {fee_rate_int} sat/vbyte")
                return fee_rate_int
            except:
                logger.info(f"[FEE] Using fallback fee rate: 1 sat/vbyte")
                return 1  # Final fallback
    
    # Old calculate_transaction_fee method removed - use FeeCalculator instead
    
    # Old _calculate_fees method removed - use FeeCalculator instead
    
    def _calculate_output_amount(self, balance: int, total_fees: int):
        """
        Calculate output amount and validate it's positive.
        
        Args:
            balance: Total balance in satoshis
            total_fees: Total fees in satoshis
        
        Returns:
            dict: {'success': bool, 'amount': int, 'error': str}
        """
        output_amount = balance - total_fees
        
        if output_amount <= 0:
            return {
                'success': False,
                'amount': 0,
                'error': f'Insufficient funds for fees (have {balance}, need > {total_fees})'
            }
        
        return {'success': True, 'amount': output_amount, 'error': None}
    
    def _get_test_keys(self, key_names: list) -> dict:
        """
        Load test private keys for transaction building.
        
        Uses ContractDefinition key names directly (e.g., 'alice', 'bob', 'pubkey').
        
        Args:
            key_names: List of key role names from ContractDefinition
        
        Returns:
            dict: Mapping of key names to ECPrivkey objects
                  e.g., {'alice': ECPrivkey(...), 'bob': ECPrivkey(...)}
        """
        return {name: get_test_privkey(name) for name in key_names}
    
    def _get_test_keys_for_contract(self, contract_name: str, path_name: str = None) -> dict:
        """
        Get test keys for a contract using ContractDefinition as single source of truth.
        
        Args:
            contract_name: Contract name (e.g., 'hodl', 'escrow')
            path_name: Spending path name (e.g., 'sweep', 'normal'). If None, uses first path.
        
        Returns:
            dict: Mapping of contract key names to ECPrivkey objects
                  e.g., {'pubkey': ECPrivkey(...)} for hodl
        """
        from ..cltv_lib.contracts import CONTRACTS
        
        contract = CONTRACTS.get(contract_name)
        if not contract:
            raise ValueError(f"Unknown contract: {contract_name}")
        
        # Get required keys for the path
        if path_name:
            path = contract.get_path(path_name)
            if not path:
                raise ValueError(f"Unknown path '{path_name}' for {contract_name}")
            required_key_names = path.required_keys
        else:
            if not contract.paths:
                raise ValueError(f"No paths defined for {contract_name}")
            required_key_names = contract.paths[0].required_keys
        
        # Map contract key names to test key names via ParamSpec
        keys = {}
        for key_name in required_key_names:
            # Find test_key_name from ParamSpec
            test_key_name = next(
                (p.test_key_name for p in contract.params if p.name == key_name and p.test_key_name),
                key_name  # Fallback to key_name if no mapping
            )
            try:
                keys[key_name] = get_test_privkey(test_key_name)
            except ValueError:
                pass  # Skip if test key not found
        
        return keys
    
    def _log_transaction_details(self, contract_type: str, path: str, num_utxos: int, 
                                   balance: int, total_fees: int, output_amount: int, 
                                   tx_locktime: int = None):
        """
        Log transaction building details in a consistent format.
        
        Args:
            contract_type: Type of contract (e.g., 'TWOFACTOR', 'ESCROW')
            path: Path being used (e.g., 'normal', 'recovery')
            num_utxos: Number of UTXOs
            balance: Total balance in satoshis
            total_fees: Total fees in satoshis
            output_amount: Output amount in satoshis
            tx_locktime: Transaction locktime (optional, only logged if provided)
        """
        logger.info(f"[{contract_type}] Building transaction ({path}):")
        logger.info(f"[{contract_type}]   Inputs: {num_utxos} UTXO(s) = {balance:,} sats")
        logger.info(f"[{contract_type}]   Fees: {total_fees:,} sats")
        logger.info(f"[{contract_type}]   Output: {output_amount:,} sats")
        if tx_locktime is not None:
            logger.info(f"[{contract_type}]   Locktime: {tx_locktime}")
    
    def _show_transaction_preview(self, tx, title: str):
        """Show transaction in Electrum's native preview dialog.
        
        Args:
            tx: PartialTransaction object
            title: Dialog title (currently unused, Electrum derives its own title)
        """
        try:
            if hasattr(self.window, 'show_transaction'):
                # Electrum's show_transaction doesn't accept desc parameter
                # It derives the title from the transaction itself
                self.window.show_transaction(tx)
            else:
                # Fallback to direct function call
                from electrum.gui.qt.transaction_dialog import show_transaction
                show_transaction(tx, parent=self.window)
            
            # After broadcast, Electrum will detect the transaction and fire wallet hooks.
            # Our plugin hooks (on_history, wallet_updated) will automatically refresh the main tab.
            # The dialog will refresh via on_event_wallet_updated when Electrum detects the transaction.
        
        except Exception as e:
            self.show_error(f"{_('Could not show transaction preview')}:\n\n{str(e)}")
    
    def _execute_sweep(self, path_name: str, path: str, **build_kwargs):
        """Common sweep execution pattern for all sweep methods.
        
        Args:
            path_name: Human-readable path name (e.g., "Normal Operations", "Arbitration - Alice")
            path: Spending path for unified builder (e.g., 'normal', 'recovery')
            **build_kwargs: Additional arguments for validation (requires_locktime, locktime)
        
        Returns:
            None (shows transaction dialog or error)
        """
        # 1. Validate wallet
        if not self.wallet:
            return
        
        # 2. Get a fresh destination address from the wallet
        # This ensures each sweep goes to a new address for privacy
        try:
            # Try to get an unused address first
            dest_address = self.wallet.get_unused_address()
            if not dest_address:
                # If no unused address, create a new one
                dest_address = self.wallet.create_new_address(for_change=False)
            logger.info(f"[SWEEP] Destination: {dest_address}")
        except Exception as e:
            # Fallback to standard receiving address
            dest_address = self.wallet.get_receiving_address()
            logger.info(f"[SWEEP] Using default receiving address: {dest_address}")
        
        if not dest_address:
            self.show_error(_("Cannot sweep: wallet has no receiving addresses."))
            return
        
        # 3. Pre-validate prerequisites (balance, locktime if applicable)
        if not self._validate_sweep_prerequisites(path_name, **build_kwargs):
            return
        
        # 4. Calculate dynamic fee based on UTXOs
        utxo_data = self._get_utxos_and_balance()
        if not utxo_data['success']:
            self.show_error(f"{path_name}: {utxo_data['error']}")
            return
        
        num_utxos = len(utxo_data['utxos'])
        
        # 5. Build transaction
        try:
            addr_type = self.addr_data.get('script_type', 'CLTV')
            logger.info(f"[{addr_type}] Building {path_name} tx for {self.address[:20]}...")
            
            # Use unified builder (it will calculate fees internally)
            result = self._build_cltv_transaction(dest_address, path=path, fee_sats=None)
            
            if not result.get('success'):
                self.show_error(
                    f"{_('Failed to build')} {path_name} {_('transaction')}:\n\n" +
                    result.get('error', _('Unknown error'))
                )
                return
            
            tx = result.get('tx')
            if not tx:
                self.show_error(f"{path_name}: {_('Transaction building failed')}")
                return
        
        except Exception as e:
            self.show_error(f"{path_name} {_('sweep failed')}:\n\n{str(e)}")
            return
        
        # 5. Show transaction with descriptive title
        self._show_transaction_preview(tx, f"{path_name} - {addr_type}")
    
    def setup_ui(self):
        """Build the dialog UI with scroll area for content."""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # Create scroll area for main content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # Content widget inside scroll area
        content_widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        content_widget.setLayout(layout)
        
        # === Address section ===
        addr_label = WWLabel(_("Address") + ":")
        layout.addWidget(addr_label)
        self.addr_e = ShowQRLineEdit(self.address, self.config, title=_("CLTV Address"))
        layout.addWidget(self.addr_e)
        
        # === Status + balance + coins + spending paths (all in one card) ===
        script_type = self.addr_data.get('script_type', 'unknown')
        logger.info(f"[DIALOG] Calling create_status_section() for {script_type}...")
        status_group = self.create_status_section()
        logger.info(f"[DIALOG] Status group returned: {type(status_group)}, is None: {status_group is None}")
        if status_group:
            logger.info(f"[DIALOG] Adding status group to layout...")
            layout.addWidget(status_group)
            logger.info(f"[DIALOG] Status group added to layout")
        else:
            logger.error(f"[DIALOG] [ERROR] Status group is None, not adding to layout!")
        
        # Add scroll area to main layout
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Close button (OUTSIDE scroll area, always visible)
        # Note: Action buttons now inline on spending path cards (removed bottom buttons)
        main_layout.addLayout(Buttons(CloseButton(self)))
    
    def add_balance_display(self, layout):
        """Add balance display to layout (DRY - used by both simple and escrow)."""
        try:
            c, u, x = self.wallet.get_addr_balance(self.address)
            balance = c + u + x
            if balance > 0:
                balance_text = self.plugin.config.format_amount_and_units(balance)
                fiat_text = self.plugin.format_amount_with_fiat(balance)
                balance_label = WWLabel(f"{_('Balance')}: <b>{balance_text}</b>")
                balance_label.setToolTip(fiat_text)
                balance_label.setStyleSheet(f"color: {ColorScheme.GREEN.as_color().name()};")
            else:
                balance_label = WWLabel(f"{_('Balance')}: <b>0 BTC</b>")
                balance_label.setStyleSheet("color: gray;")
            layout.addWidget(balance_label)
        except Exception:
            pass
    
    def create_status_section(self):
        """Create CLTV status information section.

        Uses ContractDefinition as single source of truth - no special cases.
        Every contract type is handled identically through its definition.
        """
        logger.info(f"[DIALOG] create_status_section() starting...")
        params = self.get_params()
        script_type = self.addr_data.get('script_type', '')
        logger.info(f"[DIALOG]   script_type: {script_type}")
        logger.info(f"[DIALOG]   params keys: {list(params.keys())}")
        logger.info(f"[DIALOG]   locktime: {params.get('locktime', 'NOT SET')}")

        # Get contract definition - this MUST exist for all supported contracts
        contract = get_contract_for_script_type(script_type)
        logger.info(f"[DIALOG]   contract: {contract.name if contract else 'None'}")
        if not contract:
            logger.error(f"[DIALOG] [ERROR] No contract definition found!")
            raise ValueError(f"No contract definition found for script_type: {script_type}. "
                           f"All contracts must be properly defined in CONTRACTS.")

        logger.info(f"[DIALOG]   contract.paths: {[p.name for p in contract.paths] if contract.paths else 'None'}")
        logger.info(f"[DIALOG]   contract.key_roles: {[k.name for k in contract.key_roles] if contract.key_roles else 'None'}")

        # Generate UI from ContractDefinition - single source of truth pattern
        return self._create_status_section_from_contract(contract, params)
    
    def _create_status_section_from_contract(self, contract: ContractDefinition, params: dict):
        """Create status section from ContractDefinition - follows e2e test pattern.

        This method mirrors how e2e tests are generated:
        1. Take ContractDefinition as single source of truth
        2. Generate complete UI based on contract.paths
        3. Each path gets appropriate buttons and status
        4. No special cases - every contract works the same way
        
        Uses Electrum-native widgets and ColorScheme for consistent theming.
        """
        logger.info(f"[DIALOG] _create_status_section_from_contract() starting for {contract.name}...")
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout
        from electrum.i18n import _

        # Create the main group box with contract name - Electrum native style
        logger.info(f"[DIALOG]   Creating group box...")
        group = QGroupBox(_(contract.name))
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(12, 16, 12, 12)

        # Contract description - using WWLabel for proper word wrapping
        if contract.short_description:
            logger.info(f"[DIALOG]   Adding description: {contract.short_description[:50]}...")
            desc_label = WWLabel(_(contract.short_description))
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # BIP reference if available - subtle styling
        if contract.bip_reference:
            logger.info(f"[DIALOG]   Adding BIP ref: {contract.bip_reference}")
            bip_label = WWLabel(f"<i>{_(contract.bip_reference)}</i>")
            bip_label.setStyleSheet(f"color: {ColorScheme.DEFAULT.as_color().name()}; font-size: 11px;")
            layout.addWidget(bip_label)

        # Locktime status - prominent display with Electrum colors
        locktime = params.get('locktime', 0)
        current_height = self.wallet.adb.get_local_height() if hasattr(self.wallet, 'adb') else 0
        is_locked = current_height < locktime
        blocks_remaining = max(0, locktime - current_height)
        logger.info(f"[DIALOG]   Locktime: {locktime}, current_height: {current_height}, is_locked: {is_locked}")

        locktime_status = self._format_locktime_status(locktime, is_locked, blocks_remaining)
        logger.info(f"[DIALOG]   Locktime status text: {locktime_status['text'][:80]}...")
        locktime_label = RichLabel(locktime_status['text'])
        locktime_label.setStyleSheet(f"color: {locktime_status['color'].name()};")
        layout.addWidget(locktime_label)

        # Balance display - using Electrum's formatting pattern
        # Get balance for use in path buttons below
        logger.info(f"[DIALOG]   Getting balance...")
        c, u, x = self.wallet.get_addr_balance(self.address)
        balance = c + u + x
        logger.info(f"[DIALOG]   Balance: {balance} sats")
        
        # Store as instance variable for refresh_balance() to update
        self.balance_label = WWLabel("")  # Will be populated by _update_balance_display
        layout.addWidget(self.balance_label)
        self._update_balance_display()
        logger.info(f"[DIALOG]   Balance label added")
        
        # Coins section - shows both spent and unspent coins
        # Uses Electrum's native MyTreeView pattern
        self.add_horizontal_separator(layout)
        
        # Coins label - stored for refresh
        self.coins_label = WWLabel("")
        layout.addWidget(self.coins_label)
        
        # Create coin list widget - will be populated by _refresh_coin_list
        logger.info(f"[DIALOG]   Creating coin list widget...")
        self.coin_list = CLTVCoinList(self.window, [], self.plugin)  # self.window is the main window (parent)
        self.coin_list.setMaximumHeight(150)
        layout.addWidget(self.coin_list)
        
        # Initial population
        logger.info(f"[DIALOG]   Refreshing coin list...")
        self._refresh_coin_list()
        logger.info(f"[DIALOG]   Coin list refreshed")

        # Visualizer button - show ALL spending paths in one tree (top-level, not per-path)
        self.add_horizontal_separator(layout)
        from electrum.gui.qt.util import OkButton
        script_type = self.addr_data.get('script_type', '')
        output_type = 'taproot' if 'taproot' in script_type else 'p2wsh'
        viz_btn = OkButton(self, _("View Spending Conditions"))
        viz_btn.setToolTip(_("View all spending paths in policy tree visualization"))
        viz_btn.clicked.connect(
            lambda checked: self._show_miniscript_visualizer_all_paths(contract, output_type, params)
        )
        layout.addWidget(viz_btn)
        
        # Spending paths section - clean visual separation
        logger.info(f"[DIALOG]   contract.paths: {contract.paths}")
        if contract.paths:
            logger.info(f"[DIALOG]   Creating {len(contract.paths)} spending path(s)...")
            self.add_horizontal_separator(layout)
            
            paths_label = WWLabel(f"<b>{_('Spending Paths')}:</b>")
            layout.addWidget(paths_label)

            # Generate UI for each path - mirrors e2e test pattern
            for i, path in enumerate(contract.paths):
                logger.info(f"[DIALOG]     Path {i}: {path.name} (requires_locktime={path.requires_locktime})")
                path_widget = self._create_path_button_from_definition(
                    path, params, balance, current_height
                )
                layout.addWidget(path_widget)
                logger.info(f"[DIALOG]     Path {i} widget added")

        # Key information section - collapsible-style display
        if contract.key_roles:
            self.add_horizontal_separator(layout)
            
            keys_label = WWLabel(f"<b>{_('Key Information')}:</b>")
            layout.addWidget(keys_label)

            # Generate key info for each role using monospace font
            for key_role in contract.key_roles:
                key_value = params.get(key_role.name, 'N/A')
                if isinstance(key_value, bytes):
                    key_value = key_value.hex()
                
                # Truncate long keys for display
                display_value = key_value if len(str(key_value)) <= 66 else f"{key_value[:32]}...{key_value[-8:]}"

                key_info = WWLabel(f"{_(key_role.display_name)}: {display_value}")
                key_info.setWordWrap(True)
                key_info.setFont(QFont(MONOSPACE_FONT))
                key_info.setStyleSheet(f"color: {ColorScheme.DEFAULT.as_color().name()}; font-size: 10px;")
                layout.addWidget(key_info)

        # Technical details - subtle footer
        script_type_label = WWLabel(f"{_('Script Type')}: <code>{self.addr_data.get('script_type', 'unknown')}</code>")
        script_type_label.setStyleSheet(f"color: {ColorScheme.DEFAULT.as_color().name()}; font-size: 11px;")
        layout.addWidget(script_type_label)

        group.setLayout(layout)
        return group

    def _create_path_button_from_definition(self, path: SpendingPath, params: dict, balance: int, current_height: int):
        """Create a row with details button + sweep button for a SpendingPath.

        This mirrors how e2e tests generate path-specific sweep data:
        - Each path gets its own button with appropriate text and behavior
        - Availability is determined by balance, locktime, and path requirements
        - Callbacks use path.name just like e2e sweep_utils
        
        Uses Electrum-native widgets and ColorScheme for consistent theming.
        
        Returns a QFrame containing:
        - Path icon and name
        - Details button (ℹ️) - shows miniscript, keys, technical info
        - Sweep button - executes the sweep
        """
        logger.info(f"[DIALOG] _create_path_button_from_definition() for '{path.name}'...")
        from PyQt6.QtWidgets import QPushButton
        from electrum.i18n import _

        # Determine if this path is available
        has_funds = balance > 0
        locktime = params.get('locktime', 0)
        locktime_satisfied = not path.requires_locktime or current_height >= locktime

        # Path is available if it has funds AND (doesn't require locktime OR locktime is satisfied)
        is_available = has_funds and (not path.requires_locktime or locktime_satisfied)

        logger.info(f"[DIALOG]   has_funds={has_funds}, locktime={locktime}, locktime_satisfied={locktime_satisfied}")
        logger.info(f"[DIALOG]   is_available={is_available}")

        # Calculate blocks remaining for locktime-dependent paths
        blocks_remaining = 0
        if path.requires_locktime and current_height < locktime:
            blocks_remaining = locktime - current_height
            logger.info(f"[DIALOG]   blocks_remaining={blocks_remaining}")

        # Create sweep button tooltip
        if not has_funds:
            sweep_tooltip = _("Address has no balance (0 sats). Cannot sweep empty address.")
            logger.info(f"[DIALOG]   Sweep disabled: no funds")
        elif not locktime_satisfied:
            sweep_tooltip = _("Timelock not yet reached") + f" ({blocks_remaining} {_('blocks remaining')})"
            logger.info(f"[DIALOG]   Sweep disabled: timelock not satisfied")
        else:
            sweep_tooltip = _(path.description)
            logger.info(f"[DIALOG]   Sweep enabled: {path.description}")

        # Create the row frame - use Electrum's ColorScheme for theme-aware colors
        row = QFrame()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(12)
        row.setLayout(row_layout)
        
        # Theme-aware styling using Electrum's ColorScheme
        # This ensures proper appearance in both light and dark themes
        if is_available:
            bg_color = ColorScheme.GREEN.as_color()
            bg_color.setAlpha(30)  # Light tint
            border_color = ColorScheme.GREEN.as_color()
            border_color.setAlpha(100)
        else:
            bg_color = ColorScheme.DEFAULT.as_color()
            bg_color.setAlpha(20)
            border_color = ColorScheme.DEFAULT.as_color()
            border_color.setAlpha(60)
        
        row.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({bg_color.red()}, {bg_color.green()}, {bg_color.blue()}, {bg_color.alpha()});
                border: 1px solid rgba({border_color.red()}, {border_color.green()}, {border_color.blue()}, {border_color.alpha()});
                border-radius: 6px;
            }}
        """)
        
        # Path icon - using unicode emoji (consistent across platforms)
        icon_label = QLabel(path.icon)
        icon_label.setFixedWidth(24)
        row_layout.addWidget(icon_label)
        
        # Path name and status - using Electrum's color scheme
        if path.requires_locktime and not locktime_satisfied:
            status_color = ColorScheme.RED.as_color().name()
            name_text = f"<b>{path.display_name}</b>"
        elif is_available:
            status_color = ColorScheme.GREEN.as_color().name()
            name_text = f"<b>{path.display_name}</b>"
        else:
            status_color = ColorScheme.DEFAULT.as_color().name()
            name_text = f"<b>{path.display_name}</b>"
        
        name_label = QLabel(name_text)
        row_layout.addWidget(name_label)
        
        row_layout.addStretch()
        
        # Details button - use Electrum's native OkButton style (info variant)
        details_btn = OkButton(self, "ℹ")
        details_btn.setFixedSize(28, 28)
        details_btn.setToolTip(_("Show path details (miniscript, keys, etc.)"))
        
        # Get contract for details dialog
        script_type = self.addr_data.get('script_type', '')
        contract = get_contract_for_script_type(script_type)
        output_type = 'taproot' if 'taproot' in script_type else 'p2wsh'
        
        # Connect details button
        details_btn.clicked.connect(
            lambda checked, p=path, c=contract, ot=output_type: self._show_path_details(p, c, ot, params)
        )
        row_layout.addWidget(details_btn)
        
        # Sweep button - use Electrum's native OkButton
        sweep_btn = OkButton(self, _("Sweep"))
        sweep_btn.setEnabled(is_available)
        sweep_btn.setToolTip(sweep_tooltip)
        sweep_btn.clicked.connect(lambda: self._execute_path_sweep(path.name))
        row_layout.addWidget(sweep_btn)

        return row
    
    def _show_path_details(self, path: SpendingPath, contract: ContractDefinition, output_type: str, params: dict):
        """Show the path details dialog."""
        network = 'signet'  # TODO: Get from wallet
        if hasattr(self, 'wallet') and self.wallet:
            if constants.net.TESTNET:
                network = 'testnet'
            elif constants.net.SIGNET:
                network = 'signet'
            elif constants.net.NET_NAME == 'mainnet':
                network = 'mainnet'
        
        dialog = PathDetailsDialog(self, contract, path, params, output_type, network)
        dialog.exec()
    
    def _show_miniscript_visualizer_all_paths(self, contract: ContractDefinition, output_type: str, params: dict):
        """Show the miniscript visualizer dialog with ALL spending paths."""
        from .miniscript_visualizer import MiniscriptVisualizerDialog
        
        # For Taproot: we'll show all leaves in the visualizer
        # For P2WSH: show the main miniscript
        # The visualizer will handle showing all paths if it's Taproot with multiple leaves
        if output_type == 'taproot' and contract.taproot_leaves:
            # Use first leaf as primary (visualizer will show all)
            miniscript_str = contract.taproot_leaves[0]
        else:
            # Use contract's miniscript directly (symbolic form)
            miniscript_str = contract.miniscript
        
        # Get key labels using contract's key_roles for better display names
        key_labels = {}
        # First, map pubkeys to parameter names from params dict
        pubkey_to_param_name = {}
        for key_name, key_value in params.items():
            if isinstance(key_value, bytes) and len(key_value) in (33, 32):  # Compressed or x-only
                pubkey_to_param_name[key_value] = key_name
            elif isinstance(key_value, str):
                # Try to parse hex string
                try:
                    pubkey_bytes = bytes.fromhex(key_value)
                    if len(pubkey_bytes) in (33, 32):
                        pubkey_to_param_name[pubkey_bytes] = key_name
                except:
                    pass
        
        # Now map to display names using contract's key_roles
        for pubkey, param_name in pubkey_to_param_name.items():
            # Try to get key role from contract
            key_role = contract.get_key_role(param_name)
            if key_role:
                # Use display name from key role (e.g., "Alice (Party A)")
                key_labels[pubkey] = key_role.display_name
            else:
                # Fallback to parameter name, but make it more readable
                # Convert "alice" -> "Alice", "key1" -> "Key 1"
                display_name = param_name.replace('_', ' ').title()
                key_labels[pubkey] = display_name
        
        # Get Taproot metadata if applicable (for all paths, not just one)
        taproot_metadata = None
        if output_type == 'taproot':
            # Try to extract Taproot metadata from address data
            taproot_metadata = {}
            if hasattr(self, 'addr_data'):
                # Look for taproot-specific fields
                addr_info = self.addr_data.get('taproot_addr_info', {})
                if addr_info:
                    # Get general taproot info (not path-specific)
                    taproot_metadata['internal_key'] = addr_info.get('internal_key')
                    taproot_metadata['output_key'] = addr_info.get('output_key')
                    taproot_metadata['merkle_root'] = addr_info.get('merkle_root')
                    # Don't set leaf_index - visualizer will show all leaves
        
        # Create visualizer dialog (will show all paths for Taproot contracts)
        dialog = MiniscriptVisualizerDialog(
            self,
            miniscript_str,
            params,
            key_labels=key_labels,
            address=self.address,
            context='tapscript' if output_type == 'taproot' else 'p2wsh',
            taproot_metadata=taproot_metadata,
            contract=contract  # Pass contract for key role lookups - visualizer will load all leaves
        )
        dialog.exec()

    
    def _update_balance_display(self, **kwargs):
        """Update the balance label with current balance from Electrum's cache."""
        if not hasattr(self, 'balance_label') or self.balance_label is None:
            return
            
        try:
            c, u, x = self.wallet.get_addr_balance(self.address)
            balance = c + u + x
            
            # Handle zero balance cleanly (avoid "0. sat" display)
            if balance > 0:
                if self.plugin.config:
                    balance_text = self.plugin.config.format_amount_and_units(balance)
                else:
                    balance_text = f"{balance:,} sat"
                balance_color = ColorScheme.GREEN.as_color().name()
            else:
                # Clean zero display
                base_unit = self.plugin.config.get_base_unit() if self.plugin.config else 'sat'
                balance_text = f"0 {base_unit}"
                balance_color = ColorScheme.DEFAULT.as_color().name()
            
            self.balance_label.setText(f"{_('Balance')}: <b>{balance_text}</b>")
            self.balance_label.setStyleSheet(f"color: {balance_color};")
        except Exception as e:
            logger.error(f"[DIALOG] Error updating balance display: {e}")
    
    def _refresh_coin_list(self):
        """Refresh the coin list with current UTXO data.
        
        Fetches UTXO data from cache and rebuilds the coin list widget.
        IMPORTANT: Never uses network fallback to prevent UI thread blocking.
        """
        logger.info(f"[DIALOG] _refresh_coin_list() starting...")
        if not hasattr(self, 'coin_list') or self.coin_list is None:
            return
        if not hasattr(self, 'coins_label') or self.coins_label is None:
            return
            
        try:
            coins_data = self._get_all_coins()
            logger.info(f"[DIALOG] _refresh_coin_list: success={coins_data.get('success')}, coins_count={len(coins_data.get('coins', []))}, unspent={coins_data.get('unspent_count', 0)}, spent={coins_data.get('spent_count', 0)}")
            
            if coins_data['success'] and coins_data['coins']:
                coins = coins_data['coins']
                unspent = coins_data['unspent_count']
                spent = coins_data['spent_count']
                
                # Update label
                if spent > 0:
                    self.coins_label.setText(f"<b>{_('Coins')}:</b> {len(coins)} ({unspent} {_('unspent')}, {spent} {_('spent')})")
                else:
                    self.coins_label.setText(f"<b>{_('Coins')}:</b> {len(coins)}")
                
                # Update coin list data and repopulate
                self.coin_list._coins = coins
                self.coin_list._populate()
            else:
                # No coins found
                self.coins_label.setText(f"<b>{_('Coins')}:</b> 0")
                self.coin_list._coins = []
                self.coin_list._populate()
                
        except Exception as e:
            logger.error(f"[DIALOG] Error refreshing coin list: {e}")
    
    def _execute_path_sweep(self, path: str):
        """Execute sweep for a given path (called by dynamically created buttons).
        
        Uses ContractDefinition as single source of truth for path metadata.
        
        Args:
            path: The spending path name (e.g., 'normal', 'recovery', 'arbitration_alice')
        """
        logger.debug(f"[DEBUG] _execute_path_sweep called with path={path!r}")
        
        # Get contract definition from single source of truth
        script_type = self.addr_data.get('script_type', 'cltv_hodl')
        
        from ..cltv_lib.address_regenerator import parse_script_type
        from ..cltv_lib.contracts import CONTRACTS
        
        contract_name, output_type = parse_script_type(script_type)
        contract = CONTRACTS.get(contract_name)
        
        if not contract:
            self.show_error(f"Unknown contract type: {contract_name}")
            return
        
        # Get path info from ContractDefinition
        path_info = contract.get_path(path)
        if not path_info:
            available_paths = [p.name for p in contract.paths]
            self.show_error(f"Unknown path '{path}'. Available: {available_paths}")
            return
        
        path_display = path_info.display_name
        path_name = f"{contract.name} - {path_display}"
        
        logger.debug(f"[DEBUG] Path: {path_name}, requires_locktime={path_info.requires_locktime}")
        
        # Special handling for data publishing publisher path - show warning
        if contract_name == 'data_publishing' and path == 'publisher':
            params = self.get_params()
            data_preimage = params.get('data_preimage', '')
            
            if not data_preimage:
                self.show_error(
                    _("Cannot claim: data preimage not available.\n\n") +
                    _("The preimage may have been deleted from wallet storage.")
                )
                return
            
            # Warn user that data will become public
            if path_info.warning:
                self.show_message(
                    _("⚠️ WARNING: Data Revelation\n\n") +
                    _(path_info.warning) + "\n\n" +
                    _("Data preimage (hex): ") + data_preimage[:40] + ("..." if len(data_preimage) > 40 else "") + "\n\n" +
                    _("If you understand and want to continue, click OK to proceed.")
                )
        
        # Get locktime from params
        params = self.get_params()
        locktime = params.get('locktime')
        
        # Execute sweep using ContractDefinition metadata
        self._execute_sweep(
            path_name=path_name,
            path=path,
            requires_locktime=path_info.requires_locktime,
            locktime=locktime
        )
    
    # ==================== UNIFIED TRANSACTION BUILDER ====================
    
    def _build_cltv_transaction(self, dest_address: str, path: str, fee_sats: int = None) -> dict:
        """Universal CLTV transaction builder for all script types.
        
        Uses script_type from addr_data to automatically:
        - Select the correct sweeper
        - Extract required parameters
        - Load appropriate test keys
        - Apply path-specific locktime logic
        
        Args:
            dest_address: Destination address for swept funds
            path: Spending path (e.g., 'normal', 'recovery', 'arbitration_alice')
            fee_sats: Optional fee override (None = use dynamic fees)
        
        Returns:
            {'success': bool, 'tx': PartialTransaction, 'error': str}
        """
        try:
            # Get script_id and use ContractDefinition (single source of truth)
            script_id = self._get_script_id()
            script_type = self.addr_data.get('script_type', 'cltv_hodl')
            
            logger.info(f"[BUILDER] ========================================")
            logger.info(f"[BUILDER] Building transaction for {script_id}")
            logger.info(f"[BUILDER] Script type: {script_type}")
            logger.info(f"[BUILDER] Path: {path}")
            logger.info(f"[BUILDER] Destination: {dest_address}")
            
            # Get contract definition from ContractDefinition (single source of truth)
            from ..cltv_lib.address_regenerator import parse_script_type
            from ..cltv_lib.contracts import CONTRACTS
            
            contract_name, output_type = parse_script_type(script_type)
            contract = CONTRACTS.get(contract_name)
            
            if not contract:
                return {'success': False, 'error': f'Unknown contract type: {contract_name}'}
            
            # Get path info from ContractDefinition
            path_info = contract.get_path(path)
            if not path_info:
                valid_paths = [p.name for p in contract.paths]
                return {'success': False, 'error': f'Invalid path "{path}" for {contract_name}. Valid: {valid_paths}'}
            
            logger.info(f"[BUILDER] Path config: requires_locktime={path_info.requires_locktime}")
            
            # Extract parameters
            params = self.get_params()
            script_hex = self.addr_data.get('script_hex')
            
            # Get registry config to validate required params
            try:
                registry_config = get_config(script_id)
            except ValueError:
                return {'success': False, 'error': f'Unknown script_id: {script_id}'}
            
            # Basic validation - check for script_hex
            if not script_hex:
                return {'success': False, 'error': 'Missing script_hex in address data'}
            
            # Get UTXOs and balance
            utxo_data = self._get_utxos_and_balance()
            if not utxo_data['success']:
                return {'success': False, 'error': utxo_data['error']}
            
            utxos = utxo_data['utxos']
            balance = utxo_data['balance']
            
            logger.info(f"[BUILDER] UTXOs: {len(utxos)}, Balance: {balance} sats")
            
            # Determine transaction locktime first (needed for fee calculation)
            locktime_param = params.get('locktime')
            
            # Handle None or ensure it's a valid number
            if locktime_param is None:
                locktime_param = 0
            
            # Determine tx_locktime based on path requirements
            if path_info.requires_locktime:
                tx_locktime = locktime_param
            else:
                tx_locktime = 0
            
            if tx_locktime is None:
                tx_locktime = 0
            
            # Use FeeCalculator for accurate fee estimation
            if fee_sats is not None:
                # User-provided fee override
                total_fees = fee_sats
                output_amount = balance - total_fees
                logger.info(f"[BUILDER] Using user-provided fee: {total_fees} sats")
            else:
                # Get fee rate
                fee_rate = self.get_dynamic_fee_rate()
                logger.info(f"[BUILDER] Fee rate: {fee_rate} sat/vbyte")
                
                # Convert UTXOs to FeeCalculator format (txid/vout instead of tx_hash/tx_pos)
                fee_calc_utxos = [
                    {
                        'txid': utxo['tx_hash'],
                        'vout': utxo['tx_pos'],
                        'value': utxo['value']
                    }
                    for utxo in utxos
                ]
                
                # Use FeeCalculator with path_name and params for exact witness size calculation
                # This eliminates the need for 20% buffer when path is known
                calculator = FeeCalculator(
                    fee_rate=fee_rate,
                    script_type=script_type,
                    path_name=path,  # Enable dynamic calculation
                    params=params,   # Needed for script size calculation
                    network=self.network  # Enable network fee estimation
                )
                fee_result = calculator.calculate_for_utxos(
                    utxos=fee_calc_utxos,
                    dest_address=dest_address,
                    locktime=tx_locktime
                )
                
                if not fee_result['success']:
                    return {'success': False, 'error': fee_result['error']}
                
                total_fees = fee_result['total_fees']
                output_amount = fee_result['output_amount']
                estimated_vsize = fee_result['estimated_vsize']
                actual_fee_rate = fee_result['fee_rate']
                
                logger.info(f"[BUILDER] Estimated tx size: {estimated_vsize} vbytes (from Electrum)")
                logger.info(f"[BUILDER] Calculated fee: {total_fees} sats ({actual_fee_rate:.2f} sat/vbyte)")
                
                # Validate minimum relay fee
                if actual_fee_rate < 1.0:
                    return {
                        'success': False, 
                        'error': f'Fee rate too low: {actual_fee_rate:.2f} sat/vbyte (minimum 1.0 sat/vbyte required)'
                    }
            
            output_data = {'success': True, 'amount': output_amount, 'error': None}
            if not output_data['success']:
                return {'success': False, 'error': output_data['error']}
            
            output_amount = output_data['amount']
            
            # CRITICAL: Detect broken addresses from parameter storage bug
            broken_reasons = []
            
            # Check for missing locktime (affects all CLTV paths that require it)
            # Note: locktime=0 is VALID (means immediately available, no waiting)
            if locktime_param is None and path_info.requires_locktime:
                broken_reasons.append(f"Locktime is missing (required for this path)")
            
            # Check for missing parameters using ContractDefinition (single source of truth)
            from ..cltv_lib.registry import parse_script_id
            from ..cltv_lib.contracts import CONTRACTS

            try:
                contract_name, _ = parse_script_id(script_type)
                contract = CONTRACTS.get(contract_name)
                if contract:
                    required_params = contract.get_required_param_names()
                    missing_params = [p for p in required_params if params.get(p) is None]
                    if missing_params:
                        broken_reasons.append(f"Missing required parameters: {missing_params}")
                else:
                    broken_reasons.append(f"Unknown contract type: {contract_name}")
            except ValueError:
                broken_reasons.append(f"Invalid script_type format: {script_type}")
            
            # If address is broken, block sweep with helpful error
            if broken_reasons:
                logger.error(f"[ERROR] ❌ Cannot sweep broken address")
                for reason in broken_reasons:
                    logger.error(f"[ERROR] ❌ {reason}")
                logger.error(f"[ERROR] ❌ This address was created before parameter storage fix")
                
                reasons_text = '\n'.join(f'  • {r}' for r in broken_reasons)
                return {
                    'success': False,
                    'error': (
                        f'Cannot sweep: Address has invalid parameters\n\n'
                        f'Problems detected:\n{reasons_text}\n\n'
                        f'This address was created with a storage bug that lost critical parameters.\n\n'
                        f'Solution:\n'
                        f'1. The fix has been applied to prevent this in the future\n'
                        f'2. This specific address cannot be recovered\n'
                        f'3. Create a new address and it will work correctly\n\n'
                        f'If funds are locked here, they are permanently unspendable '
                        f'because the script cannot be satisfied without the original parameters.'
                    )
                }
            
            # Handle None or ensure it's a valid number (for non-CLTV paths)
            if locktime_param is None:
                locktime_param = 0
            
            # Determine tx_locktime using ContractDefinition
            if path_info.requires_locktime:
                tx_locktime = locktime_param
            else:
                tx_locktime = 0
            
            # Log transaction details
            contract_name = script_type.replace('cltv_', '').replace('_', ' ').upper()
            self._log_transaction_details(contract_name, path, len(utxos), balance, total_fees, output_amount, tx_locktime if tx_locktime > 0 else None)
            
            # Get sweeper from registry (same as e2e tests)
            # Handle path-specific parameters
            sweep_kwargs = {'path': path}
            
            # Special handling for data publishing - pass data_preimage if available
            if 'data_publishing' in script_id and path == 'publisher':
                data_preimage = params.get('data_preimage', '')
                if data_preimage:
                    sweep_kwargs['data_preimage'] = data_preimage
            
            try:
                sweeper = get_sweeper(script_id, **sweep_kwargs)
                logger.info(f"[BUILDER] Got sweeper from registry: {sweeper.__class__.__name__}")
            except Exception as e:
                return {'success': False, 'error': f'Failed to get sweeper for {script_id}: {e}'}
            
            # Load keys for signing the sweep transaction
            # For now, we default to test keys. Wallet key lookup is attempted
            # but will only work if the address was created with wallet-derived keys.
            params = self.get_params()
            
            # DEBUG: Log the full address record
            logger.debug(f"[DEBUG] Address record from storage:")
            logger.debug(f"[DEBUG]   address: {self.address}")
            logger.debug(f"[DEBUG]   script_type: {script_type}")
            logger.debug(f"[DEBUG]   params: {params}")
            logger.debug(f"[DEBUG]   script_hex: {script_hex[:80]}..." if len(script_hex) > 80 else f"[DEBUG]   script_hex: {script_hex}")
            
            keys = {}
            
            # Get contract info from registry (single source of truth)
            from ..cltv_lib.registry import parse_script_id
            try:
                contract_name, _ = parse_script_id(script_type)
            except ValueError:
                contract_name = None

            logger.debug(f"[DEBUG] script_type={script_type}, contract_name={contract_name}")
            
            # For simple CLTV (both P2WSH and Taproot), get the private key from wallet
            if contract_name == 'hodl':
                pubkey_hex = params.get('pubkey')
                if not pubkey_hex:
                    return {'success': False, 'error': 'Missing pubkey in address parameters'}
                
                logger.debug(f"[DEBUG] Pubkey from params: {pubkey_hex}")
                
                # Get private key from wallet for this pubkey
                try:
                    from electrum.bitcoin import pubkey_to_address
                    from electrum_ecc import ECPubkey
                    
                    # Find the private key in the wallet
                    pubkey_obj = ECPubkey(bytes.fromhex(pubkey_hex))
                    
                    # Try to get the private key from wallet
                    privkey = None
                    if self.wallet.has_password():
                        # Need password - this is a limitation for now
                        return {'success': False, 'error': 'Wallet is encrypted. Please decrypt wallet first to sweep CLTV addresses.'}
                    
                    # Get keystore and derive the private key
                    keystore = self.wallet.get_keystore()
                    if hasattr(keystore, 'get_private_key'):
                        # Try different derivation paths
                        key_source = params.get('key_source', {})
                        logger.debug(f"[DEBUG] Key source: {key_source}")
                        
                        # First check if this IS the test key pubkey
                        # Test key: secp256k1 generator point
                        TEST_KEY_PUBKEY = '0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798'
                        
                        if pubkey_hex.upper() == TEST_KEY_PUBKEY or key_source.get('type') == 'hardcoded':
                            # Use hardcoded test key
                            # SINGLE SOURCE OF TRUTH: Get test keys using ContractDefinition
                            try:
                                test_keys = self._get_test_keys_for_contract('hodl', 'sweep')
                                keys['pubkey'] = test_keys.get('pubkey')
                                
                                # DEBUG: Log the test key being used
                                if keys['pubkey']:
                                    test_pubkey = keys['pubkey'].get_public_key_hex()
                                    logger.debug(f"[DEBUG] Using hardcoded test key from ContractDefinition")
                                    logger.debug(f"[DEBUG] Test key pubkey: {test_pubkey}")
                                    logger.debug(f"[DEBUG] Address pubkey:  {pubkey_hex}")
                                    logger.debug(f"[DEBUG] Keys match: {test_pubkey.upper() == pubkey_hex.upper()}")
                            except Exception as e:
                                logger.error(f"[WARNING] Failed to get test keys from ContractDefinition: {e}")
                                keys['pubkey'] = get_test_privkey('hodl')
                            
                            logger.info(f"[{contract_name}] Using hardcoded test key (POC)")
                        else:
                            # Try to find the key in the wallet by matching pubkey
                            logger.info(f"[KEY_LOOKUP] Searching for key with pubkey: {pubkey_hex}")
                            
                            # Get all addresses and their public keys
                            found_key = None
                            for wallet_addr in self.wallet.get_addresses():
                                try:
                                    # Get the pubkey for this address
                                    wallet_pubkey = self.wallet.get_public_key(wallet_addr)
                                    if wallet_pubkey:
                                        logger.info(f"[KEY_LOOKUP] Checking {wallet_addr}: {wallet_pubkey}")
                                        if wallet_pubkey.upper() == pubkey_hex.upper():
                                            # Found matching address - get its private key
                                            logger.info(f"[KEY_LOOKUP] ✓ Match found: {wallet_addr}")
                                            # Get private key using Electrum's API
                                            wif_key = self.wallet.export_private_key(wallet_addr, password=None)
                                            from electrum.bitcoin import deserialize_privkey
                                            from electrum_ecc import ECPrivkey
                                            txin_type, privkey_bytes, compressed = deserialize_privkey(wif_key)
                                            found_key = ECPrivkey(privkey_bytes)
                                            logger.info(f"[KEY_LOOKUP] ✓ Private key retrieved")
                                            break
                                except Exception as e:
                                    logger.error(f"[KEY_LOOKUP] Error checking {wallet_addr}: {e}")
                                    continue
                            
                            if found_key:
                                keys['pubkey'] = found_key
                                logger.info(f"[{contract_name}] Using wallet key")
                            else:
                                return {'success': False, 'error': f'Could not find private key for pubkey {pubkey_hex[:16]}... in wallet'}
                    else:
                        return {'success': False, 'error': 'Wallet keystore does not support private key extraction'}
                        
                except Exception as e:
                    return {'success': False, 'error': f'Failed to get private key: {e}'}
            else:
                # Other contract types use test keys for now (POC)
                # Get key names from ContractDefinition (single source of truth)
                from ..cltv_lib.contracts import CONTRACTS
                contract = CONTRACTS.get(contract_name)
                key_names = [role.name for role in contract.key_roles] if contract else []

                if key_names:
                    # SINGLE SOURCE OF TRUTH: Use ContractDefinition to get test keys
                    try:
                        keys_dict = self._get_test_keys_for_contract(contract_name, path)
                        logger.info(f"[{contract_name}] Using hardcoded test keys (POC)")
                        logger.debug(f"[DEBUG] Keys loaded from ContractDefinition: {list(keys_dict.keys())}")
                        keys.update(keys_dict)
                        logger.debug(f"[DEBUG] Keys for sweeper: {list(keys.keys())}")
                    except Exception as e:
                        logger.error(f"[WARNING] Failed to get test keys from ContractDefinition: {e}")
                        keys.update(self._get_test_keys(key_names))
                else:
                    return {'success': False, 'error': f'Unsupported script_id: {script_id}'}
            
            # Sweeper already created above using registry.get_sweeper() with path parameter
            logger.info(f"[BUILDER] Sweeper ready: {sweeper.__class__.__name__} (path={path})")
            
            # Build inputs
            logger.info(f"[BUILDER] Building {len(utxos)} transaction inputs...")
            tx_inputs = []
            for utxo in utxos:
                prevout = TxOutpoint(txid=bytes.fromhex(utxo['tx_hash']), out_idx=utxo['tx_pos'])
                txin = PartialTxInput(prevout=prevout)
                txin._trusted_value_sats = utxo['value']
                # CRITICAL: Use 0xFFFFFFFE for CHECKLOCKTIMEVERIFY scripts
                # Per BIP-65: nSequence = 0xFFFFFFFF disables CLTV verification
                # We must use 0xFFFFFFFE to enable CLTV, even when tx locktime is 0
                txin.nsequence = 0xFFFFFFFE
                
                # Calculate witness size dynamically from ContractDefinition (single source of truth)
                from ..cltv_lib.fee_calculator import calculate_witness_size
                
                # Calculate exact witness size dynamically from contract definition
                try:
                    witness_size = calculate_witness_size(
                        script_type=script_type,
                        path_name=path,
                        params=params
                    )
                    logger.info(f"[BUILDER] Dynamic witness size: {witness_size} bytes (path: {path})")
                except Exception as e:
                    # Fallback: estimate from contract structure
                    logger.warning(f"[BUILDER] ⚠️ Dynamic witness calculation failed: {e}, estimating from contract")
                    from ..cltv_lib.registry import parse_script_id
                    from ..cltv_lib.contracts import CONTRACTS
                    try:
                        contract_name, output_type = parse_script_id(script_type)
                        contract = CONTRACTS.get(contract_name)
                        if contract and contract.paths:
                            path_obj = contract.get_path(path)
                            if path_obj:
                                # Estimate from path structure
                                sig_size = 65 if output_type == 'taproot' else 73
                                num_sigs = len(path_obj.required_keys)
                                script_estimate = 150
                                control_block = 33 if output_type == 'taproot' else 0
                                witness_size = (num_sigs * sig_size) + script_estimate + control_block + 20
                            else:
                                witness_size = 250  # Conservative fallback
                        else:
                            witness_size = 250  # Conservative fallback
                    except Exception:
                        witness_size = 250  # Absolute fallback
                
                # Set script_type and witness_script based on address type
                if 'taproot' in script_type.lower():
                    txin.script_type = 'p2tr'
                    # CRITICAL: Mark as native segwit so is_segwit() returns True
                    # This enables witness_sizehint to be used in size estimation
                    txin._is_native_segwit = True
                    # Use dynamically calculated witness size
                    txin.witness_sizehint = witness_size
                else:
                    txin.script_type = 'p2wsh'
                    # CRITICAL: Mark as native segwit so is_segwit() returns True
                    txin._is_native_segwit = True
                    txin.witness_script = bytes.fromhex(script_hex)
                    # Use dynamically calculated witness size
                    txin.witness_sizehint = witness_size
                
                tx_inputs.append(txin)
            
            # Build output (will be adjusted after estimating actual tx size)
            logger.info(f"[BUILDER] Creating initial output: {dest_address} = {output_amount} sats")
            tx_output = PartialTxOutput.from_address_and_value(dest_address, output_amount)
            
            # Create transaction (unsigned, for size estimation)
            logger.info(f"[BUILDER] Creating transaction with locktime={tx_locktime}")
            tx = PartialTransaction.from_io(tx_inputs, [tx_output], locktime=tx_locktime)
            tx.version = 2
            
            # Log the estimated size for debugging (should match FeeCalculator's estimate)
            if fee_sats is None:
                # Verify our estimate - since inputs have _is_native_segwit=True and witness_sizehint,
                # this should match what FeeCalculator calculated
                verify_vsize = tx.estimated_size()
                logger.info(f"[BUILDER] Verified tx size: {verify_vsize} vbytes (fee: {total_fees} sats, rate: {total_fees/verify_vsize:.2f} sat/vbyte)")
                
                # Sanity check: warn if estimates differ significantly
                if hasattr(self, '_fee_calc_vsize') and abs(verify_vsize - self._fee_calc_vsize) > 5:
                    logger.warning(f"[BUILDER] ⚠️ Size estimate mismatch: FeeCalculator={self._fee_calc_vsize}, actual={verify_vsize}")
            
            logger.info(f"[{contract_name}] Signing {len(tx_inputs)} input(s)...")
            
            # CRITICAL: Sign inputs as they appear in the transaction after from_io()
            # Electrum may reorder inputs (BIP-69 lexicographic ordering)
            # We must iterate over tx.inputs(), not our original tx_inputs list
            
            # For Taproot, always recompute address info from params (deterministic)
            # NOTE: We no longer mutate txin.scriptpubkey here.
            #       Sighash computation is delegated to GenericSweeper.compute_sighash,
            #       which mirrors the e2e test flow and takes all required data explicitly.
            taproot_addr_info = None
            if 'taproot' in script_type.lower():
                # Use address_regenerator which uses build_contract() internally
                from ..cltv_lib.address_regenerator import regenerate_address_data
                try:
                    taproot_addr_info = regenerate_address_data(script_type, params)
                    logger.info(f"[BUILDER] Recomputed {script_type} address data via regenerator")
                except Exception as e:
                    logger.error(f"[BUILDER] ⚠️ Failed to regenerate Taproot address: {e}")

            for i, txin in enumerate(tx.inputs()):
                logger.info(f"[BUILDER] Signing input {i+1}/{len(tx.inputs())}...")
                logger.info(f"[BUILDER]   Input value: {txin._trusted_value_sats} sats")
                logger.info(f"[BUILDER]   Script type: {txin.script_type}")
                if hasattr(txin, 'witness_script') and txin.witness_script:
                    logger.info(f"[BUILDER]   Witness script: {txin.witness_script.hex()}")
                logger.info(f"[BUILDER]   nSequence: {hex(txin.nsequence)}")
                logger.info(f"[BUILDER]   Prevout: {txin.prevout.txid.hex()}:{txin.prevout.out_idx}")
                
                # Use script_type directly - it should already be in canonical format
                # (e.g., cltv_hodl_p2wsh, cltv_escrow_taproot)
                sweeper_script_type = script_type
                logger.info(f"[BUILDER] Using script_type: {sweeper_script_type}")
                
                # Build output dict FIRST (before sighash computation)
                # This ensures the script used for sighash matches the script in the witness
                output = {
                    'script_hex': script_hex,
                    'script_type': sweeper_script_type,
                    'locktime': locktime_param,
                    'params': params
                }
                
                # Add taproot_data for Taproot scripts (always recomputed)
                if 'taproot' in script_type.lower():
                    # Map UI path names to script path names
                    # (e.g., 'arbitration_alice' and 'arbitration_bob' both use 'arbitration' script)
                    # (e.g., 'refund' in UI maps to 'buyer_refund' in storage for data publishing)
                    script_path = path
                    if path in ('arbitration_alice', 'arbitration_bob'):
                        script_path = 'arbitration'
                    elif path == 'refund' and 'data_publishing' in script_type:
                        script_path = 'buyer_refund'
                    
                    logger.info(f"[BUILDER] Looking for script_path='{script_path}' in taproot_addr_info")
                    logger.info(f"[BUILDER] taproot_addr_info keys: {list(taproot_addr_info.keys())}")
                    
                    # Get leaf_index from path_info (single source of truth)
                    leaf_index = path_info.leaf_index if hasattr(path_info, 'leaf_index') else 0
                    leaf_key = f'leaf_{leaf_index}'
                    
                    # Determine control block and script based on contract structure
                    # Multi-path contracts: use leaf_scripts and control_blocks with leaf_N keys
                    if 'leaf_scripts' in taproot_addr_info and leaf_key in taproot_addr_info['leaf_scripts']:
                        output['script_hex'] = taproot_addr_info['leaf_scripts'][leaf_key]
                        output['control_block_hex'] = taproot_addr_info['control_blocks'].get(leaf_key)
                        logger.info(f"[BUILDER] ✓ Using leaf_scripts['{leaf_key}'] for path '{path}'")
                    else:
                        # Single-path contracts: use top-level control block and script
                        if 'control_block_hex' not in taproot_addr_info:
                            raise ValueError(f"Missing control_block_hex in taproot_addr_info for {script_type}")
                        output['control_block_hex'] = taproot_addr_info['control_block_hex']
                        output['script_hex'] = taproot_addr_info.get('script_hex')
                        logger.info(f"[BUILDER] ✓ Using top-level control_block_hex (single-path)")
                    
                    if 'control_block_hex' not in output or not output['control_block_hex']:
                        raise ValueError(f"Failed to get control_block_hex for path '{script_path}' (original path: '{path}')")
                    if 'script_hex' not in output or not output['script_hex']:
                        raise ValueError(f"Failed to get script_hex for path '{script_path}' (original path: '{path}')")
                    
                    # All contracts share these fields
                    output['internal_key'] = taproot_addr_info['internal_key']
                    output['output_key'] = taproot_addr_info['output_key']
                    
                    logger.info(f"[BUILDER] ✓ Using Taproot data (control_block: {output['control_block_hex'][:32]}..., script: {output['script_hex'][:32]}...)")
                
                # Add data_preimage for data publishing (all variants)
                if 'data_publishing' in script_type and 'data_preimage' in params:
                    output['data_preimage'] = params['data_preimage']
                    logger.info(f"[BUILDER] Added data_preimage to output: {params['data_preimage'][:16]}...")
                
                # Compute sighash using sweeper (single source of truth)
                # This ensures the script used for sighash matches the script in the witness
                logger.info(f"[BUILDER] Computing sighash using sweeper (single source of truth)...")
                try:
                    sighash = sweeper.compute_sighash(
                        tx=tx,
                        input_index=i,
                        output=output,
                        prevout_amount=txin._trusted_value_sats
                    )
                    logger.info(f"[BUILDER]   Sighash computed: {sighash.hex()}")
                except Exception as e:
                    # Fallback to manual computation if sweeper method fails
                    logger.warning(f"[BUILDER] ⚠️ Sweeper sighash computation failed: {e}, using fallback")
                    import traceback
                    traceback.print_exc()
                    if 'taproot' in script_type.lower():
                        from ..cltv_lib.builders.taproot.taproot_sighash_builder import compute_taproot_sighash
                        output_key = bytes.fromhex(output['output_key'])
                        scriptpubkey = bytes([0x51, 0x20]) + output_key
                        script_bytes = bytes.fromhex(output['script_hex'])
                        control_block_bytes = bytes.fromhex(output.get('control_block_hex', ''))
                        sighash = compute_taproot_sighash(
                            tx=tx,
                            input_index=i,
                            prevout_amount=txin._trusted_value_sats,
                            prevout_scriptpubkey=scriptpubkey,
                            script=script_bytes,
                            control_block=control_block_bytes
                        )
                    else:
                        preimage = tx.serialize_preimage(txin_index=i)
                        sighash = sha256d(preimage)
                
                logger.info(f"[BUILDER] Calling sweeper.build_witness() with {len(keys)} keys...")
                witness_items = sweeper.build_witness(output, keys, sighash)
                logger.info(f"[BUILDER] Witness built: {len(witness_items)} items")
                
                # Log witness item details (handle both bytes and ints)
                for idx, item in enumerate(witness_items):
                    if isinstance(item, int):
                        logger.info(f"[BUILDER]   Item {idx}: integer {item}")
                    elif idx == 0:
                        logger.info(f"[BUILDER]   Item {idx} (signature): {len(item)} bytes - {item.hex()[:80]}...")
                    else:
                        logger.info(f"[BUILDER]   Item {idx} (script/data): {len(item)} bytes")
                
                # Construct and attach witness
                from electrum.bitcoin import construct_witness
                txin.witness = construct_witness(witness_items)
                txin.script_sig = b''
            
            # Verify actual transaction size matches estimate (for debugging/tuning)
            if fee_sats is None:  # Only if we did automatic fee calculation
                actual_tx_size = tx.estimated_size()
                actual_fee_rate = total_fees / actual_tx_size

                logger.debug(f"[FEE] Actual tx size: {actual_tx_size} vbytes (estimate: {estimated_vsize}), fee: {total_fees} sats ({actual_fee_rate:.2f} sat/vbyte)")

                # Track fee estimation accuracy for future improvements
                calculator.record_transaction_accuracy(estimated_vsize, actual_tx_size)
                
                # NOTE: We cannot adjust output after signing because sighash commits to outputs!
                # If fee rate is too low, it's because our witness_sizehint was too small.
                # The fee calculator adds a small buffer to prevent this.
                if actual_fee_rate < 1.0:
                    logger.warning(f"[BUILDER] ⚠️ WARNING: Fee rate {actual_fee_rate:.2f} < 1.0 sat/vbyte!")
                    logger.warning(f"[BUILDER] ⚠️ Consider checking witness size calculation for '{script_type}' path '{path}'")
            
            logger.info(f"[{contract_name}] ✅ Transaction built successfully")
            return {'success': True, 'tx': tx}
            
        except Exception as e:
            logger.error(f"[BUILDER] Error building transaction: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    # ========================================================================
    # REACTIVE NETWORK UPDATES (Phase 9)
    # ========================================================================
    
    def closeEvent(self, event):
        """
        Clean up when dialog is closed.
        Note: @qt_event_listener decorator automatically unregisters callbacks.
        """
        event.accept()
    
    @qt_event_listener
    def on_event_blockchain_updated(self, *args):
        """Called when new block arrives - refresh locktime status."""
        self.refresh_status()
    
    @qt_event_listener
    def on_event_wallet_updated(self, wallet, *args):
        """Called when wallet state changes - refresh balance and coins.
        
        This is the primary event handler for wallet updates.
        Electrum automatically fires this when transactions are detected.
        """
        if wallet == self.wallet:
            self._update_balance_display()
            self._refresh_coin_list()
    
    # NOTE: on_event_history removed - wallet_updated already handles all balance/coin updates
    # Having both causes duplicate refreshes. Electrum's wallet_updated fires for all relevant changes.
    
    def refresh_status(self):
        """
        Refresh locktime status labels when blockchain height changes.
        
        This updates:
        - Current block height
        - Lock status (LOCKED/UNLOCKED)
        - Blocks remaining count
        """
        try:
            # Only refresh if we have the necessary UI elements
            if not hasattr(self, 'height_label') or not hasattr(self, 'status_label'):
                return
            
            # Get current height
            current_height = 0
            if self.wallet and self.wallet.network:
                try:
                    current_height = self.wallet.network.get_local_height()
                except Exception:
                    return
            
            # Get locktime from address data
            params = self.get_params()
            locktime = self.get_locktime()
            
            # Calculate lock status
            is_locked = current_height < locktime
            blocks_remaining = max(0, locktime - current_height)
            
            # Update height label
            self.height_label.setText(f"{_('Current Block Height)')}: <b>{current_height}</b>")
            
            # Update status label using helper method (Phase 4 - DRY principle)
            locktime_status = self._format_locktime_status(locktime, is_locked, blocks_remaining)
            self.status_label.setText(locktime_status['text'])
            self.status_label.setStyleSheet(f"color: {locktime_status['color'].name()}; font-weight: bold; font-size: 14px;")
            
            # NOTE: Balance/coin refresh is NOT done here - that's handled by wallet_updated event
            # This function only updates locktime status display
            
            logger.debug(f"[NETWORK] Updated CLTV status: height={current_height}, locktime={locktime}, locked={is_locked}")
            
        except Exception as e:
            logger.error(f"[NETWORK] Error refreshing status: {e}")
