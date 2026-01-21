# CLTV Plugin Architecture Documentation

## Overview

The CHECKLOCKTIMEVERIFY (CLTV) Electrum Plugin has been comprehensively refactored to modern best practices, transforming from a monolithic Qt plugin into a professional-grade, modular Bitcoin library with clean separation of concerns.

## Version Information

- **Current Version**: 3.2.0
- **Storage Version**: 12.0.0
- **Network Support**: Mainnet, Testnet, Testnet4, Signet, Regtest
- **Script Types**: P2WSH (SegWit v0), Taproot (SegWit v1)

## Architecture Overview

### 1. Core Principles

```
┌─────────────────────────────────────────────────────────────┐
│                     CLTV Plugin v3.2.0                      │
├─────────────────────────────────────────────────────────────┤
│  Services Layer (Business Logic)                           │
│  ├── StorageService         ├── WalletIntegrationService   │
│  ├── FormattingService      ├── ValidationService          │
│  └── ContractService        └── NetworkService              │
├─────────────────────────────────────────────────────────────┤
│  Interface Layer (Abstraction)                              │
│  ├── CryptoInterface        ├── ScriptInterface            │
│  ├── NetworkInterface      └── ValidationInterface         │
├─────────────────────────────────────────────────────────────┤
│  Implementation Layer (Electrum Adapters)                   │
│  ├── ElectrumCryptoAdapter  ├── ElectrumScriptAdapter      │
│  ├── ElectrumNetworkAdapter └── ElectrumValidationAdapter   │
├─────────────────────────────────────────────────────────────┤
│  Data Layer (Type-Safe Models)                             │
│  ├── AddressRecord          ├── LockStatusInfo             │
│  ├── SweepResult            ├── NetworkInfo               │
│  └── StorageMetadata        └── ValidationRule            │
├─────────────────────────────────────────────────────────────┤
│  Foundation Layer                                           │
│  ├── Constants (Enums)      ├── Exceptions (Hierarchy)     │
│  └── Logging (CLTVLogger)   └── Validation (Rule Engine)   │
└─────────────────────────────────────────────────────────────┘
```

### 2. Module Structure

```
checklocktimeverify/
├── cltv_lib/                          # Core library
│   ├── __init__.py                    # Public API exports (39 modules)
│   ├── constants.py                   # Centralized enums & constants
│   ├── exceptions.py                  # 8 domain-specific exceptions
│   ├── models.py                      # 6 type-safe dataclasses
│   ├── logging_utils.py               # CLTVLogger with decorators
│   ├── interfaces.py                  # Protocol interfaces
│   ├── adapters/                      # Electrum-specific implementations
│   │   ├── crypto_adapter.py
│   │   ├── script_adapter.py
│   │   └── network_adapter.py
│   ├── services/                      # Business logic services
│   │   ├── storage_service.py         # 12 storage methods
│   │   ├── wallet_integration_service.py # 4 wallet methods
│   │   └── formatting_service.py      # 8 formatting methods
│   └── validation/                    # Contract validation
│       └── contract_validation.py      # Rule-based validation
├── tests/                             # Modern test infrastructure
│   ├── unit/                          # Unit test organization
│   ├── fixtures/                      # Test data
│   ├── conftest.py                    # Pytest configuration
│   ├── pytest.ini                     # Pytest settings with markers
│   └── README.md                      # Test documentation
├── qt.py                              # Qt GUI (uses services)
├── cltv_*.py                          # Core Bitcoin functionality
├── manifest.json                      # Plugin metadata
└── .gitignore                         # Plugin exclusions
```

## Core Capabilities

### 1. Contract Generation & Management

#### Supported Contract Types
1. **hodl** - Single-sig timelock
2. **escrow** - Three-party arbitration  
3. **twofactor** - 2FA wallet with recovery
4. **payment_channel** - Cooperative close with refund
5. **data_publishing** - PayPub contract

#### Unified API
```python
from cltv_lib.builders.unified.generic import build_contract

# Build any contract type
result = build_contract('escrow', {
    'locktime': 600000,
    'alice': '02abc...',
    'bob': '03def...',
    'lenny': '02ghi...',
}, output_type='taproot', network='signet')

print(f"Address: {result['address']}")
print(f"Script: {result['script']}")
print(f"Descriptor: {result['descriptor']}")
```

### 2. Address Generation

#### Supported Output Types
- **P2WSH** (Pay-to-Witness-Script-Hash) - SegWit v0
- **Taproot** (Pay-to-Taproot) - SegWit v1
- **NO P2SH** (deprecated and removed)

#### Address API
```python
from cltv_lib.address import generate_address

# Generate P2WSH address
p2wsh_addr = generate_address(script, 'p2wsh', network='mainnet')

# Generate Taproot address  
taproot_addr = generate_address(script, 'taproot', network='testnet')
```

### 3. Contract Sweeping & Spending

