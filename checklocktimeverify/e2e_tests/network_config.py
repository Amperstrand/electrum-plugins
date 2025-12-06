#!/usr/bin/env python3
"""
Central network configuration for E2E tests.
Change NETWORK to switch between testnet4 and signet.
"""

from electrum.constants import BitcoinTestnet4, BitcoinSignet

# ============================================================================
# CONFIGURATION - Change this to switch networks
# ============================================================================

# Options: 'testnet4' or 'signet'
NETWORK = 'signet'  # Default to signet (change to 'testnet4' if needed)

# ============================================================================
# Network Constants (auto-configured based on NETWORK)
# ============================================================================

if NETWORK == 'testnet4':
    ELECTRUM_NETWORK = BitcoinTestnet4
    NETWORK_FLAG = '--testnet4'
    WALLET_SUBDIR = 'testnet4'
    EXPLORER_BASE = 'https://mempool.space/testnet4'
    NETWORK_NAME = 'Testnet4'
    
elif NETWORK == 'signet':
    ELECTRUM_NETWORK = BitcoinSignet
    NETWORK_FLAG = '--signet'
    WALLET_SUBDIR = 'signet'
    EXPLORER_BASE = 'https://mempool.space/signet'
    NETWORK_NAME = 'Signet'
    
else:
    raise ValueError(f"Invalid NETWORK: {NETWORK}. Must be 'testnet4' or 'signet'")


def get_network_config():
    """
    Returns a dictionary with all network configuration.
    """
    return {
        'network': NETWORK,
        'electrum_network': ELECTRUM_NETWORK,
        'network_flag': NETWORK_FLAG,
        'wallet_subdir': WALLET_SUBDIR,
        'explorer_base': EXPLORER_BASE,
        'network_name': NETWORK_NAME,
    }


def configure_electrum():
    """
    Configure electrum.constants.net to use the selected network.
    Call this at the start of any script that uses Electrum.
    """
    import electrum.constants
    electrum.constants.net = ELECTRUM_NETWORK


# Convenience functions
def get_wallet_path(wallet_name='default_wallet'):
    """Get the path to a wallet file for the current network."""
    from pathlib import Path
    return Path.home() / f'.electrum/{WALLET_SUBDIR}/wallets/{wallet_name}'


def get_explorer_url(txid=None, address=None):
    """Get explorer URL for a transaction or address."""
    if txid:
        return f'{EXPLORER_BASE}/tx/{txid}'
    elif address:
        return f'{EXPLORER_BASE}/address/{address}'
    else:
        return EXPLORER_BASE


def print_network_info():
    """Print current network configuration."""
    print(f"🌐 Network: {NETWORK_NAME}")
    print(f"   Flag: {NETWORK_FLAG}")
    print(f"   Wallet dir: ~/.electrum/{WALLET_SUBDIR}/")
    print(f"   Explorer: {EXPLORER_BASE}")
    print()


if __name__ == '__main__':
    print("=" * 70)
    print("NETWORK CONFIGURATION")
    print("=" * 70)
    print()
    print_network_info()
    print("Configuration:")
    import json
    print(json.dumps(get_network_config(), indent=2, default=str))

