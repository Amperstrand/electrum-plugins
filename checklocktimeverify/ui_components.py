"""
Reusable UI Components for BIP-65 CLTV Examples Plugin

This module provides DRY UI components used across all example tabs.

Benefits:
- Single source of truth for common UI patterns
- Consistent styling and behavior
- Easy to update across all tabs
- Reduced code duplication
"""

from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QHBoxLayout, QVBoxLayout, QFormLayout,
    QRadioButton, QButtonGroup, QLabel, QPushButton, QSpinBox,
    QLineEdit, QDateTimeEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QFont


class OutputTypeSelector(QWidget):
    """
    P2SH/Taproot toggle widget with educational tooltips.
    
    Usage:
        selector = OutputTypeSelector()
        layout.addWidget(selector)
        
        # Later, get selected type:
        output_type = selector.get_output_type()  # 'p2sh' or 'taproot'
    """
    
    def __init__(self, default='p2sh', parent=None):
        super().__init__(parent)
        self.setup_ui(default)
    
    def setup_ui(self, default):
        """Setup the UI components"""
        # Main group box
        group = QGroupBox("Address Type")
        layout = QHBoxLayout()
        
        # Radio buttons
        self.button_group = QButtonGroup()
        
        self.p2sh_radio = QRadioButton("P2SH (Legacy)")
        self.p2sh_radio.setToolTip(
            "Pay-to-Script-Hash - Traditional Bitcoin scripting\n"
            "• Widely supported by all wallets\n"
            "• Addresses start with '3' (mainnet) or '2'/'t' (testnet)\n"
            "• Full script visible when spent\n"
            "• Battle-tested, proven format"
        )
        
        self.taproot_radio = QRadioButton("Taproot (BIP-341)")
        self.taproot_radio.setToolTip(
            "Taproot - Modern Bitcoin standard (activated Nov 2021)\n"
            "• Better privacy (script hidden until spend)\n"
            "• Lower transaction fees (smaller witness)\n"
            "• Addresses start with 'bc1p' (mainnet) or 'tb1p' (testnet)\n"
            "• More flexible script trees (MAST)\n"
            "• Future of Bitcoin scripting"
        )
        
        # Set default
        if default == 'taproot':
            self.taproot_radio.setChecked(True)
        else:
            self.p2sh_radio.setChecked(True)
        
        self.button_group.addButton(self.p2sh_radio, 0)
        self.button_group.addButton(self.taproot_radio, 1)
        
        # Info label with help icon
        info_label = QLabel(" ⓘ")
        info_label.setToolTip(
            "📖 Address Type Comparison:\n\n"
            "P2SH (Pay-to-Script-Hash):\n"
            "  Address: 3... (mainnet) or 2... (testnet)\n"
            "  Privacy: Script visible when spent\n"
            "  Support: Universal wallet support\n"
            "  Fees: Standard SegWit savings\n\n"
            "Taproot (BIP-341):\n"
            "  Address: bc1p... (mainnet) or tb1p... (testnet)\n"
            "  Privacy: Script hidden until spend\n"
            "  Support: Modern wallets (Nov 2021+)\n"
            "  Fees: ~10-30% lower than P2SH\n\n"
            "💡 Recommendation:\n"
            "  • Use P2SH for maximum compatibility\n"
            "  • Use Taproot for privacy and lower fees"
        )
        info_label.setStyleSheet("QLabel { font-size: 14pt; color: #1976d2; }")
        
        # Layout
        layout.addWidget(self.p2sh_radio)
        layout.addWidget(self.taproot_radio)
        layout.addWidget(info_label)
        layout.addStretch()
        
        group.setLayout(layout)
        
        # Set as main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)
        self.setLayout(main_layout)
    
    def get_output_type(self):
        """
        Get selected output type.
        
        Returns:
            str: 'p2sh' or 'taproot'
        """
        return 'taproot' if self.taproot_radio.isChecked() else 'p2sh'
    
    def set_output_type(self, output_type):
        """
        Set output type programmatically.
        
        Args:
            output_type: 'p2sh' or 'taproot'
        """
        if output_type == 'taproot':
            self.taproot_radio.setChecked(True)
        else:
            self.p2sh_radio.setChecked(True)


