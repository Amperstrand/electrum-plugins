#!/bin/bash
# Comprehensive E2E Test - All Contracts, All Formats, All Paths
# 
# This script:
# 1. Clears old test state
# 2. Creates all 20 tests (5 contracts × 2 formats × 2 paths)
# 3. Funds all addresses in ONE batch transaction
# 4. Sweeps all paths systematically

set -e

LOCKTIME=${1:-280197}
NETWORK=${2:-signet}

echo "=================================================================================="
echo "COMPREHENSIVE E2E TEST - ALL CONTRACTS, ALL FORMATS, ALL PATHS"
echo "=================================================================================="
echo ""
echo "Locktime: $LOCKTIME"
echo "Network: $NETWORK"
echo ""

cd "$(dirname "$0")"
PYTHONPATH=..:.

# Step 1: Clear old test state
echo "STEP 1: Clearing old test state..."
python3 << EOF
import json
from pathlib import Path

state_file = Path("test_state_${LOCKTIME}.json")
if state_file.exists():
    backup = Path("test_state_${LOCKTIME}_backup.json")
    if backup.exists():
        backup.unlink()
    state_file.rename(backup)
    print("✅ Backed up old state to test_state_${LOCKTIME}_backup.json")

# Create fresh state
fresh_state = {"last_updated": None}
with open(state_file, 'w') as f:
    json.dump(fresh_state, f, indent=2)
print("✅ Created fresh test state")
EOF

echo ""
echo "STEP 2: Creating all 20 tests..."
echo ""

# Step 2: Create all tests (they'll be CREATED status)
/Users/macbook/src/electrum/venv/bin/python3 -m pytest test_e2e_full.py \
    -v \
    --locktime=$LOCKTIME \
    -W ignore::DeprecationWarning \
    --tb=short \
    2>&1 | grep -E "CREATED|TEST|PASSED|FAILED" | head -30

echo ""
echo "STEP 3: Funding all addresses in ONE batch transaction..."
echo ""

# Step 3: Fund all CREATED addresses in one transaction
/Users/macbook/src/electrum/venv/bin/python3 -m pytest test_e2e_full.py \
    -v \
    --locktime=$LOCKTIME \
    --fund \
    --fundsize=500 \
    -W ignore::DeprecationWarning \
    --tb=short \
    2>&1 | tail -20

echo ""
echo "STEP 4: Sweeping all paths..."
echo ""

# Step 4: Sweep all funded tests
/Users/macbook/src/electrum/venv/bin/python3 -m pytest test_e2e_full.py \
    -v \
    --locktime=$LOCKTIME \
    -W ignore::DeprecationWarning \
    --tb=short \
    2>&1 | grep -E "SWEEP|TXID|PASSED|FAILED" | head -30

echo ""
echo "=================================================================================="
echo "✅ COMPREHENSIVE TEST COMPLETE"
echo "=================================================================================="
echo ""
echo "Check test_state_${LOCKTIME}.json for results"
echo ""

