"""
CLTV Dialogs Package

GUI dialogs for creating and managing CLTV timelock addresses.

Key Components:
- CLTVList: Tab-based interface for managing timelock addresses (replaces ManageTimelocksDialog)
- UnifiedCreationDialog: Create any of the 5 contract types from ContractDefinition
- CLTVAddressDialog: Detailed view for a single address (sweeping, scripts, etc.)
"""

import logging
_logger = logging.getLogger(__name__)

def _log_import_error(name: str, error: Exception):
    """Log import errors safely (handles missing stdout/stderr)"""
    try:
        _logger.warning(f"Failed to import {name}: {error}")
    except OSError:
        pass  # Ignore I/O errors when no terminal attached

# Tab-based list widget (replaces ManageTimelocksDialog)
try:
    from .cltv_list import CLTVList
except ImportError as e:
    _log_import_error("CLTVList", e)
    CLTVList = None

# Unified creation dialog (single dialog for all 5 contract types)
try:
    from .unified_creation_dialog import UnifiedCreationDialog
except ImportError as e:
    _log_import_error("UnifiedCreationDialog", e)
    UnifiedCreationDialog = None

# Address detail dialog
try:
    from .cltv_address_dialog import CLTVAddressDialog
except ImportError as e:
    _log_import_error("CLTVAddressDialog", e)
    CLTVAddressDialog = None

# Path details dialog (shows miniscript, keys, technical info)
try:
    from .path_details_dialog import PathDetailsDialog, show_path_details
except ImportError as e:
    _log_import_error("PathDetailsDialog", e)
    PathDetailsDialog = None
    show_path_details = None

# UI Generator functions (for dynamic UI from ContractDefinition)
try:
    from .ui_generator import (
        get_contract_for_script_type,
        generate_status_section,
        generate_path_button,
        generate_key_section,
        generate_miniscript_section,
    )
except ImportError as e:
    _log_import_error("ui_generator", e)

__all__ = [
    'CLTVList',
    'UnifiedCreationDialog',
    'CLTVAddressDialog',
    'PathDetailsDialog',
    'show_path_details',
    'get_contract_for_script_type',
    'generate_status_section',
    'generate_path_button',
    'generate_key_section',
    'generate_miniscript_section',
]