#### Unified Sweeper
```python
from cltv_lib.sweepers import sweep_output, validate_sweep_conditions

# Validate conditions
conditions_met = validate_sweep_conditions(contract_data, current_block)

# Sweep output
result = sweep_output(output, contract_data, private_keys, current_block)
print(f"Transaction: {result['transaction']}")
print(f"Fee: {result['fee']}")
```

### 4. Descriptor Support

#### Miniscript & Bitcoin Descriptors
```python
from cltv_lib.descriptors import get_miniscript, get_descriptor

# Get Miniscript representation
miniscript = get_miniscript(contract_config)

# Get Bitcoin descriptor
descriptor = get_descriptor(contract_config, output_type='taproot')
```

## Service Layer Architecture

### StorageService
**Purpose**: All wallet database operations with type safety
**Methods**: 12 comprehensive storage methods
```python
storage = StorageService()

# Save address with validation
storage.save_address(wallet, address_record)

# Load addresses with filtering  
addresses = storage.load_addresses_by_script_type(wallet, 'hodl')

# Update metadata
storage.update_metadata(wallet, script_type, metadata)

# Clean up old versions
storage.purge_old_versions(wallet, current_version)
```

### WalletIntegrationService
**Purpose**: Bridge between CLTV logic and Electrum wallet
**Methods**: 4 wallet integration methods
```python
wallet_service = WalletIntegrationService()

# Register addresses in wallet
wallet_service.register_addresses(wallet, addresses, script_type)

# Get wallet balance for CLTV addresses
balance = wallet_service.get_wallet_balance(wallet, script_type)

# List addresses by type  
addresses = wallet_service.list_addresses_by_type(wallet, 'escrow')

# Check wallet compatibility
is_compatible = wallet_service.check_wallet_compatibility(wallet)
```

### FormattingService
**Purpose**: Data presentation and formatting
**Methods**: 8 formatting utilities
```python
formatter = FormattingService()

# Format amounts for display
formatted = formatter.format_amount(satoshis, network='mainnet')

# Compute lock status
status = formatter.compute_lock_status(locktime, current_block)

# Format time until unlock
time_str = formatter.format_time_until_unlock(locktime, current_block)
```

## Interface Layer (Dependency Injection)

### CryptoInterface
```python
class CryptoInterface(Protocol):
    def verify_signature(self, message: str, signature: str, pubkey: str) -> bool: ...
    def sign_message(self, message: str, privkey: str) -> str: ...
    def get_public_key(self, privkey: str) -> str: ...
```

### ScriptInterface  
```python
class ScriptInterface(Protocol):
    def build_cltv_script(self, locktime: int, pubkey: str) -> str: ...
    def validate_script(self, script: str) -> bool: ...
    def extract_pubkey(self, script: str) -> str: ...
```

### NetworkInterface
```python
class NetworkInterface(Protocol):
    def get_current_block(self) -> int: ...
    def get_network(self) -> str: ...
    def validate_address(self, address: str) -> bool: ...
```

## Data Models (Type Safety)

### AddressRecord
```python
@dataclass
class AddressRecord:
    address: str
    script_type: str
    locktime: int
    creation_time: float
    network: str
    output_type: str
    metadata: Dict[str, Any]
```

### LockStatusInfo
```python
@dataclass
class LockStatusInfo:
    status: str  # "Locked" or "Unlocked"
    blocks_remaining: int
    time_remaining: str
    current_block: int
    locktime: int
```

### SweepResult
```python
@dataclass
class SweepResult:
    success: bool
    transaction: Optional[str]
    fee: Optional[int]
    error: Optional[str]
    required_keys: List[str]
```

## Exception Hierarchy

### Domain-Specific Exceptions
```python
# Base exception
CLTVError

# Specific error types
ValidationError       # Parameter validation errors
StorageError          # Database operation failures  
WalletError           # Wallet integration issues
NetworkError          # Network-related problems
BuildError            # Contract building failures
SweepError            # Contract sweeping issues
LockedError           # Contract not yet spendable
```

## Validation System

### Rule-Based Validation
```python
from cltv_lib.validation.contract_validation import validate_script_type

# Validate script type configuration
config = validate_script_type('hodl', {'locktime': 600000})

# Custom validation rules
class CustomRule(ValidationRule):
    def validate(self, config: Dict) -> List[str]:
        # Custom validation logic
        return []
```

## Electrum Adapter Pattern

### Benefits
- **Testability**: Mock adapters for unit testing
- **Extensibility**: Support for different Bitcoin clients
- **Maintainability**: Clear interface contracts
- **Consistency**: Unified API across implementations

### Current Adapters
```python
# Electrum-specific implementations
ElectrumCryptoAdapter    # Electrum crypto operations
ElectrumScriptAdapter    # Electrum script handling  
ElectrumNetworkAdapter   # Electrum network access
```

