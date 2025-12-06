#!/usr/bin/env bash
#
# Test runner script for CLTV plugin test suite
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh unit         # Run unit tests only
#   ./run_tests.sh coverage     # Run with coverage report
#   ./run_tests.sh fast         # Run fast tests only (unit, no slow)
#   ./run_tests.sh watch        # Run in watch mode (requires pytest-watch)
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Use Electrum's venv if available
VENV_PYTHON="/Users/macbook/src/electrum/venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    PYTEST="$VENV_PYTHON -m pytest"
    echo -e "${BLUE}Using Electrum venv: $VENV_PYTHON${NC}"
else
    PYTEST="pytest"
    echo -e "${YELLOW}Warning: Electrum venv not found, using system pytest${NC}"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CLTV Plugin Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# Default command
CMD="$PYTEST tests/ -v"

# Parse arguments
case "${1:-all}" in
    all)
        echo -e "${GREEN}Running all tests...${NC}"
        CMD="$PYTEST tests/ -v"
        ;;
    
    unit)
        echo -e "${GREEN}Running unit tests only...${NC}"
        CMD="$PYTEST tests/unit/ -v"
        ;;
    
    integration)
        echo -e "${GREEN}Running integration tests only...${NC}"
        CMD="$PYTEST tests/integration/ -v"
        ;;
    
    coverage)
        echo -e "${GREEN}Running tests with coverage report...${NC}"
        CMD="$PYTEST tests/ --cov=. --cov-report=html --cov-report=term-missing -v"
        ;;
    
    fast)
        echo -e "${GREEN}Running fast tests only (unit, no slow)...${NC}"
        CMD="$PYTEST tests/unit/ -m 'not slow' -v"
        ;;
    
    watch)
        echo -e "${GREEN}Running in watch mode...${NC}"
        if ! command -v ptw &> /dev/null; then
            echo -e "${YELLOW}Warning: pytest-watch not found${NC}"
            echo "Install with: pip install pytest-watch"
            echo "Falling back to normal test run..."
            CMD="pytest tests/ -v"
        else
            CMD="ptw tests/ -- -v"
        fi
        ;;
    
    builders)
        echo -e "${GREEN}Running builder tests...${NC}"
        CMD="$PYTEST tests/unit/test_builders.py -v"
        ;;
    
    sweepers)
        echo -e "${GREEN}Running sweeper tests...${NC}"
        CMD="$PYTEST tests/unit/test_sweepers.py -v"
        ;;
    
    address)
        echo -e "${GREEN}Running address generation tests...${NC}"
        CMD="$PYTEST tests/unit/test_address_generation.py -v"
        ;;
    
    registry)
        echo -e "${GREEN}Running registry tests...${NC}"
        CMD="pytest tests/unit/test_registry.py -v"
        ;;
    
    descriptors)
        echo -e "${GREEN}Running descriptor tests...${NC}"
        CMD="pytest tests/unit/test_descriptors.py -v"
        ;;
    
    help|--help|-h)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  all          Run all tests (default)"
        echo "  unit         Run unit tests only"
        echo "  integration  Run integration tests only"
        echo "  coverage     Run with coverage report"
        echo "  fast         Run fast tests only (unit, no slow)"
        echo "  watch        Run in watch mode (auto-rerun on file changes)"
        echo "  builders     Run builder tests"
        echo "  sweepers     Run sweeper tests"
        echo "  address      Run address generation tests"
        echo "  registry     Run registry tests"
        echo "  descriptors  Run descriptor tests"
        echo "  help         Show this help message"
        exit 0
        ;;
    
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Run '$0 help' for usage"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}Command: ${YELLOW}$CMD${NC}"
echo ""

# Run tests
if $CMD; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    
    # Show coverage report location if generated
    if [[ "$1" == "coverage" ]]; then
        echo ""
        echo -e "${BLUE}Coverage report: ${YELLOW}htmlcov/index.html${NC}"
        echo "Open with: open htmlcov/index.html"
    fi
    
    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Tests failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
