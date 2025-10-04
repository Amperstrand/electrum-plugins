"""
CHECKLOCKTIMEVERIFY Plugin for Electrum
Based on BIP-65: https://github.com/bitcoin/bips/blob/master/bip-0065.mediawiki

This plugin creates time-locked Bitcoin addresses using OP_CHECKLOCKTIMEVERIFY.
Funds sent to these addresses can only be spent after a specified block height or timestamp.

⚠️  DISCLAIMER ⚠️
This is a SIGNET-PRODUCTION level quality proof of concept!
Development sponsored by Vibes Capital Management with real signet coins.

It is NOT suitable for mainnet usage.
DO NOT use this plugin on Bitcoin mainnet with real funds.
Testing on signet/testnet only!

Sponsored by: Vibes Capital Management 🚀
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
from electrum.bitcoin import hash160_to_p2sh
from electrum import bitcoin, constants
from electrum.transaction import Transaction, PartialTxInput, PartialTxOutput, PartialTransaction

# Setup logger
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
            self.log("[ERROR] This plugin is SIGNET-PRODUCTION quality only!")
            self.log("[ERROR] Development sponsored by Vibes Capital Management with real signet coins")
            self.log("[ERROR] DO NOT USE ON MAINNET!")
            QMessageBox.critical(
                parent,
                "🚨 MAINNET NOT SUPPORTED 🚨",
                "This CHECKLOCKTIMEVERIFY plugin is a proof of concept!\n\n"
                "⚠️  SIGNET-PRODUCTION quality ⚠️\n\n"
                "It is NOT suitable for mainnet usage with real Bitcoin!\n\n"
                "Please restart Electrum with --testnet or --signet\n\n"
                "Development sponsored by Vibes Capital Management with real signet coins 🚀"
            )
            raise RuntimeError("CLTV Plugin cannot run on mainnet")
        
        self.setWindowTitle("Create Timelocked Address (CHECKLOCKTIMEVERIFY) [SIGNET-PRODUCTION]")
        self.setMinimumWidth(900)
        self.setMinimumHeight(800)
        self.resize(950, 900)
        
        # Storage file for timelock data
        wallet_dir = os.path.dirname(self.wallet.storage.path)
        self.storage_file = os.path.join(wallet_dir, 'cltv_timelock_data.json')
        self.log(f"[INIT] CLTV Plugin initialized")
        self.log(f"[INIT] Storage file: {self.storage_file}")
        
        self.setup_ui()
        
        # Auto-load keys after UI is fully constructed
        self.auto_load_keys()
    
    def log(self, message: str):
        """Log message to console"""
        msg = f"[CLTV Plugin] {message}"
        logger.info(msg)
        print(msg)  # Also print to stdout for visibility
    
    def save_timelock_data(self, data: Dict):
        """Save timelock data to JSON file"""
        try:
            # Load existing data
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    all_data = json.load(f)
            else:
                all_data = []
            
            # Add new entry
            all_data.append(data)
            
            # Save
            with open(self.storage_file, 'w') as f:
                json.dump(all_data, f, indent=2)
            
            self.log(f"[STORAGE] Saved timelock data to {self.storage_file}")
            self.log(f"[STORAGE] Entry: {data['address']}")
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
        title = QLabel("🔒 CHECKLOCKTIMEVERIFY Timelock Generator")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        desc = QLabel(
            "Create a Bitcoin address that can only be spent after a specific time.\n"
            "Based on BIP-65 OP_CHECKLOCKTIMEVERIFY opcode."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # Tab widget for script types
        self.tabs = QTabWidget()
        
        # Tab 1: Simple Timelock
        simple_tab = self.create_simple_timelock_tab()
        self.tabs.addTab(simple_tab, "Simple Timelock")
        
        # Tab 2: Escrow with Timelock
        escrow_tab = self.create_escrow_tab()
        self.tabs.addTab(escrow_tab, "Escrow with Timelock Fallback")
        
        # Tab 3: Sweep Funds
        sweep_tab = self.create_sweep_tab()
        self.tabs.addTab(sweep_tab, "Sweep Locked Funds")
        
        layout.addWidget(self.tabs)
        
        # Result area (shared by both tabs)
        result_group = QGroupBox("Generated Address & Script")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(350)
        self.result_text.setMaximumHeight(500)
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
        
        # Description
        desc = QLabel(
            "Simple single-key timelock. Script: <locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG\n"
            "Only the owner can spend, but only after the locktime expires."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # Locktime type selection
        locktime_group = QGroupBox("Locktime Type")
        locktime_layout = QVBoxLayout()
        
        self.simple_locktime_group = QButtonGroup()
        self.simple_block_radio = QRadioButton("Block Height")
        self.simple_time_radio = QRadioButton("Date && Time (Timestamp)")
        self.simple_block_radio.setChecked(True)
        
        self.simple_locktime_group.addButton(self.simple_block_radio, 0)
        self.simple_locktime_group.addButton(self.simple_time_radio, 1)
        
        locktime_layout.addWidget(self.simple_block_radio)
        locktime_layout.addWidget(self.simple_time_radio)
        
        locktime_group.setLayout(locktime_layout)
        layout.addWidget(locktime_group)
        
        # Block height input
        self.simple_block_group = QGroupBox("Block Height")
        block_layout = QFormLayout()
        self.simple_block_input = QSpinBox()
        self.simple_block_input.setRange(0, 99999999)
        
        # Default to current height + 2 blocks for testing
        network = self.window.network if hasattr(self.window, 'network') else None
        current_height = network.get_local_height() if network else 0
        default_locktime = current_height + 2 if current_height > 0 else 870000
        self.simple_block_input.setValue(default_locktime)
        self.simple_block_input.setMinimumWidth(200)
        block_layout.addRow("Block Height:", self.simple_block_input)
        
        current_info = QLabel(f"Current block height: {current_height} (locktime = current + 2)")
        current_info.setStyleSheet("QLabel { color: gray; font-size: 10pt; }")
        block_layout.addRow("", current_info)
        
        self.simple_block_group.setLayout(block_layout)
        layout.addWidget(self.simple_block_group)
        
        # Timestamp input
        self.simple_time_group = QGroupBox("Date && Time")
        time_layout = QFormLayout()
        self.simple_time_input = QDateTimeEdit()
        self.simple_time_input.setDateTime(QDateTime.currentDateTime().addDays(30))
        self.simple_time_input.setCalendarPopup(True)
        self.simple_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.simple_time_input.setMinimumWidth(250)
        time_layout.addRow("Unlock Date/Time:", self.simple_time_input)
        
        self.simple_time_group.setLayout(time_layout)
        self.simple_time_group.hide()
        layout.addWidget(self.simple_time_group)
        
        # Toggle visibility based on radio selection
        self.simple_block_radio.toggled.connect(
            lambda checked: self.simple_block_group.setVisible(checked)
        )
        self.simple_time_radio.toggled.connect(
            lambda checked: self.simple_time_group.setVisible(checked)
        )
        
        # Public key input
        key_group = QGroupBox("Public Key (Auto-selected from Wallet)")
        key_layout = QFormLayout()
        self.simple_pubkey_input = QLineEdit()
        self.simple_pubkey_input.setReadOnly(True)
        self.simple_pubkey_input.setPlaceholderText("Loading key from wallet...")
        self.simple_pubkey_input.setMinimumWidth(550)
        self.simple_pubkey_input.setFont(QFont("Courier", 10))
        key_layout.addRow("Public Key:", self.simple_pubkey_input)
        
        self.simple_key_info = QLabel("")
        self.simple_key_info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        self.simple_key_info.setWordWrap(True)
        key_layout.addRow("", self.simple_key_info)
        
        get_key_btn = QPushButton("Select Different Key from Wallet")
        get_key_btn.clicked.connect(lambda: self.get_wallet_pubkey(self.simple_pubkey_input, self.simple_key_info))
        key_layout.addRow("", get_key_btn)
        
        key_group.setLayout(key_layout)
        layout.addWidget(key_group)
        
        # Generate button
        gen_btn = QPushButton("Generate Simple Timelock Address")
        gen_btn.clicked.connect(self.generate_simple_timelock)
        layout.addWidget(gen_btn)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
        
    def create_escrow_tab(self):
        """Create tab for escrow script with timelock fallback"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Description
        desc = QLabel(
            "Escrow with timelock fallback (BIP-65 example):\n"
            "• Normal case: Requires 2-of-2 multisig (both parties)\n"
            "• After timeout: Third party (escrow agent) + either party can spend\n\n"
            "Script: IF <locktime> CLTV DROP <escrow_pubkey> CHECKSIGVERIFY 1 ELSE 2 ENDIF "
            "<pubkey1> <pubkey2> 2 CHECKMULTISIG"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        layout.addWidget(desc)
        
        layout.addSpacing(10)
        
        # Locktime type selection
        locktime_group = QGroupBox("Locktime Type")
        locktime_layout = QVBoxLayout()
        
        self.escrow_locktime_group = QButtonGroup()
        self.escrow_block_radio = QRadioButton("Block Height")
        self.escrow_time_radio = QRadioButton("Date && Time (Timestamp)")
        self.escrow_block_radio.setChecked(True)
        
        self.escrow_locktime_group.addButton(self.escrow_block_radio, 0)
        self.escrow_locktime_group.addButton(self.escrow_time_radio, 1)
        
        locktime_layout.addWidget(self.escrow_block_radio)
        locktime_layout.addWidget(self.escrow_time_radio)
        
        locktime_group.setLayout(locktime_layout)
        layout.addWidget(locktime_group)
        
        # Block height input
        self.escrow_block_group = QGroupBox("Block Height")
        block_layout = QFormLayout()
        self.escrow_block_input = QSpinBox()
        self.escrow_block_input.setRange(0, 99999999)
        self.escrow_block_input.setValue(870000)
        self.escrow_block_input.setMinimumWidth(200)
        block_layout.addRow("Block Height:", self.escrow_block_input)
        self.escrow_block_group.setLayout(block_layout)
        layout.addWidget(self.escrow_block_group)
        
        # Timestamp input
        self.escrow_time_group = QGroupBox("Date && Time")
        time_layout = QFormLayout()
        self.escrow_time_input = QDateTimeEdit()
        self.escrow_time_input.setDateTime(QDateTime.currentDateTime().addMonths(3))
        self.escrow_time_input.setCalendarPopup(True)
        self.escrow_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.escrow_time_input.setMinimumWidth(250)
        time_layout.addRow("Unlock Date/Time:", self.escrow_time_input)
        self.escrow_time_group.setLayout(time_layout)
        self.escrow_time_group.hide()
        layout.addWidget(self.escrow_time_group)
        
        # Toggle visibility
        self.escrow_block_radio.toggled.connect(
            lambda checked: self.escrow_block_group.setVisible(checked)
        )
        self.escrow_time_radio.toggled.connect(
            lambda checked: self.escrow_time_group.setVisible(checked)
        )
        
        # Public keys
        keys_group = QGroupBox("Public Keys (Auto-selected from Wallet)")
        keys_layout = QFormLayout()
        
        self.escrow_party1_input = QLineEdit()
        self.escrow_party1_input.setReadOnly(True)
        self.escrow_party1_input.setPlaceholderText("Loading party 1 key...")
        self.escrow_party1_input.setMinimumWidth(550)
        self.escrow_party1_input.setFont(QFont("Courier", 10))
        keys_layout.addRow("Party 1 Pubkey:", self.escrow_party1_input)
        self.escrow_party1_info = QLabel("")
        self.escrow_party1_info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        keys_layout.addRow("", self.escrow_party1_info)
        
        self.escrow_party2_input = QLineEdit()
        self.escrow_party2_input.setReadOnly(True)
        self.escrow_party2_input.setPlaceholderText("Loading party 2 key...")
        self.escrow_party2_input.setMinimumWidth(550)
        self.escrow_party2_input.setFont(QFont("Courier", 10))
        keys_layout.addRow("Party 2 Pubkey:", self.escrow_party2_input)
        self.escrow_party2_info = QLabel("")
        self.escrow_party2_info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        keys_layout.addRow("", self.escrow_party2_info)
        
        self.escrow_agent_input = QLineEdit()
        self.escrow_agent_input.setReadOnly(True)
        self.escrow_agent_input.setPlaceholderText("Loading escrow agent key...")
        self.escrow_agent_input.setMinimumWidth(550)
        self.escrow_agent_input.setFont(QFont("Courier", 10))
        keys_layout.addRow("Escrow Agent Pubkey:", self.escrow_agent_input)
        self.escrow_agent_info = QLabel("")
        self.escrow_agent_info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        keys_layout.addRow("", self.escrow_agent_info)
        
        refresh_keys_btn = QPushButton("Refresh Keys from Wallet")
        refresh_keys_btn.clicked.connect(self.load_escrow_keys)
        keys_layout.addRow("", refresh_keys_btn)
        
        keys_group.setLayout(keys_layout)
        layout.addWidget(keys_group)
        
        # Generate button
        gen_btn = QPushButton("Generate Escrow Address with Timelock")
        gen_btn.clicked.connect(self.generate_escrow_timelock)
        layout.addWidget(gen_btn)
        
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
        list_group = QGroupBox("Your Timelocked Addresses")
        list_layout = QVBoxLayout()
        
        self.timelock_table = QTableWidget()
        self.timelock_table.setColumnCount(6)
        self.timelock_table.setHorizontalHeaderLabels([
            "Address", "Locktime", "Type", "Status", "Balance", "Action"
        ])
        self.timelock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.timelock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        list_layout.addWidget(self.timelock_table)
        
        refresh_btn = QPushButton("Refresh List")
        refresh_btn.clicked.connect(self.refresh_timelock_list)
        list_layout.addWidget(refresh_btn)
        
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
        """Load 3 different keys from wallet for escrow script"""
        try:
            # Get 3 different receiving addresses
            addresses = []
            for i in range(10):  # Try to get unused addresses
                addr = self.wallet.get_receiving_address()
                if addr and addr not in addresses:
                    addresses.append(addr)
                if len(addresses) >= 3:
                    break
            
            if len(addresses) < 3:
                QMessageBox.warning(self, "Error", 
                    f"Could only get {len(addresses)} addresses from wallet. Need 3 for escrow.")
                return
            
            # Party 1
            pubkey1 = self.wallet.get_public_key(addresses[0])
            if pubkey1:
                self.escrow_party1_input.setText(pubkey1)
                self.escrow_party1_info.setText(f"Address: {addresses[0]}")
            
            # Party 2
            pubkey2 = self.wallet.get_public_key(addresses[1])
            if pubkey2:
                self.escrow_party2_input.setText(pubkey2)
                self.escrow_party2_info.setText(f"Address: {addresses[1]}")
            
            # Escrow Agent
            pubkey3 = self.wallet.get_public_key(addresses[2])
            if pubkey3:
                self.escrow_agent_input.setText(pubkey3)
                self.escrow_agent_info.setText(f"Address: {addresses[2]}")
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error loading escrow keys: {str(e)}")
    
    def auto_load_keys(self):
        """Auto-load wallet keys after dialog is fully constructed"""
        try:
            # Load simple tab key
            self.get_wallet_pubkey(self.simple_pubkey_input, self.simple_key_info)
            # Load escrow tab keys
            self.load_escrow_keys()
        except Exception as e:
            # Silently fail - user can click refresh if needed
            print(f"[CLTV Plugin] Auto-load keys failed: {e}")
            
    def generate_simple_timelock(self):
        """Generate simple timelock address: <locktime> CLTV DROP <pubkey> CHECKSIG"""
        try:
            self.log("[GENERATE] Starting simple timelock address generation")
            
            # Get locktime value
            if self.simple_block_radio.isChecked():
                locktime = self.simple_block_input.value()
                locktime_type = "block height"
                locktime_display = str(locktime)
                self.log(f"[GENERATE] Locktime type: Block height = {locktime}")
            else:
                dt = self.simple_time_input.dateTime().toPyDateTime()
                locktime = int(dt.timestamp())
                locktime_type = "timestamp"
                locktime_display = f"{locktime} ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
                self.log(f"[GENERATE] Locktime type: Timestamp = {locktime} ({dt})")
                
            # Validate locktime
            if locktime < 0:
                self.log("[ERROR] Locktime cannot be negative")
                QMessageBox.warning(self, "Error", "Locktime cannot be negative")
                return
                
            # Get public key
            pubkey_hex = self.simple_pubkey_input.text().strip()
            if not pubkey_hex:
                self.log("[ERROR] No public key provided")
                QMessageBox.warning(self, "Error", "Please provide a public key")
                return
            
            self.log(f"[GENERATE] Public key: {pubkey_hex}")
                
            # Validate pubkey format
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
                if len(pubkey_bytes) not in (33, 65):
                    raise ValueError("Invalid pubkey length")
                self.log(f"[GENERATE] Pubkey validated: {len(pubkey_bytes)} bytes ({'compressed' if len(pubkey_bytes) == 33 else 'uncompressed'})")
            except Exception as e:
                self.log(f"[ERROR] Invalid pubkey format: {e}")
                QMessageBox.warning(self, "Error", f"Invalid public key format: {str(e)}")
                return
                
            # Build the script: <locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG
            self.log("[GENERATE] Building CLTV script: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG")
            script = self.build_simple_cltv_script(locktime, pubkey_hex)
            self.log(f"[GENERATE] Script built: {script}")
            self.log(f"[GENERATE] Script size: {len(bytes.fromhex(script))} bytes")
            
            # Create P2SH address
            self.log("[GENERATE] Creating P2SH address from script hash")
            address = self.script_to_p2sh_address(script)
            self.log(f"[GENERATE] ✓ P2SH Address generated: {address}")
            
            # Save to storage
            timelock_data = {
                "address": address,
                "script_hex": script,
                "locktime": locktime,
                "locktime_type": locktime_type,
                "pubkey": pubkey_hex,
                "script_type": "simple",
                "created": datetime.now().isoformat()
            }
            self.save_timelock_data(timelock_data)
            self.log("[GENERATE] Timelock data saved for future sweeping")
            
            # Generate technical details
            miniscript = f"and_v(v:after({locktime}),pk({pubkey_hex[:16]}...))"
            
            witness_stack = f"""To spend this P2SH output, you need:

1. scriptSig format:
   <signature> <serialized_redeem_script>

2. Witness stack (when spending):
   - Push signature for pubkey
   - Push the redeem script ({len(bytes.fromhex(script))} bytes)

3. Transaction requirements:
   - nSequence must be set appropriately for CLTV
   - nLockTime in transaction must be >= {locktime}
   
4. Bitcoin Script execution:
   [signature] [redeem_script] → OP_HASH160 [script_hash] OP_EQUAL
   Then executes redeem script:
   [signature] → {locktime} CLTV DROP {pubkey_hex[:16]}... CHECKSIG"""
            
            # Display results
            self.display_results(
                address=address,
                script_hex=script,
                script_type="Simple Timelock",
                locktime=locktime_display,
                locktime_type=locktime_type,
                details=f"✓ Spendable by pubkey {pubkey_hex[:16]}... after {locktime_display}",
                miniscript=miniscript,
                witness_stack=witness_stack
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate address: {str(e)}")
            import traceback
            traceback.print_exc()
            
    def generate_escrow_timelock(self):
        """Generate escrow timelock address"""
        try:
            # Get locktime value
            if self.escrow_block_radio.isChecked():
                locktime = self.escrow_block_input.value()
                locktime_type = "block height"
                locktime_display = str(locktime)
            else:
                dt = self.escrow_time_input.dateTime().toPyDateTime()
                locktime = int(dt.timestamp())
                locktime_type = "timestamp"
                locktime_display = f"{locktime} ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
                
            # Get public keys
            party1_hex = self.escrow_party1_input.text().strip()
            party2_hex = self.escrow_party2_input.text().strip()
            agent_hex = self.escrow_agent_input.text().strip()
            
            if not all([party1_hex, party2_hex, agent_hex]):
                QMessageBox.warning(self, "Error", "Please provide all three public keys")
                return
                
            # Validate pubkeys
            for pubkey_hex in [party1_hex, party2_hex, agent_hex]:
                try:
                    pubkey_bytes = bytes.fromhex(pubkey_hex)
                    if len(pubkey_bytes) not in (33, 65):
                        raise ValueError("Invalid pubkey length")
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Invalid public key format: {str(e)}")
                    return
                    
            # Build the escrow script
            script = self.build_escrow_cltv_script(locktime, agent_hex, party1_hex, party2_hex)
            
            # Create P2SH address
            address = self.script_to_p2sh_address(script)
            
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
                script_type="Escrow with Timelock Fallback",
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
            
    def build_simple_cltv_script(self, locktime: int, pubkey_hex: str) -> str:
        """
        Build simple CLTV script: <locktime> CHECKLOCKTIMEVERIFY DROP <pubkey> CHECKSIG
        
        Returns hex string of the script
        """
        from electrum.transaction import opcodes
        
        self.log("[SCRIPT] Building simple CLTV script step-by-step:")
        
        script_bytes = bytearray()
        
        # Push locktime value
        self.log(f"[SCRIPT] Step 1: Push locktime value {locktime}")
        locktime_push = self.push_int(locktime)
        self.log(f"[SCRIPT]   Encoded as: {locktime_push.hex()}")
        script_bytes.extend(locktime_push)
        
        # OP_CHECKLOCKTIMEVERIFY (0xb1)
        self.log(f"[SCRIPT] Step 2: Add OP_CHECKLOCKTIMEVERIFY (0xb1)")
        script_bytes.append(opcodes.OP_CHECKLOCKTIMEVERIFY)
        
        # OP_DROP (0x75) - remove locktime from stack
        self.log(f"[SCRIPT] Step 3: Add OP_DROP (0x75) - removes locktime from stack")
        script_bytes.append(opcodes.OP_DROP)
        
        # Push public key
        self.log(f"[SCRIPT] Step 4: Push public key ({len(bytes.fromhex(pubkey_hex))} bytes)")
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        pubkey_push = self.push_bytes(pubkey_bytes)
        self.log(f"[SCRIPT]   Push opcode: 0x{pubkey_push[0]:02x}")
        script_bytes.extend(pubkey_push)
        
        # OP_CHECKSIG (0xac)
        self.log(f"[SCRIPT] Step 5: Add OP_CHECKSIG (0xac)")
        script_bytes.append(opcodes.OP_CHECKSIG)
        
        self.log(f"[SCRIPT] ✓ Script construction complete: {len(script_bytes)} bytes")
        
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

📍 P2SH ADDRESS (send funds here):
{address}

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
        
        self.result_text.setText(result)
        self.current_address = address
        self.current_script = script_hex
        self.copy_address_btn.setEnabled(True)
        self.copy_script_btn.setEnabled(True)
        
    def copy_address(self):
        """Copy address to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.current_address)
        QMessageBox.information(self, "Copied", f"Address copied to clipboard:\n{self.current_address}")
        
    def copy_script(self):
        """Copy redeem script to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.current_script)
        QMessageBox.information(self, "Copied", "Redeem script copied to clipboard")
    
    def refresh_timelock_list(self):
        """Refresh the list of timelocked addresses"""
        self.log("[SWEEP] Refreshing timelock list")
        
        # Load saved timelocks
        timelocks = self.load_timelock_data()
        
        # Clear table
        self.timelock_table.setRowCount(0)
        
        # TODO: Get current block height from network
        # For now, use a placeholder
        current_block = 210000  # Signet approximate
        
        for i, lock in enumerate(timelocks):
            self.timelock_table.insertRow(i)
            
            # Address
            self.timelock_table.setItem(i, 0, QTableWidgetItem(lock['address']))
            
            # Locktime
            locktime_str = str(lock['locktime'])
            if lock['locktime_type'] == 'timestamp':
                dt = datetime.fromtimestamp(lock['locktime'])
                locktime_str += f" ({dt.strftime('%Y-%m-%d')})"
            self.timelock_table.setItem(i, 1, QTableWidgetItem(locktime_str))
            
            # Type
            self.timelock_table.setItem(i, 2, QTableWidgetItem(lock['locktime_type']))
            
            # Status
            status = "Locked"
            if lock['locktime_type'] == 'block height' and current_block >= lock['locktime']:
                status = "Unlocked ✓"
            elif lock['locktime_type'] == 'timestamp' and time.time() >= lock['locktime']:
                status = "Unlocked ✓"
            self.timelock_table.setItem(i, 3, QTableWidgetItem(status))
            
            # Balance (TODO: query blockchain)
            self.timelock_table.setItem(i, 4, QTableWidgetItem("Check explorer"))
            
            # Action button
            sweep_btn = QPushButton("Sweep")
            sweep_btn.clicked.connect(lambda checked, idx=i: self.sweep_timelock(idx))
            self.timelock_table.setCellWidget(i, 5, sweep_btn)
        
        self.log(f"[SWEEP] Loaded {len(timelocks)} timelock entries")
    
    def sweep_timelock(self, index: int):
        """Sweep a specific timelock entry"""
        timelocks = self.load_timelock_data()
        if index >= len(timelocks):
            return
        
        lock = timelocks[index]
        self.log(f"[SWEEP] Attempting to sweep {lock['address']}")
        
        # Perform sweep
        self.perform_sweep(lock['script_hex'], lock['locktime'], lock.get('pubkey'))
    
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
    
    def perform_sweep(self, redeem_script_hex: str, locktime: int, pubkey: Optional[str]):
        """Perform the actual sweep transaction"""
        self.log("[SWEEP] ======== STARTING SWEEP PROCESS ========")
        self.log(f"[SWEEP] Redeem script: {redeem_script_hex}")
        self.log(f"[SWEEP] Locktime: {locktime}")
        
        try:
            # Calculate P2SH address
            from electrum.bitcoin import hash_160
            from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput
            
            script_bytes = bytes.fromhex(redeem_script_hex)
            script_hash = hash_160(script_bytes)
            address = hash160_to_p2sh(script_hash)
            self.log(f"[SWEEP] P2SH address: {address}")
            
            # Check current block height
            network = self.window.network if hasattr(self.window, 'network') else None
            current_height = network.get_local_height() if network else 0
            self.log(f"[SWEEP] Current block height: {current_height}")
            self.log(f"[SWEEP] Locktime required: {locktime}")
            
            if current_height < locktime:
                QMessageBox.warning(
                    self,
                    "Cannot Sweep Yet",
                    f"Locktime not reached!\\n\\n"
                    f"Current block: {current_height}\\n"
                    f"Locktime: {locktime}\\n"
                    f"Blocks remaining: {locktime - current_height}\\n\\n"
                    f"Wait approximately {(locktime - current_height) * 10} minutes."
                )
                return
            
            # Get coins (UTXOs) at this address
            self.log(f"[SWEEP] Querying network for UTXOs at {address}...")
            
            # Query network for UTXOs using scripthash
            sh = bitcoin.address_to_scripthash(address)
            self.log(f"[SWEEP] Script hash: {sh}")
            
            # Get UTXOs from network
            utxos = network.run_from_another_thread(network.listunspent_for_scripthash(sh))
            
            self.log(f"[SWEEP] Raw UTXO response from network:")
            self.log(f"[SWEEP]   Type: {type(utxos)}")
            self.log(f"[SWEEP]   Length: {len(utxos) if utxos else 0}")
            
            if not utxos:
                self.log(f"[SWEEP] No UTXOs found at {address}")
                QMessageBox.warning(
                    self,
                    "No Funds Found",
                    f"No UTXOs found at address:\n{address}\n\n"
                    f"Make sure:\n"
                    f"1. The address has been funded\n"
                    f"2. The transaction is confirmed\n"
                    f"3. Electrum is synced (check bottom status bar)\n\n"
                    f"Script hash: {sh}\n\n"
                    f"Check on block explorer:\n"
                    f"https://mempool.space/signet/address/{address}"
                )
                return
            
            self.log(f"[SWEEP] Found {len(utxos)} UTXO(s) from network")
            
            # Build detailed message for UI
            utxo_details = f"Found {len(utxos)} UTXO(s) at {address}:\n\n"
            for i, utxo in enumerate(utxos):
                self.log(f"[SWEEP] UTXO #{i+1}:")
                self.log(f"[SWEEP]   tx_hash: {utxo.get('tx_hash', 'N/A')}")
                self.log(f"[SWEEP]   tx_pos: {utxo.get('tx_pos', 'N/A')}")
                self.log(f"[SWEEP]   value: {utxo.get('value', 'N/A')} sats")
                self.log(f"[SWEEP]   height: {utxo.get('height', 'N/A')}")
                self.log(f"[SWEEP]   All keys: {list(utxo.keys())}")
                
                # Add to UI message
                utxo_details += f"UTXO #{i+1}:\n"
                utxo_details += f"  TX: {utxo.get('tx_hash', 'N/A')[:16]}...\n"
                utxo_details += f"  Vout: {utxo.get('tx_pos', 'N/A')}\n"
                utxo_details += f"  Value: {utxo.get('value', 0)} sats\n"
                utxo_details += f"  Height: {utxo.get('height', 'unconfirmed')}\n\n"
            
            # Show UTXO details in message box
            result = QMessageBox.information(
                self,
                "UTXOs Found",
                utxo_details + f"\nTotal UTXOs: {len(utxos)}\n\nContinue with sweep?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                self.log("[SWEEP] User cancelled after seeing UTXOs")
                return
            
            # Filter for confirmed UTXOs only
            confirmed_utxos = [u for u in utxos if u.get('height', 0) > 0]
            self.log(f"[SWEEP] Confirmed UTXOs: {len(confirmed_utxos)}")
            
            if not confirmed_utxos:
                QMessageBox.warning(
                    self,
                    "No Confirmed UTXOs",
                    f"Found {len(utxos)} UTXO(s) but none are confirmed yet.\n\n"
                    f"Wait for confirmations and try again."
                )
                return
            
            # Use only confirmed UTXOs
            utxos = confirmed_utxos
            
            self.log(f"[SWEEP] Found {len(utxos)} UTXO(s)")
            for utxo in utxos:
                self.log(f"[SWEEP]   {utxo['tx_hash']}:{utxo['tx_pos']} = {utxo['value']} sats")
            
            # Calculate total input value
            total_input = sum(utxo['value'] for utxo in utxos)
            self.log(f"[SWEEP] Total input value: {total_input} sats")
            
            # Get destination address from wallet
            receiving_address = self.wallet.get_receiving_address()
            self.log(f"[SWEEP] Destination address: {receiving_address}")
            
            # Estimate fee (2 sat/vbyte for signet)
            estimated_size = 10 + (len(utxos) * 180) + 34
            fee = estimated_size * 2
            output_value = total_input - fee
            
            self.log(f"[SWEEP] Estimated size: {estimated_size} vbytes")
            self.log(f"[SWEEP] Fee: {fee} sats (2 sat/vbyte)")
            self.log(f"[SWEEP] Output value: {output_value} sats")
            
            if output_value <= 0:
                QMessageBox.warning(self, "Error", f"Insufficient funds\nInput: {total_input}, Fee: {fee}")
                return
            
            # Create transaction inputs from UTXOs
            self.log("[SWEEP] Building transaction...")
            from electrum.transaction import TxOutpoint
            
            inputs = []
            for utxo in utxos:
                txin = PartialTxInput(
                    prevout=TxOutpoint(txid=bytes.fromhex(utxo['tx_hash']), out_idx=utxo['tx_pos']),
                    nsequence=0xfffffffe  # Required for CLTV
                )
                txin.script_type = 'p2sh'
                txin.redeem_script = script_bytes
                txin._trusted_value_sats = utxo['value']
                inputs.append(txin)
                self.log(f"[SWEEP] Added input: {utxo['tx_hash']}:{utxo['tx_pos']}, nSequence=0xfffffffe")
            
            # Create output
            outputs = [PartialTxOutput.from_address_and_value(receiving_address, output_value)]
            
            # Build transaction
            tx = PartialTransaction.from_io(inputs, outputs, locktime=locktime)
            
            self.log(f"[SWEEP] Transaction nLockTime set to: {locktime}")
            
            # Sign the transaction
            self.log("[SWEEP] Signing transaction...")
            self.wallet.sign_transaction(tx, None)
            
            if not tx.is_complete():
                QMessageBox.critical(
                    self,
                    "Signing Failed",
                    "Failed to sign transaction.\n\n"
                    "Make sure this wallet contains the private key."
                )
                return
            
            self.log("[SWEEP] ✅ Transaction signed successfully!")
            self.log(f"[SWEEP] Transaction size: {tx.estimated_size()} bytes")
            
            # Ask for confirmation
            result = QMessageBox.question(
                self,
                "Broadcast Transaction?",
                f"Ready to sweep {output_value} sats to your wallet!\n\n"
                f"From: {address}\n"
                f"To: {receiving_address}\n"
                f"Amount: {output_value} sats\n"
                f"Fee: {fee} sats\n\n"
                f"Broadcast now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result == QMessageBox.StandardButton.Yes:
                # Broadcast
                self.log("[SWEEP] Broadcasting transaction...")
                try:
                    txid = network.run_from_another_thread(network.broadcast_transaction(tx))
                    self.log(f"[SWEEP] ✅ Broadcast successful! TXID: {txid}")
                    QMessageBox.information(
                        self,
                        "Success! 🎉",
                        f"Transaction broadcast successfully!\n\n"
                        f"TXID:\n{txid}\n\n"
                        f"Funds will appear in your wallet after confirmation.\n\n"
                        f"View on explorer:\n"
                        f"https://mempool.space/signet/tx/{txid}"
                    )
                except Exception as broadcast_error:
                    self.log(f"[ERROR] Broadcast failed: {broadcast_error}")
                    QMessageBox.critical(self, "Broadcast Failed", f"Broadcast error:\n\n{broadcast_error}")
            else:
                self.log("[SWEEP] User cancelled broadcast")
            
            self.log("[SWEEP] ======== SWEEP PROCESS COMPLETE ========")
            
        except Exception as e:
            import traceback
            self.log(f"[ERROR] Sweep failed: {e}")
            self.log(f"[ERROR] Traceback: {traceback.format_exc()}")
            QMessageBox.critical(self, "Error", f"Sweep failed:\\n\\n{e}")

            import traceback
            traceback.print_exc()


class Plugin(BasePlugin):
    """CHECKLOCKTIMEVERIFY Plugin"""
    
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.windows = []
        
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
        """Add CHECKLOCKTIMEVERIFY menu item to Tools menu"""
        try:
            # Add to Tools menu
            menu = window.tools_menu
            action = menu.addAction("CHECKLOCKTIMEVERIFY Timelock...")
            action.triggered.connect(lambda: self.show_timelock_dialog(window))
        except Exception as e:
            print(f"[CLTV Plugin] Error adding menu item: {e}")
            
    def show_timelock_dialog(self, window):
        """Show the timelock address generator dialog"""
        dialog = TimelockDialog(window, self)
        dialog.exec()