## Logging Infrastructure

### CLTVLogger
```python
from cltv_lib.logging_utils import CLTVLogger

logger = CLTVLogger('cltv_lib.storage')

# Decorated logging
@with_logging('save_address')
def save_address(self, wallet, address_record):
    # Operation automatically logged
    pass
```

### Log Categories
- `storage_logger` - Storage operations
- `wallet_logger` - Wallet integration
- `ui_logger` - UI events
- `network_logger` - Network operations

## Testing Infrastructure

### Test Organization
```
tests/
├── unit/                          # Unit tests
│   ├── test_storage_service.py    # Storage service tests
│   ├── test_wallet_service.py     # Wallet service tests
│   ├── test_formatters.py         # Formatting tests
│   ├── test_validators.py         # Validation tests
│   ├── test_models.py             # Data model tests
│   ├── test_interfaces.py         # Interface tests
│   ├── test_adapters.py           # Adapter tests
│   └── test_exceptions.py        # Exception tests
├── fixtures/                      # Test data
├── conftest.py                    # Pytest configuration
├── pytest.ini                     # Pytest settings
└── README.md                      # Test documentation
```

### Test Features
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`
- **Fixtures**: Electrum wallet mocks, test data
- **Coverage**: Comprehensive service testing
- **Helpers**: Assertion utilities, test data generators

## Migration Guide

### From v2.x to v3.0
1. **Import Changes**: Use new centralized imports
2. **Service Usage**: Replace direct qt.py calls with services
3. **Type Safety**: Benefit from new data validation
4. **Testing**: Run new test suite

### Backward Compatibility
- Existing Qt GUI continues to work unchanged
- All existing API methods remain available
- Storage format automatically migrated
- No breaking changes to public interfaces

## Performance & Optimization

### Current Optimizations
- **Caching**: Address caching in wallet storage
- **Validation**: Early parameter validation
- **Logging**: Efficient structured logging
- **Memory**: Type-safe data structures
- **Database**: Efficient storage operations

### Planned Optimizations
- Batch operations for bulk address management
- Async network operations
- Improved cache invalidation
- Memory usage monitoring

## Security Considerations

### Current Security Features
- **Input Validation**: Comprehensive parameter validation
- **Type Safety**: Prevents many runtime errors
- **Error Handling**: Graceful failure modes
- **Logging**: Audit trail of operations
- **Wallet Integration**: Proper wallet API usage

### Security Best Practices
- All user inputs validated before processing
- Private keys never stored in plugin memory
- Wallet operations follow Electrum security patterns
- Error messages don't expose sensitive information

## Contributing

### Development Setup
```bash
# Install dependencies
pip install pytest pytest-cov black isort mypy

# Run tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=cltv_lib --cov-report=html

# Format code
black cltv_lib/
isort clqt_lib/
```

### Code Style
- **Black**: Code formatting
- **isort**: Import sorting
- **mypy**: Type checking
- **pylint**: Additional linting

## Future Enhancements

### Planned Features
1. **Additional Contract Types**: More complex contract patterns
2. **Multi-Sig Support**: Enhanced multi-signature contracts
3. **Hardware Wallet Integration**: Ledger/Trezor support
4. **Watch-Only Addresses**: Non-custodial monitoring
5. **Transaction Building**: Enhanced transaction construction
6. **Fee Estimation**: Dynamic fee calculation
7. **Block Height Monitoring**: Real-time blockchain updates

### Technical Improvements
1. **Async Operations**: Non-blocking network calls
2. **Database Indexing**: Improved storage performance
3. **Memory Management**: Better resource usage
4. **Error Recovery**: Enhanced error handling
5. **Plugin API**: Better plugin integration

## Support & Documentation

### Getting Help
- **Issues**: GitHub Issues for bug reports
- **Documentation**: This document and inline docstrings
- **Tests**: Comprehensive test examples
- **Examples**: Usage examples in test files

### Additional Resources
- **BIP-65**: CHECKLOCKTIMEVERIFY specification
- **SegWit**: Bitcoin improvement proposals for SegWit
- **Miniscript**: Script language documentation
- **Electrum Plugin**: Plugin development guide

---

## Summary

The CLTV Plugin v3.2.0 represents a complete architectural transformation, providing:

✅ **Professional Architecture**: Clean separation of concerns, dependency injection, and service layer design

✅ **Type Safety**: Comprehensive data models, validation, and error handling

✅ **Testability**: Mock interfaces, comprehensive test suite, and proper testing infrastructure

✅ **Maintainability**: Centralized constants, logging, and configuration management

✅ **Extensibility**: Plugin system ready for future enhancements and new features

✅ **Backward Compatibility**: Existing functionality preserved while adding new capabilities

This refactoring establishes the CLTV Plugin as a production-ready, maintainable, and extensible Bitcoin library for CHECKLOCKTIMEVERIFY operations.