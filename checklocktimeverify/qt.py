"""
CHECKLOCKTIMEVERIFY Plugin for Electrum
Based on BIP-65: https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki

This plugin creates time-locked Bitcoin addresses using OP_CHECKLOCKTIMEVERIFY.
Funds sent to these addresses can only be spent after a specified block height or timestamp.

⚠️  DISCLAIMER ⚠️
This is a proof of concept for educational purposes.
It is NOT suitable for mainnet usage.
DO NOT use this plugin on Bitcoin mainnet with real funds.
Testing on signet/testnet only!
"""

import time
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QRadioButton, QButtonGroup, QSpinBox,
    QDateTimeEdit, QMessageBox, QGroupBox, QFormLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QFont, QPixmap

from electrum.plugin import BasePlugin, hook
from electrum.i18n import _
from electrum.bitcoin import hash160_to_p2sh, bfh, pubkey_to_address
from electrum.crypto import hash_160
from electrum import bitcoin, constants
from electrum.transaction import Transaction, PartialTxInput, PartialTxOutput, PartialTransaction, TxOutpoint, TxOutput
from electrum.util import UserFacingException

# Import DRY architecture components
from .address_factory import create_cltv_address, AddressFactory
from .script_builders import get_builder, SCRIPT_BUILDERS
from .ui_components import (
    OutputTypeSelector, LocktimeSelector, PubkeyInput, ResultDisplay,
    create_description_label, create_generate_button
)
from .test_vectors import (
    BIP32_V1_M_PUBKEY, BIP32_V1_M0H_PUBKEY, BIP32_V1_M0H1_PUBKEY,
    BIP32_V2_M_PUBKEY, ALL_TEST_PUBKEYS
)

logger = logging.getLogger(__name__)


