"""
Electrum script operations adapter.

Delegates to electrum.bitcoin module
while implementing the ScriptInterface for dependency injection.
"""

from ..interfaces import ScriptInterface
import logging


logger = logging.getLogger(__name__)


class ElectrumScriptAdapter(ScriptInterface):
    """Adapter for Electrum's script operations."""
    
    def construct_script(self, ops: List[int], push: bool = False) -> bytes:
        """Construct Bitcoin script from opcodes."""
        from electrum.bitcoin import construct_script as electrum_construct_script
        return electrum_construct_script(ops, push=push)
    
    def opcodes(self) -> dict:
        """Get available opcodes."""
        from electrum.bitcoin import opcodes as electrum_opcodes
        return electrum_opcodes
    
    def add_number_to_script(self, script: bytes, number: int) -> bytes:
        """Add number to script."""
        from electrum.bitcoin import add_number_to_script as electrum_add_number
        return electrum_add_number(script, number)
    
    def var_int(self, n: int) -> bytes:
        """Convert integer to 4-byte var_int."""
        from electrum.bitcoin import var_int as electrum_var_int
        return electrum_var_int(n)
    
    def script_num_to_bytes(self, n: int) -> bytes:
        """Convert script number to bytes."""
        from electrum.bitcoin import script_num_to_bytes as electrum_script_num_to_bytes
        return electrum_script_num_to_bytes(n)


__all__ = [
    'ElectrumScriptAdapter',
]