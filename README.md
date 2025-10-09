# Electrum Plugins Repository

Comprehensive reference for developing Electrum plugins with 30 documented patterns, 20 plugin audits, and complete implementation guides.

## 📚 Documentation

**Start here:** [`ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md`](ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md) - **2,568 lines** of comprehensive documentation

### What's Included

- **30 Documented Patterns** - From basic hooks to advanced hardware wallet integration
- **Pattern Index** - Quick lookup by plugin type and use case
- **9 Hardware Wallets** - Complete comparison matrix and implementation guides
- **Troubleshooting** - 50+ solutions to common plugin development issues
- **20 Plugin Audits** - Detailed analysis with cross-references and best practices
- **Security Checklist** - Best practices for safe plugin development

## 🚀 Quick Start

### For Plugin Developers

1. **Read the guide**: [`ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md`](ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md)
2. **Choose a pattern**: See [Pattern Index](ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md#pattern-index)
3. **Study examples**: Review [plugin audits](docs/plugin-audits/) for real implementations
4. **Start building**: Use patterns and examples as reference

### Pattern Categories

**Core Patterns (1-12):** BasePlugin, Hooks, Settings, GUI, Network, Lightning, Transactions, Wallet Types

**Hardware Wallet (13-23):** PIN/Passphrase, Threading, PSBT, MiTM Verification, Device Pairing, Recovery UI

**General (24-26):** WaitingDialog, Optional Dependencies, Air-Gapped Workflows

**Network/Server (27-30):** Encrypted Sync, Nostr Integration, HTTP Servers, Multisig Coordination

## 📦 Example Plugins

### 1. VirtualKeyboard (Simple)
A basic plugin that creates a virtual keyboard in Qt GUI password dialogs.
- **Complexity**: Beginner
- **Lines of Code**: ~100
- **Demonstrates**: Basic plugin structure, hooks, Qt GUI integration
- **Patterns Used**: 1-5 (Core patterns)

### 2. CHECKLOCKTIMEVERIFY (Advanced)
Implements BIP-65 CHECKLOCKTIMEVERIFY for creating time-locked Bitcoin addresses with Taproot support and educational script visualization.
- **Complexity**: Advanced  
- **Lines of Code**: ~3,500 (plus 2,000+ lines of documentation)
- **Demonstrates**: Bitcoin script construction, P2SH/Taproot addresses, complex GUI, covenant scripts, educational visualization
- **Patterns Used**: 1-5, 10 (Custom Transaction Types)
- **Network**: Signet/Testnet only (educational PoC)
- **Features**: 
  - 🔄 P2SH/Taproot toggle for all 5 CLTV examples (Freezing Funds, Escrow, Two-Factor, Payment Channel, Data Publishing)
  - 🔍 Interactive Bitcoin Script visualizer with step-by-step execution
  - 📊 Stack visualization with color-coded states
  - 🎯 Educational descriptions for each script operation
  - ⚡ Persistent UTXO caching (5-min TTL) for fast startup

### 3. Full Plugin Ecosystem

See [`docs/plugin-audits/`](docs/plugin-audits/) for detailed analysis of all 20 Electrum plugins:

**Hardware Wallets:** Ledger, Trezor, Coldcard, Jade, BitBox02, KeepKey, Safe-T, DigitalBitbox, Audio Modem

**Network/Service:** Labels, NWC, Payserver, PSBT Nostr, Swapserver, Watchtower

**Advanced Scripts:** Revealer, Timelock Recovery, TrustedCoin

## 📖 Documentation Structure

```
📁 electrum-plugins/
├── 📄 ELECTRUM_PLUGIN_DEVELOPMENT_GUIDE.md  # Main guide (2,568 lines)
├── 📄 CHANGELOG.md                          # Development history
├── 📄 CONTRIBUTING.md                       # Contribution guidelines
├── 📁 docs/plugin-audits/                   # 20 plugin audits
│   ├── README.md                           # Audit process
│   ├── ledger.md                           # Hardware wallet examples
│   ├── nwc.md                              # Network plugin examples  
│   └── ...                                 # All 20 plugins
├── 📁 scripts/
│   └── audit-plugins.sh                    # Automated audit tool
├── 📁 virtualkeyboard/                      # Simple example
└── 📁 checklocktimeverify/                  # Advanced example
```

## Publishing a plugin as .zip file

In order to publish an external plugin, fork this directory and use
the `contrib/make_plugin` script in the electrum repository.

`./contrib/make_plugin <plugin_directory>`

It will create a plugin file named `yourplugin-version.zip`, where `version` is set in `manifest.json` of the plugin.

## The manifest.json file

The file contains the following fields:

 - name: The plugin internal name. Electrum will install only one plugin per name.
 - fullname: User visible name, shown in GUI
 - description: User visible description
 - available_for: List of GUIs for which the plugin is available.
 - author: The plugin author
 - license: The licence.
 - version: The version of the plugin. It is added to the zipfile name.
 - min_electrum_version (optional): Minimum supported version of Electrum
 - max_electrum_version (optional): Max supported version of Electrum


## Installing a zipfile plugin

The plugin zipfile needs to be added the `plugins` directory of your electrum directory.

On Linux:

`cp myplugin.zip ~/lelectrum/plugins/myplugin.zip`


The GUI will prompt the user for a plugin authorization password.


## Development and testing

If you are developing an external plugin, you may fork this directory,
and create a symbolic link in your electrum/electrum/plugins directory
to the place where you where you forked this repository. That way, you
will not need to publish your plugin in order to test it.

### Testing the CHECKLOCKTIMEVERIFY Plugin

1. **Setup Electrum development environment:**
   ```bash
   cd /Users/macbook/src/electrum-plugins
   ./setup-electrum-dev.sh
   ```

2. **Deploy and run the plugin:**
   ```bash
   # Kill any running Electrum processes
   pkill -9 -f "run_electrum" 2>/dev/null || true
   
   # Copy plugin files (excluding docs/tests)
   rm -rf ~/src/electrum/plugins/checklocktimeverify
   rsync -av /Users/macbook/src/electrum-plugins/checklocktimeverify ~/src/electrum/plugins/ --exclude="*.md" --exclude="test_*.py" --exclude="*.sh"
   
   # Start Electrum on signet
   cd ~/src/electrum && source venv/bin/activate && ./run_electrum --signet
   ```

3. **Enable and test the plugin:**
   - Go to **Tools → Plugins**
   - Enable "BIP-65 CLTV Examples" plugin
   - Open **Tools → BIP-65 CLTV Examples**
   - **Test P2SH/Taproot toggle:** Generate addresses in any tab, toggle between P2SH (starts with `2`) and Taproot (starts with `tb1p`)
   - **Test Script Visualizer:** In Freezing Funds tab, generate an address, then click the **🔍 Visualize Script** button to see step-by-step Bitcoin Script execution with stack visualization