class TimelockDialog(QDialog):
    """Dialog for creating CHECKLOCKTIMEVERIFY timelocked addresses"""
    
    # LOCKTIME_THRESHOLD distinguishes block height from timestamp
    # Values below 500000000 are treated as block heights
    # Values >= 500000000 are treated as Unix timestamps
    LOCKTIME_THRESHOLD = 500000000
    
    def __init__(self, parent, plugin):
        super().__init__(parent)
        self.plugin = plugin
        self.wallet = parent.wallet
        self.window = parent  # Store reference to window for network access
        
        # 🚨 MAINNET PROTECTION 🚨
        if constants.net.TESTNET == False and constants.net.REGTEST == False:
            self.log("[ERROR] ⚠️  MAINNET DETECTED - PLUGIN DISABLED ⚠️")
            self.log("[ERROR] This plugin is for educational purposes only!")
            self.log("[ERROR] DO NOT USE ON MAINNET!")
            QMessageBox.critical(
                parent,
                "🚨 MAINNET NOT SUPPORTED 🚨",
                "This CHECKLOCKTIMEVERIFY plugin is a proof of concept!\n\n"
                "⚠️  Educational use only ⚠️\n\n"
                "It is NOT suitable for mainnet usage with real Bitcoin!\n\n"
                "Please restart Electrum with --testnet or --signet"
            )
            raise RuntimeError("CLTV Plugin cannot run on mainnet")
        
        self.setWindowTitle("BIP-65 CLTV Examples - Educational Timelock Generator [SIGNET-PRODUCTION]")
        self.setMinimumWidth(900)
        self.setMinimumHeight(800)
        self.resize(950, 900)
        
        # Cache for UTXO queries to avoid duplicate network calls
        self.utxo_cache = {}  # {address: {'utxos': [...], 'balance': int, 'timestamp': float}}
        self.utxo_cache_ttl = 30  # Cache for 30 seconds
        
        # Storage file for timelock data
        wallet_dir = os.path.dirname(self.wallet.storage.path)
        self.storage_file = os.path.join(wallet_dir, 'cltv_timelock_data.json')
        self.log(f"[INIT] CLTV Plugin initialized")
        self.log(f"[INIT] Storage file: {self.storage_file}")
        
        self.setup_ui()
        
        # Auto-load keys after UI is fully constructed
        self.auto_load_keys()
        
        # Auto-refresh timelock list on window load
        self.refresh_timelock_list()
        
        # Register for new block notifications
        self.register_callbacks()
    
    def log(self, message: str):
        """Log message to Electrum console"""
        msg = f"[CLTV] {message}"
        logger.info(msg)
        print(msg)
        
        # Also log to Electrum's console if available
        try:
            if hasattr(self.window, 'console') and self.window.console:
                self.window.console.showMessage(msg)
        except Exception as e:
            # Silently fail if console not available
            pass
    
    def get_default_locktime(self) -> int:
        """Get default locktime: current block height + 2 blocks"""
        try:
            network = self.window.network if hasattr(self.window, 'network') else None
            current_height = network.get_local_height() if network else 0
            return current_height + 2 if current_height > 0 else 870000
        except Exception as e:
            self.log(f"[WARNING] Could not get current height: {e}")
            return 870000  # Fallback
    
    def get_current_height(self) -> int:
        """Get current block height from network"""
        try:
            network = self.window.network if hasattr(self.window, 'network') else None
            return network.get_local_height() if network else 0
        except Exception:
            return 0
    
    def get_block_tooltip(self, context: str = "") -> str:
        """Get consistent tooltip for block height inputs"""
        current_height = self.get_current_height()
        tooltip = f"The block height at which {context if context else 'the timelock expires'}.\n\n"
        tooltip += f"Current block: {current_height}\n"
        tooltip += f"Default: current + 2 blocks for quick testing\n\n"
        tooltip += "Tip: For testing, use current + 2 to 6 blocks"
        return tooltip
    
    def check_address_utxos(self, address: str, force_refresh: bool = False, persistent_cache: dict = None) -> dict:
        """Check UTXOs for an address with caching to avoid duplicate queries
        
        Args:
            address: Bitcoin address to check
            force_refresh: Skip cache and query network
            persistent_cache: Optional dict with cached UTXO data from JSON storage
        
        Returns:
            dict with 'has_utxos', 'balance_sats', 'utxos', 'cached' keys
        """
        current_time = time.time()
        
        # Check persistent cache from JSON first (if provided and not force refresh)
        if not force_refresh and persistent_cache:
            cache_age = current_time - persistent_cache.get('utxo_check_time', 0)
            # Use 5-minute cache for persistent storage (faster startup)
            if cache_age < 300:  # 5 minutes
                self.log(f"[CACHE] Using persistent cache for {address} (age: {int(cache_age)}s)")
                return {
                    'has_utxos': persistent_cache.get('has_utxos', False),
                    'balance_sats': persistent_cache.get('balance_sats', 0),
                    'utxos': persistent_cache.get('utxos', []),
                    'cached': True
                }
        
        # Check in-memory cache second (unless force refresh)
        if not force_refresh and address in self.utxo_cache:
            cached_data = self.utxo_cache[address]
            cache_age = current_time - cached_data['timestamp']
            
            if cache_age < self.utxo_cache_ttl:
                # Cache is still valid
                return {
                    'has_utxos': cached_data['has_utxos'],
                    'balance_sats': cached_data['balance_sats'],
                    'utxos': cached_data['utxos'],
                    'cached': True
                }
        
        # Query network for fresh data
        has_utxos = False
        balance_sats = 0
        utxos = []
        
        try:
            network = self.window.network
            if network:
                sh = bitcoin.address_to_scripthash(address)
                utxos = network.run_from_another_thread(network.listunspent_for_scripthash(sh))
                if utxos:
                    has_utxos = True
                    balance_sats = sum(utxo['value'] for utxo in utxos)
        except Exception as e:
            self.log(f"[SWEEP] Error checking {address}: {e}")
        
        # Update cache
        self.utxo_cache[address] = {
            'has_utxos': has_utxos,
            'balance_sats': balance_sats,
            'utxos': utxos,
            'timestamp': current_time
        }
        
        return {
            'has_utxos': has_utxos,
            'balance_sats': balance_sats,
            'utxos': utxos,
            'cached': False
        }
    
    def register_callbacks(self):
        """Register callbacks for network events"""
        try:
            network = self.window.network
            if network:
                # Try new API first (Electrum 4.5+)
                if hasattr(network, 'add_callback'):
                    network.add_callback(self.on_blockchain_updated, ['blockchain_updated'])
                    self.log("[INIT] Registered for blockchain_updated events (new API)")
                # Fallback to old API
                elif hasattr(network, 'register_callback'):
                    network.register_callback(self.on_blockchain_updated, ['blockchain_updated'])
                    self.log("[INIT] Registered for blockchain_updated events (old API)")
                else:
                    self.log("[INIT] Network callbacks not supported in this Electrum version")
        except Exception as e:
            self.log(f"[INIT] Could not register callbacks: {e}")
    
    def on_blockchain_updated(self, event, *args):
        """Called when a new block arrives"""
        self.log("[BLOCKCHAIN] New block detected, clearing UTXO cache and refreshing timelock list...")
        # Clear UTXO cache on new block
        self.utxo_cache.clear()
        # Refresh the list on the main thread
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.refresh_timelock_list)
    
    def closeEvent(self, event):
        """Cleanup when dialog is closed"""
        try:
            network = self.window.network
            if network:
                # Try new API first
                if hasattr(network, 'remove_callback'):
                    network.remove_callback(self.on_blockchain_updated)
                    self.log("[CLEANUP] Unregistered callbacks (new API)")
                # Fallback to old API
                elif hasattr(network, 'unregister_callback'):
                    network.unregister_callback(self.on_blockchain_updated)
                    self.log("[CLEANUP] Unregistered callbacks (old API)")
        except Exception as e:
            self.log(f"[CLEANUP] Error unregistering callbacks: {e}")
        super().closeEvent(event)  # Also print to stdout for visibility
    
    def save_timelock_data(self, data: Dict):
        """Save timelock data to JSON file with UTXO cache"""
        try:
            # Load existing data
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    all_data = json.load(f)
            else:
                all_data = []
            
            # Add UTXO cache data to new entry (for faster startup)
            address = data['address']
            utxo_info = self.check_address_utxos(address)
            data['has_utxos'] = utxo_info['has_utxos']
            data['balance_sats'] = utxo_info['balance_sats']
            data['utxos'] = utxo_info['utxos']
            data['utxo_check_time'] = time.time()
            
            # Add new entry
            all_data.append(data)
            
            # Save
            with open(self.storage_file, 'w') as f:
                json.dump(all_data, f, indent=2)
            
            self.log(f"[STORAGE] Saved timelock data to {self.storage_file}")
            self.log(f"[STORAGE] Entry: {data['address']} (UTXOs: {utxo_info['has_utxos']}, Balance: {utxo_info['balance_sats']} sats)")
        except Exception as e:
            self.log(f"[ERROR] Failed to save timelock data: {e}")
            QMessageBox.warning(self, "Storage Error", f"Could not save timelock data: {e}")
    
    def load_timelock_data(self) -> List[Dict]:
        """Load all timelock data from JSON file"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                self.log(f"[STORAGE] Loaded {len(data)} timelock entries")
                return data
            else:
                self.log("[STORAGE] No existing timelock data found")
                return []
        except Exception as e:
            self.log(f"[ERROR] Failed to load timelock data: {e}")
            return []
        
    def setup_ui(self):
        """Setup the dialog UI"""
        from PyQt6.QtWidgets import QScrollArea
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # Content widget
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        
        # Vibes Capital Management Logo & Disclaimer
        logo_disclaimer_layout = QHBoxLayout()
        
        # Try to load and display logo
        logo_path = os.path.join(os.path.dirname(__file__), 'vibes_logo.jpg')
        if os.path.exists(logo_path):
            logo_label = QLabel()
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_disclaimer_layout.addWidget(logo_label)
        
        # Disclaimer text
        disclaimer = QLabel(
            "<b>⚠️  SIGNET-PRODUCTION Quality Proof of Concept ⚠️</b><br>"
            "<small>Development sponsored by <b>Vibes Capital Management</b> with real signet coins 🚀<br>"
            "NOT for mainnet usage!</small>"
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("QLabel { background-color: #fff3cd; padding: 8px; border: 2px solid #ffc107; border-radius: 5px; }")
        logo_disclaimer_layout.addWidget(disclaimer, 1)
        
        layout.addLayout(logo_disclaimer_layout)
        layout.addSpacing(5)
        
        # Title and description
        title = QLabel("� BIP-65 CLTV Examples - Educational Timelock Generator")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        desc = QLabel(
            "Learn Bitcoin timelocks through all 5 canonical BIP-65 examples.\n"
            "Create P2SH addresses using OP_CHECKLOCKTIMEVERIFY with exact BIP-65 script patterns.\n\n"
            "💡 Tip: Open the Electrum Console (View → Show Console) to see detailed logging of script construction and BIP-65 explanations!"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # Tab widget for script types
        self.tabs = QTabWidget()
        
        # Tab 1: Simple Timelock
        simple_tab = self.create_simple_timelock_tab()
        self.tabs.addTab(simple_tab, "Freezing Funds")
        
        # Tab 2: Escrow with Timelock
        escrow_tab = self.create_escrow_tab()
        self.tabs.addTab(escrow_tab, "Escrow")
        
        # Tab 3: Two-Factor Wallets
        twofactor_tab = self.create_twofactor_tab()
        self.tabs.addTab(twofactor_tab, "Two-Factor Wallets")
        
        # Tab 4: Payment Channels
        payment_tab = self.create_payment_channel_tab()
        self.tabs.addTab(payment_tab, "Payment Channels")
        
        # Tab 5: Data Publishing
        datapub_tab = self.create_datapub_tab()
        self.tabs.addTab(datapub_tab, "Trustless Payments for Publishing Data")
        
        # Tab 6: Sweep Funds
        sweep_tab = self.create_sweep_tab()
        self.tabs.addTab(sweep_tab, "Sweep Locked Funds")
        
        layout.addWidget(self.tabs)
        
        # Result area (shared by both tabs)
        result_group = QGroupBox("Generated Address & Script")
        result_layout = QVBoxLayout()
        
        # Address display at top (inline with copy button)
        address_container = QWidget()
        address_layout = QHBoxLayout()
        address_layout.setContentsMargins(0, 0, 0, 0)
        
        address_label = QLabel("📍 P2SH Address:")
        address_label.setStyleSheet("font-weight: bold;")
        address_layout.addWidget(address_label)
        
        self.address_display = QLineEdit()
        self.address_display.setReadOnly(True)
        self.address_display.setPlaceholderText("Generate an address to see it here...")
        self.address_display.setFont(QFont("Courier", 10))
        self.address_display.setStyleSheet("QLineEdit { background-color: #f0f0f0; color: #2c5282; font-weight: bold; }")
        address_layout.addWidget(self.address_display, 1)
        
        self.quick_copy_address_btn = QPushButton("📋 Copy")
        self.quick_copy_address_btn.setEnabled(False)
        self.quick_copy_address_btn.clicked.connect(self.copy_address)
        self.quick_copy_address_btn.setMaximumWidth(80)
        address_layout.addWidget(self.quick_copy_address_btn)
        
        address_container.setLayout(address_layout)
        result_layout.addWidget(address_container)
        
        result_layout.addSpacing(10)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(300)
        self.result_text.setMaximumHeight(450)
        self.result_text.setFont(QFont("Courier", 9))
        result_layout.addWidget(self.result_text)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # Set the content widget in scroll area
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Buttons (outside scroll area, always visible at bottom)
        button_layout = QHBoxLayout()
        
        self.copy_address_btn = QPushButton("Copy Address")
        self.copy_address_btn.clicked.connect(self.copy_address)
        self.copy_address_btn.setEnabled(False)
        button_layout.addWidget(self.copy_address_btn)
        
        self.copy_script_btn = QPushButton("Copy Redeem Script")
        self.copy_script_btn.clicked.connect(self.copy_script)
        self.copy_script_btn.setEnabled(False)
        button_layout.addWidget(self.copy_script_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
    def create_simple_timelock_tab(self):
        """Create tab for simple timelock script: <locktime> CLTV DROP <pubkey> CHECKSIG"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description (using DRY helper)
        desc = create_description_label(
            "🔒 Freezing Funds (BIP-65 Motivation)\n\n"
            "Funds can be frozen in UTXOs directly on the blockchain.\n"
            "Nobody will be able to spend the encumbered output until the provided expiry time.\n\n"
            "Script: <expiry time> CHECKLOCKTIMEVERIFY DROP DUP HASH160 <pubKeyHash> EQUALVERIFY CHECKSIG\n"
            "(This plugin uses simplified form: <expiry time> CLTV DROP <pubkey> CHECKSIG)"
        )
        layout.addWidget(desc)
        layout.addSpacing(10)
        
        # Output Type Selector (NEW: P2SH/Taproot toggle)
        self.simple_output_selector = OutputTypeSelector(default='p2sh')
        layout.addWidget(self.simple_output_selector)
        
        # Locktime selector (DRY component)
        current_height = self.get_current_height()
        default_locktime = self.get_default_locktime()
        self.simple_locktime_selector = LocktimeSelector(
            current_height=current_height,
            default_locktime=default_locktime
        )
        layout.addWidget(self.simple_locktime_selector)
        
        # Public key input (DRY component)
        self.simple_pubkey_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Public Key (Auto-selected from Wallet)"
        )
        layout.addWidget(self.simple_pubkey_widget)
        
        # Generate button (DRY helper)
        gen_btn = create_generate_button(
            "Generate Freezing Funds Address",
            self.generate_simple_timelock
        )
        layout.addWidget(gen_btn)
        
        # Visualize button (NEW!)
        visualize_btn = QPushButton("🔍 Visualize Script")
        visualize_btn.setToolTip("Step-by-step execution visualization of the CLTV script")
        visualize_btn.clicked.connect(self.visualize_simple_script)
        visualize_btn.setEnabled(False)  # Initially disabled until address is generated
        self.simple_visualize_btn = visualize_btn
        layout.addWidget(visualize_btn)
        tab.setLayout(layout)
        return tab
        
    def create_escrow_tab(self):
        """Create tab for escrow script with timelock fallback"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description
        desc = create_description_label(
            "Escrow (BIP-65 Motivation):\n"
            "• Normal case: Requires 2-of-2 multisig (both parties)\n"
            "• After timeout: Third party (escrow agent) + either party can spend\n\n"
            "BIP-65 script form: IF <locktime> CLTV DROP <agent_pubkey> CHECKSIGVERIFY 1 \n"
            "ELSE 2 ENDIF <party1_pubkey> <party2_pubkey> 2 CHECKMULTISIG"
        )
        layout.addWidget(desc)
        layout.addSpacing(10)
        
        # Output type selector (P2SH/Taproot toggle)
        self.escrow_output_selector = OutputTypeSelector()
        layout.addWidget(self.escrow_output_selector)
        
        # Locktime selector (block height or timestamp)
        current_height = self.get_current_height()
        default_locktime = self.get_default_locktime()
        self.escrow_locktime_selector = LocktimeSelector(
            current_height=current_height,
            default_locktime=default_locktime,
            parent=self
        )
        layout.addWidget(self.escrow_locktime_selector)
        
        # Public keys (3 separate widgets for party1, party2, and agent)
        self.escrow_party1_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Party 1 Pubkey:"
        )
        layout.addWidget(self.escrow_party1_widget)
        
        self.escrow_party2_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Party 2 Pubkey:"
        )
        layout.addWidget(self.escrow_party2_widget)
        
        self.escrow_agent_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Escrow Agent Pubkey:"
        )
        layout.addWidget(self.escrow_agent_widget)
        
        # Generate button
        gen_btn = create_generate_button(
            "Generate Escrow Address with Timelock",
            self.generate_escrow_timelock
        )
        layout.addWidget(gen_btn)
        
        # Result display
        self.escrow_result = ResultDisplay()
        layout.addWidget(self.escrow_result)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def create_twofactor_tab(self):
        """Create tab for two-factor wallet (BIP-65 Example 2)"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description
        desc = create_description_label(
            "🔐 Two-Factor Wallets (BIP-65 Motivation: Non-interactive Time-locked Refunds)\n\n"
            "• Normal spending: Requires user + service signature (both signatures required)\n"
            "• Recovery path: After timeout, user + recovery key can spend\n\n"
            "Script: IF <service> CHECKSIGVERIFY ELSE <expiry time> CLTV DROP ENDIF <user> CHECKSIG\n\n"
            "Services like GreenAddress store bitcoins with 2-of-2 multisig. The user is always\n"
            "able to spend their funds without the co-operation of the service by waiting for\n"
            "the expiry time to be reached.",
            background_color="#e3f2fd"
        )
        layout.addWidget(desc)
        layout.addSpacing(10)
        
        # Output type selector (P2SH/Taproot toggle)
        self.twofactor_output_selector = OutputTypeSelector()
        layout.addWidget(self.twofactor_output_selector)
        
        # Locktime selector (block height or timestamp)
        current_height = self.get_current_height()
        default_locktime = self.get_default_locktime()
        self.twofactor_locktime_selector = LocktimeSelector(
            current_height=current_height,
            default_locktime=default_locktime,
            parent=self
        )
        layout.addWidget(self.twofactor_locktime_selector)
        
        # Public keys (3 separate widgets: user, service, recovery)
        self.twofactor_user_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="User Pubkey:"
        )
        layout.addWidget(self.twofactor_user_widget)
        
        self.twofactor_service_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Service Pubkey:"
        )
        layout.addWidget(self.twofactor_service_widget)
        
        self.twofactor_recovery_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Recovery Pubkey:"
        )
        layout.addWidget(self.twofactor_recovery_widget)
        
        # Generate button
        gen_btn = create_generate_button(
            "Generate Two-Factor Wallet Address",
            self.generate_twofactor_wallet
        )
        layout.addWidget(gen_btn)
        
        # Result display
        self.twofactor_result = ResultDisplay()
        layout.addWidget(self.twofactor_result)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def create_payment_channel_tab(self):
        """Create tab for payment channel (BIP-65 Example 3)"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Description
        desc = create_description_label(
            "💳 Payment Channels (BIP-65 Motivation: Non-interactive Time-locked Refunds)\n\n"
            "• Normal: Receiver can claim with sender cooperation (off-chain updates)\n"
            "• Refund: If receiver never claims, sender can refund after timeout.\n\n"
            "Script: IF 2 <sender> <receiver> 2 CHECKMULTISIG ELSE <locktime> CLTV DROP <sender> CHECKSIG ENDIF\n\n"
            "Use case: Off-chain payments with non-interactive refund mechanism.",
            background_color="#fff3e0"
        )
        layout.addWidget(desc)
        layout.addSpacing(10)
        
        # Output type selector (P2SH/Taproot toggle)
        self.payment_output_selector = OutputTypeSelector()
        layout.addWidget(self.payment_output_selector)
        
        # Locktime selector (block height or timestamp)
        current_height = self.get_current_height()
        default_locktime = self.get_default_locktime()
        self.payment_locktime_selector = LocktimeSelector(
            current_height=current_height,
            default_locktime=default_locktime,
            parent=self
        )
        layout.addWidget(self.payment_locktime_selector)
        
        # Public keys (2 widgets: sender and receiver)
        self.payment_sender_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Sender Pubkey (Payer):"
        )
        layout.addWidget(self.payment_sender_widget)
        
        self.payment_receiver_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Receiver Pubkey (Payee):"
        )
        layout.addWidget(self.payment_receiver_widget)
        
        # Generate button
        gen_btn = create_generate_button(
            "Generate Payment Channel Address",
            self.generate_payment_channel
        )
        layout.addWidget(gen_btn)
        
        # Result display
        self.payment_result = ResultDisplay()
        layout.addWidget(self.payment_result)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def create_datapub_tab(self):
        """Create tab for data publishing script: HASH160 <hash> EQUALVERIFY <pubkey> CHECKSIG"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description
        desc = create_description_label(
            "📚 Trustless Payments for Publishing Data (BIP-65 Motivation)\n\n"
            "• Publisher path: Reveal data preimage + sign to claim payment\n"
            "• Buyer refund path: After timeout, buyer can cancel offer\n\n"
            "Script: IF HASH160 <hash> EQUALVERIFY <publisher_pubkey> CHECKSIG\n"
            "ELSE <expiry> CLTV DROP <buyer_pubkey> CHECKSIG ENDIF\n\n"
            "Use case: Pay for data in trustless way, with buyer refund if publisher doesn't deliver.",
            background_color="#f3e5f5"
        )
        layout.addWidget(desc)
        layout.addSpacing(10)
        
        # Output type selector (P2SH/Taproot toggle)
        self.datapub_output_selector = OutputTypeSelector()
        layout.addWidget(self.datapub_output_selector)
        
        # Data hash input (custom - not using PubkeyInput)
        data_group = QGroupBox("Data Hash (SHA256 Preimage)")
        data_layout = QFormLayout()
        self.datapub_data_input = QLineEdit()
        self.datapub_data_input.setMinimumWidth(550)
        self.datapub_data_input.setFont(QFont("Courier", 10))
        data_layout.addRow("Data/Secret:", self.datapub_data_input)
        
        hash_btn = QPushButton("Generate SHA256 Hash")
        hash_btn.clicked.connect(self.generate_data_hash)
        data_layout.addRow("", hash_btn)
        
        self.datapub_hash_input = QLineEdit()
        self.datapub_hash_input.setReadOnly(True)
        self.datapub_hash_input.setPlaceholderText("SHA256 hash will appear here...")
        self.datapub_hash_input.setMinimumWidth(550)
        self.datapub_hash_input.setFont(QFont("Courier", 10))
        data_layout.addRow("SHA256 Hash:", self.datapub_hash_input)
        
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)
        
        # Locktime selector
        current_height = self.get_current_height()
        default_locktime = self.get_default_locktime()
        self.datapub_locktime_selector = LocktimeSelector(
            current_height=current_height,
            default_locktime=default_locktime,
            parent=self
        )
        layout.addWidget(self.datapub_locktime_selector)
        
        # Public keys (2 widgets: buyer and publisher)
        self.datapub_buyer_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Buyer Pubkey (You):"
        )
        layout.addWidget(self.datapub_buyer_widget)
        
        self.datapub_publisher_widget = PubkeyInput(
            get_key_callback=self.get_wallet_pubkey,
            label="Publisher Pubkey:"
        )
        layout.addWidget(self.datapub_publisher_widget)
        
        # Generate button
        gen_btn = create_generate_button(
            "Generate Data Publishing Address",
            self.generate_datapub_contract
        )
        layout.addWidget(gen_btn)
        
        # Result display
        self.datapub_result = ResultDisplay()
        layout.addWidget(self.datapub_result)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def create_sweep_tab(self):
        """Create tab for sweeping timelocked funds"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description
        desc = QLabel(
            "Sweep funds from CLTV-locked addresses back to your wallet.\\n"
            "This will only work if the locktime has passed and you have the private key."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # Timelock list
        list_group = QGroupBox("Your Timelocked Addresses (Auto-refreshes on new blocks)")
        list_layout = QVBoxLayout()
        
        # Add refresh button
        refresh_layout = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh UTXO Data")
        refresh_btn.setToolTip("Force refresh UTXO balances from network (clears cache)")
        refresh_btn.clicked.connect(lambda: self.refresh_timelock_list(force_refresh=True))
        refresh_layout.addWidget(refresh_btn)
        refresh_layout.addStretch()
        list_layout.addLayout(refresh_layout)
        
        self.timelock_table = QTableWidget()
        self.timelock_table.setColumnCount(8)  # Added Script Type and Visualize columns
        self.timelock_table.setHorizontalHeaderLabels([
            "Address", "Script Type", "Locktime", "Type", "Status", "Balance", "Sweep", "Visualize"
        ])
        self.timelock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.timelock_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.timelock_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.timelock_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.timelock_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.timelock_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.timelock_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.timelock_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        list_layout.addWidget(self.timelock_table)
        
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # Manual sweep section
        manual_group = QGroupBox("Manual Sweep (Paste Redeem Script)")
        manual_layout = QFormLayout()
        
        self.manual_redeem_script = QTextEdit()
        self.manual_redeem_script.setMaximumHeight(100)
        self.manual_redeem_script.setPlaceholderText("Paste redeem script hex here...")
        self.manual_redeem_script.setFont(QFont("Courier", 10))
        manual_layout.addRow("Redeem Script:", self.manual_redeem_script)
        
        manual_sweep_btn = QPushButton("Sweep with Manual Script")
        manual_sweep_btn.clicked.connect(self.manual_sweep)
        manual_layout.addRow("", manual_sweep_btn)
        
        manual_group.setLayout(manual_layout)
        layout.addWidget(manual_group)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def get_wallet_pubkey(self, target_input, info_label=None):
        """Get a public key from the wallet and show derivation info"""
        try:
            # Get a receiving address from the wallet
            addr = self.wallet.get_receiving_address()
            if not addr:
                QMessageBox.warning(self, "Error", "No addresses available in wallet")
                return
                
            # Get the public key for this address
            pubkey = self.wallet.get_public_key(addr)
            if pubkey:
                target_input.setText(pubkey)
                
                # Show derivation info if label provided
                if info_label:
                    # Try to get derivation path
                    try:
                        keystore = self.wallet.get_keystore()
                        if hasattr(keystore, 'derivation'):
                            derivation = keystore.derivation
                        else:
                            derivation = "Unknown"
                        
                        # Get address index
                        addr_index = self.wallet.get_address_index(addr)
                        if addr_index:
                            change, index = addr_index
                            path_suffix = f"/{change}/{index}"
                        else:
                            path_suffix = ""
                        
                        info_text = f"Address: {addr}\nPath: {derivation}{path_suffix}"
                        info_label.setText(info_text)
                    except Exception:
                        info_label.setText(f"Address: {addr}")
            else:
                QMessageBox.warning(self, "Error", "Could not retrieve public key from wallet")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error getting wallet key: {str(e)}")
    
    def load_escrow_keys(self):
        """Load keys for escrow script: Party 1 from wallet, Party 2 and Agent from BIP-32 test vector"""
        try:
            # Party 1 - From wallet (Alice)
            addr1 = self.wallet.get_receiving_address()
            if addr1:
                pubkey1 = self.wallet.get_public_key(addr1)
                if pubkey1:
                    self.escrow_party1_widget.pubkey_edit.setText(pubkey1)
                    self.escrow_party1_widget.info_label.setText(f"🔑 From wallet: {addr1}")
                    self.log(f"[KEYS] Escrow Party 1 (Alice): {pubkey1} from wallet")
            
            # Party 2 - From BIP-32 test vector (Bob)
            self.escrow_party2_widget.pubkey_edit.setText(self.BIP32_V1_M0H_PUBKEY)
            self.escrow_party2_widget.info_label.setText(f"🧪 BIP-32 V1 m/0' (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Escrow Party 2 (Bob): {self.BIP32_V1_M0H_PUBKEY} from BIP-32 test vector 1 m/0'")
            
            # Agent - Also from BIP-32 test vector (Lenny/Escrow Agent)
            # Using different key from Party 2 - would be different party in real use
            self.escrow_agent_widget.pubkey_edit.setText(self.BIP32_V1_M0H1_PUBKEY)
            self.escrow_agent_widget.info_label.setText(f"🧪 BIP-32 V1 m/0'/1 (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Escrow Agent (Lenny): {self.BIP32_V1_M0H1_PUBKEY} from BIP-32 test vector 1 m/0'/1")
            
            self.log("[KEYS] ⚠️  Party 2 & Agent use BIP-32 test vectors - publicly known keys, TEST ONLY!")
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error loading escrow keys: {str(e)}")
    
    def auto_load_keys(self):
        """Auto-load wallet keys after dialog is fully constructed"""
        try:
            # Load simple tab key (using DRY component)
            self.get_wallet_pubkey(
                self.simple_pubkey_widget.pubkey_edit,
                self.simple_pubkey_widget.info_label
            )
            
            # Load escrow tab keys (wallet + BIP-32 test vector)
            self.load_escrow_keys()
            
            # Load two-factor wallet keys
            self.load_twofactor_keys()
            
            # Load payment channel keys
            self.load_payment_keys()
            
            # Load data publishing keys
            self.load_datapub_keys()
            
        except Exception as e:
            # Silently fail - user can click refresh if needed
            print(f"[CLTV Plugin] Auto-load keys failed: {e}")
    
    def load_twofactor_keys(self):
        """Load keys for two-factor wallet: User from wallet, Service and Recovery from BIP-32"""
        try:
            # User key - From wallet
            addr = self.wallet.get_receiving_address()
            if addr:
                pubkey = self.wallet.get_public_key(addr)
                if pubkey:
                    self.twofactor_user_widget.pubkey_edit.setText(pubkey)
                    self.twofactor_user_widget.info_label.setText(f"🔑 From wallet: {addr}")
                    self.log(f"[KEYS] Two-Factor User: {pubkey} from wallet")
            
            # Service key - From BIP-32 test vector 2 (two-factor service)
            self.twofactor_service_widget.pubkey_edit.setText(self.BIP32_V2_M_PUBKEY)
            self.twofactor_service_widget.info_label.setText(f"🧪 BIP-32 V2 m (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Two-Factor Service: {self.BIP32_V2_M_PUBKEY} from BIP-32 test vector 2")
            
            # Recovery key - From BIP-32 test vector 2 (recovery path)
            self.twofactor_recovery_widget.pubkey_edit.setText(self.BIP32_V2_M_PUBKEY)
            self.twofactor_recovery_widget.info_label.setText(f"🧪 BIP-32 V2 m/0' (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Two-Factor Recovery: {self.BIP32_V2_M_PUBKEY} from BIP-32 test vector 2")
            
        except Exception as e:
            print(f"[CLTV Plugin] Error loading two-factor keys: {e}")
    
    def load_payment_keys(self):
        """Load keys for payment channel: Sender from wallet, Receiver from BIP-32"""
        try:
            # Sender key - From wallet (you are sending)
            addr = self.wallet.get_receiving_address()
            if addr:
                pubkey = self.wallet.get_public_key(addr)
                if pubkey:
                    self.payment_sender_widget.pubkey_edit.setText(pubkey)
                    self.payment_sender_widget.info_label.setText(f"🔑 From wallet: {addr}")
                    self.log(f"[KEYS] Payment Sender: {pubkey} from wallet")
            
            # Receiver key - From BIP-32 test vector 1 m/0' (different from sender)
            self.payment_receiver_widget.pubkey_edit.setText(self.BIP32_V1_M0H_PUBKEY)
            self.payment_receiver_widget.info_label.setText(f"🧪 BIP-32 V1 m/0' (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Payment Receiver: {self.BIP32_V1_M0H_PUBKEY} from BIP-32 test vector 1 m/0'")
            
        except Exception as e:
            print(f"[CLTV Plugin] Error loading payment keys: {e}")
    
    def load_datapub_keys(self):
        """Load keys for data publishing: Buyer from wallet, Publisher from BIP-32"""
        try:
            # Buyer key - From wallet (you are buying)
            addr = self.wallet.get_receiving_address()
            if addr:
                pubkey = self.wallet.get_public_key(addr)
                if pubkey:
                    self.datapub_buyer_widget.pubkey_edit.setText(pubkey)
                    self.datapub_buyer_widget.info_label.setText(f"🔑 From wallet: {addr}")
                    self.log(f"[KEYS] Data Publishing Buyer: {pubkey} from wallet")
            
            # Publisher key - From BIP-32 test vector 2 (different from buyer)
            self.datapub_publisher_widget.pubkey_edit.setText(self.BIP32_V2_M_PUBKEY)
            self.datapub_publisher_widget.info_label.setText(f"🧪 BIP-32 V2 m (TEST ONLY - NOT FOR MAINNET)")
            self.log(f"[KEYS] Data Publishing Publisher: {self.BIP32_V2_M_PUBKEY} from BIP-32 test vector 2")
            
        except Exception as e:
            print(f"[CLTV Plugin] Error loading data publishing keys: {e}")
            import traceback
            traceback.print_exc()
    
    # ========================================================================
    # HELPER METHODS - DRY Refactoring
    # ========================================================================
    
    def get_locktime_from_ui(self, tab_prefix: str):
        """Extract locktime value from UI elements.
        
        Args:
            tab_prefix: 'simple', 'escrow', 'twofactor', 'payment', 'datapub'
        
        Returns:
            tuple: (locktime: int, locktime_type: str, locktime_display: str)
        """
        block_radio = getattr(self, f'{tab_prefix}_block_radio')
        block_input = getattr(self, f'{tab_prefix}_block_input')
        time_input = getattr(self, f'{tab_prefix}_time_input')
        
        if block_radio.isChecked():
            locktime = block_input.value()
            locktime_type = "block height"
            locktime_display = str(locktime)
            self.log(f"[GENERATE] Locktime type: Block height = {locktime}")
        else:
            dt = time_input.dateTime().toPyDateTime()
            locktime = int(dt.timestamp())
            locktime_type = "timestamp"
            locktime_display = f"{locktime} ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
            self.log(f"[GENERATE] Locktime type: Timestamp = {locktime} ({dt})")
        
        return locktime, locktime_type, locktime_display
    
    def validate_pubkey(self, pubkey_hex: str, field_name: str = "Public key") -> bool:
        """Validate a public key hex string.
        
        Args:
            pubkey_hex: The hex-encoded public key
            field_name: Name for error messages (e.g., "User pubkey")
        
        Returns:
            bool: True if valid, False otherwise (shows error dialog)
        """
        if not pubkey_hex:
            QMessageBox.warning(self, "Error", f"{field_name} is required")
            return False
        
        try:
            pubkey_bytes = bytes.fromhex(pubkey_hex)
            if len(pubkey_bytes) not in (33, 65):
                raise ValueError(f"Invalid length: {len(pubkey_bytes)} bytes")
            self.log(f"[VALIDATE] {field_name} valid: {len(pubkey_bytes)} bytes")
            return True
        except Exception as e:
            QMessageBox.warning(
                self, 
                "Invalid Public Key", 
                f"{field_name} is invalid.\n\n"
                f"Expected: 33 bytes (compressed) or 65 bytes (uncompressed)\n"
                f"Error: {str(e)}"
            )
            return False
    
    def validate_pubkeys(self, *pubkey_tuples) -> bool:
        """Validate multiple public keys at once.
        
        Args:
            *pubkey_tuples: Variable args of (pubkey_hex, field_name) tuples
        
        Returns:
            bool: True if all valid, False otherwise
        
        Example:
            if not self.validate_pubkeys(
                (user_pk, "User pubkey"),
                (service_pk, "Service pubkey")
            ):
                return
        """
        for pubkey_hex, field_name in pubkey_tuples:
            if not self.validate_pubkey(pubkey_hex, field_name):
                return False
        return True
    
    def create_p2sh_timelock(self, script_hex: str, metadata: dict, script_type: str):
        """Generate P2SH address and save timelock data.
        
        Args:
            script_hex: The redeem script in hex
            metadata: Type-specific data (locktime, pubkeys, etc.)
            script_type: "simple", "escrow", "twofactor", "payment_channel", "data_publishing"
        
        Returns:
            tuple: (address: str, script_hex: str)
        """
        self.log("\n📦 P2SH ADDRESS GENERATION:")
        self.log("-" * 80)
        self.log(f"Script type: {self.get_script_type_label(script_type)}")
        self.log(f"Redeem script (hex): {script_hex}")
        self.log(f"Redeem script size: {len(bytes.fromhex(script_hex))} bytes")
        
        # Create P2SH address
        script_bytes = bytes.fromhex(script_hex)
        script_hash = hash_160(script_bytes)
        
        self.log(f"\nP2SH Hashing Process:")
        import hashlib
        sha256_hash = hashlib.sha256(script_bytes).digest()
        self.log(f"  1. SHA256(script) = {sha256_hash.hex()}")
        self.log(f"  2. RIPEMD160(SHA256(script)) = {script_hash.hex()}")
        
        address = self.script_to_p2sh_address(script_hex)
        
        self.log(f"\nP2SH Address Construction:")
        self.log(f"  Version byte: 0xc4 (Signet P2SH)")
        self.log(f"  Script hash: {script_hash.hex()}")
        self.log(f"  ✅ Final address: {address}")
        self.log(f"\n💡 To spend from this address, you must provide:")
        self.log(f"  1. Valid signature(s) for the pubkey(s)")
        self.log(f"  2. The full redeem script (revealed when spending)")
        self.log(f"  3. Transaction with nLockTime >= {metadata.get('locktime', 'N/A')}")
        self.log("-" * 80 + "\n")
        
        # Prepare storage data
        timelock_data = {
            "address": address,
            "script_hex": script_hex,
            "script_hash": script_hash.hex(),
            "script_type": script_type,
            "created": datetime.now().isoformat(),
            "created_at": int(time.time()),
            **metadata  # Merge type-specific fields
        }
        
        self.save_timelock_data(timelock_data)
        self.log("💾 Timelock data saved for future sweeping\n")
        
        return address, script_hex
    
    def get_script_type_label(self, script_type: str) -> str:
        """Get friendly label for script type based on BIP-65 naming.
        
        Args:
            script_type: Internal type ("simple", "escrow", "twofactor", etc.)
        
        Returns:
            str: BIP-65 canonical name for the script pattern
        """
        script_labels = {
            "simple": "Freezing Funds",
            "escrow": "Escrow",
            "twofactor": "Two-Factor Wallets",
            "payment_channel": "Payment Channels", 
            "data_publishing": "Trustless Payments for Publishing Data"
        }
        return script_labels.get(script_type, script_type.title())
    
    def display_result(self, result_text: str, address: str, script: str):
        """Display generation result and enable copy buttons.
        
        Args:
            result_text: Formatted result text to display
            address: The generated P2SH address
            script: The redeem script hex
        """
        # Update inline address display
        self.address_display.setText(address)
        self.quick_copy_address_btn.setEnabled(True)
        
        # Update detailed result text
        self.result_text.setText(result_text)
        
        # Store for legacy copy buttons
        self.current_address = address
        self.current_script = script
        self.copy_address_btn.setEnabled(True)
        self.copy_script_btn.setEnabled(True)
    
    # ========================================================================
    # GENERATION METHODS
    # ========================================================================
            
    def generate_simple_timelock(self):
        """Generate simple timelock address using DRY AddressFactory"""
        try:
            self.log("\n" + "="*80)
            self.log("🔧 GENERATING: Freezing Funds CLTV Address")
            self.log("="*80)
            
            # Get locktime from DRY component
            locktime, locktime_type, locktime_display = self.simple_locktime_selector.get_locktime()
            self.log(f"✓ Locktime: {locktime} ({locktime_type})")
            if locktime_type == "timestamp":
                dt = datetime.fromtimestamp(locktime)
                self.log(f"  Date: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                self.log(f"  Block height: #{locktime}")
                
            # Validate locktime
            if locktime < 0:
                self.log("[ERROR] Locktime cannot be negative")
                raise UserFacingException(
                    _("Locktime cannot be negative.\n\n"
                      f"Please enter a valid block height (> 0) or timestamp (>= {self.LOCKTIME_THRESHOLD})")
                )
                
            # Get pubkey from DRY component
            pubkey_hex = self.simple_pubkey_widget.get_pubkey()
            if not pubkey_hex:
                self.log("[ERROR] No public key provided")
                raise UserFacingException(
                    _("No public key provided.\n\n"
                      "Click 'Select Different Key from Wallet' to choose a key.")
                )
            
            # Validate pubkey
            if not self.validate_pubkey(pubkey_hex, "Public key"):
                return
            
            # Get output type from DRY component (NEW!)
            output_type = self.simple_output_selector.get_output_type()
            self.log(f"✓ Output type: {output_type.upper()}")
            
            # Use AddressFactory to create address (DRY!)
            self.log(f"[FACTORY] Using AddressFactory to create {output_type} address...")
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
            except ValueError:
                raise UserFacingException(_("Invalid public key hex format"))
            
            result = create_cltv_address(
                script_type='freezing_funds',
                locktime=locktime,
                locktime_type=locktime_type,
                locktime_display=locktime_display,
                output_type=output_type,
                pubkey=pubkey_bytes
            )
            
            self.log(f"✅ Generated {output_type.upper()} address: {result['address']}")
            
            # Get educational content from builder
            builder = get_builder('freezing_funds')
            educational_content = f"{builder.get_description()}\n\n{builder.get_bip65_quote()}"
            
            # Format script breakdown (pass script_type)
            script_breakdown = self.format_script_breakdown(result['script_hex'], 'freezing_funds')
            
            # Store address data for future sweeping
            timelock_data = {
                "address": result['address'],
                "script_hex": result['script_hex'],
                "script_type": "freezing_funds",
                "locktime": result['locktime'],
                "pubkey": pubkey_hex,
                "output_type": result['output_type'],
                "created": datetime.now().isoformat(),
                "created_at": int(time.time())
            }
            self.save_timelock_data(timelock_data)
            
            # Display using existing display_results (will be enhanced later)
            self.display_results(
                address=result['address'],
                script_hex=result['script_hex'],
                script_type="Freezing Funds",
                locktime=locktime_display,
                locktime_type=locktime_type,
                details=f"✓ Spendable by pubkey {pubkey_hex[:16]}... after {locktime_display}",
                miniscript=f"and_v(v:after({locktime}),pk({pubkey_hex[:16]}...))",
                witness_stack=self._get_witness_info(result, pubkey_hex)
            )
            
            # Enable visualize button after successful generation
            self.simple_visualize_btn.setEnabled(True)
            
        except UserFacingException:
            raise
        except Exception as e:
            self.log(f"[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            raise UserFacingException(
                _(f"Failed to generate address.\n\nError: {str(e)}\n\n"
                  f"Check Tools → Console for details.")
            )
    
    def visualize_simple_script(self):
        """Launch script visualizer for the simple freeze script"""
        try:
            # Get the current values from the UI
            locktime, locktime_type, locktime_display = self.simple_locktime_selector.get_locktime()
            pubkey_hex = self.simple_pubkey_widget.get_pubkey()
            
            if not pubkey_hex:
                QMessageBox.warning(self, "Error", "No public key available for visualization")
                return
            
            # Get current height for validation
            current_height = self.get_current_height()
            
            # Import and create interpreter
            from .simple_script_interpreter import SimpleScriptInterpreter
            
            interpreter = SimpleScriptInterpreter(
                locktime_value=locktime,
                pubkey_hex=pubkey_hex,
                current_height=current_height
            )
            
            # Execute script and get steps
            steps = interpreter.execute()
            
            # Import and show visualizer dialog
            from .script_visualizer_dialog import ScriptVisualizerDialog
            
            dialog = ScriptVisualizerDialog(self, locktime, pubkey_hex, current_height)
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to visualize script: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def visualize_sweep_script(self, index: int):
        """Launch script visualizer for the sweep script at the given index"""
        try:
            timelocks = self.load_timelock_data()
            if index >= len(timelocks):
                QMessageBox.warning(self, "Error", "Timelock data not found")
                return
            
            lock = timelocks[index]
            script_hex = lock.get('script_hex', '')
            locktime = lock.get('locktime', 0)
            pubkey_hex = lock.get('pubkey', '')
            
            if not script_hex:
                QMessageBox.warning(self, "Error", "No script data available for visualization")
                return
            
            if not pubkey_hex:
                QMessageBox.warning(self, "Error", "No pubkey data available for visualization")
                return
            
            # Get current height for validation
            current_height = self.get_current_height()
            
            # Import and create interpreter
            from .simple_script_interpreter import SimpleScriptInterpreter
            
            interpreter = SimpleScriptInterpreter(
                locktime_value=locktime,
                pubkey_hex=pubkey_hex,
                current_height=current_height
            )
            
            # Execute script and get steps
            steps = interpreter.execute()
            
            # Import and show visualizer dialog
            from .script_visualizer_dialog import ScriptVisualizerDialog
            
            dialog = ScriptVisualizerDialog(self, locktime, pubkey_hex, current_height)
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to visualize sweep script: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _get_witness_info(self, result, pubkey_hex):
        """Generate witness/spending information based on output type"""
        output_type = result.get('output_type', 'p2sh')
        locktime = result.get('locktime', 0)
        script_hex = result['script_hex']
        
        if output_type == 'p2sh':
            return f"""P2SH Spending Requirements:

