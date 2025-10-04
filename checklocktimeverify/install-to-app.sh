#!/bin/bash
# Install CHECKLOCKTIMEVERIFY plugin to Electrum.app and launch in signet mode

echo "🔧 Installing CHECKLOCKTIMEVERIFY Plugin to Electrum.app"
echo "========================================================"
echo ""

PLUGIN_SOURCE="/Users/macbook/src/electrum-plugins/checklocktimeverify"
PLUGIN_TARGET="/Volumes/Electrum/Electrum.app/Contents/Resources/electrum/plugins/checklocktimeverify"

# Check if source exists
if [ ! -d "$PLUGIN_SOURCE" ]; then
    echo "❌ Plugin source not found at: $PLUGIN_SOURCE"
    exit 1
fi

echo "📂 Plugin source: $PLUGIN_SOURCE"
echo "📂 Target: $PLUGIN_TARGET"
echo ""
echo "⚠️  This requires sudo to modify the app bundle"
echo ""

# Remove old plugin if exists
if [ -d "$PLUGIN_TARGET" ]; then
    echo "🗑️  Removing old plugin..."
    sudo rm -rf "$PLUGIN_TARGET"
fi

# Copy plugin
echo "📦 Copying plugin..."
sudo cp -r "$PLUGIN_SOURCE" "$PLUGIN_TARGET"

if [ $? -eq 0 ]; then
    echo "✅ Plugin installed successfully!"
    echo ""
    
    # Verify installation
    if [ -f "$PLUGIN_TARGET/manifest.json" ]; then
        echo "✅ Verified: manifest.json found"
        echo "✅ Verified: qt.py found" 
    fi
    
    echo ""
    echo "🚀 Launching Electrum in SIGNET mode..."
    echo ""
    
    # Launch Electrum with signet
    open -a /Volumes/Electrum/Electrum.app --args --signet
    
    echo "✅ Electrum launched!"
    echo ""
    echo "Next steps in Electrum:"
    echo "1. Wait for Electrum to start"
    echo "2. Go to: Tools → Plugins"
    echo "3. Enable: CHECKLOCKTIMEVERIFY Timelock"
    echo "4. Use it: Tools → CHECKLOCKTIMEVERIFY Timelock..."
    echo ""
    
else
    echo "❌ Failed to copy plugin"
    exit 1
fi
