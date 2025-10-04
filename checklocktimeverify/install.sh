#!/bin/bash
# Quick Installation Script for CHECKLOCKTIMEVERIFY Plugin

echo "🔧 CHECKLOCKTIMEVERIFY Plugin Installer"
echo "========================================"
echo ""

# Check if Electrum directory exists
ELECTRUM_DIR="$HOME/electrum"
PLUGIN_DIR="$ELECTRUM_DIR/electrum/plugins"

if [ ! -d "$ELECTRUM_DIR" ]; then
    echo "❌ Electrum directory not found at $ELECTRUM_DIR"
    echo ""
    echo "Please either:"
    echo "1. Clone Electrum: git clone https://github.com/spesmilo/electrum.git ~/electrum"
    echo "2. Or specify your Electrum location"
    exit 1
fi

echo "✅ Found Electrum at: $ELECTRUM_DIR"
echo ""

# Get current plugin directory
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SOURCE="$CURRENT_DIR"

echo "📂 Plugin source: $PLUGIN_SOURCE"
echo "📂 Target: $PLUGIN_DIR/checklocktimeverify"
echo ""

# Check if symlink already exists
if [ -L "$PLUGIN_DIR/checklocktimeverify" ]; then
    echo "⚠️  Symlink already exists. Removing old symlink..."
    rm "$PLUGIN_DIR/checklocktimeverify"
fi

# Create symlink
echo "🔗 Creating symlink..."
ln -s "$PLUGIN_SOURCE" "$PLUGIN_DIR/checklocktimeverify"

if [ $? -eq 0 ]; then
    echo "✅ Symlink created successfully!"
    echo ""
    echo "🎉 Installation Complete!"
    echo ""
    echo "Next steps:"
    echo "1. Run Electrum: cd ~/electrum && ./run_electrum"
    echo "2. Go to: Tools → Plugins"
    echo "3. Enable: CHECKLOCKTIMEVERIFY Timelock"
    echo "4. Use it: Tools → CHECKLOCKTIMEVERIFY Timelock..."
    echo ""
    echo "📖 See TESTING.md for detailed testing instructions"
else
    echo "❌ Failed to create symlink"
    exit 1
fi
