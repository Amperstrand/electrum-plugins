# CLTV Plugin Test Suite

Comprehensive pytest-based test suite for the CheckLockTimeVerify Electrum plugin.

## Overview

This test suite provides unit and integration tests for all components of the CLTV plugin with a target of **90%+ code coverage**.

## Structure

```
tests/
├── conftest.py                      # Shared fixtures and configuration
├── unit/                            # Unit tests (fast, no external deps)
│   ├── test_builders.py            # Script builders (5 types)
│   ├── test_sweepers.py            # Transaction sweepers (5 types)
│   ├── test_address_generation.py  # P2WSH/Taproot address generation
│   ├── test_registry.py            # Script registry
│   ├── test_descriptors.py         # Miniscript & output descriptors
│   ├── test_miniscript_formatter.py # Krux-style formatting
│   └── test_test_keys.py           # Test key management
├── integration/                     # Integration tests (may need Electrum)
│   └── (to be added)
└── README.md                        # This file
```

## Installation

### Prerequisites

```bash
# Install pytest and plugins
pip install pytest pytest-cov pytest-mock

# Ensure Electrum is installed
cd ~/src/electrum
source venv/bin/activate
pip install -e .
```

## Running Tests

### Run all tests

```bash
cd ~/src/electrum-plugins/checklocktimeverify
pytest tests/
```

### Run with coverage

```bash
pytest tests/ --cov=. --cov-report=html --cov-report=term
```

### Run only unit tests (fast)

```bash
pytest tests/unit/ -v
```

### Run specific test file

```bash
pytest tests/unit/test_builders.py -v
```

### Run specific test class or function

```bash
pytest tests/unit/test_builders.py::TestSimpleCLTVBuilder -v
pytest tests/unit/test_builders.py::TestSimpleCLTVBuilder::test_build_script_valid -v
```

### Run tests matching a pattern

```bash
pytest tests/ -k "simple" -v  # All tests with "simple" in name
pytest tests/ -k "build" -v   # All tests with "build" in name
```

### Run tests by marker

```bash
pytest tests/ -m unit          # Only unit tests
pytest tests/ -m integration   # Only integration tests
pytest tests/ -m "not slow"    # Exclude slow tests
```

## Test Markers

- `@pytest.mark.unit` - Fast unit tests, no external dependencies
- `@pytest.mark.integration` - Integration tests, may require Electrum
- `@pytest.mark.slow` - Slow tests (>1s execution time)

## Fixtures

### Test Keys
- `test_keys` - All hardcoded test keys (alice, bob, lenny, etc.)

### Mock Objects
- `mock_wallet` - Mock Electrum wallet
- `mock_network` - Mock Electrum network
- `mock_config` - Mock Electrum config
- `mock_plugin` - Mock CLTV plugin

### Script Parameters
- `simple_cltv_params` - Parameters for simple CLTV
- `escrow_params` - Parameters for 3-party escrow
- `twofactor_params` - Parameters for two-factor wallet
- `payment_channel_params` - Parameters for payment channel
- `data_publishing_params` - Parameters for data publishing

## Writing New Tests

### Example Unit Test

```python
def test_my_feature(simple_cltv_params):
    """Test description"""
    from cltv_lib.builders.simple import SimpleCLTVBuilder
    
    builder = SimpleCLTVBuilder()
    result = builder.build_script(simple_cltv_params)
    
    assert result is not None
    assert isinstance(result, bytes)
```

### Example Parametrized Test

```python
@pytest.mark.parametrize("locktime", [1, 100, 500000, 2**31-1])
def test_various_locktimes(simple_cltv_params, locktime):
    """Test different locktime values"""
    params = simple_cltv_params.copy()
    params['locktime'] = locktime
    
    builder = SimpleCLTVBuilder()
    script = builder.build_script(params)
    
    assert script is not None
```

## Coverage Goals

| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| Builders | 95%+ | High |
| Sweepers | 95%+ | High |
| Address Generation | 90%+ | High |
| Registry | 95%+ | High |
| Descriptors | 90%+ | High |
| Dialogs | 80%+ | Medium |
| UI Widgets | 70%+ | Low |

## Current Status

### ✅ Completed
- [x] Test infrastructure (conftest.py)
- [x] Builder tests (test_builders.py)
- [x] Sweeper tests (test_sweepers.py)
- [x] Address generation tests (test_address_generation.py)
- [x] Registry tests (test_registry.py)
- [x] Descriptor tests (test_descriptors.py)
- [x] Miniscript formatter tests (test_miniscript_formatter.py)
- [x] Test key tests (test_test_keys.py)

### 🚧 In Progress
- [ ] Integration tests (dialogs, full sweep flows)
- [ ] Taproot-specific tests
- [ ] Storage integration tests
- [ ] Network integration tests

### 📋 Todo
- [ ] Fee estimation tests
- [ ] UI widget tests
- [ ] Performance/benchmark tests
- [ ] Property-based tests (hypothesis)

## Continuous Integration

### Pre-commit Checks

```bash
# Run fast tests before commit
pytest tests/unit/ -x --tb=short
```

### CI Pipeline (Suggested)

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-mock
          pip install -e ~/src/electrum
      - name: Run tests
        run: pytest tests/ --cov=. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Troubleshooting

### Import Errors

If you see import errors:

```bash
# Ensure plugin is in PYTHONPATH
export PYTHONPATH=$PYTHONPATH:~/src/electrum-plugins/checklocktimeverify

# Or run pytest with explicit path
cd ~/src/electrum-plugins/checklocktimeverify
pytest tests/
```

### Electrum Not Found

If Electrum imports fail:

```bash
# Add Electrum to path
export PYTHONPATH=$PYTHONPATH:~/src/electrum

# Or install Electrum in development mode
cd ~/src/electrum
pip install -e .
```

### Test Discovery Issues

If pytest can't find tests:

```bash
# Ensure __init__.py exists in test directories
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py

# Or run with explicit test discovery
pytest tests/ --collect-only
```

## Best Practices

1. **Keep tests fast** - Unit tests should run in < 100ms
2. **Mock external dependencies** - Don't require real wallet/network
3. **Use fixtures** - Reuse test data via fixtures
4. **Test edge cases** - Boundary values, errors, invalid inputs
5. **Descriptive names** - `test_build_script_with_invalid_locktime_raises_error`
6. **One assertion per test** - Makes failures easier to debug
7. **Parametrize similar tests** - DRY principle for test code
8. **Document complex tests** - Clear docstrings

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Pytest Parametrize](https://docs.pytest.org/en/stable/parametrize.html)
- [Pytest Coverage](https://pytest-cov.readthedocs.io/)
- [Electrum Developer Guide](https://electrum.readthedocs.io/)

## Contributing

When adding new features:

1. Write tests first (TDD)
2. Ensure tests pass (`pytest tests/`)
3. Check coverage (`pytest --cov`)
4. Add test documentation
5. Update this README if needed

## License

Same as the CLTV plugin (see main README.md)