1. scriptSig format:
   <signature> <serialized_redeem_script>

2. Witness stack:
   - Push signature for pubkey {pubkey_hex[:16]}...
   - Push the redeem script ({len(bytes.fromhex(script_hex))} bytes)

3. Transaction requirements:
   - nSequence must be set appropriately for CLTV
   - nLockTime in transaction must be >= {locktime}
   
4. Script execution:
   [signature] [redeem_script] → OP_HASH160 [script_hash] OP_EQUAL
   Then executes: {locktime} CLTV DROP {pubkey_hex[:16]}... CHECKSIG"""
        else:  # taproot
            return f"""Taproot Spending Requirements:

1. Witness stack (script-path spend):
   - <signature> (for pubkey {pubkey_hex[:16]}...)
   - <tapscript> ({len(bytes.fromhex(script_hex))} bytes)
   - <control_block> ({len(result.get('control_block', ''))} hex chars)

2. Transaction requirements:
   - nLockTime in transaction must be >= {locktime}
   - Standard taproot witness rules apply

3. Script execution:
   Script: {locktime} CLTV DROP <xonly_pubkey> CHECKSIG
   
4. Privacy benefit:
   - Script hidden until spend
   - Looks like any other taproot address
   - Control block proves script is in tree"""
            
    def generate_escrow_timelock(self):
        """Generate escrow timelock address"""
        try:
            # Get output type (P2SH or Taproot)
            output_type = self.escrow_output_selector.get_output_type()
            
            # Get locktime (returns 3-value tuple)
            locktime, locktime_type, locktime_display = self.escrow_locktime_selector.get_locktime()
            is_block_height = (locktime_type == 'block')
                
            # Get public keys from PubkeyInput widgets
            party1_hex = self.escrow_party1_widget.get_pubkey()
            party2_hex = self.escrow_party2_widget.get_pubkey()
            agent_hex = self.escrow_agent_widget.get_pubkey()
            
            # Validate all pubkeys using helper
            if not self.validate_pubkeys(
                (party1_hex, "Party 1 pubkey"),
                (party2_hex, "Party 2 pubkey"),
                (agent_hex, "Agent pubkey")
            ):
                return
            
            # Convert pubkeys to bytes
            party1_bytes = bytes.fromhex(party1_hex)
            party2_bytes = bytes.fromhex(party2_hex)
            agent_bytes = bytes.fromhex(agent_hex)
                    
            self.log("\n📚 BIP-65 Example: ESCROW")
            self.log("-" * 80)
            self.log("From BIP-65:")
            self.log("  'However, with CHECKLOCKTIMEVERIFY the funds can be stored in scriptPubKeys")
            self.log("   of the form:'")
            self.log("")
            self.log("   IF")
            self.log("       <now + 3 months> CHECKLOCKTIMEVERIFY DROP")
            self.log("       <Lenny's pubkey> CHECKSIGVERIFY")
            self.log("       1")
            self.log("   ELSE")
            self.log("       2")
            self.log("   ENDIF")
            self.log("   <Alice's pubkey> <Bob's pubkey> 2 CHECKMULTISIG")
            self.log("")
            self.log("  'At any time the funds can be spent with the following scriptSig:'")
            self.log("   0 <Alice's signature> <Bob's signature> 0")
            self.log("")
            self.log("  'After 3 months have passed Lenny and one of either Alice or Bob can")
            self.log("   spend the funds with the following scriptSig:'")
            self.log("   0 <Alice/Bob's signature> <Lenny's signature> 1")
            self.log("-" * 80 + "\n")
            
            self.log(f"[GENERATE] Creating escrow timelock ({output_type})...")
            self.log(f"[GENERATE] Party 1 pubkey: {party1_hex}")
            self.log(f"[GENERATE] Party 2 pubkey: {party2_hex}")
            self.log(f"[GENERATE] Agent pubkey: {agent_hex}")
            self.log(f"[GENERATE] Fallback timeout: {locktime_display}")
            
            # Create address using AddressFactory (supports both P2SH and Taproot)
            result = create_cltv_address(
                script_type='escrow',
                output_type=output_type,
                locktime=locktime,
                locktime_type=locktime_type,
                locktime_display=locktime_display,
                pubkey1=party1_bytes,
                pubkey2=party2_bytes,
                pubkey_agent=agent_bytes
            )
            
            address = result['address']
            script = result['script_hex']
            
            # Generate technical details
            miniscript = f"""or_d(
  and_v(v:after({locktime}),and_v(v:pk({agent_hex[:16]}...),thresh(1,pk({party1_hex[:16]}...),pk({party2_hex[:16]}...)))),
  thresh(2,pk({party1_hex[:16]}...),pk({party2_hex[:16]}...))
)"""
            
            witness_stack = f"""To spend this P2SH output, you have TWO options:

OPTION A - Normal Spending (2-of-2 multisig, no timelock):
   scriptSig: OP_0 <sig_party2> <sig_party1> OP_0 <redeem_script>
   - Push 0 (for CHECKMULTISIG bug)
   - Push Party 2 signature
   - Push Party 1 signature  
   - Push 0 (selects ELSE branch)
   - Push redeem script
   
OPTION B - Timelock Recovery (agent + 1 party after timeout):
   scriptSig: OP_0 <sig_party> <sig_agent> OP_1 <redeem_script>
   - Push 0 (for CHECKMULTISIG bug)
   - Push one party's signature (party1 OR party2)
   - Push agent signature
   - Push 1 (selects IF branch, triggers CLTV check)
   - Push redeem script
   - Requires tx nLockTime >= {locktime}

Script execution flow:
   IF branch (timelock): agent sig verified, then 1-of-2 multisig
   ELSE branch (normal): 2-of-2 multisig, no timelock check"""
            
            # Display results
            self.display_results(
                address=address,
                script_hex=script,
                script_type="Escrow",
                locktime=locktime_display,
                locktime_type=locktime_type,
                details=(
                    f"✓ Normal spending: Requires both Party 1 and Party 2 (2-of-2 multisig)\n"
                    f"✓ Timelock fallback: After {locktime_display}, requires Escrow Agent + either party (1-of-2 multisig)"
                ),
                miniscript=miniscript,
                witness_stack=witness_stack
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate address: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def generate_twofactor_wallet(self):
        """Generate two-factor wallet address (BIP-65 Example 2)"""
        try:
            # Get output type (P2SH or Taproot)
            output_type = self.twofactor_output_selector.get_output_type()
            
            # Get locktime (returns 3-value tuple)
            locktime, locktime_type, locktime_display = self.twofactor_locktime_selector.get_locktime()
            is_block_height = (locktime_type == 'block')
                
            # Get public keys from PubkeyInput widgets
            user_hex = self.twofactor_user_widget.get_pubkey()
            service_hex = self.twofactor_service_widget.get_pubkey()
            recovery_hex = self.twofactor_recovery_widget.get_pubkey()
            
            # Validate pubkeys using helper
            if not self.validate_pubkeys(
                (user_hex, "User pubkey"),
                (service_hex, "Service pubkey"),
                (recovery_hex, "Recovery pubkey")
            ):
                return
            
            # Convert pubkeys to bytes
            user_bytes = bytes.fromhex(user_hex)
            service_bytes = bytes.fromhex(service_hex)
            recovery_bytes = bytes.fromhex(recovery_hex)
                    
            self.log("\n📚 BIP-65 Example: TWO-FACTOR WALLETS")
            self.log("-" * 80)
            self.log("From BIP-65:")
            self.log("  'With CHECKLOCKTIMEVERIFY rather than creating refund signatures on demand")
            self.log("   scriptPubKeys of the following form are used instead:'")
            self.log("")
            self.log("   IF")
            self.log("       <user pubkey> CHECKSIGVERIFY")
            self.log("       <service pubkey> CHECKSIG")
            self.log("   ELSE")
            self.log("       <expiry time> CHECKLOCKTIMEVERIFY DROP")
            self.log("       <user pubkey> CHECKSIGVERIFY")
            self.log("       <recovery pubkey> CHECKSIG")
            self.log("   ENDIF")
            self.log("")
            self.log("  'Now the user is always able to spend their funds without the co-operation")
            self.log("   of the service by waiting for the expiry time to be reached.'")
            self.log("-" * 80 + "\n")
            
            self.log(f"[GENERATE] Creating two-factor wallet ({output_type})...")
            self.log(f"[GENERATE] User pubkey: {user_hex}")
            self.log(f"[GENERATE] Service pubkey: {service_hex}")
            self.log(f"[GENERATE] Recovery pubkey: {recovery_hex}")
            self.log(f"[GENERATE] Recovery timeout: {locktime_display}")
            
            # Create address using AddressFactory (supports both P2SH and Taproot)
            result = create_cltv_address(
                script_type='twofactor',
                output_type=output_type,
                locktime=locktime,
                locktime_type=locktime_type,
                locktime_display=locktime_display,
                user_pubkey=user_bytes,
                service_pubkey=service_bytes,
                recovery_pubkey=recovery_bytes
            )
            
            address = result['address']
            script = result['script_hex']
            
            # Display result
            self.twofactor_result.display_result(
                result=result,
                locktime=locktime,
                is_block_height=is_block_height,
                script_type='twofactor'
            )
            
        except Exception as e:
            print(f"[CLTV] Error generating two-factor wallet: {str(e)}")
            import traceback
            traceback.print_exc()
            self.show_error(f"Error generating two-factor wallet: {str(e)}")
            
    def generate_payment_channel(self):
        """Generate payment channel address (BIP-65 Example 3)"""
        try:
            # Get output type (P2SH or Taproot)
            output_type = self.payment_output_selector.get_output_type()
            
            # Get locktime (returns 3-value tuple)
            locktime, locktime_type, locktime_display = self.payment_locktime_selector.get_locktime()
            is_block_height = (locktime_type == 'block')
                
            # Get public keys from PubkeyInput widgets
            sender_hex = self.payment_sender_widget.get_pubkey()
            receiver_hex = self.payment_receiver_widget.get_pubkey()
            
            # Validate pubkeys using helper
            if not self.validate_pubkeys(
                (sender_hex, "Sender pubkey"),
                (receiver_hex, "Receiver pubkey")
            ):
                return
            
            # Convert pubkeys to bytes
            sender_bytes = bytes.fromhex(sender_hex)
            receiver_bytes = bytes.fromhex(receiver_hex)
                    
            self.log("\n📚 BIP-65 Example: PAYMENT CHANNELS")
            self.log("-" * 80)
            self.log("From BIP-65:")
            self.log("  'Jeremy Spilman style payment channels first setup a deposit controlled by")
            self.log("   2-of-2 multisig, tx1, and then adjust a second transaction, tx2, that spends")
            self.log("   the output of tx1 to payor and payee. Prior to publishing tx1 a refund")
            self.log("   transaction is created, tx3, to ensure that should the payee vanish the payor")
            self.log("   can get their deposit back. The process by which the refund transaction is")
            self.log("   created is currently vulnerable to transaction malleability attacks, and")
            self.log("   additionally, requires the payor to store the refund. Using the same")
            self.log("   scriptPubKey form as in the Two-factor wallets example solves both these")
            self.log("   issues.'")
            self.log("-" * 80 + "\n")
            
            self.log(f"[GENERATE] Creating payment channel ({output_type})...")
            self.log(f"[GENERATE] Sender pubkey: {sender_hex}")
            self.log(f"[GENERATE] Receiver pubkey: {receiver_hex}")
            self.log(f"[GENERATE] Refund timeout: {locktime_display}")
            
            # Create address using AddressFactory (supports both P2SH and Taproot)
            result = create_cltv_address(
                script_type='payment_channel',
                output_type=output_type,
                locktime=locktime,
                locktime_type=locktime_type,
                locktime_display=locktime_display,
                sender_pubkey=sender_bytes,
                receiver_pubkey=receiver_bytes
            )
            
            address = result['address']
            script = result['script_hex']
            
            # Generate technical details
            miniscript = f"""or_d(
  and_v(v:pk({receiver_pubkey[:16]}...),pk({sender_pubkey[:16]}...)),
  and_v(v:after({locktime}),pk({sender_pubkey[:16]}...))
)"""
            
            witness_stack = f"""To spend this P2SH output, you have TWO options:

PATH A - Normal Payment (Anytime):
   Requires: Receiver signature + Sender signature
   scriptSig: <sender_sig> <receiver_sig> 1 <redeem_script>
   
   Execution:
   1. Push sender signature
   2. Push receiver signature  
   3. Push 1 (selects IF branch)
   4. Push redeem script
   
   The IF branch executes:
   - <receiver_sig> → <receiver_pubkey> CHECKSIGVERIFY (receiver must sign)
   - <sender_sig> → <sender_pubkey> CHECKSIG (sender co-signs)

PATH B - Refund (After timeout {locktime}):
   Requires: Sender signature only
   scriptSig: <sender_sig> 0 <redeem_script>
   
   Execution:
   1. Push sender signature
   2. Push 0 (selects ELSE branch)
   3. Push redeem script
   
   The ELSE branch executes:
   - {locktime} CLTV (checks nLockTime >= {locktime})
   - DROP (removes locktime from stack)
   - <sender_sig> → <sender_pubkey> CHECKSIG (sender gets refund)

