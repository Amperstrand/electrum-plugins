#!/usr/bin/env python3
"""
Path Setup Utilities

Centralized path manipulation for test modules to avoid duplication.
Configures sys.path for:
- Third-party BIP reference implementations (bip_0340, bip_350)
- bitcoin-tx-tutorial functions
- E2E test utilities (taproot_utils, opcodes_ext)
"""

import sys
import os
from pathlib import Path


def setup_third_party_path():
    """Add third_party directory to sys.path for BIP reference implementations."""
    third_party = os.path.normpath(os.path.join(os.path.dirname(__file__), 'third_party'))
    if third_party not in sys.path:
        sys.path.insert(0, third_party)


def setup_tutorial_path():
    """Add bitcoin-tx-tutorial to sys.path for BIP-340 reference functions."""
    # From script_builders/taproot/*.py: 5 levels up
    # From sweepers/taproot/*.py: 3 levels up
    # Try both locations
    tutorial_path_5 = Path(__file__).parent.parent.parent.parent / 'bitcoin-tx-tutorial' / 'functions'
    tutorial_path_3 = Path(__file__).parent.parent / 'bitcoin-tx-tutorial' / 'functions'
    
    tutorial_path = tutorial_path_5 if tutorial_path_5.exists() else tutorial_path_3
    if tutorial_path.exists() and str(tutorial_path) not in sys.path:
        sys.path.insert(0, str(tutorial_path))


def setup_e2e_utils_path():
    """Add e2e_tests directory to sys.path for taproot_utils and opcodes_ext."""
    e2e_path = os.path.normpath(os.path.join(os.path.dirname(__file__)))
    if e2e_path not in sys.path:
        sys.path.insert(0, e2e_path)


def setup_taproot_helpers_path():
    """Add script_builders/taproot to sys.path for taproot_sighash_helper, etc."""
    taproot_helpers = os.path.normpath(os.path.join(os.path.dirname(__file__), 'script_builders/taproot'))
    if taproot_helpers not in sys.path:
        sys.path.insert(0, taproot_helpers)


def setup_all_paths():
    """Configure all common paths for e2e test modules."""
    setup_third_party_path()
    setup_tutorial_path()
    setup_e2e_utils_path()
    setup_taproot_helpers_path()
