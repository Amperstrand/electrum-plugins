"""
CHECKLOCKTIMEVERIFY Plugin for Electrum

Full-featured plugin for creating and managing BIP-65 CLTV timelock addresses.
Supports both P2WSH and Taproot formats for all contract types.

Storage format: v12.0.0 (minimal stateless - script_type + params only)
Legacy format support has been removed for code clarity.
"""

import logging
import time
from typing import Dict, List, Optional
from datetime import datetime
from electrum.plugin import BasePlugin, hook
from electrum.i18n import _
from electrum import bitcoin
from PyQt6.QtWidgets import QLabel, QCheckBox, QSpinBox, QPushButton, QGridLayout
from electrum.gui.qt.util import WindowModalDialog
from electrum.gui.qt.history_list import TX_ICONS

logger = logging.getLogger(__name__)


class Plugin(BasePlugin):
    """CHECKLOCKTIMEVERIFY Plugin - POC Version
    
    Console Commands (accessible via Electrum console):
    ===================================================
    
    Get the plugin instance:
        >>> cltv = plugins.get('checklocktimeverify')
        >>> wallet = window.wallet
    
    Delete ALL CLTV addresses (full reset):
        >>> cltv.cleanup_all_addresses(wallet)
    
    Delete a single address:
        >>> cltv.delete_address('tb1q...', wallet)
    """
    
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.windows = []
        self.wallet_windows = {}  # Map wallet -> window
        self._monitors = {}  # Map wallet -> CLTVAddressMonitor
        
        # No plugin-level UTXO cache - we rely on Electrum's wallet.adb which already caches and updates automatically
        
        # Get version info
        try:
            from .cltv_lib.version_info import get_version_dict
            version_info = get_version_dict()
            version_str = version_info['display']
            commit_hash = version_info['commit_hash']
            commit_date = version_info['commit_date']
        except Exception:
            version_str = "unknown"
            commit_hash = "unknown"
            commit_date = "unknown"
        
        # Log initialization with version info
        logger.info("=" * 80)
        logger.info(f"[CLTV] CLTV Plugin {version_str} Initializing...")
        logger.info(f"[CLTV]   - Plugin name: {name}")
        logger.info(f"[CLTV]   - Git commit: {commit_hash}")
        logger.info(f"[CLTV]   - Commit date: {commit_date}")
        logger.info("=" * 80)
        logger.info(f"[CLTV] Plugin {version_str} initialized")
        logger.info(f"[CLTV]   Git: {commit_hash} @ {commit_date}")
    
    def format_amount_with_fiat(self, amount_sat: int, *, add_thousands_sep: bool = True) -> str:
        """Format amount with optional fiat value (like Electrum's history tooltips)
        
        Returns: "0.00001234 BTC" or "0.00001234 BTC (≈ $0.50)" if FX available
        """
        # Base amount formatting
        base_str = self.config.format_amount_and_units(amount_sat)
        
        # Try to add fiat value if FX is enabled
        try:
            fx = self.config.get_fx() if hasattr(self.config, 'get_fx') else None
            if fx and fx.is_enabled():
                fiat_value = fx.value_str(amount_sat, add_thousands_sep=add_thousands_sep)
                if fiat_value:
                    return f"{base_str} (≈ {fiat_value})"
        except Exception:
            pass  # FX not available or error
        
        return base_str

    def requires_settings(self):
        """Signal that this plugin has user-configurable settings."""
        return True

    def settings_dialog(self, window, wallet):
        """Show plugin settings dialog."""
        d = WindowModalDialog(window, _("CLTV Plugin Settings"))
        
        layout = QGridLayout(d)
        
        # Debug logging toggle
        layout.addWidget(QLabel(_('Enable debug logging:')), 0, 0)
        debug_cb = QCheckBox()
        debug_cb.setChecked(self.config.get('cltv_debug', False))
        layout.addWidget(debug_cb, 0, 1)
        
        # Locktime offset
        layout.addWidget(QLabel(_('Default locktime offset (blocks):')), 1, 0)
        offset_spinbox = QSpinBox()
        offset_spinbox.setMinimum(1)
        offset_spinbox.setMaximum(1000)
        offset_spinbox.setValue(self.config.get('cltv_lock_offset', 3))
        offset_spinbox.setToolTip(_('Number of blocks to add to current height for new addresses'))
        layout.addWidget(offset_spinbox, 1, 1)
        
        # Info label
        info_label = QLabel(
            _('<i>Debug logs appear in Electrum console and follow Electrum logging configuration</i><br>'
              '<i>Locktime offset determines default value for new timelock addresses</i>')
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label, 2, 0, 1, 2)
        
        # Clear cache button
        # OK button
        ok_button = QPushButton(_("OK"))
        def save_settings():
            # Debug logging is now controlled via Electrum's standard logging configuration
            # Users can adjust log levels in Electrum's settings or via environment variables
            new_debug = debug_cb.isChecked()
            self.config.set_key('cltv_debug', new_debug)  # Keep for backward compatibility, but not used
            
            if new_debug:
                logger.info(f"[CLTV] [SETTINGS] Note: Debug logging is controlled via Electrum's standard logging configuration")
            
            # Save locktime offset
            old_offset = self.config.get('cltv_lock_offset', 3)
            new_offset = offset_spinbox.value()
            self.config.set_key('cltv_lock_offset', new_offset)
            
            if old_offset != new_offset:
                logger.info(f"[CLTV] [SETTINGS] Locktime offset changed: {old_offset} -> {new_offset} blocks")
            
            d.accept()
        
        ok_button.clicked.connect(save_settings)
        layout.addWidget(ok_button, 4, 1)
        
        return bool(d.exec())

    # ========= Shared Helpers (centralization for Electrum integration) =========
    def get_lock_status(self, wallet, locktime: int) -> dict:
        """Compute lock status for a CLTV block-height locktime.

        Returns dict:
            {
                'locked': bool,
                'blocks_remaining': int,
                'current_height': int,
                'icon_name': Optional[str],
                'label': str,              # "Locked" | "Unlocked"
                'tooltip': str,            # human-friendly description
            }
        """
        try:
            # Prefer AddressSynchronizer local height if available
            current_height = 0
            if getattr(wallet, 'adb', None):
                try:
                    current_height = wallet.adb.get_local_height()
                except Exception:
                    current_height = 0
            if current_height == 0 and getattr(wallet, 'network', None):
                try:
                    current_height = wallet.network.get_local_height()
                except Exception:
                    pass

            locked = current_height < locktime
            blocks_remaining = max(0, locktime - current_height)
            if locked:
                label = "Locked"
                icon_name = "lock.png"
                tooltip = (
                    f"CLTV locked until block {locktime:,}.\n"
                    f"Current height: {current_height:,}.\n"
                    f"Remaining: {blocks_remaining:,} block(s)."
                )
            else:
                label = "Unlocked"
                icon_name = None
                tooltip = (
                    f"CLTV unlocked.\n"
                    f"Current height: {current_height:,}.\n"
                    f"Required locktime was: {locktime:,}."
                )
            return {
                'locked': locked,
                'blocks_remaining': blocks_remaining,
                'current_height': current_height,
                'icon_name': icon_name,
                'label': label,
                'tooltip': tooltip,
            }
        except Exception as e:
            logger.error(f"[CLTV] [HELPER] get_lock_status error (locktime={locktime}): {e}")
            return {
                'locked': True,
                'blocks_remaining': 0,
                'current_height': 0,
                'icon_name': "lock.png",
                'label': "Locked",
                'tooltip': f"CLTV lock status unavailable (locktime {locktime}).",
            }

    def get_default_locktime(self, wallet, *, offset_blocks: int = 3) -> int:
        """Return a sensible default CLTV locktime: current height + configured offset.

        Reads 'cltv_lock_offset' from Electrum config if set; otherwise uses provided
        offset_blocks (default 3). Falls back safely if height undetermined.
        """
        try:
            configured_offset = self.config.get('cltv_lock_offset', offset_blocks) if getattr(self, 'config', None) else offset_blocks
            offset = max(1, int(configured_offset))
            height = 0
            if getattr(wallet, 'adb', None):
                try:
                    height = wallet.adb.get_local_height()
                except Exception:
                    height = 0
            if height == 0 and getattr(wallet, 'network', None):
                try:
                    height = wallet.network.get_local_height()
                except Exception:
                    height = 0
            return (height or 0) + offset
        except Exception as e:
            logger.warning(f"[CLTV] [HELPER] get_default_locktime failed: {e}")
            return max(1, int(offset_blocks))

    def build_status_cell(self, wallet, txid: str, is_lightning: bool = False) -> tuple:
        """Return (status, status_str, icon_name, tooltip) consistent with Electrum history.

        Uses wallet.get_tx_status and TX_ICONS from Electrum's history_list module.
        """
        # Get mined info directly from Electrum's ADB
        adb = wallet.adb
        tx_mined_info_raw = adb.get_tx_height(txid)
        # Build a synthetic TxMinedInfo for wallet.get_tx_status
        from electrum.util import TxMinedInfo
        tx_mined_info = TxMinedInfo(
            _height=tx_mined_info_raw._height if hasattr(tx_mined_info_raw, '_height') else tx_mined_info_raw.height(),
            conf=tx_mined_info_raw.conf if tx_mined_info_raw.conf is not None else 0,
            timestamp=getattr(tx_mined_info_raw, 'timestamp', None),
        )
        status, status_str = wallet.get_tx_status(txid, tx_mined_info)
        icon_name = "lightning" if is_lightning else (TX_ICONS[status] if 0 <= status < len(TX_ICONS) else None)

        # Tooltip similar to Electrum
        if status < 4:  # unconfirmed variants
            if status == 0:
                tip = "Unconfirmed (in mempool)"
            elif status == 1:
                tip = "Unconfirmed parent (parent not confirmed)"
            elif status == 2:
                tip = "Local or future (not SPV verified)"
            elif status == 3:
                tip = "Local broadcast (not yet confirmed)"
            else:
                tip = "Unconfirmed"
        else:
            if mined['conf'] >= 6:
                tip = f"Confirmed ≥6 (depth: {mined['conf']})"
            else:
                tip = f"Confirmed ({mined['conf']} conf)"
            if not mined['spv_verified']:
                tip += " - SPV header timestamp pending"
            else:
                # Append human-readable time if timestamp is known
                try:
                    from electrum.util import format_time
                    if mined['timestamp']:
                        tip += f"\nTime: {format_time(mined['timestamp'])}"
                except Exception:
                    pass
        return status, status_str, icon_name, tip
        
    @hook
    def load_wallet(self, wallet, window):
        """Called when a wallet is loaded - add CLTV tab + start monitoring"""
        logger.info(f"[CLTV] load_wallet called for window: {window}")
        if window not in self.windows:
            self.windows.append(window)
            self.wallet_windows[wallet] = window
            
            # Add CLTV tab to main window (Electrum pattern)
            # This is the primary UI - all functionality accessible from tab
            self.add_cltv_tab(window)
            
            # Initialize address monitor for this wallet (like Lightning)
            self._init_address_monitor(wallet)
            
    @hook  
    def close_wallet(self, wallet):
        """Called when wallet is closed - cleanup monitor"""
        logger.info(f"[CLTV] close_wallet called")
        
        # Cleanup monitor (prevent memory leaks)
        if wallet in self._monitors:
            try:
                self._monitors[wallet].unregister_callbacks()
                del self._monitors[wallet]
                logger.info(f"[CLTV] [MONITOR] Cleaned up monitor for wallet")
            except Exception as e:
                logger.error(f"[CLTV] [MONITOR] Error cleaning up: {e}")
    
    @hook
    def on_history(self, wallet, *args):
        """Called when wallet history updates - refresh CLTV tab."""
        if hasattr(self, 'cltv_list') and self.cltv_list:
            logger.debug(f"[CLTV] [HOOK] on_history: emitting update_rows for wallet {id(wallet)}")
            self.cltv_list.update_rows.emit(wallet)
        # Dialogs handle their own refresh via QtEventListener
    
    @hook
    def blockchain_updated(self, *args):
        """Called when new block arrives - refresh UI."""
        # Electrum's ADB cache is automatically updated
        if hasattr(self, 'cltv_list') and self.cltv_list:
            for wallet in self.wallet_windows.keys():
                self.cltv_list.update_rows.emit(wallet)
        # Dialogs handle their own refresh via QtEventListener
    
    @hook
    def wallet_updated(self, wallet, *args):
        """Called when wallet state changes - refresh UI."""
        if hasattr(self, 'cltv_list') and self.cltv_list:
            logger.debug(f"[CLTV] [HOOK] wallet_updated: emitting update_rows for wallet {id(wallet)}")
            self.cltv_list.update_rows.emit(wallet)
        # Dialogs handle their own refresh via QtEventListener
    
    def _init_address_monitor(self, wallet):
        """Initialize address registration for CLTV addresses.
        
        Note: Custom CLTVAddressMonitor was removed during cleanup.
        We now rely on Electrum's address synchronizer for UTXO tracking.
        Addresses are registered with wallet.adb.add_address(), which makes Electrum
        track them and fire wallet hooks (on_history, blockchain_updated, wallet_updated)
        automatically when transactions are detected.
        """
        # Register all existing CLTV addresses with Electrum's synchronizer
        # This ensures the ElectrumX server sends us scripthash notifications
        try:
            addresses = self.load_all_addresses(wallet, use_cache=False)
            if addresses:
                self._register_addresses_with_wallet(wallet, addresses)
        except Exception as e:
            logger.error(f"[CLTV] [WALLET] Error registering addresses: {e}")
            import traceback
            traceback.print_exc()
    
    def _register_addresses_with_wallet(self, wallet, addresses):
        """Register CLTV addresses with Electrum's ADB for automatic UTXO tracking."""
        if not addresses:
            return
        
        try:
            registered_count = 0
            
            for addr_data in addresses:
                address = addr_data['address']
                
                # Skip if already tracked
                if wallet.is_mine(address):
                    continue
                
                # Register with ADB (lower-level, works for all wallet types)
                if hasattr(wallet, 'adb') and hasattr(wallet.adb, 'add_address'):
                    try:
                        wallet.adb.add_address(address)
                        registered_count += 1
                    except Exception:
                        pass
            
            if registered_count > 0:
                # Trigger sync to fetch history for newly added addresses
                if hasattr(wallet, 'synchronize'):
                    wallet.synchronize()
                logger.info(f"[CLTV] [WALLET] Registered {registered_count} CLTV addresses with Electrum")
            
        except Exception as e:
            logger.error(f"[CLTV] [WALLET] Error registering addresses: {e}")
    
    def _register_single_address_with_wallet(self, wallet, address):
        """Register a single CLTV address with Electrum wallet."""
        try:
            # Check if already registered
            if wallet.is_mine(address):
                logger.debug(f"[CLTV] [WALLET] Address already is_mine: {address[:20]}...")
                return
            
            logger.debug(f"[CLTV] [WALLET] Attempting to register: {address[:20]}...")
            logger.debug(f"[CLTV] [WALLET]   Wallet type: {type(wallet).__name__}")
            logger.debug(f"[CLTV] [WALLET]   has import_address: {hasattr(wallet, 'import_address')}")
            
            # Add to wallet's address list for UTXO tracking
            try:
                # Import as watching address
                wallet.import_address(address)
                logger.info(f"[CLTV] [WALLET] ✓ Registered address via import_address: {address[:20]}...")
            except AttributeError as ae:
                logger.debug(f"[CLTV] [WALLET] import_address not available: {ae}")
                # Wallet type doesn't support import_address (e.g., deterministic wallets)
                # Try alternative method: add to address synchronizer directly
                if hasattr(wallet, 'adb') and hasattr(wallet.adb, 'add_address'):
                    wallet.adb.add_address(address)
                    logger.info(f"[CLTV] [WALLET] ✓ Added via ADB.add_address: {address[:20]}...")
                else:
                    logger.warning(f"[CLTV] [WALLET] ⚠️  No registration method available for: {address[:20]}...")
            except Exception as e:
                logger.warning(f"[CLTV] [WALLET] ⚠️  import_address failed for {address[:20]}...: {e}")
                # Try ADB fallback
                if hasattr(wallet, 'adb') and hasattr(wallet.adb, 'add_address'):
                    try:
                        wallet.adb.add_address(address)
                        logger.info(f"[CLTV] [WALLET] ✓ Fallback to ADB.add_address: {address[:20]}...")
                    except Exception as e2:
                        logger.error(f"[CLTV] [WALLET] ❌ ADB.add_address also failed: {e2}")
            
            # Trigger sync to fetch history for newly added address
            if hasattr(wallet, 'synchronize'):
                wallet.synchronize()
        except Exception as e:
            logger.info(f"[CLTV] [WALLET] Error registering address {address[:20]}...: {e}")
    
    def _trigger_address_sync(self, wallet, address):
        """Trigger network sync to fetch history for newly added address"""
        try:
            # Get the synchronizer from the wallet
            if not hasattr(wallet, 'adb'):
                return
            
            adb = wallet.adb
            if not hasattr(adb, 'synchronizer') or not adb.synchronizer:
                logger.debug(f"[CLTV] [SYNC] No synchronizer available")
                return
            
            # Request scripthash subscription from the network
            # This will trigger the synchronizer to fetch the address history
            from electrum.bitcoin import address_to_scripthash
            sh = address_to_scripthash(address)
            
            # The synchronizer will automatically fetch history when we subscribe
            # Force an immediate sync by calling the synchronizer's method
            if hasattr(adb.synchronizer, 'synchronize'):
                adb.synchronizer.synchronize()
                logger.info(f"[CLTV] [SYNC] ✓ Triggered network sync for {address[:20]}...")
            
        except Exception as e:
            logger.debug(f"[CLTV] [SYNC] Could not trigger sync: {e}")
    
    # ========================================================================
    # Monitor Callback Methods
    # ========================================================================
    # All removed - stateless model doesn't need callbacks
    # UI updates reactively via AddressSynchronizer events
    
    def trigger_ui_refresh(self, wallet=None, address: Optional[str] = None):
        """Notify UI that address status changed - refresh tab.
        
        Dialogs handle their own refresh via QtEventListener, so we only need to
        refresh the main tab list.
        
        Args:
            wallet: Optional wallet instance (if None, refreshes all)
            address: Optional address string (if provided, only updates that row)
        """
        # If address is provided, update only that row (much faster!)
        if address and wallet and hasattr(self, 'cltv_list') and self.cltv_list:
            self.cltv_list.update_single_row.emit(wallet, address)
        else:
            # Full refresh for all wallets
            if hasattr(self, 'cltv_list') and self.cltv_list:
                wallets = [wallet] if wallet else self.wallet_windows.keys()
                for w in wallets:
                    self.cltv_list.update_rows.emit(w)
    
    # ==================== Electrum Query Helpers ====================
    # Query blockchain data from Electrum's cache (v3.0.0-optimized)
    
    # get_sweep_info() REMOVED - no swept state tracking
    # Spending transactions visible in Electrum's transaction history via HistoryModel

    # ==================== End Query Helpers ====================
    
    # ==================== Tab-Based UI (Electrum Pattern) ====================
    
    def add_cltv_tab(self, window):
        """
        Add CLTV Contracts tab to main window.
        
        Follows Electrum's ChannelsList pattern:
        1. Check for existing valid tab - reuse if found
        2. Remove any invalid/duplicate tabs
        3. Create new tab if needed
        
        Args:
            window: ElectrumWindow instance
        """
        try:
            from .dialogs.cltv_list import CLTVList
            from electrum.gui.qt.util import read_QIcon
            
            # Find all "Contracts" tabs and check if any are valid
            tab_count = window.tabs.count()
            contracts_tab_indices = []
            valid_tab_index = None
            valid_list_widget = None
            
            for i in range(tab_count):
                try:
                    tab_text = window.tabs.tabText(i)
                    if tab_text == _("Contracts"):
                        contracts_tab_indices.append(i)
                        # Check if this tab has a valid CLTVList widget
                        widget = window.tabs.widget(i)
                        if widget and hasattr(widget, 'list_widget'):
                            list_widget = widget.list_widget
                            if isinstance(list_widget, CLTVList):
                                valid_tab_index = i
                                valid_list_widget = list_widget
                                logger.info(f"[CLTV] [TAB] Found valid CLTV tab at index {i}")
                except Exception:
                    continue
            
            # If we found a valid tab, reuse it
            if valid_tab_index is not None and valid_list_widget is not None:
                logger.info(f"[CLTV] [TAB] Reusing existing valid CLTV tab")
                self.cltv_list = valid_list_widget
                # Remove any duplicate/invalid tabs
                for i in reversed(contracts_tab_indices):
                    if i != valid_tab_index:
                        logger.info(f"[CLTV] [TAB] Removing duplicate/invalid Contracts tab at index {i}")
                        try:
                            widget = window.tabs.widget(i)
                            window.tabs.removeTab(i)
                            if widget:
                                widget.deleteLater()
                        except Exception as e:
                            logger.info(f"[CLTV] [TAB] Error removing tab at index {i}: {e}")
                # Refresh data
                self.cltv_list.update_rows.emit(window.wallet)
                return
            
            # No valid tab found - remove all existing "Contracts" tabs and create a new one
            if contracts_tab_indices:
                logger.info(f"[CLTV] [TAB] Found {len(contracts_tab_indices)} invalid Contracts tab(s) - removing")
                for i in reversed(contracts_tab_indices):
                    try:
                        widget = window.tabs.widget(i)
                        window.tabs.removeTab(i)
                        if widget:
                            widget.deleteLater()
                    except Exception as e:
                        logger.info(f"[CLTV] [TAB] Error removing invalid tab at index {i}: {e}")
            
            # Create new tab
            logger.info(f"[CLTV] [TAB] Creating new CLTV tab...")
            
            # Create the list widget (like ChannelsList)
            self.cltv_list = CLTVList(window, self)
            
            # Wrap in tab container with toolbar (Electrum pattern)
            tab = window.create_list_tab(self.cltv_list)
            
            # Store reference for later access
            self.cltv_tab = tab
            
            # Add to main window's tabs
            # Use a timelock icon (or create custom one)
            try:
                icon = read_QIcon("clock1.png")  # Try Electrum's clock icon
            except Exception:
                icon = None
            
            window.tabs.addTab(tab, icon, _("Contracts"))
            
            # Initial data load
            self.cltv_list.update_rows.emit(window.wallet)
            
            logger.info(f"[CLTV] [TAB] ✅ CLTV tab added successfully")
            
        except Exception as e:
            logger.error(f"[CLTV] [TAB] [ERROR] Failed to add CLTV tab: {e}")
            import traceback
            logger.info(f"[CLTV] [TAB] Traceback:\n{traceback.format_exc()}")
    
    def refresh_cltv_tab(self, wallet):
        """Refresh the CLTV tab data."""
        if hasattr(self, 'cltv_list') and self.cltv_list:
            self.cltv_list.update_rows.emit(wallet)
    
    # ==================== End Tab-Based UI ====================
    
    # ==================== Dialog Launchers (Used by Tab) ====================
    

    def settings_widget(self, window):
        """Return QWidget for Electrum's built-in plugin settings panel.
        Exposes:
          - Verbose debug logging toggle (cltv_debug)
          - Default locktime offset (cltv_lock_offset)
          - Derivation branch (cltv_derivation_branch) for CLTV keys
          - Clear sweep cache action
        """
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox,
            QLineEdit, QPushButton
        )
        from PyQt6.QtCore import Qt

        w = QWidget(window)
        vbox = QVBoxLayout(w)

        # Verbose debug logging toggle
        cb_debug = QCheckBox(_("Enable verbose debug logs"))
        cb_debug.setChecked(bool(self.config.get('cltv_debug', False)))
        def on_debug_toggle(state):
            val = state == Qt.CheckState.Checked
            try:
                self.config.set_key('cltv_debug', val)
            except Exception:
                pass
            # verbose_debug removed - use Electrum's standard logging configuration instead
            logger.info(f"[CLTV] Note: Debug logging is controlled via Electrum's standard logging configuration")
            logger.info(f"[CLTV] cltv_debug set to {val}")
        cb_debug.stateChanged.connect(on_debug_toggle)
        vbox.addWidget(cb_debug)

        # Default locktime offset spinner
        h_offset = QHBoxLayout()
        h_offset.addWidget(QLabel(_("Default locktime offset (blocks):")))
        sb_offset = QSpinBox()
        sb_offset.setRange(1, 5000)
        sb_offset.setValue(int(self.config.get('cltv_lock_offset', 3)))
        def on_offset_changed(val):
            try:
                self.config.set_key('cltv_lock_offset', int(val))
                logger.info(f"[CLTV] cltv_lock_offset set to {val}")
            except Exception:
                pass
        sb_offset.valueChanged.connect(on_offset_changed)
        h_offset.addWidget(sb_offset)
        h_offset.addStretch()
        vbox.addLayout(h_offset)

        # Derivation branch input (numeric)
        h_branch = QHBoxLayout()
        h_branch.addWidget(QLabel(_("Derivation branch (change index):")))
        le_branch = QLineEdit()
        branch_val = str(self.config.get('cltv_derivation_branch', '9999'))
        le_branch.setText(branch_val)
        le_branch.setPlaceholderText("9999")
        le_branch.setToolTip(_("Non-standard branch isolates CLTV keys (default 9999)."))
        def on_branch_edit():
            val = le_branch.text().strip()
            if not val.isdigit():
                return
            try:
                self.config.set_key('cltv_derivation_branch', val)
                logger.info(f"[CLTV] cltv_derivation_branch set to {val}")
            except Exception:
                pass
        le_branch.editingFinished.connect(on_branch_edit)
        h_branch.addWidget(le_branch)
        h_branch.addStretch()
        vbox.addLayout(h_branch)

        # Info label
        info_label = QLabel(_("Changes persist immediately. Default locktime uses offset above when creating new timelocks."))
        info_label.setWordWrap(True)
        vbox.addWidget(info_label)

        vbox.addStretch()
        w.setLayout(vbox)
        return w
    
    # ========================================================================
    # Storage Methods
    # ========================================================================
    
    def save_timelock_data(self, address: str, wallet, **data) -> None:
        """Save timelock address data to wallet.db
        
        Storage Format v12.0.0 (Minimal/Stateless):
        Only stores script_type + params. Everything else (scripts, control blocks,
        output script) is derived on-demand via address_regenerator.
        
        Args:
            address: The generated address
            wallet: Wallet instance
            **data: All address metadata including:
                - script_type: Contract type identifier
                - All params unpacked at top level (locktime, user_pubkey, etc.)
            
        Raises:
            RuntimeError: If wallet has no database or storage fails
            ValueError: If required parameters are missing or invalid
        """
        script_type = data.get('script_type', 'unknown')
        logger.info(f"[CLTV] [STORAGE] 💾 Saving {script_type} address {address[:20]}...")
        logger.debug(f"[CLTV] [STORAGE] 🔍 DEBUG: Incoming data keys: {list(data.keys())}")
        
        # Get plugin storage from wallet.db
        if not hasattr(wallet, 'db'):
            raise RuntimeError(f"Wallet has no database attribute - cannot save address")
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get('checklocktimeverify', {})
            
            # Initialize structure if needed
            if not cltv_data or 'addresses' not in cltv_data:
                cltv_data = {'addresses': {}}
            
            # Get contract definition (single source of truth)
            script_type = data.get('script_type', 'cltv_hodl_p2wsh')
            
            try:
                from .cltv_lib.registry import parse_script_id
                from .cltv_lib.contracts import CONTRACTS
                
                contract_name, output_type = parse_script_id(script_type)
                contract = CONTRACTS.get(contract_name)
                
                if not contract:
                    raise ValueError(f"Unknown contract: {contract_name} (from script_type: {script_type})")
                
                required_params = contract.get_required_param_names()
                logger.info(f"[CLTV] [STORAGE] 📋 Contract requires: {required_params}")
                
                # Extract params from nested or flat format
                params = {}
                
                if 'params' in data and isinstance(data['params'], dict):
                    logger.debug(f"[CLTV] [STORAGE] 🔍 Found nested params, extracting...")
                    nested_params = data['params']
                    for param_name in required_params:
                        if param_name in nested_params:
                            params[param_name] = nested_params[param_name]
                            logger.info(f"[CLTV] [STORAGE] ✓ Found {param_name}: {str(nested_params[param_name])[:40]}...")
                        else:
                            logger.error(f"[CLTV] [STORAGE] ❌ Missing required param: {param_name}")
                else:
                    # Extract from flat data
                    for param_name in required_params:
                        if param_name in data:
                            params[param_name] = data[param_name]
                            logger.info(f"[CLTV] [STORAGE] ✓ Found {param_name}: {str(data[param_name])[:40]}...")
                        else:
                            logger.error(f"[CLTV] [STORAGE] ❌ Missing required param: {param_name}")
                
                # Validate extracted parameters
                missing = [p for p in required_params if params.get(p) is None]
                if missing:
                    raise ValueError(f"Missing required parameters: {missing}. Available keys: {list(data.keys())}")
                
                logger.info(f"[CLTV] [STORAGE] ✅ All required parameters present")
                    
            except ValueError as e:
                # Unknown script type - cannot proceed
                raise ValueError(f"Invalid script type: {script_type} - {e}")
            
            # Validate critical parameters
            if 'locktime' in params:
                locktime = params['locktime']
                if locktime is None:
                    logger.warning(f"[CLTV] [STORAGE] [WARNING] locktime is None, defaulting to 0")
                    params['locktime'] = 0
                elif not isinstance(locktime, int):
                    logger.warning(f"[CLTV] [STORAGE] [WARNING] locktime is {type(locktime)}, converting to int")
                    params['locktime'] = int(locktime)
            
            # Log extracted params for debugging
            param_summary = {k: (v if not isinstance(v, str) or len(v) < 20 else f"{v[:20]}...") 
                            for k, v in params.items()}
            logger.info(f"[CLTV] [STORAGE] Extracted params: {param_summary}")
            
            # Add key_source tracking (optional metadata, not used for regeneration)
            if 'key_source' in data:
                params['key_source'] = data['key_source']
            
            # Build minimal address entry - only store script_type + params
            # Everything else is derived on-demand via regenerate_address_data()
            address_data = {
                'script_type': script_type,
                'params': params,
                'created_at': int(time.time())
            }
            
            # Save to nested structure (allow overwrites for storage format updates)
            is_update = address in cltv_data['addresses']
            cltv_data['addresses'][address] = address_data
            plugin_storage['checklocktimeverify'] = cltv_data
            try:
                wallet.db.write()
            except Exception as e:
                raise RuntimeError(f"Failed to write to wallet database: {e}") from e
            
            # Update cache with new address instead of invalidating (much faster!)
            # Build complete address entry for cache
            cache_entry = {
                'address': address,
                'script_type': script_type,
                'params': params,
                'created_at': address_data.get('created_at', int(time.time())),
            }
            # Regenerate full data for cache
            try:
                from .cltv_lib.address_regenerator import regenerate_address_data
                regenerated = regenerate_address_data(script_type, params)
                cache_entry.update(regenerated)
            except Exception as e:
                logger.warning(f"[CLTV] [STORAGE] ⚠️  Failed to regenerate for cache: {e}")
            
            self.update_address_cache(wallet, address, cache_entry)
            
            # Register with monitor for automatic tracking
            if wallet in self._monitors:
                self._monitors[wallet].add_cltv_address(address, address_data)
            
            # Register with Electrum wallet for UTXO tracking
            self._register_single_address_with_wallet(wallet, address)
            
            # Trigger immediate network sync for the new address
            self._trigger_address_sync(wallet, address)
            
            action = "Updated" if is_update else "Saved"
            logger.info(f"[CLTV] [STORAGE] ✓ {action} {script_type} ({len(cltv_data['addresses'])} total)")
    
    def load_all_addresses(self, wallet, use_cache: bool = True) -> List[Dict]:
        """Load all saved CLTV addresses from wallet.db
        
        Args:
            wallet: Wallet instance
            use_cache: If True, use cached data if available (default: True)
        
        Returns:
            List of address dictionaries with regenerated data
        """
        try:
            if not hasattr(wallet, 'db'):
                return []
            
            # Check cache first (wallet-specific)
            wallet_id = id(wallet)
            if use_cache and hasattr(self, '_address_cache'):
                cached = self._address_cache.get(wallet_id)
                if cached is not None:
                    return cached
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get('checklocktimeverify', {})
            
            if not cltv_data or 'addresses' not in cltv_data:
                return []
            
            # Check storage version - skip if not v12.0.0
            storage_version = cltv_data.get('version')
            if storage_version != '12.0.0':
                version_str = storage_version if storage_version else '(not set)'
                logger.info(f"[CLTV] [STORAGE] ⏭️  Skipping addresses (storage version {version_str}, expected 12.0.0)")
                return []
            
            # Load addresses (v12.0.0 format only - script_type + params)
            addresses = []
            skipped_count = 0
            failed_count = 0
            
            for addr, data in list(cltv_data['addresses'].items()):
                script_type = data.get('script_type', '')
                params = data.get('params', {})
                
                # Skip addresses without required fields
                if not script_type or not params:
                    skipped_count += 1
                    logger.info(f"[CLTV] [STORAGE] ⏭️  Skipping {addr[:20]}... (missing script_type or params)")
                    continue
                
                # Regenerate full address data from script_type + params
                # If regeneration fails, the address is broken and cannot be loaded
                try:
                    from .cltv_lib.address_regenerator import regenerate_address_data
                    addr_entry = regenerate_address_data(script_type, params)
                    
                    # Override with stored address (the key) and metadata
                    addr_entry['address'] = addr  # Use stored address as key
                    addr_entry['created_at'] = data.get('created_at', 0)
                    
                    addresses.append(addr_entry)
                        
                except Exception as regen_err:
                    failed_count += 1
                    import traceback
                    tb_str = traceback.format_exc()
                    
                    # Log full error details for debugging
                    logger.error(f"[CLTV] [STORAGE] ❌ CRITICAL: Failed to regenerate address {addr[:20]}...")
                    logger.error(f"[CLTV] [STORAGE] ❌   Script Type: {script_type}")
                    logger.error(f"[CLTV] [STORAGE] ❌   Params: {params}")
                    logger.error(f"[CLTV] [STORAGE] ❌   Error: {regen_err}")
                    logger.error(f"[CLTV] [STORAGE] ❌   Traceback:\n{tb_str}")
                    logger.error(f"[CLTV] [STORAGE] ❌   This address cannot be loaded and will be skipped.")
                    # Don't add to addresses list - address is broken
            
            # Log summary
            if skipped_count > 0:
                logger.info(f"[CLTV] [STORAGE] ⏭️  Skipped {skipped_count} addresses (missing required fields)")
            if failed_count > 0:
                logger.error(f"[CLTV] [STORAGE] ❌ FAILED to load {failed_count} addresses (regeneration errors - see logs above)")
            
            # Cache the result
            if not hasattr(self, '_address_cache'):
                self._address_cache = {}
            self._address_cache[wallet_id] = addresses
            
            # Register addresses with wallet for UTXO tracking
            # Uses Electrum's native address tracking
            try:
                if wallet and addresses:
                    self._register_addresses_with_wallet(wallet, addresses)
            except Exception as e:
                logger.info(f"[CLTV] [WALLET] Could not register addresses on load: {e}")
            
            logger.info(f"[CLTV] [STORAGE] ✓ Loaded {len(addresses)} addresses (with regeneration)")
            
            # Debug: Show breakdown by script type
            type_counts = {}
            for addr in addresses:
                st = addr.get('script_type', 'unknown')
                type_counts[st] = type_counts.get(st, 0) + 1
            if type_counts:
                logger.info(f"[CLTV] [STORAGE] 📊 Breakdown: {dict(sorted(type_counts.items()))}")
            
            return addresses
            
        except Exception as e:
            logger.info(f"[CLTV] [STORAGE] ERROR loading: {e}")
            return []
    
    def invalidate_address_cache(self, wallet=None):
        """Invalidate address cache after saves/deletes.
        
        Args:
            wallet: If specified, only invalidate for this wallet. Otherwise clear all.
        """
        if not hasattr(self, '_address_cache'):
            return
        
        if wallet:
            wallet_id = id(wallet)
            self._address_cache.pop(wallet_id, None)
        else:
            self._address_cache.clear()
    
    def update_address_cache(self, wallet, address: str, address_data: Dict):
        """Update cache with a single new/updated address instead of invalidating.
        
        This is much faster than invalidating and reloading all addresses.
        
        Args:
            wallet: Wallet instance
            address: The address string
            address_data: Complete address data dict (will be regenerated if needed)
        """
        if not hasattr(self, '_address_cache'):
            self._address_cache = {}
        
        wallet_id = id(wallet)
        cached = self._address_cache.get(wallet_id)
        
        if cached is None:
            # Cache doesn't exist yet, invalidate to force reload
            self.invalidate_address_cache(wallet)
            return
        
        # Check if address already exists in cache
        existing_idx = None
        for i, addr_entry in enumerate(cached):
            if addr_entry.get('address') == address:
                existing_idx = i
                break
        
        # Regenerate full address data if needed
        if 'script_hex' not in address_data or not address_data.get('script_hex'):
            try:
                script_type = address_data.get('script_type', '')
                params = address_data.get('params', {})
                if script_type and params:
                    from .cltv_lib.address_regenerator import regenerate_address_data
                    regenerated = regenerate_address_data(script_type, params)
                    address_data.update(regenerated)
            except Exception as e:
                logger.warning(f"[CLTV] [CACHE] ⚠️  Failed to regenerate {address[:20]}: {e}")
        
        # Update or append to cache
        if existing_idx is not None:
            cached[existing_idx] = address_data
        else:
            cached.append(address_data)
        
        self._address_cache[wallet_id] = cached
    
    
    def delete_address(self, address: str, wallet) -> bool:
        """Delete a single CLTV address from wallet storage.
        
        Args:
            address: Address to delete
            wallet: Wallet instance
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            if not hasattr(wallet, 'db'):
                return False
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get('checklocktimeverify', {})
            
            if 'addresses' not in cltv_data:
                return False
            
            if address in cltv_data['addresses']:
                del cltv_data['addresses'][address]
                plugin_storage['checklocktimeverify'] = cltv_data
                wallet.db.write()
                self.invalidate_address_cache(wallet)
                logger.info(f"[CLTV] [CLEANUP] 🗑️  Deleted address: {address[:30]}...")
                return True
            
            return False
            
        except Exception as e:
            logger.info(f"[CLTV] [CLEANUP] ERROR deleting address: {e}")
            return False
    
    def remove_address(self, wallet, address: str) -> bool:
        """Remove a CLTV address from wallet storage (alias for delete_address)."""
        return self.delete_address(address, wallet)
    
    def set_address_label(self, wallet, address: str, label: str) -> bool:
        """Set a label for a CLTV address.
        
        Args:
            wallet: Wallet instance
            address: Address to label
            label: Label text
            
        Returns:
            True if label was set, False otherwise
        """
        try:
            if not hasattr(wallet, 'db'):
                return False
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get('checklocktimeverify', {})
            
            if 'addresses' not in cltv_data or address not in cltv_data['addresses']:
                return False
            
            cltv_data['addresses'][address]['label'] = label
            plugin_storage['checklocktimeverify'] = cltv_data
            wallet.db.write()
            self.invalidate_address_cache(wallet)
            logger.debug(f"[CLTV] [LABEL] Set label for {address[:20]}...: {label}")
            return True
            
        except Exception as e:
            logger.info(f"[CLTV] [LABEL] ERROR setting label: {e}")
            return False
    
    def cleanup_all_addresses(self, wallet) -> Dict:
        """Remove ALL CLTV addresses from wallet (full reset).
        
        ⚠️  WARNING: This deletes all addresses, including valid ones!
        
        Args:
            wallet: Wallet instance
            
        Returns:
            {'deleted': int, 'addresses': list}
        """
        logger.warning(f"[CLTV] [CLEANUP] ⚠️  WARNING: Deleting ALL CLTV addresses!")
        
        try:
            if not hasattr(wallet, 'db'):
                return {'deleted': 0, 'addresses': [], 'error': 'No wallet database'}
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get('checklocktimeverify', {})
            
            if 'addresses' not in cltv_data:
                return {'deleted': 0, 'addresses': []}
            
            all_addrs = list(cltv_data['addresses'].keys())
            count = len(all_addrs)
            
            # Clear all addresses
            cltv_data['addresses'] = {}
            plugin_storage['checklocktimeverify'] = cltv_data
            wallet.db.write()
            self.invalidate_address_cache(wallet)
            
            logger.info(f"[CLTV] [CLEANUP] 🗑️  Deleted ALL {count} CLTV addresses")
            return {'deleted': count, 'addresses': all_addrs}
            
        except Exception as e:
            logger.info(f"[CLTV] [CLEANUP] ERROR: {e}")
            return {'deleted': 0, 'addresses': [], 'error': str(e)}

    # Note: We use Electrum's native synchronizer for address monitoring.
    # Addresses are registered via adb.add_address() and balances are fetched
    # from wallet.get_addr_balance() which reads from Electrum's cache.
    # UTXOs are fetched directly via wallet.adb.get_addr_utxo().
    
    def sign_cltv_transaction(self, tx, pubkey_hex: str, privkey_hex: str = None):
        """
        Manually sign a CLTV transaction with custom witness script.
        
        Since Electrum can't auto-extract pubkeys from our custom CLTV script,
        we sign manually using the same ECDSA approach Electrum uses.
        
        Args:
            tx: PartialTransaction to sign
            pubkey_hex: Public key for signing
            privkey_hex: Private key (uses hardcoded test key if None)
            
        Returns:
            Signed transaction
        """
        from electrum.bitcoin import construct_witness
        from electrum.crypto import sha256d
        import electrum_ecc as ecc
        from electrum_ecc import ecdsa_der_sig_from_ecdsa_sig64
        
        # Get private key
        if pubkey_hex.upper() == '0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798':
            if privkey_hex is None:
                privkey_hex = '0000000000000000000000000000000000000000000000000000000000000001'
                logger.info(f"[CLTV] [SIGN] Using hardcoded test key for generator point")
        
        if privkey_hex is None:
            raise ValueError("Private key not available for signing")
        
        logger.info(f"[CLTV] [SIGN] 🔐 Signing {len(tx.inputs())} input(s)...")
        
        privkey = ecc.ECPrivkey(bytes.fromhex(privkey_hex))
        
        # Sign each input
        for i, txin in enumerate(tx.inputs()):
            logger.info(f"[CLTV] [SIGN]   Input {i}: Computing sighash...")
            
            preimage = tx.serialize_preimage(txin_index=i)
            sighash = sha256d(preimage)
            
            logger.info(f"[CLTV] [SIGN]     Signing with ECDSA...")
            sig_compact = privkey.ecdsa_sign(sighash)
            sig_der = ecdsa_der_sig_from_ecdsa_sig64(sig_compact)
            sig = sig_der + b'\x01'  # SIGHASH_ALL
            
            logger.info(f"[CLTV] [SIGN]     Building witness...")
            witness_items = [sig, txin.witness_script]
            txin.witness = construct_witness(witness_items)
            txin.script_sig = b''
            
            logger.info(f"[CLTV] [SIGN]   [OK] Input {i} signed")
        
        logger.info(f"[CLTV] [SIGN] [OK] Transaction fully signed: {tx.txid()}")
        
        return tx
    
    def get_cltv_keypairs(self, pubkey_hex: str, privkey_hex: str = None) -> dict:
        """
        Create external_keypairs dictionary for CLTV signing.
        
        Note: This is kept for compatibility but won't work with custom CLTV scripts
        because Electrum can't extract pubkeys from them. We use sign_cltv_transaction()
        instead for manual signing.
        
        Args:
            pubkey_hex: Public key from CLTV address parameters
            privkey_hex: Private key (for POC, uses hardcoded test key)
            
        Returns:
            Dictionary mapping pubkey_bytes -> privkey_bytes
        """
        # For POC: Use hardcoded test key if it's the secp256k1 generator point
        if pubkey_hex.upper() == '0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798':
            if privkey_hex is None:
                privkey_hex = '0000000000000000000000000000000000000000000000000000000000000001'
                logger.info(f"[CLTV] [KEYPAIRS] Using hardcoded test key for generator point")
        
        if privkey_hex is None:
            raise ValueError("Private key not available for signing")
        
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        privkey_bytes = bytes.fromhex(privkey_hex)
        
        logger.info(f"[CLTV] [KEYPAIRS] Created external_keypairs for pubkey: {pubkey_hex[:32]}...")
        
        return {pubkey_bytes: privkey_bytes}
    
    def create_sweep_tx_maker(
        self,
        address: str,
        utxos: list,
        dest_address: str,
        locktime: int,
        script_hex: str,
        pubkey_hex: str,
        wallet
    ):
        """
        Create a make_tx function for Electrum's ConfirmTxDialog.
        
        The returned function builds unsigned CLTV sweep transactions with
        proper fee calculation based on the fee policy.
        
        Args:
            address: CLTV address being swept from
            utxos: List of UTXOs to sweep
            dest_address: Destination address
            locktime: Required locktime for CLTV
            script_hex: Witness script hex
            pubkey_hex: Public key for signing
            wallet: Wallet instance
            
        Returns:
            Callable that accepts (fee_policy, confirmed_only, base_tx)
            and returns a PartialTransaction
        """
        
        def make_tx(fee_policy, *, confirmed_only=False, base_tx=None):
            """Build unsigned CLTV sweep transaction"""
            from electrum.transaction import (
                PartialTransaction, PartialTxInput, 
                PartialTxOutput, TxOutpoint
            )
            from electrum.util import NotEnoughFunds
            
            logger.info(f"[CLTV] [MAKE_TX] Building transaction with fee_policy: {fee_policy}")
            
            # Build inputs from CLTV UTXOs
            tx_inputs = []
            total_input = 0
            
            pubkey_bytes = bytes.fromhex(pubkey_hex)
            script_bytes = bytes.fromhex(script_hex)
            
            for utxo in utxos:
                prevout = TxOutpoint(
                    txid=bytes.fromhex(utxo['tx_hash']), 
                    out_idx=utxo['tx_pos']
                )
                txin = PartialTxInput(prevout=prevout)
                txin._trusted_value_sats = utxo['value']
                txin.nsequence = 0xFFFFFFFE  # Enable locktime, disable RBF
                txin.script_type = 'p2wsh'
                txin.witness_script = script_bytes
                
                # Note: We can't set txin.pubkeys directly (it's computed from script_descriptor)
                # For custom CLTV scripts, we'll sign manually using sign_cltv_transaction()
                
                tx_inputs.append(txin)
                total_input += utxo['value']
            
            logger.info(f"[CLTV] [MAKE_TX]   Inputs: {len(tx_inputs)} UTXOs = {total_input:,} sats")
            
            # Estimate transaction size for fee calculation
            # P2WSH witness: ~108 bytes per input, ~31 bytes per output
            estimated_size = (
                10 +  # Version, locktime, etc.
                len(tx_inputs) * 41 +  # Input outpoints + nSequence
                32 +  # Single output
                len(tx_inputs) * 108  # Witness data per input
            )
            
            logger.info(f"[CLTV] [MAKE_TX]   Estimated size: {estimated_size} vbytes")
            
            # Calculate fee using Electrum's policy
            fee = fee_policy.estimate_fee(
                size=estimated_size,
                network=wallet.network,
                allow_fallback_to_static_rates=True
            )
            
            logger.info(f"[CLTV] [MAKE_TX]   Fee: {fee:,} sats ({fee/estimated_size:.1f} sat/vbyte)")
            
            # Calculate output amount (sweep all minus fee)
            output_amount = total_input - fee
            
            logger.info(f"[CLTV] [MAKE_TX]   Output: {output_amount:,} sats to {dest_address[:20]}...")
            
            # Build single output (no change for sweeps)
            txout = PartialTxOutput.from_address_and_value(
                dest_address, 
                output_amount
            )
            
            # Create transaction
            tx = PartialTransaction.from_io(
                tx_inputs, 
                [txout], 
                locktime=locktime
            )
            tx.version = 2
            
            logger.info(f"[CLTV] [MAKE_TX] [OK] Built unsigned transaction: {total_input:,} - {fee:,} = {output_amount:,} sats")
            
            return tx
        
        return make_tx
    
    def fund_test_addresses(self, wallet, amount: int = 2000, fee: int = 1000) -> Dict:
        """
        Fund all unfunded CLTV test addresses with a single transaction.
        
        Usage from Electrum console:
            >>> cltv = plugins.get('checklocktimeverify')
            >>> cltv.fund_test_addresses(wallet, amount=2000)
        
        Args:
            wallet: Electrum wallet instance
            amount: Amount to send to each address (default: 2000 sats)
            fee: Total transaction fee (default: 1000 sats)
        
        Returns:
            dict with 'success', 'funded_count', 'tx', 'txid'
        """
        try:
            from electrum.transaction import PartialTransaction, PartialTxOutput
            
            logger.info(f"[CLTV] [FUND] Loading CLTV addresses from wallet...")
            addresses = self.load_all_addresses(wallet)
            
            if not addresses:
                return {'success': False, 'error': 'No CLTV addresses found'}
            
            # Find unfunded addresses (balance = 0)
            unfunded = []
            for addr_data in addresses:
                addr = addr_data['address']
                c, u, x = wallet.get_addr_balance(addr)
                balance = c + u + x
                if balance == 0:
                    unfunded.append(addr)
            
            if not unfunded:
                logger.info(f"[CLTV] [FUND] All {len(addresses)} addresses are already funded")
                return {'success': True, 'funded_count': 0, 'message': 'All addresses already funded'}
            
            logger.info(f"[CLTV] [FUND] Found {len(unfunded)} unfunded addresses (out of {len(addresses)} total)")
            
            # Build outputs
            outputs = [(addr, amount) for addr in unfunded]
            
            # Create transaction
            logger.info(f"[CLTV] [FUND] Building transaction: {len(unfunded)} outputs × {amount} sats + {fee} sat fee")
            tx = wallet.mktx(outputs=outputs, password=None, fee=fee)
            
            # Sign transaction
            logger.info(f"[CLTV] [FUND] Signing transaction...")
            wallet.sign_transaction(tx, password=None)
            
            # Broadcast
            logger.info(f"[CLTV] [FUND] Broadcasting transaction...")
            network = wallet.network
            if network:
                result = network.run_from_another_thread(network.broadcast_transaction(tx))
                txid = tx.txid()
                
                logger.info(f"[CLTV] [FUND] ✅ Successfully funded {len(unfunded)} addresses")
                logger.info(f"[CLTV] [FUND]    TXID: {txid}")
                for i, addr in enumerate(unfunded):
                    logger.info(f"[CLTV] [FUND]    [{i+1}] {addr[:30]}... = {amount} sats")
                
                return {
                    'success': True,
                    'funded_count': len(unfunded),
                    'tx': tx,
                    'txid': txid,
                    'addresses': unfunded
                }
            else:
                return {'success': False, 'error': 'No network connection'}
                
        except Exception as e:
            logger.info(f"[CLTV] [FUND] Error: {e}")
            import traceback
            logger.info(f"[CLTV] {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
