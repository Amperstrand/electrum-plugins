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
13. [Pattern Index](#pattern-index)
14. [Troubleshooting Common Plugin Issues](#troubleshooting-common-plugin-issues)
15. [Auditing Plugins — Quick Workflow](#auditing-plugins--quick-workflow)

---

## Pattern Index

### Core Plugin Patterns (Implicit 1-12)

These patterns are covered in the main sections of the guide:

1. **BasePlugin Architecture** - See [Plugin Architecture](#plugin-architecture)
2. **Manifest Configuration** - See [The manifest.json File](#the-manifestjson-file)
3. **Hook System** - See [Hooks System](#hooks-system)
4. **Settings/Configuration UI** - See [Plugin Class](#the-plugin-class)
5. **GUI Integration (Qt/QML)** - See [VirtualKeyboard Plugin Deep Dive](#virtualkeyboard-plugin-deep-dive)
6. **Wallet Integration** - See [Plugin Architecture](#plugin-architecture)
7. **Network Integration** - See [Development Workflow](#development-workflow)
8. **Lightning Integration** - See [Examples of Existing Plugins](#examples-of-existing-plugins)
9. **Transaction Handling** - See [Security Considerations](#security-considerations)
10. **Custom Transaction Types** - See [Examples of Existing Plugins](#examples-of-existing-plugins)
11. **Custom Wallet Types** - See [Examples of Existing Plugins](#examples-of-existing-plugins)
12. **Error Handling & User Feedback** - See [Security Considerations](#security-considerations)

### Hardware Wallet Patterns (13-23)

- **[Pattern 13: PIN and Passphrase Handling](#pattern-13-pin-and-passphrase-handling)** - Trezor/KeepKey matrix PIN, host passphrase
- **[Pattern 14: Threaded Device Invocation](#pattern-14-threaded-device-invocation-with-ui-callbacks)** - `@runs_in_hwd_thread` decorator
- **[Pattern 15: Feature/Capability Gating](#pattern-15-featurecapability-gating)** - Firmware version checks
- **[Pattern 16: Validating Media Assets](#pattern-16-validating-and-transforming-media-assets-homescreen)** - Homescreen validation (Trezor)
- **[Pattern 17: PSBT & File-Based Workflows](#pattern-17-psbt--file-based-workflows-coldcard-like-devices)** - Coldcard microSD/USB
- **[Pattern 18: Device Authenticity & MiTM Verification](#pattern-18-device-authenticity--mitm-verification)** - Coldcard session key
- **[Pattern 19: UX Busy Wrapping](#pattern-19-ux-busy-wrapping--centralized-error-handling)** - Coldcard `wrap_busy` decorator
- **[Pattern 20: Opportunistic Xpub Filling](#pattern-20-opportunistic-xpub-filling)** - Coldcard privacy pattern
- **[Pattern 21: Worker → UI Input (BlockingQueuedConnection)](#pattern-21-worker--ui-input-blockingqueuedconnection)** - BitBox02 multisig naming
- **[Pattern 22: Pairing & Client Retrieval](#pattern-22-pairing--client-retrieval-best-practices)** - BitBox02 `scan_now=False`
- **[Pattern 23: Character-Based Recovery UI](#pattern-23-character-based-recovery-ui-keepkey-like)** - KeepKey QEventLoop pattern

### General Plugin Patterns (24-26)

- **[Pattern 24: WaitingDialog for Blocking Operations](#pattern-24-waitingdialog-for-blocking-operations)** - Background worker threads
- **[Pattern 25: Optional Dependencies](#pattern-25-optional-dependencies-with-graceful-degradation)** - Library availability checks
- **[Pattern 26: Air-Gapped Transaction Workflows](#pattern-26-air-gapped-transaction-workflows)** - Audio/QR/File channels

### Network & Server Patterns (27-30)

- **[Pattern 27: Server Sync with Client-Side Encryption](#pattern-27-server-sync-with-client-side-encryption)** - Labels encrypted sync
- **[Pattern 28: Nostr Protocol Integration](#pattern-28-nostr-protocol-integration)** - NWC WebSocket relays
- **[Pattern 29: HTTP Server Plugin](#pattern-29-http-server-plugin)** - Payserver daemon mode
- **[Pattern 30: Nostr Multisig Coordination](#pattern-30-nostr-multisig-coordination)** - PSBT Nostr decentralized

### Jade-Specific Patterns

- **Serial/COM Transport Enumeration** - See [Jade-Specific Patterns](#jade-specific-patterns)
- **Simulator Integration & Test Seed** - See [Jade-Specific Patterns](#jade-specific-patterns)
- **HTTP Proxy for Device Requests** - See [Jade-Specific Patterns](#jade-specific-patterns)
- **Multisig Registration** - See [Jade-Specific Patterns](#jade-specific-patterns)
- **PSBT Signing & Signature Merge** - See [Jade-Specific Patterns](#jade-specific-patterns)

### Quick Pattern Lookup

**By Plugin Type:**
- Hardware Wallets → Patterns 13-23 + Jade-Specific
- Network/Server → Patterns 27-30
- Air-Gapped → Patterns 24, 26
- UI/Threading → Patterns 14, 21, 23, 24
- Security → Patterns 18, 20, 27

**By Use Case:**
- Device signing → Patterns 13-20
- Multisig coordination → Patterns 21, 22, 30, Jade multisig
- Server operations → Patterns 27, 28, 29
- Offline workflows → Pattern 26
- Cross-device sync → Pattern 27

---

## Plan to Update Context (systematic)

Purpose: turn this document into the canonical, living reference used by the VibeCoding team when creating Electrum plugins. The plan below defines a repeatable audit process to ensure the guide contains concrete, up-to-date, and actionable context for every plugin pattern we expect to implement.

High-level Process:

1. Inventory: enumerate all plugins in `electrum/electrum/plugins/` (internal and local symlinks).
2. Per-plugin Audit: for each plugin perform a lightweight audit and record findings in a per-plugin checklist/report.
3. Identify Gaps: compare audit findings with this guide and record inconsistencies, missing code patterns, API changes, dependency notes, and UX patterns.
4. Update Guide: for each class of gap, add a targeted section to this guide containing code snippets, gotchas, and best-practice patterns.
5. Validate: add a minimal test or manual verification step in the plugin repo and update the guide with the test procedure.
6. Persist: save per-plugin audit reports under `docs/plugin-audits/` and add a changelog entry to this guide for traceability.

Deliverables:
- `ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md` updated with new patterns and concrete examples
- `docs/plugin-audits/<plugin-name>.md` per-plugin audit notes (short, actionable)
- `CHANGELOG.md` entry summarizing the audit and guide updates

Per-Plugin Audit Checklist (template to use):

- Plugin name: <plugin>
- Path: <repo-relative path>
- Purpose / feature summary: <one line>
- Manifest: does it declare platforms / hooks / resources? (yes/no + notes)
- Main module(s): (qt.py, __init__.py, etc.) — key functions/classes
- Hooks used: (list of hook names)
- GUI patterns: dialogs, tabs, QWidgets used, sizing patterns
- Network usage: does plugin use `window.network` / `network.run_from_another_thread()` / merkle/ ElectrumX calls
- Wallet access: read-only, key lookups, signing
- Storage: where does the plugin store persistent data? (wallet dir vs plugin dir)
- Dependencies: external pip packages or system libs (PyQt6, cryptography, libs)
- Mainnet protection: implemented? (yes/no)
- Security notes: any suspicious behavior or fund-handling risk
- Tests included: automated/manual instructions
- Inconsistencies vs guide: list of guide sections that must be updated
- Suggested guide updates: (bullet list of new sections/snippets to add)
- Audit status: not-started / in-progress / complete

Initial Inventory (run-time snapshot):
- audio_modem
- bitbox02
- checklocktimeverify (local symlink)
- coldcard
- digitalbitbox
- jade
- keepkey
- labels
- ledger
- nwc
- payserver
- psbt_nostr
- revealer
- safe_t
- swapserver
- timelock_recovery
- trezor
- trustedcoin
- watchtower

Initial Prioritization (suggested):
1. Hardware wallet integrations (ledger, trezor, coldcard, bitbox02, keepkey, jade) — high priority because of signing patterns and secure UI
2. Timelock / recovery (timelock_recovery, checklocktimeverify) — medium priority for script construction and sweep patterns
3. PSBT/Nostr/Swap/Server integrations (psbt_nostr, swapserver, payserver) — medium priority
4. UX/support/aux (labels, revealer, audio_modem, watchtower) — lower priority

Repository Changes to Make Now:
- Create folder `docs/plugin-audits/` and commit an empty README for the audits
- Add `CHANGELOG.md` to track guide updates and dates
- Add `scripts/audit-plugins.sh` helper to run a list of lightweight checks (manifest presence, main module, syntax check)

Next Action (today):
1. Add the `Plan to Update Context` section and the per-plugin audit checklist into `ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md` (done).
2. Create `docs/plugin-audits/` and add `audio_modem.md` with a first-pass audit summary (we will iterate). — I'll create the file next unless you prefer to do it.

---

## Overview

Electrum's plugin system allows developers to extend functionality without modifying the core codebase. Plugins can add features to the GUI, provide new wallet capabilities, enable integrations, and more.

**Key Benefits:**
- Modular architecture keeps core code lean
- Easy to enable/disable via **Menu Bar** > **Tools** > **Plugins**
- Support for both internal (shipped with Electrum) and external (third-party) plugins
- GUI-specific implementations (Qt, Android, etc.)

### Plugin Development Philosophy

**When to Create a Plugin** (vs. Core Contribution):

- ✅ **Plugin**: Feature requires non-Python libraries (e.g., hardware device drivers, audio codecs)
- ✅ **Plugin**: Feature requires communication with remote servers (other than Electrum servers)
- ✅ **Plugin**: Feature introduces new dependencies (keeps core lean)
- ✅ **Plugin**: Feature is experimental or use-case specific
- ❌ **Core**: Core wallet functionality (address generation, signing, etc.)
- ❌ **Core**: Essential security features
- ❌ **Core**: Universal protocol improvements (SPV, transaction handling)

**Maintenance Expectations:**

1. **Developer Responsibility**: Plugin developers must maintain their code
2. **Electrum Compatibility**: Core changes may require plugin updates
3. **Easy Maintenance**: Plugins must be simple to maintain or they'll be rejected
4. **No Code Duplication**: Don't duplicate existing Electrum code
5. **Removability**: Plugins must be safely removable without threatening users
6. **Architecture Fit**: Must follow Electrum's conventions and patterns

**Acceptance Criteria:**

- Clean, maintainable code
- Follows Electrum patterns (see Pattern Index)
- Clear documentation
- No unnecessary dependencies
- Graceful failure modes
- User safety paramount (especially for fund-handling)

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
| `icon` | string | No | Icon filename (SVG or PNG) for GUI display. File must be in plugin root. |
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
  "icon": "keyboard-icon.svg",
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
    
    # Add keyboard to grid spanning 3 columns
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

## Daemon & CLI Plugin Configuration

### Enabling Plugins in Daemon Mode

Some plugins (like `swapserver` and `payserver`) are designed to run in daemon mode. They can be enabled via command line:

```bash
# Enable plugin via config
electrum setconfig plugins.swapserver.enabled True

# Restart daemon to load plugin
electrum stop
electrum daemon -d
electrum load_wallet
```

### Swapserver Plugin Example

**Purpose**: Offer submarine swaps to Electrum users (earn fees for liquidity)

**Configuration:**

```bash
# Enable the plugin
electrum setconfig plugins.swapserver.enabled True

# Set swap fee (default 5000 = 0.5%)
electrum setconfig plugins.swapserver.fee_millionths 5000

# Set proof-of-work target for ranking (default 30)
# Higher = better ranking but takes longer to compute
electrum setconfig swapserver_pow_target 30

# Configure Nostr relays (comma-separated)
electrum setconfig nostr_relays "wss://relay1.com,wss://relay2.com"

# Restart to apply
electrum stop
electrum daemon -d
electrum load_wallet
```

**Requirements:**
- Funded Lightning channels with balanced liquidity
- On-chain balance for swap operations
- Gossip enabled (optional but recommended):
  ```bash
  electrum setconfig use_gossip True
  ```

**Key Features:**
- No port forwarding required (works behind firewall)
- Announces via Nostr relays
- PoW-based spam protection
- Automatic swap execution

### Payserver Plugin Example

**Purpose**: Run HTTP server for receiving Bitcoin payments (merchant integration)

**Configuration:**

```bash
# Set SSL certificate (required for BIP-70)
electrum setconfig ssl_keyfile /path/to/ssl/privkey.pem
electrum setconfig ssl_certfile /path/to/ssl/fullchain.pem

# Configure server address
electrum setconfig payserver_address yourdomain.com:443

# Enable plugin
electrum setconfig plugins.payserver.enabled True

# Start daemon
electrum daemon -d
electrum load_wallet
```

**Creating Payment Requests:**

```bash
# On-chain payment request
electrum add_request 0.5 -m "Product XYZ"
# Returns:
# - bip70_url: BIP-70 signed payment request
# - view_url: Web page displaying request

# Lightning payment request
electrum add_request 0.0001 --lightning --memo "Coffee"
```

**Response Example:**

```json
{
  "URI": "bitcoin:bc1q...?amount=0.5&message=test",
  "address": "bc1q...",
  "amount_BTC": "0.5",
  "bip70_url": "https://yourdomain.com:443/bip70/bc1q....bip70",
  "view_url": "https://yourdomain.com:443/r/pay?id=bc1q...",
  "status": 0,
  "status_str": "Expires in about 1 hour"
}
```

**Key Features:**
- BIP-70 signed payment requests (SSL required)
- WebSocket updates (payment page auto-refreshes)
- QR code generation
- Both on-chain and Lightning support
- Read-only wallet (use watching-only wallet for security)

**Security Best Practice:**

1. Create full wallet on secure machine
2. Export master public key: `electrum getmpk`
3. Restore watching-only wallet on server: `electrum restore xpub...`
4. Server can receive payments but cannot spend

### Plugin Configuration Patterns

**Reading Plugin-Specific Config:**

```python
class Plugin(BasePlugin):
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        
        # Read plugin-specific config with default
        self.fee = config.get('plugins.myplugin.fee', 1000)
        
        # Boolean config
        self.enabled = config.get('plugins.myplugin.enabled', False)
```

**Setting Config from CLI:**

```bash
# User sets via command line
electrum setconfig plugins.myplugin.fee 2000

# Or directly edit ~/.electrum/config
{
  "plugins": {
    "myplugin": {
      "enabled": true,
      "fee": 2000
    }
  }
}
```

**Plugin Lifecycle in Daemon Mode:**

```python
class Plugin(BasePlugin):
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.network = None
        
    @hook
    def set_network(self, network):
        """Called when daemon starts"""
        self.network = network
        # Start background tasks here
        
    @hook
    def close_wallet(self, wallet):
        """Called when daemon stops"""
        # Cleanup tasks here
```

---

## Daemon & CLI Plugin Configuration

### Enabling Plugins in Daemon Mode

Some plugins (like `swapserver` and `payserver`) are designed to run in daemon mode. They can be enabled via command line:

```bash
# Enable plugin via config
electrum setconfig plugins.swapserver.enabled True

# Restart daemon to load plugin
electrum stop
electrum daemon -d
electrum load_wallet
```

### Swapserver Plugin Example

**Purpose**: Offer submarine swaps to Electrum users (earn fees for liquidity)

**Configuration:**

```bash
# Enable the plugin
electrum setconfig plugins.swapserver.enabled True

# Set swap fee (default 5000 = 0.5%)
electrum setconfig plugins.swapserver.fee_millionths 5000

# Set proof-of-work target for ranking (default 30)
# Higher = better ranking but takes longer to compute
electrum setconfig swapserver_pow_target 30

# Configure Nostr relays (comma-separated)
electrum setconfig nostr_relays "wss://relay1.com,wss://relay2.com"

# Restart to apply
electrum stop
electrum daemon -d
electrum load_wallet
```

**Requirements:**
- Funded Lightning channels with balanced liquidity
- On-chain balance for swap operations
- Gossip enabled (optional but recommended):
  ```bash
  electrum setconfig use_gossip True
  ```

**Key Features:**
- No port forwarding required (works behind firewall)
- Announces via Nostr relays
- PoW-based spam protection
- Automatic swap execution

### Payserver Plugin Example

**Purpose**: Run HTTP server for receiving Bitcoin payments (merchant integration)

**Configuration:**

```bash
# Set SSL certificate (required for BIP-70)
electrum setconfig ssl_keyfile /path/to/ssl/privkey.pem
electrum setconfig ssl_certfile /path/to/ssl/fullchain.pem

# Configure server address
electrum setconfig payserver_address yourdomain.com:443

# Enable plugin
electrum setconfig plugins.payserver.enabled True

# Start daemon
electrum daemon -d
electrum load_wallet
```

**Creating Payment Requests:**

```bash
# On-chain payment request
electrum add_request 0.5 -m "Product XYZ"
# Returns:
# - bip70_url: BIP-70 signed payment request
# - view_url: Web page displaying request

# Lightning payment request
electrum add_request 0.0001 --lightning --memo "Coffee"
```

**Response Example:**

```json
{
  "URI": "bitcoin:bc1q...?amount=0.5&message=test",
  "address": "bc1q...",
  "amount_BTC": "0.5",
  "bip70_url": "https://yourdomain.com:443/bip70/bc1q....bip70",
  "view_url": "https://yourdomain.com:443/r/pay?id=bc1q...",
  "status": 0,
  "status_str": "Expires in about 1 hour"
}
```

**Key Features:**
- BIP-70 signed payment requests (SSL required)
- WebSocket updates (payment page auto-refreshes)
- QR code generation
- Both on-chain and Lightning support
- Read-only wallet (use watching-only wallet for security)

**Security Best Practice:**

1. Create full wallet on secure machine
2. Export master public key: `electrum getmpk`
3. Restore watching-only wallet on server: `electrum restore xpub...`
4. Server can receive payments but cannot spend

### Plugin Configuration Patterns

**Reading Plugin-Specific Config:**

```python
class Plugin(BasePlugin):
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        
        # Read plugin-specific config with default
        self.fee = config.get('plugins.myplugin.fee', 1000)
        
        # Boolean config
        self.enabled = config.get('plugins.myplugin.enabled', False)
```

**Setting Config from CLI:**

```bash
# User sets via command line
electrum setconfig plugins.myplugin.fee 2000

# Or directly edit ~/.electrum/config
{
  "plugins": {
    "myplugin": {
      "enabled": true,
      "fee": 2000
    }
  }
}
```

**Plugin Lifecycle in Daemon Mode:**

```python
class Plugin(BasePlugin):
    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.network = None
        
    @hook
    def set_network(self, network):
        """Called when daemon starts"""
        self.network = network
        # Start background tasks here
        
    @hook
    def close_wallet(self, wallet):
        """Called when daemon stops"""
        # Cleanup tasks here
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

## Hardware Wallet Integration Patterns

Hardware wallet plugins require special considerations. They interface with external devices (USB/HID, transports) and must be robust to missing libraries, device disconnects, firmware issues, and concurrency. Below are common patterns distilled from auditing the Ledger, Trezor, Coldcard, and other hardware wallet plugins.

### Universal Hardware Wallet Structure

All hardware wallet plugins follow this base structure:

```python
from electrum.hw_wallet import HW_PluginBase, HardwareClientBase
from electrum.keystore import Hardware_KeyStore
from electrum.plugin import runs_in_hwd_thread

class MyHardwareWallet_Client(HardwareClientBase):
    """Device communication layer"""
    
    @runs_in_hwd_thread
    def sign_transaction(self, tx, ...):
        # Device signing logic
        pass
    
    @runs_in_hwd_thread
    def show_address(self, address_path, ...):
        # Show address on device screen
        pass

class MyHardwareWallet_KeyStore(Hardware_KeyStore):
    """Wallet keystore integration"""
    hw_type = 'myhardwarewallet'
    device = 'My Hardware Wallet'
    
    @runs_in_hwd_thread
    def sign_transaction(self, tx, password):
        client = self.get_client()
        # Delegate to client
        
class MyHardwareWalletPlugin(HW_PluginBase):
    """Main plugin class"""
    keystore_class = MyHardwareWallet_KeyStore
    
    @runs_in_hwd_thread
    def create_client(self, device, handler):
        # Instantiate and return client
        pass
```

### Manifest Declaration

```json
{
  "name": "myhardwarewallet",
  "registers_keystore": ["hardware", "myhardwarewallet", "My Hardware Wallet"],
  "requires": [["device_library", "github.com/vendor/library"]],
  "available_for": ["qt", "cmdline"]
}
```

**Key fields:**
- `registers_keystore`: `["hardware", <identifier>, <display_name>]` tells Electrum this provides a hardware keystore
- `requires`: External dependencies with installation URLs for user guidance

### 1. Mandatory Patterns (All Hardware Wallets)

**Pattern 1.1: Optional Dependency Import (Pattern 25)**
```python
try:
    import device_library
    LIBRARY_AVAILABLE = True
except ImportError:
    LIBRARY_AVAILABLE = False

class Plugin(HW_PluginBase):
    def __init__(self, parent, config, name):
        HW_PluginBase.__init__(self, parent, config, name)
        self.libraries_available = self.check_libraries_available()
```

**Pattern 1.2: Threading Safety (Pattern 14)**
```python
@runs_in_hwd_thread
def sign_transaction(self, tx, password):
    # Runs in hardware device thread, not UI thread
    # Prevents deadlocks and UI freezing
    pass
```

**Pattern 1.3: Address Verification**
```python
@runs_in_hwd_thread
def show_address(self, sequence, txin_type):
    client = self.get_client()
    hw_address = client.show_address(path, ...)
    
    # Critical: compare device output to Electrum computation
    if hw_address != expected_address:
        self.handler.show_error('Address mismatch!')
        raise UserFacingException('Device address verification failed')
```

**Pattern 1.4: Wizard Integration**
```python
def extend_wizard(self, wizard):
    views = {
        'myhw_start': {'next': 'myhw_xpub'},
        'myhw_xpub': {
            'next': lambda d: wizard.wallet_password_view(d) if wizard.last_cosigner(d) 
                    else 'multisig_cosigner_keystore',
            'accept': wizard.maybe_master_pubkey
        }
    }
    wizard.navmap_merge(views)
```

### 2. Common Optional Patterns

**Pattern 2.1: Client Factory (Ledger, Trezor)**
```python
@staticmethod
def construct_new(transport, device, plugin):
    """Factory method to select appropriate client implementation"""
    try:
        # Try modern client
        modern_client = ModernClient(transport)
        return Modern_HW_Client(modern_client, plugin)
    except:
        # Fallback to legacy
        return Legacy_HW_Client(transport, plugin)
```

**Pattern 2.2: Firmware Version Gating (All)**
```python
MIN_SUPPORTED_VERSION = (1, 6, 0)

@runs_in_hwd_thread
def create_client(self, device, handler):
    client = MyClient(device.path)
    version = client.get_version()
    
    if version < MIN_SUPPORTED_VERSION:
        msg = f"Firmware too old. Please update at https://vendor.com/update"
        handler.show_error(msg)
        raise OutdatedHwFirmwareException(msg)
    
    return client
```

**Pattern 2.3: Device Pairing (BitBox02, Jade)**
```python
def is_pairable(self):
    return True

@runs_in_hwd_thread  
def pair_device(self, device_info):
    # Perform pairing handshake
    # Store pairing token/session info
    pass
```

### 3. Specialized Patterns by Use Case

**File-Based PSBT (Coldcard) — Pattern 17**
- Upload PSBT to device via microSD/USB
- Poll for signing completion
- Download signed PSBT

**MiTM Verification (Coldcard) — Pattern 18**
- Verify device authenticity via signed session key
- Compare against expected xpub fingerprint

**Serial/COM Transport (Jade)**
- Enumerate serial ports by VID/PID
- Use `serial.tools.list_ports` for device discovery

**Multisig Registration (Jade, Ledger)**
- Register multisig wallet metadata on device
- Use deterministic naming (e.g., `'ele' + sha256(fingerprint)[:12]`)

### 4. Hardware Wallet Comparison Matrix

| Feature | Ledger | Trezor | Coldcard | Jade | BitBox02 | KeepKey | Safe-T | DigitalBitbox | Total |
|---------|--------|--------|----------|------|----------|---------|--------|---------------|-------|
| **Transport** | USB/HID | USB/HID | USB+SD | Serial | USB/HID | USB/HID | USB/HID | USB/HID | 8/9 USB |
| **PIN Entry** | On-device | Matrix | On-device | On-device | On-device | Matrix | Matrix | Basic | 3 Matrix |
| **Passphrase** | ✅ On-dev | ✅ Host | ✅ | ✅ | ❌ | ✅ Host | ✅ Host | ✅ Basic | 7/9 |
| **PSBT** | ✅ | ❌ Direct | ✅ File | ✅ | ❌ | ❌ | ❌ | ❌ | 3/9 |
| **Multisig Reg** | ✅ | ❌ | ❌ | ✅ Determ | ✅ UI | ❌ | ❌ | ❌ | 3/9 |
| **Legacy Fallback** | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | 4/9 |
| **Simulator** | ❌ | ✅ | ✅ | ✅ qemu | ❌ | ❌ | ❌ | ❌ | 3/9 |
| **Address Verify** | ✅ Screen | ✅ Screen | ✅ Screen | ✅ Screen | ✅ Screen | ✅ Screen | ✅ Screen | ✅ Screen | 9/9 |
| **Firmware Gate** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | 5/9 |
| **Settings UI** | ❌ | ✅ Rich | ✅ | ❌ | ❌ | ✅ Rich | ✅ Rich | ✅ Simple | 5/9 |
| **Active Dev** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Limited | ⚠️ Limited | ❌ Legacy | 5/9 |
| **Protocol** | Ledger | Trezor | Coldcard | Jade | BitBox02 | Trezor | Trezor | Custom | - |
| **Codebase (qt.py)** | ~10KB | ~30KB | ~11KB | ~2KB | ~5KB | ~29KB | ~26KB | ~4KB | - |

**Key Insights:**
- **Universal**: All 9 wallets verify addresses on-device (security baseline)
- **Matrix PIN**: Trezor, KeepKey, Safe-T share host-side PIN matrix pattern (keylogger protection)
- **PSBT**: Only Coldcard (file), Jade, and Ledger support PSBT workflows
- **Simulator**: Trezor, Coldcard, Jade enable automated testing
- **Trezor Protocol**: Trezor, KeepKey, Safe-T share compatible protocol (3 wallets)
- **Legacy**: DigitalBitbox deprecated, succeeded by BitBox02
- **Complexity**: Trezor/KeepKey/Safe-T largest codebases (~26-30KB) due to rich UI

**Development Recommendations:**
- **Study Ledger** for client factory and legacy fallback patterns
- **Study Trezor** for comprehensive PIN/passphrase/settings UI
- **Study Coldcard** for file-based PSBT and MiTM verification
- **Study Jade** for serial transport and simulator integration
- **Study BitBox02** for blocking UI input and pairing flows
- **Study KeepKey** for character-based recovery patterns

**Key Takeaways:**
- **All** require `@runs_in_hwd_thread` for device operations
- **All** must verify addresses on-device and compare with host
- **Most** support optional dependencies with graceful degradation
- **File-based** workflows (Coldcard) require different UX patterns
- **Serial devices** (Jade) need custom enumeration logic

### 5. Testing Recommendations

**Unit Tests:**
- Mock device client with predictable responses
- Test client factory selection logic
- Verify version gating and error messages

**Integration Tests:**
- Simulator-based tests (Trezor, Coldcard, Jade support simulators)
- Device connect/disconnect scenarios
- Firmware upgrade flows

**Manual Testing Checklist:**
```markdown
- [ ] Device enumeration (plug/unplug)
- [ ] Wizard flow (new wallet creation)
- [ ] Address verification (compare on-device vs Electrum)
- [ ] Transaction signing (single-sig and multisig)
- [ ] Firmware version check (test with old firmware)
- [ ] Library missing scenario (uninstall deps, verify graceful failure)
- [ ] Error messages (clear, actionable instructions)
```

### 6. Hardware Wallet Wizard Integration

**Important**: Hardware wallet plugins are **not** displayed in the standard plugin list (Menu > Tools > Plugins). Instead, they're integrated into the **New Wallet Wizard**.

**Wizard Integration Pattern:**

```python
class MyHardwareWalletPlugin(HW_PluginBase):
    def __init__(self, parent, config, name):
        HW_PluginBase.__init__(self, parent, config, name)
        # Plugin automatically appears in wizard when enabled
```

**Manifest Requirements:**

```json
{
  "name": "myhardwarewallet",
  "fullname": "My Hardware Wallet",
  "registers_keystore": ["hardware", "myhw", "My Hardware Wallet"],
  "available_for": ["qt", "cmdline"],
  "requires": [
    ["hidapi", "https://pypi.org/project/hidapi/"]
  ]
}
```

**The `registers_keystore` field:**
- First element: Always `"hardware"` for hardware wallets
- Second element: Keystore type identifier (unique, lowercase)
- Third element: Display name in wizard

**The `requires` field:**
- Array of `["package_name", "install_url"]` tuples
- Shows installation instructions if dependency missing
- Common dependencies: `hidapi`, `btchip-python`, `trezor`, `ckcc-protocol`

**Wizard Flow:**

1. User selects "Create new wallet" or "Restore wallet"
2. Wizard shows "Use a hardware device" option
3. User selects your hardware wallet from list
4. Your plugin's `create_client()` method is called
5. Device enumeration and pairing occurs
6. Wallet is created with `Hardware_KeyStore`

**Third-Party Hardware Wallet Distribution:**

You can distribute a hardware wallet plugin as a `.zip` file including all Python dependencies:

```bash
# Include all dependencies in plugin directory
myhardwarewallet/
├── __init__.py
├── manifest.json
├── qt.py
├── cmdline.py
└── vendor/           # Bundle your dependencies
    ├── hidapi.py
    └── device_library/
```

**Note**: Non-Python dependencies (like `hidapi` shared libraries) are typically bundled in Electrum binaries. See [requirements-hw.txt](https://github.com/spesmilo/electrum/blob/master/contrib/requirements/requirements-hw.txt).

**User Import Flow:**

1. User downloads your `.zip` file
2. Opens Electrum wizard
3. Clicks "Import hardware wallet plugin"
4. Selects your `.zip` file
5. Plugin is extracted and registered
6. User can now create wallets with your device

### 6. Hardware Wallet Wizard Integration

**Important**: Hardware wallet plugins are **not** displayed in the standard plugin list (Menu > Tools > Plugins). Instead, they're integrated into the **New Wallet Wizard**.

**Wizard Integration Pattern:**

```python
class MyHardwareWalletPlugin(HW_PluginBase):
    def __init__(self, parent, config, name):
        HW_PluginBase.__init__(self, parent, config, name)
        # Plugin automatically appears in wizard when enabled
```

**Manifest Requirements:**

```json
{
  "name": "myhardwarewallet",
  "fullname": "My Hardware Wallet",
  "registers_keystore": ["hardware", "myhw", "My Hardware Wallet"],
  "available_for": ["qt", "cmdline"],
  "requires": [
    ["hidapi", "https://pypi.org/project/hidapi/"]
  ]
}
```

**The `registers_keystore` field:**
- First element: Always `"hardware"` for hardware wallets
- Second element: Keystore type identifier (unique, lowercase)
- Third element: Display name in wizard

**The `requires` field:**
- Array of `["package_name", "install_url"]` tuples
- Shows installation instructions if dependency missing
- Common dependencies: `hidapi`, `btchip-python`, `trezor`, `ckcc-protocol`

**Wizard Flow:**

1. User selects "Create new wallet" or "Restore wallet"
2. Wizard shows "Use a hardware device" option
3. User selects your hardware wallet from list
4. Your plugin's `create_client()` method is called
5. Device enumeration and pairing occurs
6. Wallet is created with `Hardware_KeyStore`

**Third-Party Hardware Wallet Distribution:**

You can distribute a hardware wallet plugin as a `.zip` file including all Python dependencies:

```bash
# Include all dependencies in plugin directory
myhardwarewallet/
├── __init__.py
├── manifest.json
├── qt.py
├── cmdline.py
└── vendor/           # Bundle your dependencies
    ├── hidapi.py
    └── device_library/
```

**Note**: Non-Python dependencies (like `hidapi` shared libraries) are typically bundled in Electrum binaries. See [requirements-hw.txt](https://github.com/spesmilo/electrum/blob/master/contrib/requirements/requirements-hw.txt).

**User Import Flow:**

1. User downloads your `.zip` file
2. Opens Electrum wizard
3. Clicks "Import hardware wallet plugin"
4. Selects your `.zip` file
5. Plugin is extracted and registered
6. User can now create wallets with your device

### 7. Security Checklist for Hardware Wallet Plugins

- ✅ Never export or log private keys
- ✅ Always compare on-device address with Electrum's computation
- ✅ Verify device authenticity (MiTM checks where applicable)
- ✅ Use `@runs_in_hwd_thread` for all device I/O
- ✅ Handle device disconnects gracefully
- ✅ Provide clear upgrade instructions for outdated firmware
- ✅ Gate features based on device capabilities
- ✅ Use `UserFacingException` for user-actionable errors

### 8. Quick Start: New Hardware Wallet Plugin

1. **Study reference implementations:**
   - **Ledger**: Best example of client factory and legacy fallback
   - **Trezor**: PIN/passphrase flows, comprehensive device settings
   - **Coldcard**: File-based PSBT, MiTM verification
   - **Jade**: Serial transport, simulator support, HTTP proxy
   - **BitBox02**: Blocking UI input pattern, pairing flows

2. **Copy base structure** from Ledger or Trezor

3. **Implement required methods:**
   - `create_client()` — device initialization
   - `sign_transaction()` — delegate to device
   - `show_address()` — on-device verification
   - `extend_wizard()` — wallet setup UI

4. **Add device-specific features:**
   - Custom transport (serial, bluetooth, etc.)
   - Multisig registration if supported
   - PSBT file workflows if applicable

5. **Test thoroughly** with simulator (if available) and real device

---

## Trezor-Specific Patterns

Trezor integration requires additional patterns for PIN/passphrase handling, device invocation, capability gating, and media asset validation. These patterns ensure a secure and user-friendly experience when interacting with Trezor devices.

---

### Pattern 13: PIN and Passphrase Handling

Hardware wallet plugins commonly need secure PIN and passphrase entry flows. Key patterns:

1. Use a `PinMatrixWidget` (or similar) for secure PIN entry that avoids exposing typed characters in plain text.
2. Provide an "enter on device" option for passphrases where available (`PASSPHRASE_ON_DEVICE`) and document its effect.
3. Always display user-facing warnings explaining that a passphrase is not a PIN and that forgetting it can make funds irrecoverable.

```python
# Example passphrase dialog
def passphrase_dialog(self, msg, confirm):
    d = WindowModalDialog(parent, 'Enter Passphrase')
    new_pw = PasswordLineEdit()
    conf_pw = PasswordLineEdit()
    # confirm logic, enable OK only when matches
    # provide 'On Device' button that sets passphrase to PASSPHRASE_ON_DEVICE
```

**Security**: Never log full passphrases. If providing the user the option to enter passphrase on-device, communicate clearly in the UI that this is more secure.

---

### Pattern 14: Threaded Device Invocation with UI Callbacks

Use the `keystore.thread.add()` (or equivalent `thread` abstraction) to run device RPCs off the UI thread and `on_success` to update the UI safely when the RPC finishes.

```python
def invoke_client(method, *args, **kwargs):
    def task():
        client = devmgr.client_by_id(device_id)
        if not client:
            raise RuntimeError('Device disconnected')
        return getattr(client, method)(*args, **kwargs)
    thread.add(task, on_success=update_ui)
```

**Key Points:**
- Avoid blocking the UI thread during device operations
- Use `on_success` and `on_error` callbacks to update UI in the main thread
- Protect against device disconnects between task creation and execution

---

### Pattern 15: Feature/Capability Gating

Many devices expose a `features` object describing supported capabilities and firmware versions. Use capability checks to conditionally show or hide UI elements and warn users about unsupported combinations.

```python
model = client.get_trezor_model()
capabilities = client.client.features.capabilities
if Capability.Shamir in capabilities:
    show_shamir_ui()
```

**UI Tip**: Use non-intrusive tooltips for disabled features explaining why a feature is disabled (e.g., "Requires firmware >= 1.7.1").

---

### Pattern 16: Validating and Transforming Media Assets (Homescreen)

When uploading custom images to device homescreens, validate file format and dimensions, and provide deterministic conversion to the device's expected binary format.

```python
# Validate image size
from PIL import Image
im = Image.open(filename)
if im.size != (128, 64):
    handler.show_error('Image must be 128x64')
im = im.convert('1')
# Transform to device bitmap and invoke client.change_homescreen(img)
```

---

## Coldcard-Specific Patterns

Coldcard integration requires additional patterns for PSBT file workflows, MiTM verification, wrap_busy UX pattern, and opportunistic xpub filling. These patterns ensure a secure and user-friendly experience when interacting with Coldcard devices.

---

### Pattern 17: PSBT & File-Based Workflows (Coldcard-like devices)

Some devices (Coldcard, others) operate primarily with file-based PSBT workflows (microSD or USB file upload). Plugins must:

1. Validate incoming PSBTs and reject oversized or malformed files.
2. Upload binary blobs to the device with a checksum and length, then trigger device signing via protocol commands.
3. Poll device for completion and download the signed PSBT/txn.

```python
# Example psuedocode
raw_psbt = open(file, 'rb').read()
if len(raw_psbt) < MIN_SIZE or len(raw_psbt) > MAX_SIZE:
    raise UserFacingException('PSBT too big')
length, checksum = device.upload_file(raw_psbt)
device.send_sign_request(length, checksum)
while True:
    status = device.poll_sign_status()
    if status.done:
        signed = device.download_file(status.length, status.checksum)
        break
    sleep(0.2)
```

Security points:
- Always limit PSBT size and validate checksums.
- Use simulator paths and `is_simulator` flags in unit tests.


### Pattern 18: Device Authenticity & MiTM Verification

A strong pattern used by Coldcard: verify device authenticity using a signed session key and expected xpub fingerprint.

```python
# After pairing, store expected_xfp and expected_xpub in keystore
client.dev.check_mitm(expected_xpub=expected_xpub)
# Or implement a client-side verification that validates signature
```

Why it matters:
- Prevents a man-in-the-middle which could present a different device with malicious keys
- Ensures that the device you register during wallet creation is the same device used later


### Pattern 19: UX Busy Wrapping & Centralized Error Handling

When device operations take over the UX (e.g., waiting for user confirmation on device), mark the keystore as "busy" and provide `give_error()` that shows messages through the handler and raises `UserFacingException`.

```python
def wrap_busy(func):
    def wrapper(self, *args, **kwargs):
        try:
            self.ux_busy = True
            return func(self, *args, **kwargs)
        finally:
            self.ux_busy = False
    return wrapper
```

Centralize error reporting to keep UX consistent and avoid duplicate message code.


### Pattern 20: Opportunistic Xpub Filling

When wallet files are created without a device-connected xpub, store placeholder info in the keystore and attempt to fill in the actual xpub during a later device connection.

```python
def opportunistically_fill_in_missing_info_from_device(self, client):
    if self.ckcc_xpub is None:
        self.ckcc_xpub = client._get_ckcc_master_xpub_from_device()
        self.is_requesting_to_be_rewritten_to_wallet_file = True
```

Make sure to document this in the UI and in the wallet file format so users know when extra device info will be saved.


### Jade-Specific Patterns

Blockstream's Jade hardware plugin introduces several useful patterns worth documenting explicitly:

1. Serial / COM Transport Enumeration

- Jade scans serial ports using `serial.tools.list_ports.comports()`, filters by `(vid, pid)` pairs in `DEVICE_IDS`, and constructs `Device` objects where `path` is the serial device path (e.g. `/dev/ttyUSB0`).
- Use `interface_number=-1` and `usage_page=-1` for non-HID transports and populate `transport_ui_string` with the device path to make UI feedback obvious.

2. Simulator Integration & Test Seed

- The plugin supports optional `SIMULATOR_PATH` and `SIMULATOR_TEST_SEED` variables to detect and register a simulator during enumeration. It attempts to `set_seed()` on the simulator and only registers it if that succeeds.
- Include a small helper script and CI job that spins up a simulator and verifies critical flows (registration, signing, xpub export).

3. Device-Originated HTTP via Electrum Network

- Jade provides a helper `_http_request()` that uses `Network.send_http_on_proxy()` so the device's outbound HTTP calls honor Electrum proxy settings. This is safer and more consistent than calling `requests` directly from the plugin.

4. Deterministic Multisig Registration Name

- The plugin builds a multisig registration name as `'ele' + sha256(wallet.get_fingerprint()).hex()[:12]`. This deterministic, short prefix ensures re-registration is a no-op and is a convenient naming convention for cross-plugin interoperability.

5. PSBT Signing Roundtrip

- Jade's `sign_psbt()` returns serialized PSBT bytes. The host plugin converts the returned bytes to a `PartialTransaction` (`PartialTransaction.from_raw_psbt()`) and then merges signatures into the working `tx` using `tx.combine_with_other_psbt()`. Always validate the returned PSBT and handle deserialization errors gracefully.

6. Firmware Gating & User Feedback

- Check firmware versions against `MIN_SUPPORTED_FW_VERSION`. When outdated, call `handler.show_error()` with actionable instructions and raise `OutdatedHwFirmwareException` to abort flows that would otherwise confuse users or produce invalid behavior.

7. Entropy Injection & RNG Seeding

- After connecting, the plugin seeds the device RNG via `jade.add_entropy(os.urandom(32))`. This pattern can be useful for devices that allow host-supplied entropy; document the cryptographic rationale and mitigations (e.g., do not rely solely on host entropy).

8. Signing & Anti-Exfil Considerations

- The plugin deliberately avoids AE/anti-exfil signing for some `sign_message()` paths and sticks with deterministic RFC6979 signatures. Document when AE should be used and when it should be avoided (e.g., when signature verification on-device is incompatible with AE workflows).

9. Dependency-Availability Pattern

- Guard imports to set a `libraries_available` flag and call `self.device_manager().register_enumerate_func()` only when the libraries are present. Use `only_hook_if_libraries_available` or similar gating to hide hooks/UI when deps are missing.

10. Address verification

- Always compare the on-device address returned by `show_address()` to the host-computed address and present a high-severity error if they differ.


**Why these patterns matter:** Jade demonstrates a robust serial-device integration model that accounts for transport type, simulation testing, network proxying, multisig registration idempotency, and returning signed PSBT bytes. These patterns are applicable to other serial- or TCP-based hardware wallets and should be included in the general Hardware Wallet Integration section.

---

### Pattern 21: Worker → UI Input (BlockingQueuedConnection)

Background threads sometimes need synchronous UI input (text or confirmation). Use `QMetaObject.invokeMethod()` with `BlockingQueuedConnection` to request input from the main thread while the worker waits for a result.

```python
from PyQt6.QtCore import QMetaObject, Q_RETURN_ARG, Qt, Q_ARG, pyqtSlot

# Called from worker thread
name = QMetaObject.invokeMethod(
    ui_object,
    "_name_multisig_account",
    Qt.ConnectionType.BlockingQueuedConnection,
    Q_RETURN_ARG(str)
)

# In the UI thread define a slot that shows the dialog and returns the string
@pyqtSlot(result=str)
def _name_multisig_account(self):
    dialog = WindowModalDialog(None, "Create Multisig Account")
    name_edit = QLineEdit()
    # ... add OK button and layout ...
    if dialog.exec():
        return name_edit.text().strip()
    return ""
```

**When to use:**
- Worker thread needs user text input (e.g., multisig account name)
- Worker needs user confirmation before proceeding
- Device operation requires UI decision point

**Why it matters:**
- Synchronously blocks worker thread until user responds
- Keeps UI interaction on main thread (thread-safe)
- Avoids complex async callback chains for simple user input

**Caveats:**
- Worker thread blocks until user responds - don't use for long-running UI operations
- Keep dialog simple and fast to prevent prolonged worker blocking
- Provide clear cancel option and handle rejection

**Real-world usage:**
- BitBox02: multisig account naming during registration
- Any hardware wallet requiring user input during device initialization

---

### Pattern 22: Pairing & Client Retrieval Best Practices

When retrieving device clients by id during wizard flows or background tasks, prefer `scan_now=False` to avoid triggering a full USB/HID scan which can disrupt ongoing flows.

```python
# Retrieve client without triggering device re-scan
client = device_manager.client_by_id(device_id, scan_now=False)
if client is None:
    raise RuntimeError('Device not connected or pairing lost')

# Use the client
result = client.some_device_operation()
```

**When to use:**
- During wallet creation wizard flows
- When you know device should already be connected
- Background operations that shouldn't trigger USB enumeration

**Why it matters:**
- Automatic rescans can be expensive (USB/serial port enumeration)
- Can change device ordering or interrupt in-progress device operations
- Prevents race conditions during pairing

**When to force scan:**
- User explicitly requests "refresh devices"
- Initial device discovery
- After known device disconnect/reconnect

**Real-world usage:**
- BitBox02: uses `scan_now=False` during wizard to avoid rescanning while pairing
- All hardware wallets should consider this during wizard flows

---

### Pattern 23: Character-Based Recovery UI (KeepKey-like)

Some devices provide character-by-character recovery flows to minimize full-phrase entry on limited input devices. Implement a small, focused dialog that:

- Uses `QEventLoop()` to block waiting for a single-character response
- Exposes a handler `get_char()` that can be called from the hardware thread
- Uses signals to ensure UI interactions occur on the main thread

```python
from PyQt6.QtCore import QEventLoop, pyqtSignal

class CharacterDialog(WindowModalDialog):
    def __init__(self, parent):
        super().__init__(parent, "Recovery")
        self.loop = QEventLoop()
        self.data = None
        
        # Create character input buttons (a-z, space, etc.)
        # When button clicked: self.on_char_clicked(char)
        
    def on_char_clicked(self, char):
        self.data = char
        self.loop.exit()
        
    def get_char(self, word_pos, char_pos):
        """Called from worker thread via signal"""
        self.show()
        self.loop.exec()  # Block until user clicks a character
        return self.data

# In Qt Handler
class TrezorQtHandler:
    char_signal = pyqtSignal(str)
    
    def __init__(self):
        self.character_dialog = CharacterDialog(parent)
        self.char_signal.connect(self.character_dialog.get_char)
        self.done = threading.Event()
        
    def get_char(self, msg):
        """Called from hardware thread"""
        self.char_signal.emit(msg)
        self.done.wait()  # Block hardware thread until UI responds
        self.done.clear()
        return self.character_dialog.data
```

**When to use:**
- Devices with device-driven auto-complete for seed recovery
- Limited input devices (numeric keypad, matrix entry)
- When full-word entry is unsafe or inconvenient

**Why it matters:**
- Provides secure character-by-character entry
- Blocks hardware thread until user input received
- Keeps UI responsive while allowing synchronous-style hardware code

**Caveats:**
- Dialog must be fast and simple to avoid long blocking
- Provide clear cancel path
- Handle `rejected` signal appropriately

**Real-world usage:**
- KeepKey: character-based seed recovery with auto-complete
- Trezor: matrix recovery for devices with limited input

---

### Pattern 24: WaitingDialog for Blocking Operations

When performing slow I/O operations (file transfer, audio encoding, network requests, device operations), use `WaitingDialog` to run the work in a background thread while showing a progress message to the user.

```python
from electrum.gui.qt.util import WaitingDialog

def slow_operation(self, parent):
    def worker_thread():
        # This runs in background thread
        # Perform slow I/O here
        result = perform_slow_task()
        return result
    
    # Show dialog with message while worker runs
    msg = 'Processing, please wait...'
    result = WaitingDialog(parent, msg, worker_thread)
    
    # Dialog closes when worker returns; result is available here
    if result:
        print(f"Operation completed: {result}")
```

**When to use:**
- Audio encoding/decoding (audio_modem plugin)
- Device operations that require user confirmation on hardware
- Network requests or file transfers
- Any operation that could take >1 second

**Why it matters:**
- Prevents UI freeze during blocking operations
- Provides user feedback with progress message
- Automatically handles thread management and dialog lifecycle

---

### Pattern 25: Optional Dependencies with Graceful Degradation

When a plugin requires an optional external library, use try/except import at module level and expose an `is_available()` check to gracefully handle missing dependencies.

```python
# At module level (top of file)
try:
    import optional_library
    _logger.info('Optional library is available.')
    LIBRARY_AVAILABLE = True
except ImportError:
    optional_library = None
    _logger.info('Optional library not found.')
    LIBRARY_AVAILABLE = False

class Plugin(BasePlugin):
    
    def is_available(self):
        return LIBRARY_AVAILABLE
    
    def requires_settings(self):
        # Only show settings if library is available
        return self.is_available()
    
    @hook
    def some_feature(self, ...):
        if not self.is_available():
            return  # Silently skip if library missing
        
        # Use optional_library safely here
        optional_library.do_something()
```

**Manifest declaration:**
```json
{
  "requires": [["optional_library", "https://github.com/..."]]
}
```

**Why it matters:**
- Plugin loads without crashing when dependencies are missing
- User sees clear error messages and installation instructions from manifest
- Features gracefully degrade rather than causing plugin failures
- Allows development/testing without all dependencies installed

**Real-world usage:**
- audio_modem: requires `amodem` for acoustic transmission
- Hardware wallets: require device-specific libraries (ledger_bitcoin, trezorlib, etc.)
- Any plugin that interfaces with external systems or specialized hardware

---

### Pattern 26: Air-Gapped Transaction Workflows

For security-sensitive scenarios, plugins can facilitate transaction signing without network/USB connectivity using alternative data channels:

1. **Audio Modem** (acoustic coupling)
```python
# Compress transaction for acoustic transmission
blob = tx.serialize()
compressed = zlib.compress(blob.encode('ascii'))

# Transmit via audio tones
with audio_interface() as interface:
    src = BytesIO(compressed)
    dst = interface.player()
    amodem.main.send(config=modem_config, src=src, dst=dst)
```

2. **QR Codes** (visual channel)
```python
# Animated QR for large transactions
from electrum.gui.qt.qrwindow import QRDialog
qr_data = tx.serialize()
QRDialog(qr_data, parent=window, title="Scan Transaction")
```

3. **File-Based PSBT** (microSD/USB)
```python
# Export PSBT to file for hardware wallet
psbt_bytes = tx.serialize_as_bytes()
filename = "unsigned.psbt"
with open(filename, 'wb') as f:
    f.write(psbt_bytes)
```

**Security considerations:**
- Air-gapped channels prevent remote attacks but may be vulnerable to local eavesdropping
- Audio/QR: encrypt sensitive data or use in secure environment
- File transfers: validate checksums and limit file sizes
- Always verify addresses/amounts on signing device display

**When to use:**
- High-security cold storage workflows
- Environments where network/USB is restricted
- Demonstrating security best practices to users

---

### Pattern 27: Server Sync with Client-Side Encryption

For plugins that synchronize data across devices via remote servers, implement client-side encryption to preserve privacy. Encrypt all sensitive data before transmission so the server acts as an untrusted storage backend.

```python
# Labels plugin example
class LabelsPlugin(BasePlugin):
    def push_label(self, wallet, item_id, label):
        # Derive encryption key from wallet
        enc_key = wallet.get_sync_key()
        
        # Encrypt label, tx_id, and address before sending
        encrypted_label = encrypt(label, enc_key)
        encrypted_id = encrypt(item_id, enc_key)
        
        # Send to server - server cannot read contents
        response = requests.post(
            f'{self.server_url}/push',
            json={'id': encrypted_id, 'label': encrypted_label}
        )
        
    def pull_labels(self, wallet):
        enc_key = wallet.get_sync_key()
        
        # Fetch encrypted data from server
        response = requests.get(f'{self.server_url}/pull')
        
        # Decrypt locally
        for item in response.json():
            item_id = decrypt(item['id'], enc_key)
            label = decrypt(item['label'], enc_key)
            wallet.set_label(item_id, label)
```

**When to use:**
- Syncing wallet labels, contacts, or metadata across devices
- Any data that should remain private from server operators
- Cloud backup of sensitive plugin configuration

**Why it matters:**
- Server cannot read user data (zero-knowledge architecture)
- Enables cross-device sync without compromising privacy
- Prevents server operator or attacker from learning wallet activity

**Implementation checklist:**
- ✅ Derive encryption keys from wallet (not hardcoded)
- ✅ Use authenticated encryption (AEAD like AES-GCM)
- ✅ Encrypt all sensitive fields (labels, addresses, tx IDs)
- ✅ Handle encryption errors gracefully
- ✅ Provide offline mode (queue sync when server unavailable)
- ✅ Use HTTPS for transport layer security

**Real-world usage:**
- labels plugin: encrypted label sync across devices
- Any plugin implementing cloud backup or cross-device coordination

---

### Pattern 28: Nostr Protocol Integration

Integrate with Nostr relays for decentralized communication, Lightning control (NIP-47), or multisig coordination. WebSocket connections enable real-time event-driven workflows.

```python
# NWC plugin example - Nostr Wallet Connect
class NostrWalletConnectPlugin(BasePlugin):
    def __init__(self, parent, config, name):
        super().__init__(parent, config, name)
        self.relay_urls = config.get('nwc_relays', DEFAULT_RELAYS)
        self.ws_connections = {}
        
    async def connect_relay(self, relay_url):
        """Establish WebSocket connection to Nostr relay"""
        ws = await websockets.connect(relay_url)
        self.ws_connections[relay_url] = ws
        
        # Subscribe to wallet command events
        subscription = {
            "kinds": [23194],  # NIP-47 wallet commands
            "authors": [self.authorized_pubkey]
        }
        await ws.send(json.dumps(["REQ", "nwc-sub", subscription]))
        
        # Listen for events
        async for message in ws:
            await self.handle_event(json.loads(message))
    
    async def handle_event(self, event):
        """Process NIP-47 wallet commands"""
        if event[0] == "EVENT":
            decrypted = nip04_decrypt(event[2]['content'], self.privkey)
            command = json.loads(decrypted)
            
            # Execute wallet operations based on command
            if command['method'] == 'pay_invoice':
                result = await self.wallet.pay_lightning_invoice(
                    command['params']['invoice']
                )
                # Publish encrypted response
                await self.publish_response(result, event[2]['id'])
```

**When to use:**
- Remote Lightning wallet control (NIP-47)
- Decentralized multisig coordination
- Censorship-resistant communication
- Real-time event notifications

**Why it matters:**
- Nostr relays provide decentralized, censorship-resistant communication
- WebSocket connections enable real-time responsive UIs
- NIP-47 enables secure remote wallet control
- No central server dependency

**Implementation checklist:**
- ✅ WebSocket lifecycle management (connect, reconnect, disconnect)
- ✅ Multi-relay support for redundancy
- ✅ NIP-04 or NIP-44 encryption for sensitive events
- ✅ Proper error handling and relay failover
- ✅ Event subscription and filtering
- ✅ Rate limiting and spam prevention

**Real-world usage:**
- nwc plugin: NIP-47 Lightning wallet control
- psbt_nostr plugin: Decentralized multisig PSBT coordination

---

### Pattern 29: HTTP Server Plugin

Plugins can run HTTP servers for payment requests, swap services, or watchtower functionality. Implement proper server lifecycle, authentication, and RESTful API design.

```python
# Payserver plugin example
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

class PaymentRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/create_invoice':
            # Generate payment request
            amount = self.get_query_param('amount')
            invoice = self.server.plugin.create_payment_request(amount)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(invoice).encode())
    
    def do_POST(self):
        if self.path == '/notify':
            # Receive payment notification
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            self.server.plugin.handle_payment_notification(post_data)
            self.send_response(200)
            self.end_headers()

class PayServerPlugin(BasePlugin):
    def __init__(self, parent, config, name):
        super().__init__(parent, config, name)
        self.server = None
        self.server_thread = None
        
    def start_server(self):
        """Start HTTP server in background thread"""
        port = self.config.get('payserver_port', 8080)
        self.server = HTTPServer(('0.0.0.0', port), PaymentRequestHandler)
        self.server.plugin = self  # Give handler access to plugin
        
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        print(f"Payment server listening on port {port}")
        
    def stop_server(self):
        """Graceful server shutdown"""
        if self.server:
            self.server.shutdown()
            self.server_thread.join()
```

**When to use:**
- Merchant payment request services
- Submarine swap servers
- Lightning watchtower services
- Any plugin providing HTTP API

**Why it matters:**
- Enables plugin to act as service provider
- RESTful APIs allow external integration
- Background daemon mode for server operations

**Implementation checklist:**
- ✅ Proper server lifecycle (start/stop/restart)
- ✅ Background thread for non-blocking operation
- ✅ Port configuration from plugin settings
- ✅ TLS/SSL support for production
- ✅ Authentication (API keys, user/password)
- ✅ CORS headers for browser access
- ✅ Rate limiting and DDoS protection
- ✅ Graceful shutdown on plugin unload

**Real-world usage:**
- payserver: BIP70 payment request HTTP server
- swapserver: Submarine swap coordination server
- watchtower: Lightning channel monitoring HTTP service

---

### Pattern 30: Nostr Multisig Coordination

Use Nostr relays for decentralized multisig wallet coordination. Publish unsigned PSBTs as events, subscribe to cosigner signatures, and merge them without central server.

```python
# PSBT Nostr plugin example
class PSBTNostrPlugin(BasePlugin):
    async def publish_psbt(self, wallet, tx):
        """Publish unsigned PSBT to Nostr relays"""
        psbt_bytes = tx.serialize_as_bytes()
        
        # Create Nostr event with PSBT
        event = {
            "kind": 25441,  # Custom kind for PSBT coordination
            "content": base64.b64encode(psbt_bytes).decode(),
            "tags": [
                ["wallet", wallet.get_fingerprint()],
                ["cosigners", *self.get_cosigner_pubkeys(wallet)]
            ],
            "pubkey": self.config.get('nostr_pubkey'),
            "created_at": int(time.time())
        }
        
        # Sign and publish to all relays
        signed_event = self.sign_event(event)
        for relay_url in self.relay_urls:
            await self.publish_to_relay(relay_url, signed_event)
    
    async def subscribe_signatures(self, wallet, psbt_id):
        """Subscribe to cosigner signature events"""
        subscription = {
            "kinds": [25442],  # PSBT signature events
            "tags": [["p", psbt_id]]  # Reference original PSBT
        }
        
        async for event in self.relay_subscribe(subscription):
            # Extract signature from event
            sig_data = base64.b64decode(event['content'])
            partial_tx = PartialTransaction.from_raw_psbt(sig_data)
            
            # Merge signature into transaction
            wallet.tx.combine_with_other_psbt(partial_tx)
            
            # Check if fully signed
            if wallet.tx.is_complete():
                self.broadcast_transaction(wallet.tx)
                break
```

**When to use:**
- Decentralized multisig wallet coordination
- Eliminating central cosigning servers
- Censorship-resistant multisig workflows
- Privacy-preserving signature collection

**Why it matters:**
- No central point of failure or censorship
- Nostr relays provide reliable message passing
- Cosigners can be anywhere with relay access
- Event-driven architecture fits multisig workflows naturally

**Implementation checklist:**
- ✅ PSBT publishing with wallet metadata tags
- ✅ Cosigner event subscription and filtering
- ✅ Signature extraction and PSBT merging
- ✅ Multi-relay publishing for redundancy
- ✅ Timeout handling for missing cosigners
- ✅ Completion detection and broadcast
- ✅ Privacy considerations (relay operators see events)
- ✅ Encryption for sensitive PSBT metadata

**Real-world usage:**
- psbt_nostr plugin: Nostr-based multisig coordination
- Demonstrates decentralized alternative to traditional cosigning servers

---

## Troubleshooting Common Plugin Issues

### Plugin Not Loading

**Problem:** Plugin doesn't appear in Tools → Plugins menu

**Solutions:**
1. **Check manifest.json syntax**
   ```bash
   python3 -c "import json; json.load(open('manifest.json'))"
   ```
   
2. **Verify available_for platform**
   ```json
   {
     "available_for": ["qt", "cmdline"]  // Must include current platform
   }
   ```

3. **Check Python syntax**
   ```bash
   python3 -m py_compile __init__.py
   python3 -m py_compile qt.py
   ```

4. **Verify plugin directory structure**
   ```
   electrum/plugins/yourplugin/
   ├── __init__.py        # Must exist
   ├── manifest.json      # Must exist
   └── qt.py             # Optional, for GUI
   ```

5. **Check Electrum logs**
   ```bash
   ./run_electrum --verbose 2>&1 | grep -i plugin
   ```

---

### Import Errors

**Problem:** `ImportError` or `ModuleNotFoundError` when loading plugin

**Solutions:**
1. **Optional dependencies - use try/except**
   ```python
   try:
       from amodem import main as amodem_main
       libraries_available = True
   except ImportError:
       libraries_available = False
       
   def requires_settings(self):
       return not libraries_available  # Show settings if deps missing
   ```

2. **Check import paths**
   ```python
   # Correct - relative to Electrum root
   from electrum.plugin import BasePlugin
   from electrum.gui.qt.util import WindowModalDialog
   
   # Wrong - absolute imports
   from plugin import BasePlugin  # ❌
   ```

3. **Verify dependencies in manifest**
   ```json
   {
     "requires": [
       ["amodem", "github.com/romanz/amodem"]
     ]
   }
   ```

---

### Hook Not Firing

**Problem:** `@hook` decorated method never gets called

**Solutions:**
1. **Verify hook decorator syntax**
   ```python
   @hook
   def transaction_dialog(self, dialog):  # ✅ Correct
       pass
   
   @hook()  # ❌ Wrong - no parentheses
   def transaction_dialog(self, dialog):
       pass
   ```

2. **Check hook method signature**
   ```python
   # Hook signatures must match exactly
   @hook
   def transaction_dialog(self, dialog):  # ✅ Correct signature
       pass
       
   @hook
   def transaction_dialog(self, dialog, extra):  # ❌ Wrong signature
       pass
   ```

3. **Ensure plugin is enabled**
   ```python
   # In __init__.py
   class Plugin(BasePlugin):
       def is_enabled(self):
           return self.config.get('use_myplugin', False)
   ```

4. **Use only_hook_if_libraries_available**
   ```python
   @only_hook_if_libraries_available
   @hook
   def transaction_dialog(self, dialog):
       # Only fires if libraries_available = True
       pass
   ```

---

### Thread/GUI Issues

**Problem:** GUI freezes, crashes, or shows "QObject: Cannot create children for a parent that is in a different thread"

**Solutions:**
1. **Use WaitingDialog for slow operations**
   ```python
   from electrum.gui.qt.util import WaitingDialog
   
   def slow_operation(self):
       def worker():
           # Runs in background thread
           return perform_slow_task()
       
       result = WaitingDialog(parent, 'Please wait...', worker)
   ```

2. **Hardware wallet operations - use @runs_in_hwd_thread**
   ```python
   from electrum.plugin import runs_in_hwd_thread
   
   @runs_in_hwd_thread
   def sign_transaction(self, keystore, tx, prev_tx, xpub_path):
       # Safe to call device I/O here
       return device.sign(tx)
   ```

3. **UI updates from worker threads - use signals**
   ```python
   from PyQt6.QtCore import pyqtSignal, QObject
   
   class Worker(QObject):
       finished = pyqtSignal(object)
       
       def run(self):
           result = do_work()
           self.finished.emit(result)  # Safe cross-thread communication
   ```

4. **Synchronous UI input from worker - use BlockingQueuedConnection**
   ```python
   from PyQt6.QtCore import QMetaObject, Q_RETURN_ARG, Qt
   
   # From worker thread
   result = QMetaObject.invokeMethod(
       ui_object,
       "get_user_input",
       Qt.ConnectionType.BlockingQueuedConnection,
       Q_RETURN_ARG(str)
   )
   ```

---

### Hardware Wallet Issues

**Problem:** Device not detected or signing fails

**Solutions:**
1. **Verify device enumeration**
   ```python
   def enumerate_devices(self):
       if not self.libraries_available:
           return []
       
       # Log devices for debugging
       devices = self._enumerate_devices()
       print(f"Found {len(devices)} devices: {devices}")
       return devices
   ```

2. **Check firmware version gating**
   ```python
   def create_client(self, device, handler):
       client = DeviceClient(device)
       
       if client.get_version() < MIN_SUPPORTED_VERSION:
           handler.show_error(
               f"Firmware too old. Minimum: {MIN_SUPPORTED_VERSION}"
           )
           raise OutdatedHwFirmwareException()
   ```

3. **Always verify addresses on-device**
   ```python
   def show_address(self, wallet, address):
       device_address = client.get_address(address_n)
       
       if device_address != address:
           # CRITICAL - addresses don't match!
           raise UserFacingException(
               f"Address mismatch!\n"
               f"Device: {device_address}\n"
               f"Electrum: {address}"
           )
   ```

4. **Handle device disconnects gracefully**
   ```python
   try:
       result = client.sign_tx(tx)
   except DeviceDisconnectedException:
       handler.show_error("Device disconnected during signing")
       return None
   ```

---

### Settings/Configuration Issues

**Problem:** Plugin settings not persisting or not visible

**Solutions:**
1. **Implement requires_settings() for config dialog**
   ```python
   def requires_settings(self):
       return True  # Show in settings
   
   def settings_widget(self, window):
       return MyConfigWidget(self.config)
   ```

2. **Save settings to config**
   ```python
   # Save
   self.config.set_key('myplugin_option', value)
   
   # Load
   value = self.config.get('myplugin_option', default_value)
   ```

3. **Use plugin-specific namespace**
   ```python
   # Good - namespaced
   self.config.set_key('audio_modem_volume', 50)
   
   # Bad - conflicts with other plugins
   self.config.set_key('volume', 50)
   ```

---

### Network/Server Issues

**Problem:** HTTP server not starting or network requests failing

**Solutions:**
1. **Check port conflicts**
   ```python
   import socket
   
   def start_server(self):
       port = self.config.get('server_port', 8080)
       try:
           self.server = HTTPServer(('0.0.0.0', port), Handler)
           self.server.serve_forever()
       except OSError as e:
           if e.errno == 48:  # Address already in use
               print(f"Port {port} in use, try another")
   ```

2. **Use Electrum's network for proxy support**
   ```python
   # Good - respects user's proxy settings
   from electrum.network import Network
   result = Network.send_http_on_proxy(url, params)
   
   # Bad - bypasses proxy
   import requests
   result = requests.get(url)  # Won't use Tor if configured
   ```

3. **Background server threads must be daemon**
   ```python
   self.server_thread = Thread(
       target=self.server.serve_forever,
       daemon=True  # ✅ Exits when main program exits
   )
   ```

---

### Testing Issues

**Problem:** Hard to test plugin without full Electrum setup

**Solutions:**
1. **Use simulator for hardware wallets**
   ```python
   # Jade example
   if os.environ.get('JADE_SIMULATOR'):
       devices.append(Device(
           path='127.0.0.1:12345',
           interface_number=-1,
           is_simulator=True
       ))
   ```

2. **Mock dependencies for unit tests**
   ```python
   from unittest.mock import Mock, patch
   
   @patch('myplugin.expensive_library')
   def test_my_function(mock_lib):
       mock_lib.return_value = 'test_value'
       result = my_function()
       assert result == expected
   ```

3. **Test on signet/testnet first**
   ```python
   from electrum.constants import BitcoinTestnet, BitcoinMainnet
   
   if not isinstance(constants.net, BitcoinMainnet):
       # Safe to test on testnet/signet
       pass
   ```

---

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Plugin not compatible with this wallet type` | Wrong `requires_wallet_type` | Update manifest or check wallet type |
| `libraries_available_message` shown | Dependencies missing | Install required packages via pip |
| `UserFacingException` | User-actionable error | Check error message, often hardware wallet issue |
| `OutdatedHwFirmwareException` | Old device firmware | Update firmware via vendor tool |
| `DeviceDisconnectedException` | Device unplugged during operation | Reconnect device and retry |
| `Cannot create children for parent in different thread` | GUI operation from wrong thread | Use signals or WaitingDialog |

---

### Debug Tips

1. **Enable verbose logging**
   ```bash
   ./run_electrum --verbose 2>&1 | tee electrum.log
   ```

2. **Add debug prints**
   ```python
   print(f"[MYPLUGIN] Debug: {variable}")  # Visible in console
   ```

3. **Check plugin is actually loaded**
   ```python
   # In Electrum console (Ctrl+D)
   >>> window.plugins
   {'audio_modem': <AudioModem plugin>, ...}
   ```

4. **Test hooks with print statements**
   ```python
   @hook
   def transaction_dialog(self, dialog):
       print(f"[MYPLUGIN] Hook fired! Dialog: {dialog}")
       # Verify in console output
   ```

5. **Use Python debugger**
   ```python
   import pdb; pdb.set_trace()  # Breakpoint
   ```

---

## Auditing Plugins — Quick Workflow

A standard, repeatable audit process makes it easy to capture implementation patterns, security issues, and UX gotchas so future plugin authors benefit from concrete, actionable guidance.

1. Run the automated scan

   Use the helper script to generate or refresh per-plugin audit stubs:

   ```bash
   ./scripts/audit-plugins.sh
   ```

   The script writes a short report for each plugin to `docs/plugin-audits/<plugin>.md` and appends a summary line to `CHANGELOG.md`.

2. Manually expand the audit

   Open the generated file and fill in the `Findings`, `Recommended fixes`, and `Suggested Tests` sections. Use the audit template found at `docs/plugin-audits/README.md`.

3. Convert findings into guide patterns

   For each recurring pattern, add a short section to this guide under the relevant heading (e.g., "Hardware Wallet Integration Patterns", "PSBT & File-Based Workflows"). Keep each pattern:
   - Problem statement (1 line)
   - Example code (concise)
   - Why it matters (1 line)

4. Commit audit changes separately

   Commit the completed audit file and guide update as separate commits so reviewers can triage security-related items quickly.

### Audit Severity Guidance

When completing an audit, give each issue a severity label:
- Critical: irreversible fund loss or secret leakage.
- High: immediate risk that could cause lost funds or significant confusion.
- Medium: important fix but not immediately catastrophic.
- Low: polish or documentation-only.
- Informational: useful context.

Include a short remediation proposal with any High/Critical finding.

### Audit Template (short)

Use the following minimal header in each audit file so automation can parse results later:

```yaml
---
plugin: <name>
path: <repo-relative-path>
has_ui: true|false
manifest_present: true|false
libraries: [list]
severity_summary: Critical|High|Medium|Low|Informational
---
```
