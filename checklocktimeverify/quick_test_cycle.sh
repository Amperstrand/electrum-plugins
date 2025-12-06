#!/bin/bash
# Quick Test Cycle for CLTV Plugin Development
#
# This script automates the test cycle:
# 1. Kill running Electrum
# 2. Start fresh Electrum instance
# 3. Automatically enable plugin (if you modify GUI code below)
#
# Usage:
#   ./quick_test_cycle.sh [--testnet|--signet|--testnet4]

set -e

# Configuration
ELECTRUM_DIR="/Users/macbook/src/electrum"
PLUGIN_DIR="/Users/macbook/src/electrum-plugins/checklocktimeverify"
PYTHON="$ELECTRUM_DIR/venv/bin/python3"

# Network (default to signet)
NETWORK="${1:---signet}"

echo "============================================"
echo "🔄 CLTV Plugin Quick Test Cycle"
echo "============================================"
echo "Network: $NETWORK"
echo ""

# 1. Kill any running Electrum instances
echo "[1/3] 🛑 Stopping Electrum..."
pkill -f "run_electrum" || echo "  No running instance found"
sleep 1

# 2. Verify plugin is symlinked
echo "[2/3] 🔗 Checking plugin symlink..."
PLUGIN_LINK="$ELECTRUM_DIR/electrum/plugins/checklocktimeverify"
if [ -L "$PLUGIN_LINK" ]; then
    echo "  ✓ Plugin symlink exists"
    # Check if it points to the right place
    LINK_TARGET=$(readlink "$PLUGIN_LINK")
    if [ "$LINK_TARGET" = "$PLUGIN_DIR" ]; then
        echo "  ✓ Points to: $PLUGIN_DIR"
    else
        echo "  ⚠ Warning: Symlink points to different location: $LINK_TARGET"
    fi
elif [ -d "$PLUGIN_LINK" ]; then
    echo "  ℹ Plugin directory exists (not symlink)"
else
    echo "  ❌ Plugin not found! Creating symlink..."
    ln -s "$PLUGIN_DIR" "$PLUGIN_LINK"
    echo "  ✓ Created symlink"
fi

# 3. Start Electrum
echo "[3/3] 🚀 Starting Electrum..."
cd "$ELECTRUM_DIR"

# Activate venv and start Electrum properly
source venv/bin/activate
./run_electrum "$NETWORK" &
ELECTRUM_PID=$!
deactivate 2>/dev/null || true

echo ""
echo "============================================"
echo "✅ Electrum started (PID: $ELECTRUM_PID)"
echo "============================================"
echo ""
echo "📝 Next steps:"
echo "  1. Wait for Electrum to load"
echo "  2. Enable plugin: Tools → Plugins → CHECKLOCKTIMEVERIFY"
echo "  3. Open dialog: Tools → CLTV → Simple Timelock (POC)..."
echo "  4. Test your changes"
echo ""
echo "🔄 To reload after code changes:"
echo "  Option A: Run this script again"
echo "  Option B: Use reload_plugin.py from Electrum console"
echo ""
echo "To stop: kill $ELECTRUM_PID"
echo ""
