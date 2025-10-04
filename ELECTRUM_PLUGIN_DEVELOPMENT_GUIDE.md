# Electrum Plugin Development Guide

**Complete Reference for Building Electrum Plugins**

This guide provides everything you need to develop Electrum plugins, based on the official documentation and the VirtualKeyboard plugin example. Use this as context for one-shot prompts to build functional Electrum plugins.

---

## Table of Contents

1. [Overview](#overview)
2. [Plugin Types](#plugin-types)
3. [Plugin Architecture](#plugin-architecture)
4. [File Structure](#file-structure)
5. [The manifest.json File](#the-manifestjson-file)
6. [The Plugin Class](#the-plugin-class)
7. [Hooks System](#hooks-system)
8. [VirtualKeyboard Plugin Deep Dive](#virtualkeyboard-plugin-deep-dive)
9. [Development Workflow](#development-workflow)
10. [Publishing & Distribution](#publishing--distribution)
11. [Security Considerations](#security-considerations)
12. [Examples of Existing Plugins](#examples-of-existing-plugins)

---

## Overview

Electrum's plugin system allows developers to extend functionality without modifying the core codebase. Plugins can add features to the GUI, provide new wallet capabilities, enable integrations, and more.

**Key Benefits:**
- Modular architecture keeps core code lean
- Easy to enable/disable via **Menu Bar** > **Tools** > **Plugins**
- Support for both internal (shipped with Electrum) and external (third-party) plugins
- GUI-specific implementations (Qt, Android, etc.)

---

## Plugin Types

### Internal Plugins
Shipped with Electrum and maintained in the official repository.

**Examples include:**
- **Audio Modem**: Air-gapped transaction signing support
- **LabelSync**: Sync wallet labels across devices via encrypted remote storage
- **Nostr Wallet Connect**: Remote control of Lightning wallets via Nostr NIP-47
- **Nostr Cosigner**: Multi-signature wallet coordination via Nostr relays
- **Revealer**: Visual encryption backup for wallet seeds
- **Two Factor Authentication**: 2FA for wallets via TrustedCoin
- **Timelock Recovery**: Create time-locked recovery plans
- **Virtual Keyboard**: Virtual keyboard for password entry
- **Swapserver** [CLI]: Offer submarine swaps
- **Payserver** [CLI]: HTTP server for receiving payments

### External Plugins
Third-party plugins distributed as `.zip` files.

**Security Features:**
- Require plugin password on first load
- Public key verification system (stored with root permissions)
- Independent of wallet passwords

**Known External Plugins:**
- **Guardian**: Physical coercion resistance
- **LNURL Server**: Receive LN payments through static URL
- **Joinstr**: Collaborative transactions via Nostr

---

## Plugin Architecture

### Core Concepts

1. **BasePlugin Class**: All plugins inherit from `electrum.plugin.BasePlugin`
2. **Hook System**: Plugins use `@hook` decorators to inject code at specific points
3. **GUI-Specific**: Plugins can target specific GUIs (qt, android, etc.)
4. **Lazy Loading**: Plugins are only loaded when enabled

### Plugin Lifecycle

```
User Enables Plugin → Electrum Loads manifest.json → Instantiates Plugin Class → Registers Hooks → Hooks Execute at Runtime
```

---

## File Structure

A minimal plugin requires the following structure:

```
myplugin/
├── __init__.py          # Can be empty (required for Python package)
├── manifest.json        # Plugin metadata and configuration
├── qt.py               # Qt GUI implementation (if targeting Qt)
└── [resources]         # Icons, images, etc. (optional)
```

**Alternative Structure for Multi-GUI Support:**

```
myplugin/
├── __init__.py
├── manifest.json
├── qt.py              # Qt implementation
├── android.py         # Android implementation
└── resources/
    └── icons/
```

---

## The manifest.json File

The `manifest.json` file contains essential metadata about your plugin.

### Required Fields

```json
{
  "name": "myplugin",
  "fullname": "My Awesome Plugin",
  "description": "A detailed description of what the plugin does.\nCan be multi-line.",
  "available_for": ["qt"],
  "author": "Your Name",
  "license": "MIT",
  "version": "0.0.1"
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Internal plugin name (unique identifier). Only one plugin per name can be installed. |
| `fullname` | string | Yes | User-visible name shown in GUI |
| `description` | string | Yes | User-visible description. Use `\n` for multi-line text. |
| `available_for` | array | Yes | List of supported GUIs: `["qt"]`, `["android"]`, or `["qt", "android"]` |
| `author` | string | Yes | Plugin author name |
| `license` | string | Yes | License identifier (e.g., "MIT", "GPL-3.0", "Apache-2.0") |
| `version` | string | Yes | Plugin version (semver recommended: "MAJOR.MINOR.PATCH") |
| `min_electrum_version` | string | No | Minimum Electrum version required (e.g., "4.0.0") |
| `max_electrum_version` | string | No | Maximum Electrum version supported (e.g., "5.0.0") |

### Example from VirtualKeyboard

```json
{
  "name": "virtualkeyboard",
  "fullname": "Virtual Keyboard",
  "description": "Add an optional virtual keyboard to the password dialog.\nWarning: do not use this if it makes you pick a weaker password.",
  "available_for": ["qt"],
  "author": "The Electrum developers",
  "license": "MIT",
  "version": "0.0.1"
}
```

---

## The Plugin Class

### Basic Structure

Every plugin must define a `Plugin` class that inherits from `BasePlugin`:

```python
from electrum.plugin import BasePlugin, hook

class Plugin(BasePlugin):
    
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        # Initialize plugin-specific variables
    
    @hook
    def some_hook_name(self, *args, **kwargs):
        # Hook implementation
        pass
```

### Important Methods

#### Constructor
```python
def __init__(self, parent, config, name):
    BasePlugin.__init__(self, parent, config, name)
    # Your initialization code
```

**Parameters:**
- `parent`: Parent object (usually the plugin manager)
- `config`: Electrum config object
- `name`: Plugin name from manifest

#### Reading Plugin Files
```python
# Read a file from the plugin directory
content = self.read_file("filename.txt")  # Returns bytes
icon_bytes = self.read_file("icon.svg")
```

---

## Hooks System

Hooks are the primary mechanism for plugins to interact with Electrum. They allow you to inject code at specific execution points.

### Hook Decorator

```python
from electrum.plugin import hook

@hook
def hook_name(self, *args, **kwargs):
    # Your implementation
    pass
```

### Common Hooks

#### GUI Hooks (Qt)

**`password_dialog`** - Modify password dialog
```python
@hook
def password_dialog(self, pw, grid, pos):
    """
    Called when password dialog is created
    
    Args:
        pw: Password input widget (QLineEdit)
        grid: QGridLayout of the dialog
        pos: Current row position in grid
    """
    # Add widgets to the password dialog
    button = QPushButton("My Button")
    grid.addWidget(button, pos, 2)
```

**`load_wallet`** - Called when wallet is loaded
```python
@hook
def load_wallet(self, wallet, window):
    """
    Args:
        wallet: The wallet object being loaded
        window: The main window object
    """
    pass
```

**`close_wallet`** - Called when wallet is closed
```python
@hook
def close_wallet(self, wallet):
    """
    Args:
        wallet: The wallet object being closed
    """
    pass
```

**`on_receive_tx`** - Called when transaction is received
```python
@hook
def on_receive_tx(self, wallet, tx):
    """
    Args:
        wallet: The wallet that received the transaction
        tx: The transaction object
    """
    pass
```

#### Network Hooks

**`set_network`** - Called when network is set
```python
@hook
def set_network(self, network):
    """
    Args:
        network: The network object
    """
    pass
```

### Hook Execution Flow

1. User action triggers a hook point in Electrum core
2. Electrum calls all registered hooks with that name
3. Hooks execute in the order plugins were loaded
4. Return values (if any) are handled according to hook type

---

## VirtualKeyboard Plugin Deep Dive

Let's analyze the complete VirtualKeyboard plugin to understand real-world implementation.

### Full Source Code Analysis

```python
import random

from PyQt6.QtWidgets import (QVBoxLayout, QGridLayout, QPushButton)
from PyQt6.QtGui import QFontMetrics

from electrum.plugin import BasePlugin, hook
from electrum.i18n import _
from electrum.gui.qt.util import read_QIcon_from_bytes

class Plugin(BasePlugin):
    vkb = None
    vkb_index = 0

    @hook
    def password_dialog(self, pw, grid, pos):
        vkb_button = QPushButton('')
        vkb_button.setIcon(read_QIcon_from_bytes(self.read_file("keyboard-icon.svg")))
        font_height = QFontMetrics(vkb_button.font()).height()
        vkb_button.setFixedWidth(round(1.7 * font_height))
        vkb_button.clicked.connect(lambda: self.toggle_vkb(grid, pw))
        grid.addWidget(vkb_button, pos, 2)
        self.kb_pos = 2
        self.vkb = None

    def toggle_vkb(self, grid, pw):
        if self.vkb:
            grid.removeItem(self.vkb)
        self.vkb = self.virtual_keyboard(self.vkb_index, pw)
        grid.addLayout(self.vkb, self.kb_pos, 0, 1, 3)
        self.vkb_index += 1

    def virtual_keyboard(self, i, pw):
        i = i % 3
        if i == 0:
            chars = 'abcdefghijklmnopqrstuvwxyz '
        elif i == 1:
            chars = 'ABCDEFGHIJKLMNOPQRTSUVWXYZ '
        elif i == 2:
            chars = '1234567890!?.,;:/%&()[]{}+-'

        n = len(chars)
        s = []
        for i in range(n):
            while True:
                k = random.randint(0, n - 1)
                if k not in s:
                    s.append(k)
                    break

        def add_target(t):
            return lambda: pw.setText(str(pw.text()) + t)

        font_height = QFontMetrics(QPushButton().font()).height()
        btn_size = max(25, round(1.7 * font_height))

        vbox = QVBoxLayout()
        grid = QGridLayout()
        grid.setSpacing(2)
        for i in range(n):
            l_button = QPushButton(chars[s[i]])
            l_button.setFixedWidth(btn_size)
            l_button.setFixedHeight(btn_size)
            l_button.clicked.connect(add_target(chars[s[i]]))
            grid.addWidget(l_button, i // 6, i % 6)

        vbox.addLayout(grid)

        return vbox
```

### Component Breakdown

#### 1. Imports
```python
import random  # For randomizing keyboard layout

from PyQt6.QtWidgets import (QVBoxLayout, QGridLayout, QPushButton)
from PyQt6.QtGui import QFontMetrics

from electrum.plugin import BasePlugin, hook
from electrum.i18n import _  # Internationalization (not used here but common)
from electrum.gui.qt.util import read_QIcon_from_bytes
```

**Key Imports:**
- PyQt6 widgets for GUI
- `BasePlugin` and `hook` from Electrum
- `read_QIcon_from_bytes` for loading SVG icons

#### 2. Class Variables
```python
class Plugin(BasePlugin):
    vkb = None        # Current virtual keyboard layout
    vkb_index = 0     # Tracks which character set to show (0=lower, 1=upper, 2=numbers)
```

#### 3. The `password_dialog` Hook
```python
@hook
def password_dialog(self, pw, grid, pos):
    # Create button with keyboard icon
    vkb_button = QPushButton('')
    vkb_button.setIcon(read_QIcon_from_bytes(self.read_file("keyboard-icon.svg")))
    
    # Size button proportionally to font
    font_height = QFontMetrics(vkb_button.font()).height()
    vkb_button.setFixedWidth(round(1.7 * font_height))
    
    # Connect click event
    vkb_button.clicked.connect(lambda: self.toggle_vkb(grid, pw))
    
    # Add to dialog grid at position (pos, 2)
    grid.addWidget(vkb_button, pos, 2)
    
    # Track position for keyboard layout
    self.kb_pos = 2
    self.vkb = None
```

**What it does:**
1. Creates a button with keyboard icon (loaded from `keyboard-icon.svg`)
2. Sizes button based on font metrics (responsive design)
3. Connects button click to `toggle_vkb` method
4. Adds button to password dialog grid

#### 4. Toggle Virtual Keyboard
```python
def toggle_vkb(self, grid, pw):
    # Remove existing keyboard if present
    if self.vkb:
        grid.removeItem(self.vkb)
    
    # Create new keyboard with next character set
    self.vkb = self.virtual_keyboard(self.vkb_index, pw)
    
    # Add keyboard to grid (spans 3 columns)
    grid.addLayout(self.vkb, self.kb_pos, 0, 1, 3)
    
    # Cycle to next character set
    self.vkb_index += 1
```

**What it does:**
1. Removes previous keyboard if exists
2. Creates new keyboard layout with different character set
3. Adds to grid spanning 3 columns
4. Increments index to cycle through lowercase → uppercase → numbers/symbols

#### 5. Virtual Keyboard Generation
```python
def virtual_keyboard(self, i, pw):
    # Cycle through 3 character sets
    i = i % 3
    if i == 0:
        chars = 'abcdefghijklmnopqrstuvwxyz '
    elif i == 1:
        chars = 'ABCDEFGHIJKLMNOPQRTSUVWXYZ '
    elif i == 2:
        chars = '1234567890!?.,;:/%&()[]{}+-'

    # Randomize character positions (security feature)
    n = len(chars)
    s = []
    for i in range(n):
        while True:
            k = random.randint(0, n - 1)
            if k not in s:
                s.append(k)
                break

    # Closure to append character to password field
    def add_target(t):
        return lambda: pw.setText(str(pw.text()) + t)

    # Calculate button size based on font
    font_height = QFontMetrics(QPushButton().font()).height()
    btn_size = max(25, round(1.7 * font_height))

    # Create layout
    vbox = QVBoxLayout()
    grid = QGridLayout()
    grid.setSpacing(2)
    
    # Create button for each character
    for i in range(n):
        l_button = QPushButton(chars[s[i]])  # Use randomized position
        l_button.setFixedWidth(btn_size)
        l_button.setFixedHeight(btn_size)
        l_button.clicked.connect(add_target(chars[s[i]]))
        grid.addWidget(l_button, i // 6, i % 6)  # 6 columns

    vbox.addLayout(grid)
    return vbox
```

**What it does:**
1. Selects character set based on index (modulo 3)
2. **Randomizes button positions** (security: prevents shoulder surfing)
3. Creates closure for each button to append character
4. Sizes buttons responsively
5. Arranges buttons in 6-column grid
6. Returns complete layout

### Key Design Patterns

1. **Resource Loading**: Uses `self.read_file()` to load SVG icon
2. **Responsive Design**: Sizes elements based on font metrics
3. **Security**: Randomizes keyboard layout on each display
4. **State Management**: Tracks keyboard state and cycle index
5. **Qt Best Practices**: Proper widget lifecycle and layout management

---

## Development Workflow

### 1. Initial Setup

**Option A: Development Mode (Recommended)**

Create a symbolic link for rapid testing:

```bash
# Navigate to Electrum plugins directory
cd ~/electrum/electrum/plugins/

# Create symlink to your plugin
ln -s /path/to/your/plugin/directory myplugin
```

Benefits:
- No need to rebuild/reinstall after changes
- Instant testing
- Easy debugging

**Option B: Install Mode**

For testing the full installation process:

```bash
# Build plugin zip
./contrib/make_plugin /path/to/plugin/directory

# Copy to Electrum plugins directory
cp myplugin-0.0.1.zip ~/.electrum/plugins/
```

### 2. Development Checklist

```
☐ Create plugin directory structure
☐ Write manifest.json with all required fields
☐ Create __init__.py (can be empty)
☐ Implement Plugin class in appropriate file (qt.py, android.py, etc.)
☐ Add hooks for desired functionality
☐ Include any resource files (icons, etc.)
☐ Test with development symlink
☐ Test enabling/disabling in Electrum GUI
☐ Verify hooks execute correctly
☐ Test edge cases and error handling
☐ Build final .zip for distribution
```

### 3. Testing

```python
# Add debug prints to your plugin
class Plugin(BasePlugin):
    
    @hook
    def password_dialog(self, pw, grid, pos):
        print(f"[MyPlugin] password_dialog called: pw={pw}, pos={pos}")
        # Your code here
```

Run Electrum from terminal to see debug output:

```bash
cd ~/electrum
./run_electrum
```

### 4. Debugging Tips

- **Plugin not loading**: Check manifest.json syntax (use JSON validator)
- **Hook not called**: Verify hook name matches Electrum's hook points
- **Import errors**: Ensure all dependencies are available
- **GUI issues**: Test Qt widgets independently before integration

---

## Publishing & Distribution

### 1. Build the Plugin

Use Electrum's build script:

```bash
cd /path/to/electrum
./contrib/make_plugin /path/to/your/plugin/directory
```

This creates: `yourplugin-VERSION.zip` (version from manifest.json)

### 2. Zip File Structure

The resulting zip contains:

```
myplugin-0.0.1.zip
├── __init__.py
├── manifest.json
├── qt.py
└── [any resource files]
```

### 3. Distribution

**Direct Distribution:**
- Host on GitHub releases
- Provide download link on your website
- Share via plugin registry (if available)

**Installation Instructions for Users:**

On Linux:
```bash
cp myplugin-0.0.1.zip ~/.electrum/plugins/
```

On Windows:
```
Copy to: %APPDATA%\Electrum\plugins\
```

On macOS:
```bash
cp myplugin-0.0.1.zip ~/Library/Application\ Support/Electrum/plugins/
```

### 4. Plugin Authorization

**First-time setup** (for external plugins):

Users must:
1. Set a plugin password (independent of wallet password)
2. Store public key string with root permissions

**Linux - Public Key Storage:**
```bash
# Create directory
sudo mkdir -p /etc/electrum

# Store public key
sudo nano /etc/electrum/plugin_pubkey
# Paste public key string, save and exit
```

**Windows - Public Key Storage:**
1. Open Run Dialog (Windows + R)
2. Type `regedit` and press Enter
3. Navigate to `HKEY_LOCAL_MACHINE\SOFTWARE`
4. Create directory: `Electrum`
5. Create subdirectory: `PluginKey`
6. Add entry with public key string as value

---

## Security Considerations

### Plugin Security Model

1. **External Plugin Protection**:
   - Require plugin password
   - Public key verification
   - Root-permission storage (prevents malware modification)

2. **Code Review**: Users should review plugin code before installation

3. **Permissions**: Plugins have full access to:
   - Wallet data
   - Network connections
   - File system (within Electrum's permissions)
   - GUI controls

### Best Practices

**For Plugin Developers:**

```python
# ✅ DO: Use official Electrum APIs
from electrum.plugin import BasePlugin, hook
from electrum.gui.qt.util import read_QIcon_from_bytes

# ❌ DON'T: Access private/internal APIs
# from electrum.internal._private_module import something

# ✅ DO: Handle errors gracefully
@hook
def load_wallet(self, wallet, window):
    try:
        # Your code
        pass
    except Exception as e:
        print(f"Plugin error: {e}")

# ❌ DON'T: Let exceptions crash Electrum
@hook
def load_wallet(self, wallet, window):
    # Uncaught exception could crash Electrum
    risky_operation()

# ✅ DO: Validate user input
def process_input(self, user_data):
    if not isinstance(user_data, str):
        raise ValueError("Expected string input")
    sanitized = user_data.strip()
    # Process sanitized data

# ✅ DO: Use secure randomness for security features
import secrets
random_value = secrets.token_bytes(32)

# ❌ DON'T: Use predictable randomness for security
import random
random_value = random.randint(0, 1000)  # Predictable!
```

**For Users:**

- Only install plugins from trusted sources
- Review plugin code if possible
- Keep plugins updated
- Disable unused plugins
- Use strong plugin password

---

## Examples of Existing Plugins

### Plugin Ideas by Category

#### GUI Enhancements
- **VirtualKeyboard**: Virtual keyboard for password entry
- Custom themes
- Enhanced transaction history views
- Notification systems

#### Security
- **Two Factor Authentication**: 2FA integration
- **Guardian**: Coercion resistance
- Hardware wallet integrations
- Biometric authentication

#### Privacy
- **Joinstr**: Collaborative transactions
- CoinJoin implementations
- Tor integration
- Enhanced fee selection

#### Lightning Network
- **Nostr Wallet Connect**: Remote wallet control
- **LNURL Server**: Static payment URLs
- **Swapserver**: Submarine swaps
- Channel management tools

#### Wallet Management
- **LabelSync**: Label synchronization
- **Timelock Recovery**: Recovery plans
- Backup automation
- Multi-wallet management

#### Integration
- **Payserver**: Payment processing
- Exchange integrations
- Price alerts
- Merchant tools

---

## Quick Start Template

Here's a minimal plugin template to get started:

### Directory Structure
```
my_awesome_plugin/
├── __init__.py
├── manifest.json
└── qt.py
```

### `manifest.json`
```json
{
  "name": "myawesomeplugin",
  "fullname": "My Awesome Plugin",
  "description": "Does something amazing with Electrum",
  "available_for": ["qt"],
  "author": "Your Name",
  "license": "MIT",
  "version": "0.0.1"
}
```

### `__init__.py`
```python
# Empty file (required for Python package)
```

### `qt.py`
```python
from electrum.plugin import BasePlugin, hook
from PyQt6.QtWidgets import QPushButton, QMessageBox

class Plugin(BasePlugin):
    
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        print(f"[{name}] Plugin initialized!")
    
    @hook
    def load_wallet(self, wallet, window):
        """Called when a wallet is loaded"""
        print(f"[{self.name}] Wallet loaded: {wallet}")
        # Add your logic here
    
    @hook
    def password_dialog(self, pw, grid, pos):
        """Add a button to the password dialog"""
        button = QPushButton("My Button")
        button.clicked.connect(self.on_button_click)
        grid.addWidget(button, pos, 2)
    
    def on_button_click(self):
        """Handle button click"""
        QMessageBox.information(None, "My Plugin", "Button clicked!")
```

### Test It
```bash
# Create symlink for development
ln -s /path/to/my_awesome_plugin ~/.electrum/electrum/plugins/myawesomeplugin

# Run Electrum
cd ~/electrum
./run_electrum

# Enable plugin: Menu Bar > Tools > Plugins > Check "My Awesome Plugin"
```

---

## Common Patterns & Snippets

### Reading Configuration
```python
class Plugin(BasePlugin):
    
    def get_config_value(self, key, default=None):
        """Read plugin configuration"""
        return self.config.get(f'plugin_{self.name}_{key}', default)
    
    def set_config_value(self, key, value):
        """Write plugin configuration"""
        self.config.set_key(f'plugin_{self.name}_{key}', value)
```

### Adding Menu Items
```python
@hook
def init_qt(self, gui):
    """Add menu item to main window"""
    # This hook is called when Qt GUI initializes
    # You can add menu items, toolbars, etc.
    pass
```

### Network Requests
```python
from electrum.network import Network

class Plugin(BasePlugin):
    
    def make_request(self, url):
        """Make HTTP request (use Electrum's network stack)"""
        # Implement using Electrum's network module
        # or standard libraries like requests
        import requests
        response = requests.get(url)
        return response.json()
```

### Working with Transactions
```python
@hook
def on_receive_tx(self, wallet, tx):
    """Process received transaction"""
    txid = tx.txid()
    amount = tx.output_value()
    print(f"Received tx {txid}: {amount} sats")
```

---

## Additional Resources

### Electrum Documentation
- Official Docs: https://electrum.readthedocs.io/
- Plugin Development: https://electrum.readthedocs.io/en/latest/plugin_dev.html
- API Reference: Check Electrum source code

### Source Code References
- Electrum Repository: https://github.com/spesmilo/electrum
- Plugin Examples: https://github.com/spesmilo/electrum/tree/master/electrum/plugins
- External Plugin Template: https://github.com/spesmilo/electrum-plugins

### Community
- Submit plugins to docs: https://github.com/spesmilo/electrum-docs/
- Electrum Forums: Community discussions
- GitHub Issues: Report bugs, request features

---

## Hackathon-Specific Tips

### Time-Saving Strategies

1. **Start with a working example**: Clone VirtualKeyboard and modify
2. **Use development symlinks**: Avoid rebuild cycles
3. **Focus on one hook**: Master one interaction point first
4. **Minimal UI first**: Get functionality working before polishing
5. **Print debug statements**: Fastest debugging method

### Quick Win Ideas

**Easy (2-4 hours):**
- Custom notification plugin
- Transaction label automation
- Simple fee calculator
- Wallet statistics dashboard

**Medium (4-8 hours):**
- Exchange rate integrations
- Custom backup system
- QR code enhancements
- Address book with notes

**Advanced (8+ hours):**
- Lightning Network tools
- Privacy enhancements
- Multi-signature coordination
- Payment protocol implementations

### Pitfall Avoidance

```python
# ❌ Common mistake: Wrong hook name
@hook
def password_dialogue(self, pw, grid, pos):  # Typo: "dialogue" vs "dialog"
    pass

# ✅ Correct
@hook
def password_dialog(self, pw, grid, pos):
    pass

# ❌ Common mistake: Not handling None values
@hook
def load_wallet(self, wallet, window):
    name = wallet.name.upper()  # Crash if name is None!

# ✅ Correct
@hook
def load_wallet(self, wallet, window):
    name = getattr(wallet, 'name', 'Unknown')
    name = name.upper() if name else 'Unknown'

# ❌ Common mistake: Blocking the UI thread
@hook
def load_wallet(self, wallet, window):
    time.sleep(10)  # Freezes Electrum!

# ✅ Correct: Use threading
import threading

@hook
def load_wallet(self, wallet, window):
    def background_task():
        time.sleep(10)
        # Do work
    threading.Thread(target=background_task, daemon=True).start()
```

---

## Lessons Learned from Real Development

### Critical Issues & Solutions

#### 1. **Electrum Installation Methods (macOS)**

**Problem**: The Electrum.app DMG is read-only and cannot be modified.

**Solutions Attempted**:
- ❌ Modifying DMG bundle contents (read-only filesystem)
- ❌ Copying to /Applications (disk space issues)
- ❌ Symlinking to `~/.electrum/signet/plugins/` (wrong location - that's for config data)

**✅ Working Solution**: Install from source
```bash
# Clone Electrum repository
git clone https://github.com/spesmilo/electrum.git ~/src/electrum

# Create virtual environment
cd ~/src/electrum
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e '.[crypto]'
pip install -r contrib/requirements/requirements.txt

# Symlink your plugin into the source tree
ln -sf /path/to/your/plugin ~/src/electrum/electrum/plugins/yourplugin

# Run Electrum
./run_electrum --signet
```

**Key Insight**: External plugins must be in the Electrum source tree or properly packaged, not in the user config directory.

#### 2. **Configuration System Gotchas**

**Problem**: Plugin config not loading despite being set.

**Wrong Approach**:
```python
# ❌ This doesn't work - flat key structure
config.set_key("plugins.checklocktimeverify.enabled", true)
```

**Correct Approach**:
```python
# ✅ SimpleConfig uses nested dict navigation
config = {
    "plugins": {
        "checklocktimeverify": {
            "enabled": true
        }
    }
}
```

**Key Insight**: Electrum's `SimpleConfig.get('plugins.name.key')` navigates nested dicts, not flat dotted keys.

**Programmatic Fix**:
```python
import json
import os

config_file = os.path.expanduser('~/.electrum/signet/config')
with open(config_file, 'r') as f:
    config = json.load(f)

# Create nested structure
if 'plugins' not in config:
    config['plugins'] = {}
if 'yourplugin' not in config['plugins']:
    config['plugins']['yourplugin'] = {}
config['plugins']['yourplugin']['enabled'] = True

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
```

#### 3. **Missing Dependencies**

**Problem**: Import errors when loading plugin.

**Common Missing Packages**:
```bash
# Cryptography for Bitcoin operations
pip install cryptography

# PyQt6 for GUI (if not installed)
pip install PyQt6

# Other common dependencies
pip install aiohttp protobuf
```

**Key Insight**: Even with `pip install -e '.[crypto]'`, some dependencies may be missing. Install them individually as errors occur.

#### 4. **Qt Widget Initialization Timing**

**Problem**: Auto-loading wallet data during tab creation fails.

**Wrong Pattern**:
```python
def create_simple_timelock_tab(self):
    # ...
    # ❌ This executes during tab creation, before dialog is fully initialized
    self.get_wallet_pubkey(self.simple_pubkey_input, self.simple_key_info)
```

**Correct Pattern**:
```python
def __init__(self, parent, plugin):
    super().__init__(parent)
    self.wallet = parent.wallet
    self.setup_ui()
    
    # ✅ Call after UI is fully constructed
    self.auto_load_keys()

def auto_load_keys(self):
    """Load wallet keys after dialog initialization"""
    try:
        self.get_wallet_pubkey(self.simple_pubkey_input, self.simple_key_info)
        self.load_escrow_keys()
    except Exception as e:
        print(f"Auto-load failed: {e}")
```

**Key Insight**: Wallet access during widget construction may fail. Defer data loading until after `setup_ui()` completes.

#### 5. **Transaction Building Complexity**

**Problem**: Spending CLTV-locked outputs requires manual transaction construction.

**What's Required**:
```python
# Must manually set:
tx.nLockTime = locktime_value  # Must be >= CLTV locktime
tx.inputs[0].nSequence = 0xfffffffe  # Must be < 0xffffffff
tx.inputs[0].scriptSig = signature + redeem_script  # P2SH spending
```

**Key Insight**: Electrum's transaction builder doesn't have native CLTV support. You need to:
1. Manually construct `PartialTransaction` objects
2. Set `nLockTime` and `nSequence` fields correctly
3. Provide the redeem script in scriptSig
4. Sign with the appropriate wallet key

**For Hackathons**: Implement educational sweep (show instructions) rather than full auto-sweep.

#### 6. **Script Encoding Edge Cases**

**Problem**: Incorrect locktime encoding in Bitcoin Script.

**Critical Rule**: Use **minimal encoding** (little-endian, shortest form)
```python
def push_int(self, n: int) -> bytes:
    """Push integer with minimal encoding"""
    if n == -1:
        return bytes([opcodes.OP_1NEGATE])
    elif n == 0:
        return bytes([opcodes.OP_0])
    elif 1 <= n <= 16:
        return bytes([opcodes.OP_1 + n - 1])
    else:
        # Encode as little-endian, minimal bytes
        # Remove leading zeros
        b = n.to_bytes((n.bit_length() + 7) // 8, 'little')
        # Push length byte + data
        return bytes([len(b)]) + b
```

**Key Insight**: Bitcoin Script requires minimal integer encoding. Don't use fixed-width encoding.

#### 7. **UI Sizing for Long Data**

**Problem**: Public keys (66 hex chars) and scripts overflow input fields.

**Wrong**:
```python
self.pubkey_input = QLineEdit()  # Default width too narrow
```

**Correct**:
```python
self.pubkey_input = QLineEdit()
self.pubkey_input.setMinimumWidth(550)  # Accommodate 66 chars
self.pubkey_input.setFont(QFont("Courier", 10))  # Monospace for hex
```

**Also Consider**:
- Scroll areas for long content
- Adjustable dialog sizes
- Text wrapping for descriptions

#### 8. **Logging for Education**

**Problem**: Users don't understand what the plugin is doing.

**Solution**: Comprehensive logging with `print_error`
```python
from electrum.util import print_error

def log(self, message: str):
    """Educational logging to Electrum console"""
    print_error(f"[CLTV Plugin] {message}")

# Log every step
self.log("[GENERATE] Starting address generation")
self.log("[SCRIPT] Step 1: Push locktime value 870000")
self.log("[SCRIPT] Step 2: Add OP_CHECKLOCKTIMEVERIFY (0xb1)")
self.log(f"[GENERATE] ✓ P2SH Address: {address}")
```

**Key Insight**: For educational tools, verbose logging is a feature, not a bug. Log to Electrum console (View → Show Console).

#### 9. **Data Persistence**

**Problem**: Users lose redeem scripts between sessions.

**Solution**: Auto-save to JSON in wallet directory
```python
wallet_dir = os.path.dirname(self.wallet.storage.path)
storage_file = os.path.join(wallet_dir, 'cltv_timelock_data.json')

def save_timelock_data(self, data: Dict):
    if os.path.exists(self.storage_file):
        with open(self.storage_file, 'r') as f:
            all_data = json.load(f)
    else:
        all_data = []
    
    all_data.append(data)
    
    with open(self.storage_file, 'w') as f:
        json.dump(all_data, f, indent=2)
```

**Key Insight**: Store plugin data in the wallet directory, not the plugin directory. This keeps data with the wallet it belongs to.

### macOS-Specific Issues

#### Issue 1: DMG Read-Only Filesystem
**Problem**: Can't modify Electrum.app bundle on the DMG.
**Solution**: Always install from source for plugin development.

#### Issue 2: Disk Space on /Applications
**Problem**: Copying large apps may fail with "No space left on device".
**Solution**: Use source installation in home directory.

#### Issue 3: Python Version Conflicts
**Problem**: macOS system Python vs. Homebrew Python.
**Solution**: Use explicit `python3` and create venv:
```bash
/usr/local/bin/python3 -m venv venv
# or
/opt/homebrew/bin/python3 -m venv venv
```

#### Issue 4: PyQt6 Installation on macOS
**Problem**: PyQt6 may require additional system libraries.
**Solution**:
```bash
# Install via Homebrew first (if needed)
brew install qt6

# Then pip install
pip install PyQt6
```

#### Issue 5: File Permissions
**Problem**: Plugin directory permissions.
**Solution**: Ensure your user owns the Electrum directory:
```bash
chown -R $(whoami) ~/src/electrum
```

### Development Best Practices Learned

#### 1. **Start with Minimal Viable Plugin**
```python
# Get THIS working first:
class Plugin(BasePlugin):
    @hook
    def load_wallet(self, wallet, window):
        print("Plugin loaded!")
        QMessageBox.information(None, "Test", "It works!")

# Then add complexity incrementally
```

#### 2. **Use Type Hints for Clarity**
```python
from typing import Optional, Dict, List

def save_data(self, data: Dict) -> None:
    """Type hints help with autocomplete and debugging"""
    pass

def get_pubkey(self, address: str) -> Optional[str]:
    """Optional indicates it may return None"""
    return self.wallet.get_public_key(address)
```

#### 3. **Defensive Programming**
```python
# Always check for None
wallet_name = getattr(self.wallet, 'name', 'Unknown')

# Wrap risky operations
try:
    pubkey = self.wallet.get_public_key(addr)
    if not pubkey:
        raise ValueError("No pubkey found")
except Exception as e:
    self.log(f"[ERROR] {e}")
    QMessageBox.warning(self, "Error", str(e))
    return
```

#### 4. **Educational Error Messages**
```python
# ❌ Bad error message
QMessageBox.warning(self, "Error", "Invalid input")

# ✅ Good error message
QMessageBox.warning(
    self, 
    "Invalid Public Key",
    f"Expected 33-byte compressed pubkey (66 hex chars)\n"
    f"Got: {len(pubkey_hex)} characters\n\n"
    f"Compressed pubkeys start with 02 or 03."
)
```

#### 5. **Resource Management**
```python
# Store resources in plugin directory
logo_path = os.path.join(os.path.dirname(__file__), 'logo.jpg')

# Check existence before loading
if os.path.exists(logo_path):
    pixmap = QPixmap(logo_path)
else:
    self.log("[WARNING] Logo file not found")
```

### Testing Checklist

Based on our development experience:

```
☐ Test on fresh Electrum installation
☐ Test enabling/disabling plugin
☐ Test with empty wallet
☐ Test with wallet containing transactions
☐ Test all input validation
☐ Test with maximum values (large numbers, long strings)
☐ Test error paths (what if wallet.get_public_key() returns None?)
☐ Test on both signet and testnet
☐ Verify mainnet protection works
☐ Check console logs are helpful
☐ Test UI with different screen sizes
☐ Test dialog scrolling with overflow content
☐ Verify auto-saved data persists across restarts
☐ Test with multiple wallets
☐ Check memory leaks (dialog close/reopen)
```

### Common Pitfalls to Avoid

1. **Assuming wallet data is always available**
   - Always check for None
   - Handle wallet close/reload gracefully

2. **Hardcoding file paths**
   - Use `os.path.dirname(__file__)` for plugin resources
   - Use wallet directory for wallet-specific data

3. **Blocking the UI thread**
   - Long operations should use threading
   - Show progress indicators for slow tasks

4. **Not handling exceptions**
   - Uncaught exceptions can crash Electrum
   - Always try/except around risky operations

5. **Ignoring Bitcoin Script encoding rules**
   - Use minimal encoding for integers
   - Follow BIP specifications exactly
   - Test script construction with verification tools

6. **Poor UX for technical features**
   - Add tooltips for complex fields
   - Provide examples
   - Log operations for transparency
   - Include educational messages

### Quick Debugging Commands

**Check if plugin loaded:**
```python
# In Electrum console
gui.plugins.get('yourplugin')
```

**Verify config structure:**
```python
# In terminal, check config file
cat ~/.electrum/signet/config | python3 -m json.tool
```

**Test Bitcoin Script manually:**
```python
# Verify script construction
from electrum.transaction import opcodes
script = bytes.fromhex("your_script_hex")
# Parse and verify each opcode
```

**Monitor Electrum logs:**
```bash
# Run Electrum from terminal
cd ~/src/electrum
source venv/bin/activate
./run_electrum --signet --verbose
```

### Resource Files Best Practices

**Include in plugin directory:**
```
yourplugin/
├── __init__.py
├── manifest.json
├── qt.py
├── logo.jpg              # ✅ Include images
├── README.md             # ✅ Include documentation
├── TESTING.md           # ✅ Include test guide
└── examples/            # ✅ Include usage examples
    └── sample_script.txt
```

**Load resources correctly:**
```python
# Get plugin directory
plugin_dir = os.path.dirname(__file__)

# Load image
logo_path = os.path.join(plugin_dir, 'logo.jpg')
if os.path.exists(logo_path):
    pixmap = QPixmap(logo_path)
    
# Read text file
readme_path = os.path.join(plugin_dir, 'README.md')
with open(readme_path, 'r') as f:
    content = f.read()
```

### Final Recommendations

**For Educational Plugins:**
1. ✅ Add comprehensive logging
2. ✅ Include step-by-step explanations
3. ✅ Show technical details (script hex, breakdown, etc.)
4. ✅ Add disclaimers for experimental features
5. ✅ Protect against mainnet usage if appropriate

**For Production Plugins:**
1. ✅ Extensive error handling
2. ✅ Security audits for fund-handling code
3. ✅ Comprehensive test suite
4. ✅ User documentation
5. ✅ Graceful degradation when features unavailable

**For Hackathon Plugins:**
1. ✅ Focus on one feature done well
2. ✅ Make it visually impressive
3. ✅ Add humor/personality (with disclaimers!)
4. ✅ Include sponsor branding if applicable
5. ✅ Prioritize working demo over completeness

---

## Advanced Implementation Patterns

### Pattern 1: Querying Network for UTXOs at External Addresses

**Problem**: You need to find UTXOs at an address that's NOT in the wallet (like a P2SH timelock address).

**Solution**: Use network's scripthash query:

```python
from electrum import bitcoin
from electrum.transaction import TxOutpoint, PartialTxInput

# Get network from window
network = self.window.network if hasattr(self.window, 'network') else None
if not network:
    raise Exception("No network connection")

# Convert address to scripthash
address = "2MzYTr6rUUPCUGrosJMwa5oDyrkUNbtYgN5"
scripthash = bitcoin.address_to_scripthash(address)

# Query network for UTXOs
utxos = network.run_from_another_thread(network.listunspent_for_scripthash(scripthash))

# Each UTXO has:
# {
#   'tx_hash': 'abc123...',
#   'tx_pos': 0,
#   'value': 100000,
#   'height': 272394
# }

# Build transaction inputs
inputs = []
for utxo in utxos:
    txin = PartialTxInput(
        prevout=TxOutpoint(
            txid=bytes.fromhex(utxo['tx_hash']), 
            out_idx=utxo['tx_pos']
        ),
        nsequence=0xfffffffe  # For CLTV/CSV
    )
    txin._trusted_value_sats = utxo['value']
    inputs.append(txin)
```

**Key Points:**
- `wallet.get_utxos()` only works for addresses IN the wallet
- External addresses require network queries via scripthash
- `run_from_another_thread()` makes async network calls synchronous
- Filter by `height > 0` for confirmed UTXOs only

### Pattern 2: Building Transactions with Custom Scripts

**For P2SH spending with custom redeem scripts:**

```python
from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput
from electrum.bitcoin import hash_160

# Your custom redeem script
redeem_script_hex = "030a2804b17521037f47ce...ac"
script_bytes = bytes.fromhex(redeem_script_hex)

# Build inputs with redeem script
txin = PartialTxInput(prevout=TxOutpoint(...))
txin.script_type = 'p2sh'
txin.redeem_script = script_bytes
txin.nsequence = 0xfffffffe  # For CLTV
txin._trusted_value_sats = utxo_value

# Build transaction with locktime
tx = PartialTransaction.from_io(
    inputs=[txin],
    outputs=[PartialTxOutput.from_address_and_value(dest_addr, amount)],
    locktime=272394  # Block height or timestamp
)

# Sign with wallet
self.wallet.sign_transaction(tx, None)

# Check if complete
if not tx.is_complete():
    raise Exception("Transaction not fully signed")

# Broadcast
txid = network.run_from_another_thread(network.broadcast_transaction(tx))
```

**Critical for CLTV/CSV:**
- Transaction `locktime` must be >= script locktime
- Input `nsequence` must be < `0xffffffff` (use `0xfffffffe`)
- Redeem script must be set on the input
- Sign after building complete transaction

### Pattern 3: Accessing Window and Network

**Problem**: Plugin needs network or window reference.

**Solution**: Store in `__init__` and access safely:

```python
class TimelockDialog(QDialog):
    def __init__(self, parent, plugin):
        super().__init__(parent)
        self.plugin = plugin
        self.wallet = parent.wallet
        self.window = parent  # ElectrumWindow instance
        
    def get_network(self):
        """Safely get network with fallback"""
        if hasattr(self.window, 'network'):
            return self.window.network
        return None
    
    def get_current_height(self):
        """Get current blockchain height"""
        network = self.get_network()
        if network:
            return network.get_local_height()
        return 0
```

**Available on window:**
- `window.network` - Network interface for queries/broadcast
- `window.wallet` - Active wallet
- `window.config` - Configuration object
- `window.gui_object` - GUI manager

### Pattern 4: Real-Time UI Updates with Network Data

**Show live data in UI:**

```python
from PyQt6.QtCore import QTimer

class MyDialog(QDialog):
    def __init__(self, parent, plugin):
        super().__init__(parent)
        self.window = parent
        
        # Create UI elements
        self.height_label = QLabel("Current height: ...")
        
        # Setup auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_height)
        self.timer.start(10000)  # Update every 10 seconds
        
        # Initial update
        self.update_height()
    
    def update_height(self):
        """Update displayed height"""
        network = self.window.network if hasattr(self.window, 'network') else None
        if network:
            height = network.get_local_height()
            self.height_label.setText(f"Current height: {height:,}")
```

### Pattern 5: User Confirmation with Detailed Info

**Show transaction details before broadcast:**

```python
from PyQt6.QtWidgets import QMessageBox

# Build detailed confirmation
result = QMessageBox.question(
    self,
    "Confirm Transaction",
    f"Ready to broadcast transaction:\n\n"
    f"From: {input_address}\n"
    f"To: {output_address}\n"
    f"Amount: {amount:,} sats ({amount/100_000_000:.8f} BTC)\n"
    f"Fee: {fee:,} sats ({fee_rate} sat/vbyte)\n"
    f"Size: {tx.estimated_size()} bytes\n\n"
    f"TXID (preview):\n{tx.txid()}\n\n"
    f"Broadcast now?",
    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
)

if result == QMessageBox.StandardButton.Yes:
    # User confirmed
    try:
        txid = network.run_from_another_thread(network.broadcast_transaction(tx))
        QMessageBox.information(
            self, 
            "Success! 🎉",
            f"Transaction broadcast!\n\nTXID:\n{txid}\n\n"
            f"View on explorer:\nhttps://mempool.space/signet/tx/{txid}"
        )
    except Exception as e:
        QMessageBox.critical(self, "Broadcast Failed", f"Error:\n\n{e}")
```

### Pattern 6: Debugging with Console Logging

**Add verbose logging that appears in Electrum console:**

```python
import logging

logger = logging.getLogger(__name__)

class MyPlugin(BasePlugin):
    def __init__(self, parent, config, name):
        super().__init__(parent, config, name)
        
    def log(self, message: str):
        """Log to console and stdout"""
        msg = f"[MyPlugin] {message}"
        logger.info(msg)
        print(msg)  # Also print for visibility

# Usage
self.log("[SWEEP] Starting sweep process...")
self.log(f"[SWEEP] Found {len(utxos)} UTXOs")
self.log(f"[SWEEP] Total value: {total:,} sats")
```

**View logs:**
- In Electrum: View → Show Console
- Or run from terminal: `./run_electrum --signet` (logs to stdout)

### Pattern 7: Handling Multiple Confirmation States

**Filter UTXOs by confirmation:**

```python
# Get all UTXOs
utxos = network.run_from_another_thread(network.listunspent_for_scripthash(sh))

# Separate by confirmation status
confirmed = [u for u in utxos if u.get('height', 0) > 0]
unconfirmed = [u for u in utxos if u.get('height', 0) <= 0]

if not confirmed:
    QMessageBox.warning(
        self,
        "No Confirmed UTXOs",
        f"Found {len(utxos)} UTXO(s) but none are confirmed yet.\n\n"
        f"Confirmed: 0\n"
        f"Unconfirmed: {len(unconfirmed)}\n\n"
        f"Wait for confirmations and try again."
    )
    return

# Use only confirmed
total = sum(u['value'] for u in confirmed)
```

---

## One-Shot Prompt Template

When using this guide with AI assistants, structure your prompt like this:

```
I want to create an Electrum plugin that [FUNCTIONALITY].

Requirements:
- Target GUI: [qt/android/both]
- Main feature: [DESCRIPTION]
- Hooks needed: [password_dialog/load_wallet/etc.]
- Additional features: [LIST]
- Platform: [macOS/Linux/Windows]
- Network: [testnet/signet/regtest]

CRITICAL CONSTRAINTS (from lessons learned):

Installation (macOS):
- Install Electrum from source (DMG is read-only)
- Symlink plugin to ~/src/electrum/electrum/plugins/yourplugin
- Install dependencies: PyQt6, cryptography, etc.

Configuration:
- Use nested dict structure: {"plugins": {"name": {"enabled": true}}}
- NOT flat keys like "plugins.name.enabled"

UI/UX:
- Public key fields: minimum 550px width for 66 hex chars
- Use QScrollArea for dialogs with overflow
- Dialog size: minimum 900x800px
- Auto-load wallet data AFTER UI construction
- Use monospace font (Courier) for hex data

Logging:
- Use print_error() for console output: print_error("[PluginName] message")
- Make it verbose and educational
- Log every major step

Safety:
- Add mainnet protection check in __init__
- Validate all user inputs
- Clear error messages with explanations
- Include disclaimers for experimental features

Data Persistence:
- Save to wallet directory, not plugin directory
- Use JSON format for readability
- Auto-save after important operations

Bitcoin Script:
- Use minimal encoding for integers (little-endian)
- Verify opcode construction matches BIP specs
- Test scripts before using

Please generate:
1. Complete manifest.json
2. Plugin implementation (qt.py or appropriate file)
3. Any resource files needed
4. Installation instructions
5. README with usage guide

Follow the patterns from the VirtualKeyboard example and use proper
Electrum APIs. Include comprehensive error handling and educational logging.
```

---

## Conclusion

You now have everything needed to build Electrum plugins:

✅ Understanding of plugin architecture  
✅ Knowledge of manifest.json structure  
✅ Familiarity with the Plugin class and hooks system  
✅ Complete VirtualKeyboard example analysis  
✅ Development workflow and best practices  
✅ **Lessons learned from real macOS development**  
✅ **Solutions to common gotchas and pitfalls**  
✅ **Advanced patterns for logging, storage, and UI**  
✅ Security considerations  
✅ Publishing and distribution guide  

**Next Steps:**
1. Choose a plugin idea
2. **If on macOS: Install Electrum from source first**
3. Set up development environment with symlink
4. Start with the quick start template
5. **Use nested dict structure for config**
6. **Add comprehensive logging with print_error()**
7. Iterate rapidly with debug prints
8. Test thoroughly on testnet/signet
9. Build and distribute

**Remember**: Start simple, test frequently, and build upon working code. The plugin system is powerful—use it to extend Electrum in creative ways!

**Key Takeaway**: Real-world plugin development taught us that proper installation, configuration structure, UI sizing, and educational logging are just as important as the core functionality. Follow the lessons learned to avoid common pitfalls.

---

**Good luck with your hackathon project! 🚀**

*Last updated: January 2025*
*Includes lessons learned from building CHECKLOCKTIMEVERIFY plugin on macOS*
