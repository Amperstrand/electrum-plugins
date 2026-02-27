"""
Simple State Manager for E2E Tests

Manages test state in JSON format.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Miniscript/descriptor renderer for state enrichment
try:
    from miniscript_registry import miniscript_for, descriptor_for
except Exception:
    miniscript_for = None
    descriptor_for = None


class StateManager:
    """Manages test state persistence."""

    # Storage format version - increment to invalidate old state
    CURRENT_VERSION = 2

    def __init__(self, locktime: int):
        """
        Initialize StateManager with explicit locktime.
        
        Args:
            locktime: REQUIRED locktime value (determines state file name)
        
        Raises:
            TypeError: If locktime is not provided
        """
        if locktime is None:
            raise TypeError(
                "StateManager requires explicit locktime parameter.\n"
                "Example: StateManager(locktime=5)"
            )
        
        # Always use locktime-specific filename
        state_file = f"test_state_{locktime}.json"
        
        # Always store in e2e_tests/ directory
        state_path = Path(state_file)
        if not state_path.is_absolute():
            state_path = Path(__file__).parent / state_file
        self.state_file = state_path
        self.locktime = locktime
        self.state = self._load()
    
    def _load(self):
        """Load state from JSON file."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                data = json.load(f)

            # Check version compatibility - if old version or no version, clear state
            stored_version = data.get('version', 0)
            if stored_version < self.CURRENT_VERSION:
                print(f" State file version {stored_version} is outdated (current: {self.CURRENT_VERSION}). Clearing old state to purge addresses.")
                return {}

            return data
        return {}
    
    def save(self):
        """Save state to JSON file."""
        self.state['version'] = self.CURRENT_VERSION
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _enrich_with_miniscript(self, test_data: Dict) -> Dict:
        """Compute Miniscript and descriptor for test_data if possible."""
        if not miniscript_for or not descriptor_for:
            return test_data
        try:
            st = (test_data.get('script_type') or '').lower()
            params = dict(test_data.get('script_params') or {})
            if 'locktime' not in params and test_data.get('locktime') is not None:
                params['locktime'] = test_data['locktime']
            # Fill params from top-level keys (using miniscript names)
            for k in ('pubkey', 'alice', 'bob', 'lenny', 'user', 'service', 
                      'sender', 'receiver', 'publisher', 'buyer', 'data_hash'):
                if k not in params and k in test_data:
                    params[k] = test_data[k]
            
            # v12.0.0: script_type is canonical (e.g., 'cltv_hodl_p2wsh')
            # Strip output type suffix to get base type for miniscript_for
            ms_type = st.replace('_p2wsh', '').replace('_taproot', '')
            if not ms_type.startswith('cltv_'):
                return test_data
            
            ms_sym = miniscript_for(ms_type, params, style='symbolic')
            ms_conc = miniscript_for(ms_type, params, style='concrete')
            var = 'tr' if (test_data.get('format', '').upper() == 'TAPROOT') else 'wsh'
            desc = descriptor_for(ms_type, params, variant=var)
            if var == 'tr' and test_data.get('internal_key'):
                desc = desc.replace('<internal_key>', test_data['internal_key'])
            # attach
            test_data.setdefault('miniscript_symbolic', ms_sym)
            test_data.setdefault('miniscript_concrete', ms_conc)
            if var == 'wsh':
                test_data.setdefault('descriptor_wsh', desc)
            else:
                test_data.setdefault('descriptor_tr', desc)
            # also keep a generic descriptor field for quick display
            test_data.setdefault('descriptor', desc)
        except Exception:
            # best effort enrichment; ignore failures
            pass
        return test_data
    
    def add_test(self, category: str, variant: str, test_data: Dict):
        """Add a test to the state."""
        if category not in self.state:
            self.state[category] = {}
        if variant not in self.state[category]:
            self.state[category][variant] = []
        # Enrich before saving
        test_data = self._enrich_with_miniscript(test_data)
        self.state[category][variant].append(test_data)
    
    def get_tests(self, category: str, variant: str, path: Optional[str] = None) -> List[Dict]:
        """Get tests for a category/variant, optionally filtered by path."""
        tests = self.state.get(category, {}).get(variant, [])
        if path is not None:
            tests = [t for t in tests if t.get('path') == path]
        return tests
    
    def update_test(self, category: str, variant: str, test_data: Dict):
        """Update a test in the state."""
        tests = self.get_tests(category, variant)
        if tests:
            # Update the first test (we only have one per variant currently)
            self.state[category][variant][0] = test_data
    
    def delete_test(self, category: str, variant: str, test_number: Optional[int] = None):
        """Delete a test from the state.
        
        Args:
            category: Test category (e.g., 'cltv_payment_channel')
            variant: Test variant (e.g., 'p2wsh_cooperative')
            test_number: Optional test number to match (if None, deletes all tests in variant)
        """
        if category not in self.state:
            return
        
        if variant not in self.state[category]:
            return
        
        tests = self.state[category][variant]
        if test_number is not None:
            # Delete specific test by number
            self.state[category][variant] = [
                t for t in tests if t.get('test_number') != test_number
            ]
        else:
            # Delete all tests in variant
            self.state[category][variant] = []
        
        # Clean up empty categories/variants
        if not self.state[category][variant]:
            del self.state[category][variant]
        if not self.state[category]:
            del self.state[category]


