# Multiple Locktimes UX Design Decisions

## Problem Statement

The decaying multisig contract has **multiple locktime parameters** (`locktime_60m`, `locktime_66m`), where different spending paths become available at different times:
- **Normal path**: Available immediately (no locktime)
- **Decay 60m path**: Available after `locktime_60m` 
- **Decay 66m path**: Available after `locktime_66m`

Current UX assumes a single `locktime` parameter. We need to adapt the UI to handle contracts where:
1. Different paths have different locktimes
2. Multiple locktime parameters exist in the contract definition
3. Path availability depends on which locktime has been reached

## Decision Points

### 1. **SpendingPath.requires_locktime and Path-Specific Locktimes**

**Current State**: 
- `SpendingPath.requires_locktime` is a boolean
- All paths use the same `params.get('locktime')` value

**Questions**:
- [ ] Should `SpendingPath` have a `locktime_param_name` field to specify which locktime parameter it uses?
  - Example: `locktime_param_name="locktime_60m"` for decay_60m path
  - Default: `"locktime"` for backwards compatibility
- [ ] Or should we infer it from the path's position in `taproot_leaves`?
  - Leaf 0 (normal) → no locktime
  - Leaf 1 (decay_60m) → uses `locktime_60m`
  - Leaf 2 (decay_66m) → uses `locktime_66m`
- [ ] How do we handle P2WSH paths where `taproot_leaves` doesn't apply?

**Recommendation**: Add `locktime_param_name: Optional[str] = None` to `SpendingPath`. If `None`, fall back to `"locktime"` for backwards compatibility.

---

### 2. **Address Dialog: Locktime Status Display**

**Current State**: 
- Shows single locktime status: "🔒 Locked (X blocks remaining)" or "🔓 Unlocked"
- Uses `params.get('locktime')`

**Questions**:
- [ ] Should we show **one locktime status** (the earliest one) or **multiple locktime statuses**?
  - Option A: Show earliest locktime only (simpler, less cluttered)
  - Option B: Show all locktimes in a list (more informative)
  - Option C: Show locktime status per path (most accurate)
- [ ] How should we display multiple locktimes?
  - List format: "Locktime 60m: 🔒 100 blocks remaining | Locktime 66m: 🔒 106 blocks remaining"
  - Timeline format: Visual timeline showing when each path unlocks
  - Per-path format: Show locktime in each path button's tooltip/status
- [ ] Should we show a "next unlock" indicator (e.g., "Next path unlocks in 100 blocks")?

**Recommendation**: Show locktime status **per path** in the path buttons themselves. Add a summary section showing all locktimes in a compact format.

---

### 3. **Path Button Availability Logic**

**Current State**:
```python
locktime = params.get('locktime', 0)
locktime_satisfied = not path.requires_locktime or current_height >= locktime
is_available = has_funds and (not path.requires_locktime or locktime_satisfied)
```

**Questions**:
- [ ] How do we determine which locktime to check for each path?
  - Use `path.locktime_param_name` if set
  - Fall back to `"locktime"` for backwards compatibility
- [ ] What if a path doesn't specify `locktime_param_name` but the contract has multiple locktimes?
  - Should we infer from path name? (e.g., "decay_60m" → `locktime_60m`)
  - Should we use the first locktime parameter?
  - Should we require explicit specification?
- [ ] How do we handle paths that don't require locktime but the contract has locktimes?
  - Normal path: `requires_locktime=False` → always available (correct)
  - But what if we want to show "available now" vs "available after X"?

**Recommendation**: 
- Add `locktime_param_name` to `SpendingPath`
- Update availability check: `locktime = params.get(path.locktime_param_name or 'locktime', 0)`
- For paths with `requires_locktime=False`, show "Available now" regardless of locktimes

---

### 4. **Main List View (CLTVList): Locktime Column**

**Current State**:
- Shows single `locktime` value in the table
- Uses `params.get('locktime', 0)`

**Questions**:
- [ ] How should we display multiple locktimes in the table?
  - Option A: Show earliest locktime only (simplest)
  - Option B: Show range (e.g., "100-106" or "100 → 106")
  - Option C: Show all locktimes (e.g., "60m:100, 66m:106")
  - Option D: Show "Multiple" with tooltip showing all locktimes
- [ ] Should we add a "Next Unlock" column showing when the next path becomes available?
- [ ] How do we sort by locktime when there are multiple?
  - Sort by earliest locktime?
  - Sort by latest locktime?
  - Sort by "next available path"?

**Recommendation**: Show earliest locktime in the main column, with a tooltip showing all locktimes. Add a "Next Unlock" column showing when the next path becomes available.

---

### 5. **Path Details Dialog: Locktime Information**

**Current State**: 
- Shows locktime for the path being viewed
- Uses `params.get('locktime', 0)`

**Questions**:
- [ ] Should we show **only the locktime for this path**, or **all locktimes**?
  - Option A: Only this path's locktime (focused, less confusing)
  - Option B: All locktimes with this one highlighted (contextual)
