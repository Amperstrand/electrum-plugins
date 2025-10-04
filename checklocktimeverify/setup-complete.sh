#!/bin/bash
# Complete Setup: Electrum + CHECKLOCKTIMEVERIFY Plugin

echo "🚀 Complete Electrum + CHECKLOCKTIMEVERIFY Setup"
echo "================================================"
echo ""

# Step 1: Check/Install Electrum
echo "Step 1: Checking for Electrum..."
if [ ! -d "$HOME/electrum" ]; then
    echo "📥 Electrum not found. Installing..."
    cd ~
    git clone https://github.com/spesmilo/electrum.git
    cd electrum
    echo "✅ Electrum cloned"
else
    echo "✅ Electrum already installed"
fi

# Step 2: Install plugin
echo ""
echo "Step 2: Installing CHECKLOCKTIMEVERIFY plugin..."
PLUGIN_SOURCE="/Users/macbook/src/electrum-plugins/checklocktimeverify"
PLUGIN_TARGET="$HOME/electrum/electrum/plugins/checklocktimeverify"

# Remove old symlink if exists
if [ -L "$PLUGIN_TARGET" ]; then
    rm "$PLUGIN_TARGET"
    echo "🗑️  Removed old plugin symlink"
fi

# Create new symlink
ln -s "$PLUGIN_SOURCE" "$PLUGIN_TARGET"
echo "✅ Plugin installed: $PLUGIN_TARGET"

# Verify
if [ -L "$PLUGIN_TARGET" ]; then
    echo "✅ Symlink verified"
    ls -la "$PLUGIN_TARGET"
else
    echo "❌ Symlink creation failed"
    exit 1
fi

echo ""
echo "🎉 Installation Complete!"
echo ""
echo "Next Steps:"
echo "=========="
echo "1. Run Electrum:"
echo "   cd ~/electrum && ./run_electrum"
echo ""
echo "2. In Electrum GUI:"
echo "   - Go to: Tools → Plugins"
echo "   - Enable: CHECKLOCKTIMEVERIFY Timelock"
echo "   - Use it: Tools → CHECKLOCKTIMEVERIFY Timelock..."
echo ""
echo "3. Quick Test:"
echo "   - Enter block: 900000"
echo "   - Click: Get Key from Wallet"
echo "   - Click: Generate Simple Timelock Address"
echo "   - See your P2SH address! 🎉"
echo ""
