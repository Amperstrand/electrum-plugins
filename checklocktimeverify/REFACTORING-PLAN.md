# Systematic Refactoring Plan for BIP-65 CLTV Plugin

## Analysis Summary
- **Total Python Code**: 7,913 lines across 16 files
- **Largest File**: qt.py (3,582 lines) - ⚠️ NEEDS REFACTORING
- **Test Coverage**: 9/9 tests passing
- **Current Quality**: 97.5% DRY score

## Issues Identified

### 🔴 CRITICAL Priority (Security/Correctness)

1. **Hardcoded Magic Numbers**
   - Location: `qt.py:59` and line 1248
   - Issue: `500000000` hardcoded instead of using `LOCKTIME_THRESHOLD` constant
   - Impact: Maintenance risk, potential inconsistency
   - Fix: Replace magic number with constant reference

2. **TODOs in Production Code**
   - Location: `taproot_helpers.py:221, 235`
   - Issue: "TODO: Implement MAST support" in production
   - Impact: Indicates incomplete feature
   - Fix: Either implement or document as future enhancement

3. **Sponsor Messages in Code**
   - Location: `qt.py:1-16` (docstring), line 97, 105
   - Issue: Marketing copy in production code
   - Impact: Unprofessional, distracting
   - Fix: Remove or move to README/LICENSE

### 🟡 HIGH Priority (Maintainability)

4. **qt.py is Too Large (3,582 lines)**
   - Issue: Violates Single Responsibility Principle
   - Impact: Hard to maintain, navigate, test
   - Fix: Split into:
     - `qt.py` - Plugin registration and UI shell (500 lines)
     - `dialog_manager.py` - Tab and dialog coordination (800 lines)
     - `sweep_operations.py` - Sweep/spending logic (1,000 lines)
     - `script_generation.py` - Legacy script building (remaining)

5. **Duplicate Error Handling Patterns**
   - Location: Multiple `try/except` blocks with similar QMessageBox calls
   - Impact: Code duplication, inconsistent error messages
   - Fix: Create `ErrorHandler` class with standardized methods

6. **Inconsistent Logging**
   - Issue: Mix of `self.log()`, `logger.info()`, `print()`
   - Impact: Hard to debug, inconsistent log levels
   - Fix: Standardize on logger with proper levels

7. **Long Method Names**
   - Examples: 
     - `check_address_utxos(self, address: str, force_refresh: bool = False, persistent_cache: dict = None) -> dict:` (108 chars)
     - `display_results(self, address: str, script_hex: str, script_type: str, locktime: int, ...)` (107 chars)
   - Impact: Readability
   - Fix: Shorten while maintaining clarity

8. **Test Files Not Following Conventions**
   - Location: Multiple `test_*.py` files in main directory
   - Issue: Should be in `tests/` subdirectory
   - Impact: Directory clutter, unclear separation
   - Fix: Create `tests/` directory and move files

### 🟢 MEDIUM Priority (Readability)

9. **BIP-32 Test Vectors in Class Definition**
   - Location: `qt.py:61-86`
   - Issue: 26 lines of test data in class body
   - Impact: Clutters class definition
   - Fix: Move to separate `test_vectors.py` module

10. **Redundant Imports**
    - Location: Multiple files
    - Issue: `from PyQt6.QtWidgets import (...)` spans many lines
    - Impact: Visual noise
    - Fix: Group related imports, use `as` for long names

11. **Inconsistent String Quotes**
    - Issue: Mix of single and double quotes
    - Impact: Minor style inconsistency
    - Fix: Standardize on double quotes (current majority)

12. **Missing Type Hints**
    - Location: Many functions lack return type annotations
    - Impact: Reduced IDE support, unclear contracts
    - Fix: Add comprehensive type hints

13. **Comments That Should Be Docstrings**
    - Location: Inline `#` comments describing functions
    - Impact: Not accessible via `help()` or IDEs
    - Fix: Convert to proper docstrings

### 🔵 LOW Priority (Style/Polish)

14. **Emoji Overuse**
    - Location: Throughout qt.py
    - Issue: ⚠️ 🚨 🚀 appear frequently
    - Impact: Can be distracting in logs
    - Fix: Reduce to critical warnings only

15. **Verbose Variable Names**
    - Examples: `redeem_script_hex`, `publisher_pubkey_hex`
    - Impact: Minor verbosity
    - Fix: Could be `redeem_script`, `publisher_pubkey` (type hints clarify)

16. **Blank Line Inconsistencies**
    - Issue: Varying spacing between methods
    - Impact: Visual consistency
    - Fix: Enforce 2 blank lines between methods

## Refactoring Phases

### Phase 1: Quick Wins (30 min)
- [x] Remove sponsor messages from code
- [x] Replace magic number 500000000 with LOCKTIME_THRESHOLD
- [x] Standardize logging approach
- [x] Add missing type hints to key functions

### Phase 2: Structure (2 hours)
- [ ] Split qt.py into logical modules
- [ ] Move test files to tests/ directory
- [ ] Extract BIP-32 test vectors to separate module
- [ ] Create ErrorHandler utility class

### Phase 3: Polish (1 hour)
- [ ] Convert comments to docstrings
- [ ] Standardize string quotes
- [ ] Fix blank line spacing
- [ ] Reduce emoji usage

### Phase 4: Documentation (30 min)
- [ ] Address or remove TODOs
- [ ] Update docstrings with accurate descriptions
- [ ] Create REFACTORING.md with changes

## Success Criteria
- ✅ All 9 tests still pass
- ✅ No functional changes (behavior preserved)
- ✅ Code quality improved (measured by DRY analysis)
- ✅ File structure more maintainable
- ✅ No sponsor messages in production code

## Non-Goals
- ❌ Rewriting core algorithms
- ❌ Changing public APIs
- ❌ Adding new features
- ❌ Performance optimization (already fast)

## Risk Mitigation
- Run tests after each phase
- Commit after each successful phase
- Keep git history clean with descriptive messages
- Document any behavior changes (should be none)
