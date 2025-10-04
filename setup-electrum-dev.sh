#!/bin/bash
# Setup Electrum development environment with plugin support

set -e

echo "Setting up Electrum development environment..."

# Clone Electrum if not already present
if [ ! -d ~/src/electrum ]; then
    echo "Cloning Electrum repository..."
    cd ~/src
    git clone https://github.com/spesmilo/electrum.git
    cd electrum
else
    echo "Electrum already cloned, updating..."
    cd ~/src/electrum
    git pull
fi

# Create virtual environment if it doesn't exist
if [ ! -d ~/src/electrum/venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv ~/src/electrum/venv
fi

# Activate virtual environment and install
echo "Installing dependencies in virtual environment..."
source ~/src/electrum/venv/bin/activate
pip install -e .

# Symlink your plugin into the Electrum source tree
echo "Installing checklocktimeverify plugin..."
rm -f ~/src/electrum/electrum/plugins/checklocktimeverify
ln -sf /Users/macbook/src/electrum-plugins/checklocktimeverify ~/src/electrum/electrum/plugins/checklocktimeverify

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run Electrum in signet mode with your plugin:"
echo "  cd ~/src/electrum"
echo "  source venv/bin/activate"
echo "  ./run_electrum --signet"
echo ""
echo "Then enable your plugin via Tools → Plugins"
