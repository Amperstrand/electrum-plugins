Major refactoring areas
1. Removed unnecessary wrapper functions
Replaced with direct Electrum API calls:
get_address_balance() → wallet.get_addr_balance()
check_utxos() → wallet.adb.get_addr_utxo()
get_mined_info() → wallet.adb.get_tx_height()
get_address_funding_info() → removed (dead code)
_get_balance() in cltv_list.py → direct calls
_get_current_height() in cltv_list.py → wallet.adb.get_local_height()
2. Removed manual caching and network fallbacks
Removed _balance_cache, _utxo_cache, and related TTL logic
Removed network query fallbacks (_query_address_utxos_from_network)
Now relies on Electrum's ADB cache, which updates automatically
3. Removed polling and manual refresh
Removed _schedule_post_broadcast_refresh() polling mechanism
Removed "Refresh Balances" button from toolbar
Removed refresh context menu action
UI updates now happen via Electrum's native hooks (on_history, blockchain_updated, wallet_updated)
4. Dialog management refactoring
Removed plugin's dialog tracking system (_open_dialogs, register_dialog, unregister_dialog, _refresh_open_dialogs)
Removed plugin's show_* helper functions (show_unified_creation, show_settings, show_unfunded_addresses)
Dialogs now use QtEventListener for self-refreshing
Direct dialog instantiation where needed (e.g., in cltv_list.py)
5. Removed unnecessary try/except blocks
Removed try/except around wallet.get_addr_balance() calls to let exceptions propagate for better debugging
Applied across qt.py, cltv_address_dialog.py, and cltv_list.py
6. Wallet instance handling
Refactored self.wallet to be a @property that always returns self.main_window.wallet (or self.window.wallet in dialogs)
Ensures fresh wallet instances and fixes strict identity checks that prevented updates
Removed _get_main_window() method
7. Tab management simplification
Simplified add_cltv_tab logic to correctly identify and reuse valid CLTVList tabs
Removed redundant code block that was checking for existing tabs incorrectly
Removed _tabs_added tracking
8. Bug fixes
Fixed _build_p2wsh accessing witness_script_hash instead of script_hash
Fixed _wrap_address returning error string instead of raising exception for taproot
Fixed coins not showing in dialog (unconditional clearing logic)
Fixed TypeError with setFont() in unified_creation_dialog.py
Fixed @QtCore.pyqtSlot decorator placement on property instead of method
9. Legacy format cleanup
Removed all storage migration code
Removed legacy format support (only v12.0.0 format now)
Removed derive_key_from_wallet() function (unused)
Simplified address loading to skip (not delete) invalid addresses
Result
The plugin now:
Uses Electrum's native address monitoring (no manual queries)
Updates UI automatically via hooks (no polling)
Uses standard logging (no custom logging system)
Has cleaner error handling (exceptions instead of silent failures)
Follows Electrum UI patterns (QtEventListener, direct API calls)
Has less code (removed ~200 lines of wrappers, caching, and polling)
These changes align the plugin with Electrum's architecture and patterns.