- [ ] How should we display the relationship between paths and locktimes?
  - Timeline visualization?
  - List format: "Path X unlocks at block Y"
  - Tree format showing path dependencies?

**Recommendation**: Show this path's locktime prominently, with a "Contract Timeline" section showing all paths and their unlock times.

---

### 6. **Sweep Validation: Path-Specific Locktime Check**

**Current State**:
```python
locktime = output.get('locktime', 0)
can_sweep, error_msg = validate_sweep_conditions(
    self.contract_name, self.path, locktime, current_height
)
```

**Questions**:
- [ ] How do we get the correct locktime for the path being swept?
  - From `SpendingPath.locktime_param_name`?
  - From `output['script_params']` using the path's locktime parameter name?
- [ ] What if `script_params` doesn't have the locktime parameter?
  - Should we require it to be stored?
  - Should we infer from the path name?
  - Should we fail with a clear error?
- [ ] How do we validate that the correct locktime is being used?
  - Check that `locktime_60m < locktime_66m`?
  - Check that locktimes are in the future (for creation)?
  - Check that locktimes are in the past (for sweeping)?

**Recommendation**: 
- Store all locktime parameters in `script_params` when creating the address
- Use `path.locktime_param_name` to look up the correct locktime
- Validate locktime relationships when creating addresses

---

### 7. **Creation Dialog: Multiple Locktime Inputs**

**Current State**: ✅ **FIXED** - Now handles multiple locktime inputs via `locktime_edits` dict

**Questions**:
- [ ] Should we show a **visual relationship** between locktimes?
  - Timeline showing locktime_60m → locktime_66m?
  - Validation that locktime_60m < locktime_66m?
  - Helper text explaining the decay schedule?
- [ ] Should we provide **preset values** for common decay schedules?
  - "60 months" button that calculates locktime_60m
  - "66 months" button that calculates locktime_66m
  - Auto-calculate locktime_66m = locktime_60m + 6 months?
- [ ] How should we label the inputs?
  - "Locktime (60 months)" and "Locktime (66 months)" ✅ (already implemented)
  - Or more descriptive: "When 2-of-5 becomes available"?
  - Show both: label + description?

**Recommendation**: 
- Add validation that locktime_60m < locktime_66m
- Add helper text explaining the decay schedule
- Consider preset buttons for common intervals (future enhancement)

---

### 8. **Contract Definition: Locktime Parameter Mapping**

**Current State**: 
- `SpendingPath.requires_locktime` is boolean
- No way to specify which locktime parameter a path uses

**Questions**:
- [ ] Should we add `locktime_param_name: Optional[str]` to `SpendingPath`?
  - Default: `None` → use `"locktime"` for backwards compatibility
  - Example: `locktime_param_name="locktime_60m"` for decay_60m path
- [ ] Should we infer from path name or require explicit specification?
  - Infer: "decay_60m" → `locktime_60m` (magic, error-prone)
  - Explicit: Must specify in contract definition (clear, verbose)
- [ ] How do we handle contracts with a single locktime but multiple paths?
  - Some paths use locktime, some don't
  - All use the same locktime parameter name

**Recommendation**: Add `locktime_param_name: Optional[str] = None` to `SpendingPath`. Require explicit specification for clarity.

---

### 9. **Backwards Compatibility**

**Current State**: 
- All existing contracts use single `locktime` parameter
- Code assumes `params.get('locktime')` exists

**Questions**:
- [ ] How do we maintain backwards compatibility?
  - Always check for `"locktime"` if `locktime_param_name` is `None`?
  - Support both `params.get('locktime')` and `params.get(path.locktime_param_name)`?
- [ ] Should we migrate existing addresses to use the new system?
  - No: Keep old addresses as-is, only new addresses use new system
  - Yes: Update address storage to include all locktime parameters
- [ ] How do we handle addresses created before this change?
  - They only have `locktime` in params
  - New code should fall back gracefully

**Recommendation**: 
- Always support `params.get('locktime')` as fallback
- New contracts explicitly specify `locktime_param_name`
- Existing addresses continue to work with single `locktime`

---

### 10. **UI/UX Patterns: Visual Design**

**Questions**:
- [ ] How should we **visually distinguish** paths with different locktimes?
  - Color coding: Green (available), Yellow (soon), Red (locked)
  - Icons: 🔓 (unlocked), 🔒 (locked), ⏰ (countdown)
  - Progress bars showing time until unlock?
- [ ] Should we show a **timeline visualization**?
  - Horizontal timeline showing when each path unlocks
  - Vertical timeline in the address dialog
  - Mini timeline in the main list view
- [ ] How should we display **countdown information**?
  - "100 blocks remaining" (current)
  - "~17 hours remaining" (time estimate)
  - "Available in 1.4 days" (human-readable)
- [ ] Should we show **locktime relationships**?
  - "Path 2 unlocks 6 blocks after Path 1"
  - "All paths unlock within 6 blocks"
  - Visual connection between related paths

**Recommendation**: 
- Use color coding and icons (already implemented)
- Add a compact timeline in the address dialog
- Show human-readable time estimates in tooltips
- Consider a "Contract Timeline" section for complex contracts