class LocktimeSelector(QWidget):
    """
    Unified locktime selector with block height or timestamp options.
    
    Usage:
        selector = LocktimeSelector(current_height=123456, default_locktime=123458)
        layout.addWidget(selector)
        
        # Later, get values:
        locktime, locktime_type, display = selector.get_locktime()
    """
    
    def __init__(self, current_height=0, default_locktime=None, parent=None):
        super().__init__(parent)
        self.current_height = current_height
        self.default_locktime = default_locktime or (current_height + 2)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI components"""
        # Main group box
        group = QGroupBox("Locktime Selection")
        locktime_layout = QHBoxLayout()
        
        # Left side: Radio buttons
        radio_layout = QVBoxLayout()
        self.button_group = QButtonGroup()
        
        self.block_radio = QRadioButton("Block Height")
        self.block_radio.setToolTip(
            "Lock funds until a specific block height\n\n"
            "Use this for time-based locks tied to network activity.\n"
            "Average: ~10 minutes per block"
        )
        
        self.time_radio = QRadioButton("Date && Time")
        self.time_radio.setToolTip(
            "Lock funds until a specific date/time\n\n"
            "Uses Unix timestamp (seconds since 1970).\n"
            "Must be >= 500000000 to be interpreted as timestamp."
        )
        
        self.block_radio.setChecked(True)
        
        self.button_group.addButton(self.block_radio, 0)
        self.button_group.addButton(self.time_radio, 1)
        
        radio_layout.addWidget(self.block_radio)
        radio_layout.addWidget(self.time_radio)
        radio_layout.addStretch()
        
        locktime_layout.addLayout(radio_layout)
        
        # Right side: Input fields (stacked)
        input_layout = QVBoxLayout()
        
        # Block height input
        self.block_group = QWidget()
        block_layout = QFormLayout()
        block_layout.setContentsMargins(0, 0, 0, 0)
        
        self.block_input = QSpinBox()
        self.block_input.setRange(0, 99999999)
        self.block_input.setValue(self.default_locktime)
        self.block_input.setMinimumWidth(200)
        self.block_input.setToolTip(
            f"Block height when funds become spendable\n\n"
            f"Current height: {self.current_height}\n"
            f"Default: {self.default_locktime} (current + 2 blocks)"
        )
        block_layout.addRow("Block Height:", self.block_input)
        
        current_info = QLabel(f"Current: {self.current_height} (default: current + 2)")
        current_info.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        block_layout.addRow("", current_info)
        
        self.block_group.setLayout(block_layout)
        input_layout.addWidget(self.block_group)
        
        # Timestamp input
        self.time_group = QWidget()
        time_layout = QFormLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        
        self.time_input = QDateTimeEdit()
        self.time_input.setDateTime(QDateTime.currentDateTime().addDays(30))
        self.time_input.setCalendarPopup(True)
        self.time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.time_input.setMinimumWidth(250)
        self.time_input.setToolTip(
            "The date and time when funds become spendable.\n\n"
            "Converted to Unix timestamp (seconds since 1970).\n"
            "Must be >= 500000000 to be interpreted as timestamp."
        )
        time_layout.addRow("Unlock Date/Time:", self.time_input)
        
        self.time_group.setLayout(time_layout)
        self.time_group.hide()
        input_layout.addWidget(self.time_group)
        
        input_layout.addStretch()
        locktime_layout.addLayout(input_layout, 1)
        
        group.setLayout(locktime_layout)
        
        # Set as main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)
        self.setLayout(main_layout)
        
        # Toggle visibility based on radio selection
        self.block_radio.toggled.connect(
            lambda checked: self.block_group.setVisible(checked)
        )
        self.time_radio.toggled.connect(
            lambda checked: self.time_group.setVisible(checked)
        )
    
    def get_locktime(self):
        """
        Get locktime value, type, and display string.
        
        Returns:
            Tuple of (locktime: int, locktime_type: str, display: str)
            
        Examples:
            (123458, 'block', 'Block 123458')
            (1696896000, 'timestamp', 'Time 1696896000')
        """
        if self.block_radio.isChecked():
            locktime = self.block_input.value()
            return (locktime, 'block', f'Block {locktime}')
        else:
            dt = self.time_input.dateTime()
            locktime = int(dt.toSecsSinceEpoch())
            return (locktime, 'timestamp', f'Time {locktime}')
    
    def set_current_height(self, height):
        """Update current height and default locktime"""
        self.current_height = height
        self.default_locktime = height + 2
        self.block_input.setValue(self.default_locktime)


class PubkeyInput(QWidget):
    """
    Public key input field with wallet selection button.
    
    Usage:
        pubkey_input = PubkeyInput(get_key_callback=self.get_wallet_pubkey)
        layout.addWidget(pubkey_input)
        
        # Later, get value:
        pubkey_hex = pubkey_input.get_pubkey()
    """
    
    def __init__(self, get_key_callback=None, label="Public Key (Auto-selected from Wallet)", parent=None):
        super().__init__(parent)
        self.get_key_callback = get_key_callback
        self.setup_ui(label)
    
    def setup_ui(self, label):
        """Setup the UI components"""
        group = QGroupBox(label)
        layout = QFormLayout()
        
        self.pubkey_edit = QLineEdit()
        self.pubkey_edit.setReadOnly(True)
        self.pubkey_edit.setPlaceholderText("Loading key from wallet...")
        self.pubkey_edit.setMinimumWidth(550)
        self.pubkey_edit.setFont(QFont("Courier", 10))
        self.pubkey_edit.setToolTip(
            "Public key that can spend the funds after locktime.\n\n"
            "Format: Hex string\n"
            "Compressed: 33 bytes (66 hex chars)\n"
            "Uncompressed: 65 bytes (130 hex chars)"
        )
        layout.addRow("Public Key:", self.pubkey_edit)
        
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        self.info_label.setWordWrap(True)
        layout.addRow("", self.info_label)
        
        if self.get_key_callback:
            get_key_btn = QPushButton("Select Different Key from Wallet")
            get_key_btn.clicked.connect(
                lambda: self.get_key_callback(self.pubkey_edit, self.info_label)
            )
            layout.addRow("", get_key_btn)
        
        group.setLayout(layout)
        
        # Set as main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)
        self.setLayout(main_layout)
    
    def get_pubkey(self):
        """Get the pubkey hex string"""
        return self.pubkey_edit.text().strip()
    
    def set_pubkey(self, pubkey_hex, info_text=""):
        """Set the pubkey value and optional info text"""
        self.pubkey_edit.setText(pubkey_hex)
        self.info_label.setText(info_text)


class ResultDisplay(QWidget):
    """
    Unified result display with address, script breakdown, and copy buttons.
    
    Usage:
        display = ResultDisplay()
        layout.addWidget(display)
        
        # Update with results:
        display.update_results(result_dict)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Address display (inline at top)
        address_group = QGroupBox("Generated Address")
        address_layout = QHBoxLayout()
        
        self.address_edit = QLineEdit()
        self.address_edit.setReadOnly(True)
        self.address_edit.setFont(QFont("Courier", 11))
        self.address_edit.setMinimumWidth(500)
        self.address_edit.setPlaceholderText("Generate an address to see it here...")
        address_layout.addWidget(self.address_edit, 1)
        
        address_group.setLayout(address_layout)
        layout.addWidget(address_group)
        
        # Script details display
        details_group = QGroupBox("Script Details")
        details_layout = QVBoxLayout()
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Courier", 9))
        self.details_text.setMinimumHeight(400)
        details_layout.addWidget(self.details_text)
        
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        self.setLayout(layout)
    
    def clear(self):
        """Clear all displayed content"""
        self.address_edit.clear()
        self.details_text.clear()
    
    def update_results(self, result, script_breakdown="", educational_content=""):
        """
        Update display with generation results.
        
        Args:
            result: Dictionary from AddressFactory with address, script_hex, etc.
            script_breakdown: Formatted script breakdown text
            educational_content: BIP-65 quotes and descriptions
        """
        # Display address
        self.address_edit.setText(result['address'])
        
        # Build details text
        details = []
        
        # Address and basic info
        details.append("="*80)
        details.append(f"✅ ADDRESS GENERATED")
        details.append("="*80)
        details.append(f"\n📬 Address: {result['address']}")
        details.append(f"🏷️  Type: {result.get('output_type', 'p2sh').upper()}")
        details.append(f"📅 Created: {result.get('created', 'N/A')}")
        details.append(f"🔒 Script Type: {result.get('script_type', 'N/A')}")
        
        # Locktime info
        if 'locktime' in result:
            details.append(f"\n⏰ Locktime: {result['locktime']} ({result.get('locktime_type', 'N/A')})")
            details.append(f"   Display: {result.get('locktime_display', 'N/A')}")
        
        # Script breakdown
        if script_breakdown:
            details.append(f"\n{'='*80}")
            details.append("📜 SCRIPT BREAKDOWN")
            details.append("="*80)
            details.append(script_breakdown)
        
        # P2SH specific info
        if result.get('output_type') == 'p2sh':
            details.append(f"\n{'='*80}")
            details.append("🔐 P2SH DETAILS")
            details.append("="*80)
            details.append(f"Script Hash: {result.get('script_hash', 'N/A')}")
            details.append(f"Script Hex:  {result.get('script_hex', 'N/A')[:80]}...")
            details.append("\nℹ️  P2SH Format:")
            details.append("  • Widely supported legacy format")
            details.append("  • Full script visible when spent")
            details.append("  • Address starts with '3' (mainnet) or '2'/'t' (testnet)")
        
        # Taproot specific info
        elif result.get('output_type') == 'taproot':
            details.append(f"\n{'='*80}")
            details.append("🌲 TAPROOT DETAILS")
            details.append("="*80)
            details.append(f"Internal Pubkey:  {result.get('internal_pubkey', 'N/A')}")
            details.append(f"Witness Program:  {result.get('witness_program', 'N/A')}")
            details.append(f"Control Block:    {result.get('control_block', 'N/A')[:60]}...")
            details.append(f"Output Script:    {result.get('output_script', 'N/A')[:60]}...")
            details.append("\n🌟 Taproot Benefits:")
            details.append("  • Better privacy - script hidden until spend")
            details.append("  • Lower fees - smaller witness data")
            details.append("  • Modern Bitcoin standard (BIP-341)")
            details.append("  • Address starts with 'bc1p' (mainnet) or 'tb1p' (testnet)")
            details.append("\n📝 Spending Note:")
            details.append("  To spend, you need:")
            details.append("  1. Signature(s) for the script")
            details.append("  2. The tapscript itself")
            details.append("  3. The control block (proves script is in tree)")
        
        # Educational content
        if educational_content:
            details.append(f"\n{'='*80}")
            details.append("📚 EDUCATIONAL CONTENT")
            details.append("="*80)
            details.append(educational_content)
        
        # Set the text
        self.details_text.setPlainText('\n'.join(details))


# Factory functions for quick widget creation

def create_description_label(text, background_color="#e8f5e9"):
    """Create a styled description label"""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"QLabel {{ background-color: {background_color}; padding: 10px; border-radius: 5px; }}")
    return label


def create_generate_button(text, callback):
    """Create a styled generate button"""
    button = QPushButton(text)
    button.clicked.connect(callback)
    button.setMinimumHeight(35)
    button.setStyleSheet("""
        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
            font-size: 11pt;
            padding: 8px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #3d8b40;
        }
    """)
    return button