Payment Channel Flow:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Sender opens channel by funding this address
2. Sender creates signed transactions giving amounts to receiver (off-chain)
3. Receiver can claim latest amount anytime with sender's signature
4. If receiver never claims, sender gets refund after {locktime}"""
            
            script_breakdown = self.format_script_breakdown(script, "payment_channel")
            
            # Format result
            result = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 PAYMENT CHANNELS (BIP-65 Motivation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Address (send funds here):  {address}

Script Type: Payment Channels
Refund Timeout: {locktime}
Timeout Type: {locktime_type}

🔐 Spending Conditions:
Path A (Anytime): Receiver signature + Sender signature (normal payment)
Path B (After {locktime}): Sender signature alone (refund unused funds)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 TECHNICAL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 Miniscript Policy (approximate):
{miniscript}

🔹 Redeem Script (hex):
{script}

🔹 Script Hash (HASH160):
{script_hash.hex()}

🔹 Script Size: {len(script_bytes)} bytes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 SCRIPT BREAKDOWN (Annotated Hex)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{script_breakdown}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 SPENDING INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{witness_stack}

⚠️  IMPORTANT SECURITY NOTES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 REQUIRED TO SPEND YOUR FUNDS:

Path A (Payment): 
  ✅ 1. Receiver signature (claims payment)
  ✅ 2. Sender's PRIVATE KEY (co-signs)

Path B (Refund):
  ✅ 1. Wait until block {locktime} or later
  ✅ 2. REDEEM SCRIPT (shown above) - SAVE THIS!
  ✅ 3. Sender's PRIVATE KEY

📁 Auto-saved to: {self.storage_file}

Use the "Sweep Locked Funds" tab to claim refund after timeout.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  PLUGIN DISCLAIMER ⚠━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a SIGNET-PRODUCTION quality proof of concept!
Development sponsored by Vibes Capital Management with real signet coins 🚀

NOT suitable for mainnet usage.
"""
            
            # Display result
            self.payment_result.display_result(
                result=result,
                locktime=locktime,
                is_block_height=is_block_height,
                script_type='payment_channel'
            )
            
        except Exception as e:
            print(f"[CLTV] Error generating payment channel: {str(e)}")
            import traceback
            traceback.print_exc()
            self.show_error(f"Error generating payment channel: {str(e)}")
    
    def generate_data_hash(self):
        """Generate SHA256 hash from input data"""
        data = self.datapub_data_input.text().strip()
        if not data:
            QMessageBox.warning(self, "Error", "Please enter data to hash")
            return
        
        from electrum.crypto import sha256
        data_bytes = data.encode('utf-8')
        hash_bytes = sha256(data_bytes)
        hash_hex = hash_bytes.hex()
        
        self.datapub_hash_input.setText(hash_hex)
        self.log(f"[HASH] Generated SHA256: {hash_hex}")
        self.log(f"[HASH] From data: {data}")
        QMessageBox.information(self, "Hash Generated", 
            f"SHA256 hash generated successfully!\n\n"
            f"Data: {data}\n"
            f"Hash: {hash_hex}\n\n"
            f"⚠️ SAVE THE DATA - you'll need it to spend!")
    
    def generate_datapub_contract(self):
        """Generate data publishing contract address (BIP-65 Example 4)"""
        try:
            # Get output type (P2SH or Taproot)
            output_type = self.datapub_output_selector.get_output_type()
            
            # Get locktime (returns 3-value tuple)
            locktime, locktime_type, locktime_display = self.datapub_locktime_selector.get_locktime()
            is_block_height = (locktime_type == 'block')
            
            # Get inputs
            data_hash = self.datapub_hash_input.text().strip()
            publisher_hex = self.datapub_publisher_widget.get_pubkey()
            buyer_hex = self.datapub_buyer_widget.get_pubkey()
            
            # Validate hash
            if not data_hash:
                self.show_error("Please provide data hash")
                return
            
            try:
                hash_bytes = bytes.fromhex(data_hash)
                if len(hash_bytes) != 32:
                    raise ValueError("Hash must be 32 bytes (64 hex chars)")
            except Exception as e:
                self.show_error(f"Invalid hash format: {str(e)}")
                return
            
            # Validate pubkeys using helper
            if not self.validate_pubkeys(
                (publisher_hex, "Publisher pubkey"),
                (buyer_hex, "Buyer pubkey")
            ):
                return
            
            # Convert pubkeys to bytes
            publisher_bytes = bytes.fromhex(publisher_hex)
            buyer_bytes = bytes.fromhex(buyer_hex)
            
            self.log("\n📚 BIP-65 Example: TRUSTLESS PAYMENTS FOR PUBLISHING DATA")
            self.log("-" * 80)
            self.log("From BIP-65:")
            self.log("  'This problem can be solved interactively with the refund transaction technique;")
            self.log("   with CHECKLOCKTIMEVERIFY the problem can be non-interactively solved using")
            self.log("   scriptPubKeys of the following form:'")
            self.log("")
            self.log("   IF")
            self.log("       HASH160 <Hash160(encryption key)> EQUALVERIFY")
            self.log("       <publisher pubkey> CHECKSIG")
            self.log("   ELSE")
            self.log("       <expiry time> CHECKLOCKTIMEVERIFY DROP")
            self.log("       <buyer pubkey> CHECKSIG")
            self.log("   ENDIF")
            self.log("")
            self.log("  'The buyer of the data is now making a secure offer with an expiry time. If the")
            self.log("   publisher fails to accept the offer before the expiry time is reached the buyer")
            self.log("   can cancel the offer by spending the output.'")
            self.log("-" * 80 + "\n")
            
            self.log(f"[GENERATE] Creating data publishing contract ({output_type})...")
            self.log(f"[GENERATE] Data hash: {data_hash}")
            self.log(f"[GENERATE] Publisher pubkey: {publisher_hex}")
            self.log(f"[GENERATE] Buyer pubkey: {buyer_hex}")
            self.log(f"[GENERATE] Refund timeout: {locktime_display}")
            
            # Create address using AddressFactory (supports both P2SH and Taproot)
            # Note: data_hash needs to be HASH160 (20 bytes), so we hash it
            from electrum.bitcoin import hash_160
            data_hash160 = hash_160(hash_bytes)
            
            result = create_cltv_address(
                script_type='data_publishing',
                output_type=output_type,
                locktime=locktime,
                locktime_type=locktime_type,
                locktime_display=locktime_display,
                publisher_pubkey=publisher_bytes,
                buyer_pubkey=buyer_bytes,
                data_hash=data_hash160
            )
            
            address = result['address']
            script = result['script_hex']
            
            # Display result
            self.datapub_result.display_result(
                result=result,
                locktime=locktime,
                is_block_height=is_block_height,
                script_type='data_publishing'
            )
            
        except Exception as e:
            print(f"[CLTV] Error generating data publishing contract: {str(e)}")
            import traceback
            traceback.print_exc()
            self.show_error(f"Error generating data publishing contract: {str(e)}")
            
            # Generate technical details
            miniscript = f"""or_i(
  and_v(v:sha256({data_hash[:16]}...),pk({publisher_pubkey[:16]}...)),
  and_v(v:after({locktime}),pk({buyer_pubkey[:16]}...))
)"""
            
            witness_stack = f"""To spend this P2SH output, you have TWO options:

PATH A - Publish Data (Anytime):
   Requires: Data preimage + Publisher signature
   scriptSig: <publisher_sig> <data_preimage> 1 <redeem_script>
   
   Execution:
   1. Push publisher signature
   2. Push data preimage (the actual data)
   3. Push 1 (selects IF branch)
   4. Push redeem script
   
   The IF branch executes:
   - HASH160 <data_preimage> (hash the data)
   - Compare with {data_hash[:16]}...
   - EQUALVERIFY (must match or fail)
   - <publisher_sig> → <publisher_pubkey> CHECKSIG (publisher signs)

PATH B - Refund (After timeout {locktime}):
   Requires: Buyer signature only
   scriptSig: <buyer_sig> 0 <redeem_script>
   
   Execution:
   1. Push buyer signature
   2. Push 0 (selects ELSE branch)
   3. Push redeem script
   
   The ELSE branch executes:
   - {locktime} CLTV (checks nLockTime >= {locktime})
   - DROP (removes locktime from stack)
   - <buyer_sig> → <buyer_pubkey> CHECKSIG (buyer gets refund)

Data Publishing Flow:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Buyer pays publisher by funding this address
2. Publisher reveals data (preimage) to claim payment
3. Once published, data is public (visible on blockchain)
4. If publisher never reveals data, buyer gets refund after {locktime}"""
            
            script_breakdown = self.format_script_breakdown(script, "data_publishing")
            
            # Format result
            result = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