---

### 11. **Data Storage: Locktime Parameters**

**Current State**: 
- Address storage includes `script_params` dict
- Single `locktime` parameter stored

**Questions**:
- [ ] Should we store **all locktime parameters** in `script_params`?
  - Yes: `{"locktime_60m": 100, "locktime_66m": 106, ...}`
  - Also store `"locktime"` for backwards compatibility?
- [ ] How do we handle **addresses created before multiple locktimes**?
  - They only have `"locktime"` in params
  - Should we infer other locktimes? (No - too error-prone)
  - Should we require migration? (No - keep as-is)
- [ ] Should we validate **locktime relationships** when saving?
  - Ensure `locktime_60m < locktime_66m`?
  - Ensure locktimes are in the future (for new addresses)?
  - Ensure locktimes are reasonable (not 1000 years in the future)?

**Recommendation**: 
- Store all locktime parameters in `script_params`
- Also store `"locktime"` = earliest locktime for backwards compatibility
- Validate locktime relationships when creating addresses

---

### 12. **E2E Tests: Multiple Locktime Testing**

**Current State**: ✅ **FIXED** - Test generation handles multiple locktimes with offsets

**Questions**:
- [ ] Should we test **all locktime combinations**?
  - Current: `locktime_60m = base`, `locktime_66m = base + 6`
  - Should we test with different offsets?
  - Should we test edge cases (locktime_60m = locktime_66m)?
- [ ] How do we test **path availability** at different blockchain heights?
  - Test at height < locktime_60m (only normal path available)
  - Test at height >= locktime_60m but < locktime_66m (normal + 60m available)
  - Test at height >= locktime_66m (all paths available)
- [ ] Should we test **sweeping with wrong locktime**?
  - Try to sweep decay_60m path before locktime_60m (should fail)
  - Try to sweep decay_66m path before locktime_66m (should fail)

**Recommendation**: 
- Test all three scenarios (before 60m, between 60m-66m, after 66m)
- Test that wrong locktime validation fails correctly
- Current offset approach (base, base+6) is sufficient for e2e

---

## Implementation Priority

### Phase 1: Core Functionality (Required)
1. ✅ Add `locktime_param_name` to `SpendingPath` 
2. ✅ Update path availability logic to use path-specific locktime
3. ✅ Update sweep validation to use path-specific locktime
4. ✅ Store all locktime parameters in address storage
5. ✅ Update UI to show path-specific locktime status

### Phase 2: UX Improvements (Recommended)
6. Add timeline visualization in address dialog
7. Update main list view to show multiple locktimes
8. Add locktime relationship validation
9. Improve tooltips with human-readable time estimates

### Phase 3: Polish (Optional)
10. Add preset buttons for common decay schedules
11. Add "Contract Timeline" section in path details
12. Add visual connections between related paths

---

## Example: Decaying Multisig UX Flow

### Creation Dialog
```
Contract: Decaying Multisig
─────────────────────────────
Locktime (60 months): [1000] blocks
Locktime (66 months): [1006] blocks  ← Auto-calculated or manual

Key 1: [alice pubkey...] [Test Key]
Key 2: [bob pubkey...] [Test Key]
...
```

### Address Dialog - Status Section
```
🔓 Decaying Multisig
─────────────────────
Locktimes:
  • Normal path: Available now
  • 60-month decay: 🔒 100 blocks remaining (block 1000)
  • 66-month decay: 🔒 106 blocks remaining (block 1006)

Balance: 100,000 sats
```

### Address Dialog - Path Buttons
```
[✅ Normal (3-of-5)]          ← Green, enabled
   Available now - Spend with 3 of 5 keys

[🔒 After 60 Months (2-of-5)] ← Red, disabled
   Available after block 1000 (100 blocks remaining)

[🔒 After 66 Months (1-of-5)] ← Red, disabled  
   Available after block 1006 (106 blocks remaining)
```

### After Block 1000
```
[✅ Normal (3-of-5)]          ← Green, enabled
[✅ After 60 Months (2-of-5)]  ← Green, enabled (newly available!)
[🔒 After 66 Months (1-of-5)] ← Red, disabled (6 blocks remaining)
```

---

## Open Questions Summary

1. **SpendingPath.locktime_param_name**: Add field? Infer from name? Require explicit?
2. **Address Dialog Display**: One locktime or multiple? Per-path or summary?
3. **Main List View**: How to show multiple locktimes in table?
4. **Path Details**: Show only this path's locktime or all locktimes?
5. **Visual Design**: Timeline? Color coding? Progress bars?
6. **Backwards Compatibility**: How to handle old addresses with single locktime?
7. **Data Storage**: Store all locktimes? Validate relationships?
8. **E2E Testing**: Test all locktime scenarios? Edge cases?

---

## Next Steps

1. **Decide on `SpendingPath.locktime_param_name`** - Add field or infer?
2. **Update path availability logic** - Use path-specific locktime
3. **Update UI components** - Show path-specific locktime status
4. **Update sweep validation** - Check path-specific locktime
5. **Test with decaying multisig** - Verify all paths work correctly










