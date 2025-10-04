#!/bin/bash
# Install plugin to Electrum.app in Applications folder

echo "🔧 Installing CHECKLOCKTIMEVERIFY Plugin"
echo "========================================"
echo ""

PLUGIN_SOURCE="/Users/macbook/src/electrum-plugins/checklocktimeverify"
ELECTRUM_APP="/Applications/Electrum.app"
PLUGIN_TARGET="$ELECTRUM_APP/Contents/Resources/electrum/plugins/checklocktimeverify"

# Check if Electrum is in Applications
if [ ! -d "$ELECTRUM_APP" ]; then
    echo "📥 Electrum not found in Applications folder"
    echo "   Copying from /Volumes/Electrum/Electrum.app..."
    echo ""
    
    if [ -d "/Volumes/Electrum/Electrum.app" ]; then
        sudo cp -R /Volumes/Electrum/Electrum.app /Applications/
        echo "✅ Electrum copied to Applications"
    else
        echo "❌ Electrum.app not found. Please mount the DMG first."
        exit 1
    fi
fi

echo "📂 Plugin source: $PLUGIN_SOURCE"
echo "📂 Target: $PLUGIN_TARGET"
echo ""

# Remove old plugin if exists
if [ -d "$PLUGIN_TARGET" ]; then
    echo "🗑️  Removing old plugin..."
    sudo rm -rf "$PLUGIN_TARGET"
fi

# Copy plugin
echo "📦 Installing plugin..."
sudo cp -r "$PLUGIN_SOURCE" "$PLUGIN_TARGET"

if [ $? -eq 0 ]; then
    echo "✅ Plugin installed successfully!"
    echo ""
    
    # Verify installation
    if [ -f "$PLUGIN_TARGET/manifest.json" ]; then
        echo "✅ Verified: Files installed correctly"
        ls "$PLUGIN_TARGET" | head -5
    fi
    
    echo ""
    echo "🚀 Launching Electrum in SIGNET mode..."
    echo ""
    
    # Launch Electrum with signet
    open -a /Applications/Electrum.app --args --signet
    
    echo "✅ Electrum launched!"
    echo ""
    echo "📋 Next steps in Electrum:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "1. Wait for Electrum to start (signet mode)"
    echo "2. Go to: Tools → Plugins"
    echo "3. Find: CHECKLOCKTIMEVERIFY Timelock"
    echo "4. ✅ Check the box to enable it"
    echo "5. Use: Tools → CHECKLOCKTIMEVERIFY Timelock..."
    echo ""
    echo "🎉 Enjoy your timelocked Bitcoin addresses!"
    echo ""
    
else
    echo "❌ Failed to install plugin"
    exit 1
fi
