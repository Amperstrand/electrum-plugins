"""
Simple State Manager for E2E Tests

Manages test state in JSON format.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class StateManager:
    """Manages test state persistence."""
    
    def __init__(self, state_file='test_state.json'):
        # If state_file is relative, look in parent directory (one level up from e2e_tests/)
        state_path = Path(state_file)
        if not state_path.is_absolute():
            # When running from e2e_tests/, go up one level
            state_path = Path(__file__).parent.parent / state_file
        self.state_file = state_path
        self.state = self._load()
    
    def _load(self):
        """Load state from JSON file."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save(self):
        """Save state to JSON file."""
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def add_test(self, category: str, variant: str, test_data: Dict):
        """Add a test to the state."""
        if category not in self.state:
            self.state[category] = {}
        if variant not in self.state[category]:
            self.state[category][variant] = []
        self.state[category][variant].append(test_data)
    
    def get_tests(self, category: str, variant: str) -> List[Dict]:
        """Get tests for a category/variant."""
        return self.state.get(category, {}).get(variant, [])
    
    def update_test(self, category: str, variant: str, test_data: Dict):
        """Update a test in the state."""
        tests = self.get_tests(category, variant)
        if tests:
            # Update the first test (we only have one per variant currently)
            self.state[category][variant][0] = test_data

