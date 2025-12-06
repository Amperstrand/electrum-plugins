"""
Registry - Compatibility Shim for cltv_lib

Provides backward-compatible APIs for E2E tests while delegating
to cltv_lib.registry.
"""

import sys
import os

# Add parent directory to import cltv_lib
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from cltv_lib.registry import (
    REGISTRY,
    ScriptConfig,
    get_config,
    get_builder,
    get_sweeper,
    list_scripts,
)

def build_script(script_type: str, params: dict) -> str:
    """Build a script and return its hex."""
    builder = get_builder(script_type)
    script = builder.build(params)
    return script.hex()

def verify_script(script_type: str, params: dict, expected_hex: str) -> bool:
    """Verify that building a script produces the expected hex."""
    return build_script(script_type, params) == expected_hex

def get_format(script_type: str) -> str:
    """Get the script format for a given script type."""
    config = get_config(script_type)
    # output_type is already a string ('p2wsh' or 'taproot')
    return config.output_type.upper()

# Re-export for backward compat
SCRIPT_REGISTRY = REGISTRY

__all__ = [
    'REGISTRY', 'SCRIPT_REGISTRY', 'ScriptConfig',
    'get_config', 'get_builder', 'get_sweeper', 'list_scripts',
    'build_script', 'verify_script', 'get_format',
]