� TRUSTLESS PAYMENTS FOR PUBLISHING DATA (BIP-65 Motivation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Address (send funds here):  {address}

Script Type: Trustless Payments for Publishing Data
Refund Timeout: {locktime}
Timeout Type: {locktime_type}

🔐 Spending Conditions:
Path A (Anytime): Reveal data preimage + Publisher signature (publish and claim)
Path B (After {locktime}): Buyer signature alone (refund if data not published)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 TECHNICAL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 Miniscript Policy (approximate):
{miniscript}

🔹 Data Hash (SHA256):
{data_hash}

🔹 Redeem Script (hex):
{script}

🔹 Script Hash (HASH160):
{script_hash.hex()}

🔹 Script Size: {len(script_bytes)} bytes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 SCRIPT BREAKDOWN (Annotated Hex)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{script_breakdown}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 SPENDING INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{witness_stack}

⚠️  IMPORTANT SECURITY NOTES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 REQUIRED TO SPEND YOUR FUNDS:

Path A (Publish Data): 
  ✅ 1. The actual DATA/SECRET (preimage of {data_hash[:16]}...)
  ✅ 2. Publisher's PRIVATE KEY
  ⚠️  Data becomes PUBLIC when published to blockchain!

Path B (Refund):
  ✅ 1. Wait until block {locktime} or later
  ✅ 2. REDEEM SCRIPT (shown above) - SAVE THIS!
  ✅ 3. Buyer's PRIVATE KEY

📁 Auto-saved to: {self.storage_file}

Use the "Sweep Locked Funds" tab to claim refund after timeout.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  PLUGIN DISCLAIMER ⚠━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a SIGNET-PRODUCTION quality proof of concept!
Development sponsored by Vibes Capital Management with real signet coins 🚀

NOT suitable for mainnet usage.
"""
            
            self.display_result(result, address, script)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate data publishing contract: {str(e)}")
            import traceback
            traceback.print_exc()
        
    def build_simple_cltv_script(self, locktime: int, pubkey_hex: str) -> str:
        """
        Build simple CLTV script: <locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG
        
        Returns hex string of the script
        """
        from electrum.transaction import opcodes
        
        self.log("\n🔨 BUILDING BITCOIN SCRIPT:")
        self.log("-" * 80)
        self.log("Target script: <locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG")
        self.log("")
        
        script_bytes = bytearray()
        
        # Push locktime value
        locktime_push = self.push_int(locktime)
        self.log(f"Step 1: Push locktime value {locktime}")
        self.log(f"  Hex: {locktime_push.hex()}")
        self.log(f"  Bytes: {len(locktime_push)} byte(s)")
        script_bytes.extend(locktime_push)
        
        # OP_CHECKLOCKTIMEVERIFY (0xb1)
        self.log(f"\nStep 2: OP_CHECKLOCKTIMEVERIFY (opcode 0xb1)")
        self.log(f"  Function: Verifies transaction nLockTime >= {locktime}")
        self.log(f"  This ensures the output can't be spent before the locktime")
        script_bytes.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        
        # OP_DROP (0x75) - remove locktime from stack
        self.log(f"\nStep 3: OP_DROP (opcode 0x75)")
        self.log(f"  Function: Removes the locktime value from the stack")
        self.log(f"  Cleanup operation (CLTV doesn't consume its argument)")
        script_bytes.append(opcodes.OP_DROP)
        
        # Push public key
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        pubkey_push = self.push_bytes(pubkey_bytes)
        self.log(f"\nStep 4: Push public key")
        self.log(f"  Pubkey (hex): {pubkey_hex}")
        self.log(f"  Pubkey (bytes): {len(pubkey_bytes)} bytes")
        self.log(f"  Push opcode: 0x{pubkey_push[0]:02x} (push {len(pubkey_bytes)} bytes)")
        script_bytes.extend(pubkey_push)
        
        # OP_CHECKSIG (0xac)
        self.log(f"\nStep 5: OP_CHECKSIG (opcode 0xac)")
        self.log(f"  Function: Verifies signature matches the public key")
        self.log(f"  This ensures only the key owner can spend (after locktime)")
        script_bytes.append(opcodes.OP_CHECKSIG)
        
        script_hex = script_bytes.hex()
        self.log(f"\n✅ SCRIPT COMPLETE:")
        self.log(f"  Total size: {len(script_bytes)} bytes")
        self.log(f"  Script hex: {script_hex}")
        self.log(f"\n📊 Opcode breakdown:")
        self.log(f"  {locktime_push.hex():20} <- Push {locktime}")
        self.log(f"  b1{' '*18} <- OP_CHECKLOCKTIMEVERIFY")
        self.log(f"  75{' '*18} <- OP_DROP")
        self.log(f"  {pubkey_push.hex()[:20]:20}... <- Push pubkey ({len(pubkey_bytes)} bytes)")
        self.log(f"  ac{' '*18} <- OP_CHECKSIG")
        self.log("-" * 80 + "\n")
        
        return script_hex
    
    def build_twofactor_script(self, locktime: int, user_pubkey: str, service_pubkey: str) -> str:
        """
        Build two-factor wallet script from BIP-65 Example 2:
        IF
            <service_pubkey> CHECKSIGVERIFY
        ELSE
            <locktime> CHECKLOCKTIMEVERIFY DROP
        ENDIF
        <user_pubkey> CHECKSIG
        """
        from electrum.transaction import opcodes
        
        self.log(f"[SCRIPT] Building two-factor wallet script...")
        self.log(f"[SCRIPT] Service pubkey: {service_pubkey}")
        self.log(f"[SCRIPT] User pubkey: {user_pubkey}")
        self.log(f"[SCRIPT] Recovery locktime: {locktime}")
        
        script_bytes = bytearray()
        
        # OP_IF (0x63)
        self.log(f"[SCRIPT] Step 1: Add OP_IF (0x63)")
        script_bytes.append(opcodes.OP_IF)
        
        # IF branch: <service_pubkey> CHECKSIGVERIFY
        self.log(f"[SCRIPT] Step 2: Add service pubkey ({len(bytes.fromhex(service_pubkey))} bytes)")
        service_bytes = bytes.fromhex(service_pubkey)
        service_push = bytes([len(service_bytes)]) + service_bytes
        script_bytes.extend(service_push)
        
        # OP_CHECKSIGVERIFY (0xad)
        self.log(f"[SCRIPT] Step 3: Add OP_CHECKSIGVERIFY (0xad)")
        script_bytes.append(opcodes.OP_CHECKSIGVERIFY)
        
        # OP_ELSE (0x67)
        self.log(f"[SCRIPT] Step 4: Add OP_ELSE (0x67)")
        script_bytes.append(opcodes.OP_ELSE)
        
        # ELSE branch: <locktime> CHECKLOCKTIMEVERIFY DROP
        # Encode locktime as minimal length bytes (little-endian)
        locktime_bytes = locktime.to_bytes((locktime.bit_length() + 7) // 8, 'little')
        self.log(f"[SCRIPT] Step 5: Add locktime {locktime} ({len(locktime_bytes)} bytes): {locktime_bytes.hex()}")
        locktime_push = bytes([len(locktime_bytes)]) + locktime_bytes
        script_bytes.extend(locktime_push)
        
        # OP_CHECKLOCKTIMEVERIFY (0xb1)
        self.log(f"[SCRIPT] Step 6: Add OP_CHECKLOCKTIMEVERIFY (0xb1)")
        script_bytes.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        
        # OP_DROP (0x75)
        self.log(f"[SCRIPT] Step 7: Add OP_DROP (0x75)")
        script_bytes.append(opcodes.OP_DROP)
        
        # OP_ENDIF (0x68)
        self.log(f"[SCRIPT] Step 8: Add OP_ENDIF (0x68)")
        script_bytes.append(opcodes.OP_ENDIF)
        
        # Final: <user_pubkey> CHECKSIG
        self.log(f"[SCRIPT] Step 9: Add user pubkey ({len(bytes.fromhex(user_pubkey))} bytes)")
        user_bytes = bytes.fromhex(user_pubkey)
        user_push = bytes([len(user_bytes)]) + user_bytes
        script_bytes.extend(user_push)
        
        # OP_CHECKSIG (0xac)
        self.log(f"[SCRIPT] Step 10: Add OP_CHECKSIG (0xac)")
        script_bytes.append(opcodes.OP_CHECKSIG)
        
        self.log(f"[SCRIPT] ✓ Two-factor script construction complete: {len(script_bytes)} bytes")
        
        return script_bytes.hex()
    
    def build_datapub_script(self, data_hash_hex: str, publisher_hex: str, buyer_hex: str, locktime: int) -> str:
        """
        Build data publishing script from BIP-65 Example 4:
        IF
            HASH160 <hash> EQUALVERIFY
            <publisher_pubkey> CHECKSIG
        ELSE
            <locktime> CHECKLOCKTIMEVERIFY DROP
            <buyer_pubkey> CHECKSIG
        ENDIF
        
        Note: Using HASH160 instead of SHA256 to match standard Bitcoin practice
        """
        self.log(f"[SCRIPT] Building data publishing script...")
        self.log(f"[SCRIPT] Data hash (input SHA256): {data_hash_hex}")
        
        # Convert SHA256 to HASH160 (RIPEMD160(SHA256(data)))
        # Since we already have SHA256, we just need RIPEMD160
        from electrum.crypto import hash_160
        sha256_bytes = bytes.fromhex(data_hash_hex)
        # For the script, we want HASH160 of the preimage, not the SHA256
        # So we'll use the input as-is but note this in documentation
        # Actually, let's use HASH160 properly - take RIPEMD160 of the SHA256
        import hashlib
        hash160_bytes = hashlib.new('ripemd160', sha256_bytes).digest()
        
        self.log(f"[SCRIPT] Hash160 of SHA256: {hash160_bytes.hex()}")
        self.log(f"[SCRIPT] Publisher pubkey: {publisher_hex}")
        self.log(f"[SCRIPT] Buyer pubkey: {buyer_hex}")
        self.log(f"[SCRIPT] Refund locktime: {locktime}")
        
        script_bytes = bytearray()
        
        # OP_IF (0x63)
        self.log(f"[SCRIPT] Step 1: Add OP_IF (0x63)")
        script_bytes.append(opcodes.OP_IF)
        
        # IF branch: HASH160 <hash> EQUALVERIFY <publisher_pk> CHECKSIG
        
        # OP_HASH160 (0xa9)
        self.log(f"[SCRIPT] Step 2: Add OP_HASH160 (0xa9)")
        script_bytes.append(opcodes.OP_HASH160)
        
        # Push the hash160
        self.log(f"[SCRIPT] Step 3: Add hash ({len(hash160_bytes)} bytes)")
        hash_push = bytes([len(hash160_bytes)]) + hash160_bytes
        script_bytes.extend(hash_push)
        
        # OP_EQUALVERIFY (0x88)
        self.log(f"[SCRIPT] Step 4: Add OP_EQUALVERIFY (0x88)")
        script_bytes.append(opcodes.OP_EQUALVERIFY)
        
        # Publisher pubkey
        self.log(f"[SCRIPT] Step 5: Add publisher pubkey ({len(bytes.fromhex(publisher_hex))} bytes)")
        publisher_bytes = bytes.fromhex(publisher_hex)
        publisher_push = bytes([len(publisher_bytes)]) + publisher_bytes
        script_bytes.extend(publisher_push)
        
        # OP_CHECKSIG (0xac)
        self.log(f"[SCRIPT] Step 6: Add OP_CHECKSIG (0xac)")
        script_bytes.append(opcodes.OP_CHECKSIG)
        
        # OP_ELSE (0x67)
        self.log(f"[SCRIPT] Step 7: Add OP_ELSE (0x67)")
        script_bytes.append(opcodes.OP_ELSE)
        
        # ELSE branch: <locktime> CHECKLOCKTIMEVERIFY DROP <buyer_pk> CHECKSIG
        
        # Locktime
        locktime_bytes = locktime.to_bytes((locktime.bit_length() + 7) // 8, 'little')
        self.log(f"[SCRIPT] Step 8: Add locktime {locktime} ({len(locktime_bytes)} bytes): {locktime_bytes.hex()}")
        locktime_push = bytes([len(locktime_bytes)]) + locktime_bytes
        script_bytes.extend(locktime_push)
        
        # OP_CHECKLOCKTIMEVERIFY (0xb1)
        self.log(f"[SCRIPT] Step 9: Add OP_CHECKLOCKTIMEVERIFY (0xb1)")
        script_bytes.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        
        # OP_DROP (0x75)
        self.log(f"[SCRIPT] Step 10: Add OP_DROP (0x75)")
        script_bytes.append(opcodes.OP_DROP)
        
        # Buyer pubkey
        self.log(f"[SCRIPT] Step 11: Add buyer pubkey ({len(bytes.fromhex(buyer_hex))} bytes)")
        buyer_bytes = bytes.fromhex(buyer_hex)
        buyer_push = bytes([len(buyer_bytes)]) + buyer_bytes
        script_bytes.extend(buyer_push)
        
        # OP_CHECKSIG (0xac)
        self.log(f"[SCRIPT] Step 12: Add OP_CHECKSIG (0xac)")
        script_bytes.append(opcodes.OP_CHECKSIG)
        
        # OP_ENDIF (0x68)
        self.log(f"[SCRIPT] Step 13: Add OP_ENDIF (0x68)")
        script_bytes.append(opcodes.OP_ENDIF)
        
        self.log(f"[SCRIPT] ✓ Data publishing script construction complete: {len(script_bytes)} bytes")
        self.log(f"[SCRIPT] ⚠️  Note: Preimage must hash to HASH160 = {hash160_bytes.hex()}")
        
        return script_bytes.hex()
    
    def build_escrow_cltv_script(self, locktime: int, agent_hex: str, party1_hex: str, party2_hex: str) -> str:
        """
        Build escrow CLTV script from BIP-65:
        IF
            <locktime> CHECKLOCKTIMEVERIFY DROP
            <agent_pubkey> CHECKSIGVERIFY
            1
        ELSE
            2
        ENDIF
        <party1_pubkey> <party2_pubkey> 2 CHECKMULTISIG
        """
        from electrum.transaction import opcodes
        
        script_bytes = bytearray()
        
        # OP_IF
        script_bytes.append(opcodes.OP_IF)
        
        # Push locktime
        script_bytes.extend(self.push_int(locktime))
        
        # OP_CHECKLOCKTIMEVERIFY
        script_bytes.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        
        # OP_DROP
        script_bytes.append(opcodes.OP_DROP)
        
        # Push agent pubkey
        agent_bytes = bytes.fromhex(agent_hex)
        script_bytes.extend(self.push_bytes(agent_bytes))
        
        # OP_CHECKSIGVERIFY
        script_bytes.append(opcodes.OP_CHECKSIGVERIFY)
        
        # OP_1 (for 1-of-2 in timelock branch)
        script_bytes.append(opcodes.OP_1)
        
        # OP_ELSE
        script_bytes.append(opcodes.OP_ELSE)
        
        # OP_2 (for 2-of-2 in normal branch)
        script_bytes.append(opcodes.OP_2)
        
        # OP_ENDIF
        script_bytes.append(opcodes.OP_ENDIF)
        
        # Push party1 pubkey
        party1_bytes = bytes.fromhex(party1_hex)
        script_bytes.extend(self.push_bytes(party1_bytes))
        
        # Push party2 pubkey
        party2_bytes = bytes.fromhex(party2_hex)
        script_bytes.extend(self.push_bytes(party2_bytes))
        
        # OP_2 (number of pubkeys)
        script_bytes.append(opcodes.OP_2)
        
        # OP_CHECKMULTISIG
        script_bytes.append(opcodes.OP_CHECKMULTISIG)
        
        return script_bytes.hex()
        
    def push_int(self, n: int) -> bytes:
        """Push an integer onto the script stack (Bitcoin script format)"""
        from electrum.transaction import opcodes
        
        if n == -1 or (n >= 1 and n <= 16):
            # Use OP_1 through OP_16 for small numbers
            return bytes([opcodes.OP_1 + n - 1]) if n >= 1 else bytes([opcodes.OP_1NEGATE])
        elif n == 0:
            return bytes([opcodes.OP_0])
        else:
            # Encode as minimal little-endian bytes
            return self.push_bytes(self.encode_minimal_int(n))
            
    def encode_minimal_int(self, n: int) -> bytes:
        """Encode integer in minimal Bitcoin script format"""
        if n == 0:
            return b''
            
        result = []
        negative = n < 0
        absvalue = abs(n)
        
        while absvalue:
            result.append(absvalue & 0xff)
            absvalue >>= 8
            
        # If the most significant bit is set, add an extra byte
        if result[-1] & 0x80:
            result.append(0x80 if negative else 0x00)
        elif negative:
            result[-1] |= 0x80
            
        return bytes(result)
        
    def push_bytes(self, data: bytes) -> bytes:
        """Push bytes onto the script stack with proper length encoding"""
        from electrum.transaction import opcodes
        
        length = len(data)
        
        if length < opcodes.OP_PUSHDATA1:
            # Direct length byte
            return bytes([length]) + data
        elif length <= 0xff:
            # OP_PUSHDATA1
            return bytes([opcodes.OP_PUSHDATA1, length]) + data
        elif length <= 0xffff:
            # OP_PUSHDATA2
            return bytes([opcodes.OP_PUSHDATA2]) + length.to_bytes(2, 'little') + data
        else:
            # OP_PUSHDATA4
            return bytes([opcodes.OP_PUSHDATA4]) + length.to_bytes(4, 'little') + data
            
    def script_to_p2sh_address(self, script_hex: str) -> str:
        """Convert script to P2SH address"""
        from electrum.bitcoin import hash_160
        from electrum import constants
        
        script_bytes = bytes.fromhex(script_hex)
        script_hash = hash_160(script_bytes)
        
        # Use Electrum's function to create P2SH address
        address = hash160_to_p2sh(script_hash)
        
        return address
    
    def format_script_breakdown(self, script_hex: str, script_type: str) -> str:
        """Format script hex with annotations for each opcode/data"""
        from electrum.transaction import opcodes
        
        # Reverse lookup for opcodes
        opcode_names = {v: k for k, v in opcodes.__dict__.items() if isinstance(v, int) and k.startswith('OP_')}
        
        script_bytes = bytes.fromhex(script_hex)
        breakdown = []
        i = 0
        
        while i < len(script_bytes):
            byte = script_bytes[i]
            
            # Check if it's a data push
            if byte <= 75:  # Direct push
                length = byte
                data = script_bytes[i+1:i+1+length]
                breakdown.append(f"{byte:02x}           # PUSH {length} bytes")
                breakdown.append(f"{data.hex():20s} # Data: {data.hex()[:32]}{'...' if len(data) > 16 else ''}")
                i += 1 + length
            elif byte == opcodes.OP_PUSHDATA1:
                length = script_bytes[i+1]
                data = script_bytes[i+2:i+2+length]
                breakdown.append(f"{byte:02x}           # OP_PUSHDATA1")
                breakdown.append(f"{length:02x}           # Length: {length}")
                breakdown.append(f"{data.hex():20s} # Data: {data.hex()[:32]}{'...' if len(data) > 16 else ''}")
                i += 2 + length
            else:
                # It's an opcode
                opname = opcode_names.get(byte, f"UNKNOWN_0x{byte:02x}")
                breakdown.append(f"{byte:02x}           # {opname}")
                i += 1
        
        return "\n".join(breakdown)
        
    def display_results(self, address: str, script_hex: str, script_type: str, 
                       locktime: str, locktime_type: str, details: str, 
                       miniscript: str = "", descriptor: str = "", 
                       witness_stack: str = ""):
        """Display the generated address and script information with full technical details"""
        from electrum.bitcoin import hash_160
        
        script_bytes = bytes.fromhex(script_hex)
        script_hash = hash_160(script_bytes)
        script_breakdown = self.format_script_breakdown(script_hex, script_type)
        
        result = f"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CHECKLOCKTIMEVERIFY ADDRESS GENERATED                                    ║
╚══════════════════════════════════════════════════════════════════════════╝

✅ Address displayed above - click '📋 Copy' to copy it!

🚨 CRITICAL: SAVE THE REDEEM SCRIPT BELOW! 🚨
You MUST have the redeem script to recover your funds!
Auto-saved to: {self.storage_file}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 SCRIPT DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Script Type: {script_type}
Locktime: {locktime}
Locktime Type: {locktime_type}

🔐 Spending Conditions:
{details}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 TECHNICAL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 Miniscript Policy (approximate):
{miniscript}

🔹 Descriptor-Style Notation:
sh(raw({script_hash.hex()}))
# Note: Electrum doesn't use Bitcoin Core descriptors natively

🔹 Redeem Script (hex):
{script_hex}

🔹 Script Hash (HASH160):
{script_hash.hex()}

🔹 Script Size: {len(script_bytes)} bytes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 SCRIPT BREAKDOWN (Annotated Hex)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{script_breakdown}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 SPENDING INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{witness_stack}

⚠️  IMPORTANT SECURITY NOTES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 REQUIRED TO SWEEP/RECOVER YOUR FUNDS:
  ✅ 1. REDEEM SCRIPT (shown above) - SAVE THIS! Critical!
  ✅ 2. Your wallet's PRIVATE KEY (already in this wallet)
  ✅ 3. Wait until block {locktime} or later

📁 Auto-saved to: {self.storage_file}

Use the "Sweep Timelock" tab to recover funds after the locktime expires.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  TECHNICAL REQUIREMENTS FOR SPENDING:
1. Transaction nLockTime must be >= {locktime}
2. Transaction nSequence field must be < 0xffffffff (not finalized)
3. Before block {locktime}, the funds CANNOT be spent by anyone

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BIP-65 Reference: https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki

⚠️  PLUGIN DISCLAIMER ⚠️
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a SIGNET-PRODUCTION quality proof of concept!
Development sponsored by Vibes Capital Management with real signet coins 🚀

NOT suitable for mainnet usage.
"""
        
        # Update inline address display
        self.address_display.setText(address)
        self.quick_copy_address_btn.setEnabled(True)
        
        # Update detailed result text
        self.result_text.setText(result)
        
        # Store for legacy copy buttons
        self.current_address = address
        self.current_script = script_hex
        self.copy_address_btn.setEnabled(True)
        self.copy_script_btn.setEnabled(True)
    
    def copy_address(self):
        """Copy address to clipboard using Electrum's built-in function"""
        self.window.do_copy(self.current_address, title="Address")
        self.log(f"[COPY] Address copied: {self.current_address}")
        
    def copy_script(self):
        """Copy redeem script to clipboard using Electrum's built-in function"""
        self.window.do_copy(self.current_script, title="Redeem Script")
        self.log(f"[COPY] Redeem script copied: {self.current_script[:32]}...")
    
    def refresh_timelock_list(self, force_refresh: bool = False):
        """Refresh the list of timelocked addresses and check for UTXOs
        
        Args:
            force_refresh: If True, clear cache and query network for all addresses
        """
        if force_refresh:
            self.log("[SWEEP] Force refresh requested - clearing UTXO cache")
            self.utxo_cache.clear()
        
        self.log("[SWEEP] Refreshing timelock list")
        
        # Load saved timelocks
        timelocks = self.load_timelock_data()
        
        # Clear table
        self.timelock_table.setRowCount(0)
        
        # Get current block height from network
        network = self.window.network
        current_block = network.get_local_height() if network else 210000
        self.log(f"[SWEEP] Current block height: {current_block}")
        
        row = 0
        addresses_checked = 0
        addresses_with_utxos = 0
        
        for i, lock in enumerate(timelocks):
            # Check if address has UTXOs (with caching)
            address = lock['address']
            addresses_checked += 1
            
            # Use cached UTXO check (pass persistent cache from JSON)
            utxo_info = self.check_address_utxos(address, force_refresh=force_refresh, persistent_cache=lock)
            has_utxos = utxo_info['has_utxos']
            balance_sats = utxo_info['balance_sats']
            
            # Only log if not from cache AND has UTXOs (skip empty address spam)
            if not utxo_info['cached'] and has_utxos:
                num_utxos = len(utxo_info['utxos'])
                self.log(f"[SWEEP] {address}: {num_utxos} UTXO(s), {balance_sats} sats")
                addresses_with_utxos += 1
            elif has_utxos:
                addresses_with_utxos += 1
            
            # Only show timelocks that have UTXOs OR were recently created
            # (Allow showing unfunded timelocks created in the last hour)
            created_time = lock.get('created_at', 0)
            is_recent = (time.time() - created_time) < 3600  # 1 hour
            
            if not has_utxos and not is_recent:
                continue  # Skip without logging (reduces spam)
            
            self.timelock_table.insertRow(row)
            
            # Address
            self.timelock_table.setItem(row, 0, QTableWidgetItem(lock['address']))
            
            # Script Type (BIP-65 label)
            script_type = lock.get('script_type', 'simple')
            script_label = self.get_script_type_label(script_type)
            self.timelock_table.setItem(row, 1, QTableWidgetItem(script_label))
            
            # Locktime
            locktime_str = str(lock.get('locktime', 'N/A'))
            locktime_type = lock.get('locktime_type', 'block height')  # Default to block height
            if locktime_type == 'timestamp':
                dt = datetime.fromtimestamp(lock['locktime'])
                locktime_str += f" ({dt.strftime('%Y-%m-%d')})"
            self.timelock_table.setItem(row, 2, QTableWidgetItem(locktime_str))
            
            # Type
            self.timelock_table.setItem(row, 3, QTableWidgetItem(locktime_type))
            
            # Status - Much more detailed and user-friendly
            is_unlocked = False
            status_msg = ""
            
            if locktime_type == 'block height':
                blocks_remaining = lock['locktime'] - current_block
                if blocks_remaining <= 0:
                    is_unlocked = True
                    status_msg = f"✅ READY TO SWEEP (unlocked {abs(blocks_remaining)} blocks ago)"
                else:
                    # Estimate time (10 min per block on average, 2 min on signet)
                    is_signet = constants.net.GENESIS.startswith('00000008819873')
                    mins_per_block = 2 if is_signet else 10
                    time_remaining = blocks_remaining * mins_per_block
                    
                    if blocks_remaining == 1:
                        status_msg = f"⏳ LOCKED (1 block / ~{mins_per_block} min)"
                    elif time_remaining < 60:
                        status_msg = f"⏳ LOCKED ({blocks_remaining} blocks / ~{time_remaining} min)"
                    elif time_remaining < 1440:  # < 24 hours
                        hours = time_remaining // 60
                        status_msg = f"⏳ LOCKED ({blocks_remaining} blocks / ~{hours}h {time_remaining % 60}m)"
                    else:
                        days = time_remaining // 1440
                        hours = (time_remaining % 1440) // 60
                        status_msg = f"⏳ LOCKED ({blocks_remaining} blocks / ~{days}d {hours}h)"
            
            elif locktime_type == 'timestamp':
                time_remaining_secs = lock['locktime'] - int(time.time())
                if time_remaining_secs <= 0:
                    is_unlocked = True
                    elapsed = abs(time_remaining_secs)
                    if elapsed < 3600:
                        status_msg = f"✅ READY TO SWEEP (unlocked {elapsed // 60} min ago)"
                    elif elapsed < 86400:
                        status_msg = f"✅ READY TO SWEEP (unlocked {elapsed // 3600}h ago)"
                    else:
                        status_msg = f"✅ READY TO SWEEP (unlocked {elapsed // 86400}d ago)"
                else:
                    if time_remaining_secs < 3600:  # < 1 hour
                        mins = time_remaining_secs // 60
                        status_msg = f"⏳ LOCKED ({mins} minutes remaining)"
                    elif time_remaining_secs < 86400:  # < 24 hours
                        hours = time_remaining_secs // 3600
                        mins = (time_remaining_secs % 3600) // 60
                        status_msg = f"⏳ LOCKED ({hours}h {mins}m remaining)"
                    else:
                        days = time_remaining_secs // 86400
                        hours = (time_remaining_secs % 86400) // 3600
                        status_msg = f"⏳ LOCKED ({days}d {hours}h remaining)"
            
            self.timelock_table.setItem(row, 4, QTableWidgetItem(status_msg))
            
            # Balance
            if has_utxos:
                balance_str = f"💰 {balance_sats:,} sats"
            else:
                balance_str = "⚠️ Unfunded (new)"
            self.timelock_table.setItem(row, 5, QTableWidgetItem(balance_str))
            
            # Sweep Action button - Dynamic based on status
            if not has_utxos:
                sweep_btn = QPushButton("⚠️ No Funds")
                sweep_btn.setEnabled(False)
            elif is_unlocked:
                sweep_btn = QPushButton("🔓 Sweep Now")
                sweep_btn.setEnabled(True)
                sweep_btn.clicked.connect(lambda checked, idx=i: self.sweep_timelock(idx))
            else:
                # Show when it will be unlocked
                if locktime_type == 'block height':
                    sweep_btn = QPushButton(f"⏳ Wait {blocks_remaining} blocks")
                else:
                    unlock_dt = datetime.fromtimestamp(lock['locktime'])
                    sweep_btn = QPushButton(f"⏳ Wait until {unlock_dt.strftime('%m/%d %H:%M')}")
                sweep_btn.setEnabled(False)
            
            self.timelock_table.setCellWidget(row, 6, sweep_btn)
            
            # Visualize Script button - always available
            visualize_btn = QPushButton("🔍 Visualize")
            visualize_btn.setToolTip("Show step-by-step script execution for sweeping")
            visualize_btn.clicked.connect(lambda checked, idx=i: self.visualize_sweep_script(idx))
            self.timelock_table.setCellWidget(row, 7, visualize_btn)
            
            row += 1
        
        self.log(f"[SWEEP] Loaded {addresses_with_utxos} address(es) with UTXOs (out of {addresses_checked} checked, {len(timelocks)} total)")
    
    def show_psbt_dialog(self, tx, key_analysis, sweep_result):
        """Show PSBT export dialog with signature analysis"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle("PSBT - Partially Signed Bitcoin Transaction")
        dialog.setMinimumWidth(800)
        dialog.setMinimumHeight(600)
        
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("<h2>📝 Transaction Signature Status</h2>")
        layout.addWidget(header)
        
        # Key analysis
        analysis_text = "<h3>🔑 Keys Analysis:</h3><ul>"
        for i, key_info in enumerate(key_analysis['keys_status'], 1):
            pubkey_display = key_info['pubkey'][:20] + '...' + key_info['pubkey'][-20:]
            
            if key_info['has_private_key']:
                analysis_text += f"<li><b>Key {i}:</b> ✅ <span style='color: green;'>Available in wallet</span><br>"
                analysis_text += f"&nbsp;&nbsp;&nbsp;&nbsp;Pubkey: <code>{pubkey_display}</code><br>"
                analysis_text += f"&nbsp;&nbsp;&nbsp;&nbsp;Address: <code>{key_info['wallet_address']}</code></li>"
            else:
                analysis_text += f"<li><b>Key {i}:</b> ❌ <span style='color: red;'>Missing (test vector or external key)</span><br>"
                analysis_text += f"&nbsp;&nbsp;&nbsp;&nbsp;Pubkey: <code>{pubkey_display}</code><br>"
                analysis_text += f"&nbsp;&nbsp;&nbsp;&nbsp;<i>To sign: Import private key or use different wallet</i></li>"
        
        analysis_text += "</ul>"
        
        # Signature completeness
        if tx.is_complete():
            analysis_text += "<p><b>Status:</b> <span style='color: green; font-size: 14pt;'>✅ Fully Signed - Ready to Broadcast</span></p>"
        else:
            analysis_text += "<p><b>Status:</b> <span style='color: orange; font-size: 14pt;'>⚠️ Partially Signed - More signatures needed</span></p>"
            analysis_text += f"<p>Keys available: {key_analysis['num_keys_available']} of {key_analysis['num_keys_total']}</p>"
        
        analysis_label = QLabel(analysis_text)
        analysis_label.setWordWrap(True)
        layout.addWidget(analysis_label)
        
        # Transaction details
        details_text = f"""<h3>💰 Transaction Details:</h3>
<ul>
<li><b>From:</b> <code>{sweep_result['address']}</code></li>
<li><b>To:</b> <code>{sweep_result['receiving_address']}</code></li>
<li><b>Amount:</b> {sweep_result['output_value']} sats</li>
<li><b>Fee:</b> {sweep_result['fee']} sats</li>
<li><b>Size:</b> {len(tx.serialize())//2} bytes</li>
</ul>"""
        
        details_label = QLabel(details_text)
        layout.addWidget(details_label)
        
        # PSBT hex
        psbt_label = QLabel("<h3>📋 PSBT Base64 (for external signing):</h3>")
        layout.addWidget(psbt_label)
        
        psbt_text = QTextEdit()
        psbt_text.setReadOnly(True)
        psbt_text.setFont(QFont("Courier", 9))
        
        try:
            # Export as PSBT
            psbt_base64 = tx.to_qr_data()
            psbt_text.setPlainText(psbt_base64)
        except Exception as e:
            # Fallback to raw hex
            psbt_text.setPlainText(f"Raw transaction hex:\n{tx.serialize()}")
            self.log(f"[PSBT] Could not export as PSBT: {e}")
        
        layout.addWidget(psbt_text)
        
        # Help text
        help_text = QLabel(
            "<small><b>How to complete signing:</b><br>"
            "1. If you have all keys in this wallet, broadcast directly<br>"
            "2. If missing keys, import the private keys from test vectors (see documentation)<br>"
            "3. Or copy PSBT to external wallet/signer that has the keys<br>"
            "4. Test vector keys (WIF format) are in TEST_VECTOR_KEYS.md</small>"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("📋 Copy PSBT")
        copy_btn.clicked.connect(lambda: self.window.do_copy(psbt_text.toPlainText(), title="PSBT Base64"))
        btn_layout.addWidget(copy_btn)
        
        copy_hex_btn = QPushButton("📋 Copy Raw Hex")
        copy_hex_btn.clicked.connect(lambda: self.window.do_copy(tx.serialize(), title="Transaction Hex"))
        btn_layout.addWidget(copy_hex_btn)
        
        if tx.is_complete():
            broadcast_btn = QPushButton("✅ Broadcast Now")
            broadcast_btn.clicked.connect(lambda: self.broadcast_from_psbt_dialog(tx, dialog))
            btn_layout.addWidget(broadcast_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    # Removed copy_to_clipboard - now using window.do_copy() for DRY
    
    def broadcast_from_psbt_dialog(self, tx, dialog):
        """Broadcast transaction from PSBT dialog"""
        from electrum.gui.qt.util import WaitingDialog
        
        def broadcast():
            network = self.window.network
            txid = network.run_from_another_thread(network.broadcast_transaction(tx))
            return {'txid': txid}
        
        def on_success(result):
            dialog.close()
            QMessageBox.information(
                self,
                "Success! 🎉",
                f"Transaction broadcast successfully!\n\nTXID: {result['txid']}"
            )
            self.refresh_timelock_list()
            # Clear UTXO cache on successful sweep
            self.utxo_cache.clear()
            self.log("[SWEEP] Cache cleared after successful sweep")
        
        WaitingDialog(self, "Broadcasting...", broadcast, on_success, self.on_error)
    
    def sweep_timelock(self, index: int):
        """Sweep a specific timelock entry"""
        timelocks = self.load_timelock_data()
        if index >= len(timelocks):
            return
        
        lock = timelocks[index]
        self.log(f"[SWEEP] Attempting to sweep {lock['address']}")
        
        # Find and update button state to show "Sweeping..."
        for row in range(self.timelock_table.rowCount()):
            if self.timelock_table.item(row, 0).text() == lock['address']:
                btn = self.timelock_table.cellWidget(row, 6)
                if btn:
                    btn.setText("⏳ Sweeping...")
                    btn.setEnabled(False)
                break
        
        # Perform sweep
        self.perform_sweep(lock['script_hex'], lock['locktime'], lock.get('pubkey'), index)
    
    def manual_sweep(self):
        """Sweep using manually pasted redeem script"""
        script_hex = self.manual_redeem_script.toPlainText().strip()
        if not script_hex:
            QMessageBox.warning(self, "Error", "Please paste a redeem script")
            return
        
        self.log(f"[SWEEP] Manual sweep with script: {script_hex[:32]}...")
        
        # Parse script to extract locktime
        try:
            script_bytes = bytes.fromhex(script_hex)
            # First byte should be push length for locktime
            push_len = script_bytes[0]
            locktime_bytes = script_bytes[1:1+push_len]
            locktime = int.from_bytes(locktime_bytes, 'little')
            
            self.log(f"[SWEEP] Extracted locktime from script: {locktime}")
            self.perform_sweep(script_hex, locktime, None)
        except Exception as e:
            self.log(f"[ERROR] Failed to parse redeem script: {e}")
            QMessageBox.critical(self, "Error", f"Failed to parse redeem script: {e}")
    
    def analyze_sweep_keys(self, redeem_script_hex: str, address: str):
        """Analyze which keys are available for signing and which are missing"""
        from electrum.bitcoin import pubkey_to_address
        
        script_bytes = bytes.fromhex(redeem_script_hex)
        
        # Extract pubkey(s) from script
        # Simple CLTV: <locktime> DROP <pubkey> CHECKSIG
        # After the locktime push, look for pubkey pushes
        
        pubkeys_found = []
        keys_status = []
        
        try:
            # Parse script to find all pubkeys
            pos = 0
            while pos < len(script_bytes):
                opcode = script_bytes[pos]
                
                # Check for data push (33 bytes compressed or 65 bytes uncompressed)
                if opcode == 0x21:  # Push 33 bytes (compressed pubkey)
                    pubkey_hex = script_bytes[pos+1:pos+34].hex()
                    pubkeys_found.append(pubkey_hex)
                    pos += 34
                elif opcode == 0x41:  # Push 65 bytes (uncompressed pubkey)
                    pubkey_hex = script_bytes[pos+1:pos+66].hex()
                    pubkeys_found.append(pubkey_hex)
                    pos += 66
                elif opcode <= 0x4b:  # Push N bytes
                    pos += opcode + 1
                else:
                    pos += 1
            
            # Check each pubkey against wallet
            for pubkey_hex in pubkeys_found:
                has_key = False
                wallet_addr = None
                
                # Check if wallet has this pubkey
                for addr_type in ['p2pkh', 'p2wpkh', 'p2wpkh-p2sh']:
                    try:
                        addr = pubkey_to_address(addr_type, pubkey_hex)
                        if self.wallet.is_mine(addr):
                            has_key = True
                            wallet_addr = addr
                            break
                    except:
                        pass
                
                # Also check wallet addresses directly
                if not has_key:
                    for addr in self.wallet.get_addresses()[:50]:
                        try:
                            wallet_pubkey = self.wallet.get_public_key(addr)
                            if wallet_pubkey == pubkey_hex:
                                has_key = True
                                wallet_addr = addr
                                break
                        except:
                            pass
                
                keys_status.append({
                    'pubkey': pubkey_hex,
                    'has_private_key': has_key,
                    'wallet_address': wallet_addr,
                    'source': 'Your Wallet ✅' if has_key else 'Missing (test vector?) ❌'
                })
        
        except Exception as e:
            self.log(f"[ANALYZE] Error parsing script for pubkeys: {e}")
        
        return {
            'address': address,
            'script': redeem_script_hex,
            'pubkeys': pubkeys_found,
            'keys_status': keys_status,
            'can_sign': any(k['has_private_key'] for k in keys_status),
            'num_keys_available': sum(1 for k in keys_status if k['has_private_key']),
            'num_keys_total': len(keys_status)
        }
    
    def perform_sweep(self, redeem_script_hex: str, locktime: int, pubkey: Optional[str], table_index: Optional[int] = None):
        """Perform the actual sweep transaction"""
        from electrum.gui.qt.util import WaitingDialog
        
        self.log("[SWEEP] ======== STARTING SWEEP PROCESS ========")
        self.log(f"[SWEEP] Redeem script: {redeem_script_hex}")
        self.log(f"[SWEEP] Locktime: {locktime}")
        
        def do_sweep_work():
            """Background worker - returns result dict"""
            try:
                # Calculate P2SH address
                from electrum.bitcoin import hash_160
                from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput
                
                script_bytes = bytes.fromhex(redeem_script_hex)
                script_hash_bytes = hash_160(script_bytes)  # This is the hash for P2SH
                address = hash160_to_p2sh(script_hash_bytes)
                self.log(f"[SWEEP] P2SH address: {address}")
                
                # Check current block height
                network = self.window.network if hasattr(self.window, 'network') else None
                if not network:
                    return {'success': False, 'error': 'Network not available'}
                
                current_height = network.get_local_height() if network else 0
                self.log(f"[SWEEP] Current block height: {current_height}")
                self.log(f"[SWEEP] Locktime required: {locktime}")
                
                if current_height < locktime:
                    return {
                        'success': False,
                        'error': f"Locktime not reached!\\n\\n"\
                                f"Current block: {current_height}\\n"\
                                f"Locktime: {locktime}\\n"\
                                f"Blocks remaining: {locktime - current_height}\\n\\n"\
                                f"Wait approximately {(locktime - current_height) * 10} minutes."
                    }
                
                # Query network for UTXOs
                sh = bitcoin.address_to_scripthash(address)
                self.log(f"[SWEEP] Script hash: {sh}")
                
                utxos = network.run_from_another_thread(network.listunspent_for_scripthash(sh))
                
                if not utxos:
                    # Check if address has been used (has history) - might be already swept
                    history = network.run_from_another_thread(
                        network.get_history_for_scripthash(sh)
                    )
                    
                    if history and len(history) > 0:
                        # Address has history but no UTXOs = already spent/swept
                        return {
                            'success': False,
                            'error': f"⚠️  Address Already Swept\\n\\n"\
                                    f"Address: {address}\\n\\n"\
                                    f"This address has transaction history ({len(history)} transaction(s)) "\
                                    f"but no unspent outputs (UTXOs).\\n\\n"\
                                    f"💡 This usually means the funds have already been swept or spent.\\n\\n"\
                                    f"Check transaction history on block explorer:\\n"\
                                    f"https://mempool.space/signet/address/{address}"
                        }
                    else:
                        # No history at all = never funded
                        return {
                            'success': False,
                            'error': f"No UTXOs found at address:\\n{address}\\n\\n"\
                                    f"Make sure:\\n"\
                                    f"1. The address has been funded\\n"\
                                    f"2. The transaction is confirmed\\n"\
                                    f"3. Electrum is synced (check bottom status bar)\\n\\n"\
                                    f"Script hash: {sh}\\n\\n"\
                                    f"Check on block explorer:\\n"\
                                    f"https://mempool.space/signet/address/{address}"
                        }
                
                self.log(f"[SWEEP] Found {len(utxos)} UTXO(s)")
                
                # Filter confirmed UTXOs
                confirmed_utxos = [u for u in utxos if u.get('height', 0) > 0]
                if not confirmed_utxos:
                    return {
                        'success': False,
                        'error': f"Found {len(utxos)} UTXO(s) but none are confirmed yet.\\n\\n"\
                                f"Wait for confirmations and try again."
                    }
                
                utxos = confirmed_utxos
                
                # Calculate total
                total_input = sum(utxo['value'] for utxo in utxos)
                self.log(f"[SWEEP] Total input value: {total_input} sats")
                
                # Get destination
                receiving_address = self.wallet.get_receiving_address()
                self.log(f"[SWEEP] Destination address: {receiving_address}")
                
                # Estimate fee
                estimated_size = 10 + (len(utxos) * 180) + 34
                fee = estimated_size * 2
                output_value = total_input - fee
                
                if output_value <= 0:
                    return {
                        'success': False,
                        'error': f"Insufficient funds\\nInput: {total_input}, Fee: {fee}"
                    }
                
                # Build transaction
                from electrum.transaction import TxOutpoint
                
                # Build P2SH scriptPubKey for witness_utxo (needed for fee verification)
                # P2SH format: OP_HASH160 <20-byte-hash> OP_EQUAL
                # Hex: a914{script_hash}87
                script_hash_hex = script_hash_bytes.hex() if isinstance(script_hash_bytes, bytes) else script_hash_bytes
                script_pubkey_hex = 'a914' + script_hash_hex + '87'
                script_pubkey_bytes = bfh(script_pubkey_hex)
                
                self.log(f"[SWEEP] ScriptPubKey hex: {script_pubkey_hex}")
                self.log(f"[SWEEP] ScriptPubKey bytes length: {len(script_pubkey_bytes)}")
                
                inputs = []
                for utxo in utxos:
                    txin = PartialTxInput(
                        prevout=TxOutpoint(txid=bytes.fromhex(utxo['tx_hash']), out_idx=utxo['tx_pos']),
                        nsequence=0xfffffffe
                    )
                    txin.script_type = 'p2sh'
                    txin.redeem_script = script_bytes
                    
                    # Set witness_utxo for fee verification (critical for signing)
                    txin.witness_utxo = TxOutput(
                        scriptpubkey=script_pubkey_bytes,
                        value=utxo['value']
                    )
                    
                    self.log(f"[SWEEP] Input witness_utxo set: scriptpubkey={script_pubkey_bytes.hex()}, value={utxo['value']}")
                    
                    inputs.append(txin)
                
                outputs = [PartialTxOutput.from_address_and_value(receiving_address, output_value)]
                tx = PartialTransaction.from_io(inputs, outputs, locktime=locktime)
                
                # Extract pubkey from redeem script to find the right key
                push_len = script_bytes[0]
                after_locktime = script_bytes[1+push_len:]
                pubkey_push = after_locktime[2]
                pubkey_bytes = after_locktime[3:3+pubkey_push]
                pubkey_hex = pubkey_bytes.hex()
                
                self.log(f"[SWEEP] Extracted pubkey from script: {pubkey_hex}")
                
                # Check if wallet has this pubkey
                self.log("[SWEEP] Checking wallet for this pubkey...")
                found_address = None
                for addr_type in ['p2pkh', 'p2wpkh', 'p2wpkh-p2sh']:
                    try:
                        addr = pubkey_to_address(addr_type, pubkey_hex)
                        if self.wallet.is_mine(addr):
                            found_address = addr
                            self.log(f"[SWEEP] ✅ Found! Wallet owns {addr_type} address: {addr}")
                            break
                        else:
                            self.log(f"[SWEEP] ❌ Wallet does NOT own {addr_type} address: {addr}")
                    except Exception as e:
                        self.log(f"[SWEEP] Error checking {addr_type}: {e}")
                
                if not found_address:
                    # Check all wallet addresses for this pubkey
                    self.log("[SWEEP] Checking all wallet addresses...")
                    wallet_addrs = self.wallet.get_addresses()
                    self.log(f"[SWEEP] Wallet has {len(wallet_addrs)} addresses")
                    for addr in wallet_addrs[:20]:  # Check first 20
                        try:
                            wallet_pubkey = self.wallet.get_public_key(addr)
                            if wallet_pubkey == pubkey_hex:
                                found_address = addr
                                self.log(f"[SWEEP] 🎯 MATCH! Found pubkey at address: {addr}")
                                break
                        except:
                            pass
                
                if not found_address:
                    return {
                        'success': False,
                        'error': f'Cannot sweep: Wallet does not contain the private key.\\n\\n'\
                                f'Required pubkey: {pubkey_hex}\\n\\n'\
                                f'This timelock was created with a pubkey that is not in the current wallet.\\n\\n'\
                                f'Solutions:\\n'\
                                f'1. Use the wallet that created this timelock\\n'\
                                f'2. Import the private key for this pubkey\\n'\
                                f'3. Restore wallet from the same seed'
                    }
                
                # Manual signing for P2SH CLTV inputs
                # Standard wallet.sign_transaction() won't work because P2SH address isn't in wallet
                self.log("[SWEEP] Performing manual signature for P2SH CLTV input...")
                
                keystore = self.wallet.get_keystore()
                if not keystore:
                    return {
                        'success': False,
                        'error': 'Cannot access wallet keystore for signing'
                    }
                
                # Sign each input manually
                from electrum.crypto import sha256d
                
                for i, txin in enumerate(tx.inputs()):
                    if txin.is_complete():
                        continue
                    
                    self.log(f"[SWEEP] Signing input {i} manually...")
                    
                    try:
                        # Get pre-image for signing
                        # For P2SH, we need to set the scriptcode to the redeem script
                        pre_image = tx.serialize_preimage(i)
                        
                        # Double SHA256 to get the message to sign
                        tx_hash = sha256d(pre_image)
                        self.log(f"[SWEEP] TX hash to sign: {tx_hash.hex()}")
                        
                        # Now we need to sign this hash with the private key for our pubkey
                        # Find which wallet address corresponds to this pubkey
                        sig = None
                        for addr_type in ['p2pkh', 'p2wpkh', 'p2wpkh-p2sh']:
                            try:
                                test_addr = pubkey_to_address(addr_type, pubkey_hex)
                                if self.wallet.is_mine(test_addr):
                                    self.log(f"[SWEEP] Wallet owns {addr_type}: {test_addr}")
                                    
                                    # Get address index to retrieve private key
                                    addr_index = self.wallet.get_address_index(test_addr)
                                    if addr_index:
                                        self.log(f"[SWEEP] Address index: {addr_index}")
                                        
                                        # Get the private key using the address index
                                        sequence = (addr_index[0], addr_index[1])  # (change, index)
                                        privkey_data = keystore.get_private_key(sequence, None)
                                        
                                        if privkey_data:
                                            # get_private_key returns (privkey_bytes, is_compressed)
                                            sec, is_compressed = privkey_data
                                            self.log(f"[SWEEP] Got private key, compressed={is_compressed}")
                                            
                                            # Sign the transaction using Electrum's sign_txin method
                                            # This returns the signature with SIGHASH byte already appended
                                            sig_with_sighash = tx.sign_txin(i, sec)
                                            
                                            self.log(f"[SWEEP] ✅ Generated signature ({len(sig_with_sighash)} bytes)")
                                            
                                            # Build scriptSig: <sig> <redeem_script>
                                            from electrum.bitcoin import push_script
                                            
                                            # Push signature and redeem script (both as bytes)
                                            script_sig_bytes = push_script(sig_with_sighash) + push_script(script_bytes)
                                            txin.script_sig = script_sig_bytes
                                            
                                            self.log(f"[SWEEP] ✅ Set scriptSig ({len(script_sig_bytes)} bytes)")
                                            sig = sig_with_sighash
                                            break
                            except Exception as e:
                                import traceback
                                self.log(f"[SWEEP] Attempt with {addr_type} failed: {e}")
                                self.log(f"[SWEEP] Traceback: {traceback.format_exc()}")
                                continue
                        
                        if not sig:
                            self.log("[SWEEP] ❌ Failed to generate signature")
                    except Exception as e:
                        import traceback
                        self.log(f"[SWEEP] ❌ Error signing input {i}: {e}")
                        self.log(f"[SWEEP] Traceback: {traceback.format_exc()}")
                
                if not tx.is_complete():
                    self.log("[SWEEP] ❌ Transaction still incomplete after manual signing")
                    return {
                        'success': False,
                        'error': f'Failed to sign transaction.\\n\\n'\
                                f'The wallet contains the pubkey but signing failed.\\n\\n'\
                                f'Pubkey: {pubkey_hex}\\n\\n'\
                                f'Found in wallet address: {found_address}\\n\\n'\
                                f'Check console logs for details.'\
                    }
                
                self.log("[SWEEP] Transaction signed successfully")
                
                # Log the fully signed transaction
                tx_hex = tx.serialize()
                self.log(f"[SWEEP] ✅ Signed transaction hex ({len(tx_hex)} chars):")
                self.log(f"[SWEEP] {tx_hex}")
                self.log(f"[SWEEP] Transaction is complete: {tx.is_complete()}")
                self.log(f"[SWEEP] Transaction size: {len(tx_hex)//2} bytes")
                
                return {
                    'success': True,
                    'tx': tx,
                    'address': address,
                    'receiving_address': receiving_address,
                    'output_value': output_value,
                    'fee': fee,
                    'utxos': len(utxos)
                }
                
            except Exception as e:
                import traceback
                self.log(f"[ERROR] Sweep failed: {e}")
                self.log(f"[ERROR] Traceback: {traceback.format_exc()}")
                return {
                    'success': False,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
        
        def on_success(result):
            """Called when background task completes"""
            if not result['success']:
                error_msg = result['error']
                if 'traceback' in result:
                    # Show traceback in console but not to user
                    self.log(f"[ERROR] Full traceback:\\n{result['traceback']}")
                
                # Restore button state if we have table_index
                if table_index is not None:
                    self.refresh_timelock_list()
                
                raise UserFacingException(error_msg)
            
            # Show confirmation with options
            tx = result['tx']
            
            # Analyze key status
            key_analysis = self.analyze_sweep_keys(redeem_script_hex, result['address'])
            
            # Build status message
            sig_status = "\n\n📝 Signature Status:\n"
            for i, key_info in enumerate(key_analysis['keys_status'], 1):
                pubkey_short = key_info['pubkey'][:16] + '...' + key_info['pubkey'][-8:]
                sig_status += f"  Key {i}: {pubkey_short}\n"
                sig_status += f"         {key_info['source']}\n"
                if key_info['wallet_address']:
                    sig_status += f"         From: {key_info['wallet_address']}\n"
            
            msg = (
                f"Ready to sweep {result['output_value']} sats to your wallet!\\n\\n"
                f"From: {result['address']}\\n"
                f"To: {result['receiving_address']}\\n"
                f"Amount: {result['output_value']} sats\\n"
                f"Fee: {result['fee']} sats\\n"
                f"UTXOs: {result['utxos']}"
                f"{sig_status}\\n"
                f"Transaction complete: {'Yes ✅' if tx.is_complete() else 'No (partial) ⚠️'}\\n\\n"
                f"Choose action:"
            )
            
            self.log(f"[SWEEP] Showing action dialog...")
            
            # Create custom dialog with multiple buttons
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Sweep Transaction Ready")
            msg_box.setText(msg)
            msg_box.setIcon(QMessageBox.Icon.Question)
            
            broadcast_btn = msg_box.addButton("Broadcast Now", QMessageBox.ButtonRole.AcceptRole)
            psbt_btn = msg_box.addButton("Show PSBT", QMessageBox.ButtonRole.ActionRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == psbt_btn:
                # Show PSBT export dialog
                self.show_psbt_dialog(tx, key_analysis, result)
                return
            elif clicked_button != broadcast_btn:
                self.log("[SWEEP] User cancelled")
                if table_index is not None:
                    self.refresh_timelock_list()
                return
            
            response = QMessageBox.StandardButton.Yes  # Treat broadcast button as Yes
            
            if response == QMessageBox.StandardButton.Yes:
                self.log("[SWEEP] User confirmed broadcast, starting broadcast process...")
                # Broadcast in another waiting dialog
                def broadcast():
                    self.log("[SWEEP] Inside broadcast task...")
                    network = self.window.network
                    self.log(f"[SWEEP] Network: {network}")
                    txid = network.run_from_another_thread(network.broadcast_transaction(tx))
                    self.log(f"[SWEEP] ✅ Broadcast successful! TXID: {txid}")
                    return {'txid': txid}
                
                def on_broadcast_success(broadcast_result):
                    txid = broadcast_result['txid']
                    self.log(f"[SWEEP] 🎉 Broadcast complete, showing success dialog for {txid}")
                    QMessageBox.information(
                        self,
                        "Success! 🎉",
                        f"Transaction broadcast successfully!\\n\\n"
                        f"TXID:\\n{txid}\\n\\n"
                        f"Funds will appear in your wallet after confirmation.\\n\\n"
                        f"View on explorer:\\n"
                        f"https://mempool.space/signet/tx/{txid}"
                    )
                    
                    # Clear cache for this address and refresh the list
                    if table_index is not None:
                        # Invalidate cache for swept address
                        if result.get('address') in self.utxo_cache:
                            del self.utxo_cache[result['address']]
                        self.refresh_timelock_list()
                
                self.log("[SWEEP] Creating WaitingDialog for broadcast...")
                WaitingDialog(
                    parent=self,
                    message="Broadcasting transaction...",
                    task=broadcast,
                    on_success=on_broadcast_success
                )
            else:
                self.log("[SWEEP] User declined broadcast")
                # Restore button state if declined
                if table_index is not None:
                    self.refresh_timelock_list()
        
        # Show waiting dialog
        WaitingDialog(
            parent=self,
            message="Querying network and building sweep transaction...\\nThis may take a few seconds.",
            task=do_sweep_work,
            on_success=on_success
        )


class Plugin(BasePlugin):
    """CHECKLOCKTIMEVERIFY Plugin"""
    
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.windows = []
        
        # Load configuration
        self.default_locktime_blocks = config.get('cltv_default_locktime_blocks', 144)
        self.fee_rate = config.get('cltv_fee_rate_sat_vb', 2)
        self.auto_save = config.get('cltv_auto_save', True)
    
    def requires_settings(self):
        """Enable settings button in plugin dialog"""
        return True
    
    def settings_widget(self, window):
        """Settings UI for the plugin"""
        from PyQt6.QtWidgets import QWidget, QFormLayout, QLabel, QSpinBox, QCheckBox
        
        widget = QWidget()
        layout = QFormLayout()
        
        # Default locktime (blocks ahead)
        locktime_spin = QSpinBox()
        locktime_spin.setRange(1, 10000)
        locktime_spin.setValue(self.default_locktime_blocks)
        locktime_spin.setToolTip("Default number of blocks to add when creating timelock")
        locktime_spin.valueChanged.connect(
            lambda v: self.config.set_key('cltv_default_locktime_blocks', v)
        )
        layout.addRow("Default locktime offset (blocks):", locktime_spin)
        
        # Fee rate
        fee_spin = QSpinBox()
        fee_spin.setRange(1, 1000)
        fee_spin.setValue(self.fee_rate)
        fee_spin.setToolTip("Default fee rate for sweep transactions")
        fee_spin.valueChanged.connect(
            lambda v: self.config.set_key('cltv_fee_rate_sat_vb', v)
        )
        layout.addRow("Default fee rate (sat/vB):", fee_spin)
        
        # Auto-save
        auto_save_cb = QCheckBox()
        auto_save_cb.setChecked(self.auto_save)
        auto_save_cb.setToolTip("Automatically save timelock data for future sweeps")
        auto_save_cb.toggled.connect(
            lambda checked: self.config.set_key('cltv_auto_save', checked)
        )
        layout.addRow("Auto-save timelock data:", auto_save_cb)
        
        # Info label
        info = QLabel(
            "Settings are saved in your Electrum config file.\n"
            "Changes take effect immediately."
        )
        info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        info.setWordWrap(True)
        layout.addRow("", info)
        
        widget.setLayout(layout)
        return widget
        
    @hook
    def load_wallet(self, wallet, window):
        """Called when a wallet is loaded - add menu item"""
        if window not in self.windows:
            self.windows.append(window)
            self.add_menu_item(window)
            
    @hook  
    def close_wallet(self, wallet):
        """Called when wallet is closed"""
        # Clean up if needed
        pass
        
    def add_menu_item(self, window):
        """Add BIP-65 CLTV Examples menu item to Tools menu"""
        try:
            # Add to Tools menu
            menu = window.tools_menu
            action = menu.addAction("BIP-65 CLTV Examples...")
            action.triggered.connect(lambda: self.show_timelock_dialog(window))
        except Exception as e:
            print(f"[CLTV Plugin] Error adding menu item: {e}")
            
    def show_timelock_dialog(self, window):
        """Show the timelock address generator dialog"""
        # Switch to console tab for better UX (user can see logs/debug info)
        try:
            if hasattr(window, 'tabs') and window.tabs:
                console_index = -1
                for i in range(window.tabs.count()):
                    if 'console' in window.tabs.tabText(i).lower():
                        console_index = i
                        break
                if console_index >= 0:
                    window.tabs.setCurrentIndex(console_index)
        except Exception as e:
            # If switching tabs fails, just continue - not critical
            pass
        
        dialog = TimelockDialog(window, self)
        dialog.exec()


