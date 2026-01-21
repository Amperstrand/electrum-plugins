# CLTV Plugin API Reference

## Table of Contents
1. [Quick Start](#quick-start)
2. [Core API](#core-api)
3. [Services API](#services-api)
4. [Advanced Usage](#advanced-usage)
5. [Examples](#examples)

## Quick Start

### Installation
The plugin is available as a zip file for Electrum. Install by placing in the `plugins` directory.

### Basic Usage
```python
from cltv_lib.builders.unified.generic import build_contract

# Build a CLTV contract
result = build_contract('hodl', {
    'locktime': 600000,  # Block height
    'pubkey': '02abc123...',  # Public key
}, output_type='taproot', network='mainnet')

print(f"Address: {result['address']}")
print(f"Script: {result['script']}")
```

## Core API

### Contract Building

#### `build_contract(script_type, config, output_type, network)`
The main entry point for building any CLTV contract.

**Parameters:**
- `script_type` (str): Contract type ('hodl', 'escrow', 'twofactor', 'payment_channel', 'data_publishing')
- `config` (dict): Contract configuration parameters
- `output_type` (str): Output type ('p2wsh' or 'taproot')
- `network` (str): Bitcoin network ('mainnet', 'testnet', 'signet', etc.)

**Returns:**
```python
{
    'address': str,           # Generated address
    'script': str,            # CLTV script hex
    'descriptor': str,       # Bitcoin descriptor
    'redeem_script': str,     # P2WSH redeem script (if applicable)
    'witness_script': str,    # Taproot witness script
    'pubkeys': list,          # Required public keys
    'required_sigs': int,     # Required signatures
}
```

**Example:**
```python
# HODL contract (single signature timelock)
hodl_result = build_contract('hodl', {
    'locktime': 600000,
    'pubkey': '02abc123...',
}, output_type='taproot', network='mainnet')

# Escrow contract (three-party arbitration)
escrow_result = build_contract('escrow', {
    'locktime': 600000,
    'alice': '02abc123...',
    'bob': '03def456...',
    'lenny': '02ghi789...',
    'refund_delay': 1000,  # Additional refund timelock
}, output_type='p2wsh', network='testnet')
```

### Address Generation

#### `generate_address(script_hex, output_type, network)`
Generate a Bitcoin address from a script.

**Parameters:**
- `script_hex` (str): Script in hexadecimal format
- `output_type` (str): Output type ('p2wsh' or 'taproot')
- `network` (str): Bitcoin network

**Returns:** Bitcoin address string

**Example:**
```python
from cltv_lib.address import generate_address

# Generate P2WSH address
address = generate_address(script_hex, 'p2wsh', 'mainnet')
```

### Descriptor Generation

#### `get_miniscript(contract_config)`
Get Miniscript representation of a contract.

**Parameters:**
- `contract_config` (dict): Contract configuration

**Returns:** Miniscript string

#### `get_descriptor(contract_config, output_type)`
Get Bitcoin descriptor for a contract.

**Parameters:**
- `contract_config` (dict): Contract configuration
- `output_type` (str): Output type ('p2wsh' or 'taproot')

**Returns:** Bitcoin descriptor string

**Example:**
```python
from cltv_lib.descriptors import get_miniscript, get_descriptor

# Get Miniscript
miniscript = get_miniscript({'locktime': 600000, 'pubkey': '02abc...'})

# Get Descriptor
descriptor = get_descriptor({'locktime': 600000, 'pubkey': '02abc...'}, 'taproot')
```

## Services API

### StorageService

#### `save_address(wallet, address_record)`
Save a CLTV address to wallet storage.

**Parameters:**
- `wallet`: Electrum wallet instance
- `address_record`: `AddressRecord` instance

**Raises:** `StorageError`, `ValidationError`

#### `load_addresses_by_script_type(wallet, script_type)`
Load addresses filtered by script type.

**Parameters:**
- `wallet`: Electrum wallet instance
- `script_type` (str): Script type ('hodl', 'escrow', etc.)

**Returns:** List of `AddressRecord` objects

#### `load_all_addresses(wallet)`
Load all CLTV addresses from storage.

**Parameters:**
- `wallet`: Electrum wallet instance

**Returns:** List of all `AddressRecord` objects

#### `delete_address(wallet, address)`
Delete an address from storage.

**Parameters:**
- `wallet`: Electrum wallet instance
- `address` (str): Address to delete

**Raises:** `StorageError`

#### `update_metadata(wallet, script_type, metadata)`
Update metadata for a script type.

**Parameters:**
- `wallet`: Electrum wallet instance
- `script_type` (str): Script type
- `metadata` (dict): Metadata to update

#### `get_storage_metadata(wallet)`
Get storage metadata information.

**Parameters:**
- `wallet`: Electrum wallet instance

**Returns:** `StorageMetadata` object

#### `purge_old_versions(wallet, current_version)`
Purge old storage versions.

**Parameters:**
- `wallet`: Electrum wallet instance
- `current_version` (str): Current storage version

#### `address_exists(wallet, address)`
Check if an address exists in storage.

**Parameters:**
- `wallet`: Electrum wallet instance
- `address` (str): Address to check

**Returns:** Boolean indicating if address exists

#### `get_address_count(wallet, script_type)`
Get count of addresses for a script type.

**Parameters:**
- `wallet`: Electrum wallet instance
- `script_type` (str): Script type

**Returns:** Integer count

#### `get_all_script_types(wallet)`
Get all script types in use.

**Parameters:**
- `wallet`: Electrum wallet instance

**Returns:** List of script type strings

#### `validate_storage_integrity(wallet)`
Validate storage integrity.

**Parameters:**
- `wallet`: Electrum wallet instance

**Returns:** List of validation errors

**Example:**
```python
from cltv_lib.services.storage_service import StorageService
from cltv_lib.models import AddressRecord
from cltv_lib.constants import CURRENT_STORAGE_VERSION, PLUGIN_NAME

storage = StorageService()

# Create address record
record = AddressRecord(
    address='tb1p...',
    script_type='hodl',
    locktime=600000,
    creation_time=time.time(),
    network='mainnet',
    output_type='taproot',
    metadata={'source': 'manual'}
)

# Save to wallet
storage.save_address(wallet, record)

# Load all hodl addresses
hodl_addresses = storage.load_addresses_by_script_type(wallet, 'hodl')
```

### WalletIntegrationService

#### `register_addresses(wallet, addresses, script_type)`
Register addresses in the wallet.

**Parameters:**
- `wallet`: Electrum wallet instance
- `addresses` (list): List of addresses to register
- `script_type` (str): Script type for the addresses

**Raises:** `WalletError`

#### `get_wallet_balance(wallet, script_type)`
Get balance of CLTV addresses in wallet.

**Parameters:**
- `wallet`: Electrum wallet instance
- `script_type` (str): Script type to check

**Returns:** Dictionary with balance information

#### `list_addresses_by_type(wallet, script_type)`
List addresses by script type.

**Parameters:**
- `wallet`: Electrum wallet instance
- `script_type` (str): Script type

**Returns:** List of address strings

#### `check_wallet_compatibility(wallet)`
Check wallet compatibility with CLTV plugin.

**Parameters:**
- `wallet`: Electrum wallet instance

**Returns:** Boolean indicating compatibility

**Example:**
```python
from cltv_lib.services.wallet_integration_service import WalletIntegrationService

wallet_service = WalletIntegrationService()

# Register addresses
addresses = ['tb1p...', 'tb1p...']
wallet_service.register_addresses(wallet, addresses, 'hodl')

# Get balance
balance = wallet_service.get_wallet_balance(wallet, 'hodl')
print(f"Balance: {balance['confirmed']} SAT")

# List addresses
hodl_addresses = wallet_service.list_addresses_by_type(wallet, 'hodl')
```

### FormattingService

#### `format_amount(satoshis, network)`
Format satoshis for display.

**Parameters:**
- `satoshis` (int): Amount in satoshis
- `network` (str): Bitcoin network

**Returns:** Formatted string

#### `compute_lock_status(locktime, current_block)`
Compute lock status of a timelock.

**Parameters:**
- `locktime` (int): Locktime (block height)
- `current_block` (int): Current block height

**Returns:** `LockStatusInfo` object

#### `format_time_until_unlock(locktime, current_block)`
Format time remaining until unlock.

**Parameters:**
- `locktime` (int): Locktime (block height)
- `current_block` (int): Current block height

**Returns:** Formatted time string

#### `get_script_display_name(script_type)`
Get user-friendly display name for script type.

**Parameters:**
- `script_type` (str): Script type

**Returns:** Display name string

#### `format_script_config(script_type, config)`
Format script configuration for display.

**Parameters:**
- `script_type` (str): Script type
- `config` (dict): Configuration dictionary

**Returns:** Formatted configuration string

#### `validate_network(network)`
Validate network string.

**Parameters:**
- `network` (str): Network string

**Returns:** Boolean indicating validity

#### `get_network_display_name(network)`
Get user-friendly network name.

**Parameters:**
- `network` (str): Network string

**Returns:** Display name string

#### `parse_amount(amount_str)`
Parse amount string to satoshis.

**Parameters:**
- `amount_str` (str): Amount string (e.g., "1.23 BTC")

**Returns:** Integer amount in satoshis

**Example:**
```python
from cltv_lib.services.formatting_service import FormattingService

formatter = FormattingService()

# Format amount
formatted = formatter.format_amount(123456, 'mainnet')  # "1.23456 BTC"

# Compute lock status
status = formatter.compute_lock_status(600000, 599500)
print(f"Status: {status.status}")
print(f"Blocks remaining: {status.blocks_remaining}")

# Format time until unlock
time_str = formatter.format_time_until_unlock(600000, 599500)
print(f"Time remaining: {time_str}")
```

## Advanced Usage

### Contract Sweeping

#### `sweep_output(output, contract_data, private_keys, current_block)`
Sweep a CLTV output.

**Parameters:**
- `output`: Output information
- `contract_data`: Contract configuration
- `private_keys` (list): List of private keys
- `current_block` (int): Current block height

**Returns:** `SweepResult` object

#### `get_required_keys(contract_data)`
Get required keys for a contract.

**Parameters:**
- `contract_data`: Contract configuration

**Returns:** List of required public keys

#### `validate_sweep_conditions(contract_data, current_block)`
Validate if sweep conditions are met.

**Parameters:**
- `contract_data`: Contract configuration
- `current_block` (int): Current block height

**Returns:** Boolean indicating if conditions are met

#### `build_witness(scriptsig, private_keys, messages)`
Build witness for transaction.

**Parameters:**
- `scriptsig`: Script signature
- `private_keys` (list): Private keys
- `messages` (list): Messages to sign

**Returns:** Witness data

**Example:**
```python
from cltv_lib.sweepers import sweep_output, validate_sweep_conditions

# Check if contract can be swept
can_sweep = validate_sweep_conditions(contract_data, current_block)

if can_sweep:
    # Sweep the output
    result = sweep_output(output, contract_data, private_keys, current_block)
    if result.success:
        print(f"Transaction: {result.transaction}")
        print(f"Fee: {result.fee}")
    else:
        print(f"Error: {result.error}")
```

### Custom Validation

#### `validate_script_type(script_type, config)`
Validate script type configuration.

**Parameters:**
- `script_type` (str): Script type
- `config` (dict): Configuration dictionary

**Returns:** Validated configuration

#### `ValidationRule`
Base class for custom validation rules.

**Example:**
```python
from cltv_lib.validation.contract_validation import ValidationRule

class CustomRule(ValidationRule):
    def validate(self, config: dict) -> list:
        errors = []
        if config.get('locktime', 0) < 500000:
            errors.append("Locktime must be at least 500000")
        return errors

# Use custom validation
registry = ContractValidationRegistry()
registry.add_rule('hodl', CustomRule())
```

## Examples

### Example 1: Creating a HODL Contract

```python
from cltv_lib.builders.unified.generic import build_contract
from cltv_lib.services.formatting_service import FormattingService
from cltv_lib.sweepers import validate_sweep_conditions

# Build HODL contract
hodl_result = build_contract('hodl', {
    'locktime': 700000,  # Block height
    'pubkey': '02abc123def456...',  # Your public key
}, output_type='taproot', network='mainnet')

print(f"Address: {hodl_result['address']}")
print(f"Script: {hodl_result['script']}")
print(f"Descriptor: {hodl_result['descriptor']}")

# Check lock status
formatter = FormattingService()
current_block = 699000  # Current block height
lock_status = formatter.compute_lock_status(700000, current_block)
print(f"Status: {lock_status.status}")
print(f"Blocks remaining: {lock_status.blocks_remaining}")

# Check if can sweep
can_sweep = validate_sweep_conditions({'locktime': 700000}, current_block)
print(f"Can sweep: {can_sweep}")
```

### Example 2: Managing Multiple Contracts

```python
from cltv_lib.builders.unified.generic import build_contract
from cltv_lib.services.storage_service import StorageService
from cltv_lib.models import AddressRecord
import time

# Build multiple contract types
contracts = [
    build_contract('hodl', {
        'locktime': 600000,
        'pubkey': '02abc123...',
    }, 'taproot', 'mainnet'),
    
    build_contract('escrow', {
        'locktime': 650000,
        'alice': '02abc123...',
        'bob': '03def456...',
        'lenny': '02ghi789...',
    }, 'p2wsh', 'testnet'),
]

# Store in wallet
storage = StorageService()
for contract in contracts:
    record = AddressRecord(
        address=contract['address'],
        script_type=contract['script_type'],
        locktime=contract['locktime'],
        creation_time=time.time(),
        network=contract['network'],
        output_type=contract['output_type'],
        metadata=contract
    )
    storage.save_address(wallet, record)

# List all addresses
all_addresses = storage.load_all_addresses(wallet)
print(f"Total addresses: {len(all_addresses)}")

for addr in all_addresses:
    print(f"{addr.address} - {addr.script_type} - {addr.locktime}")
```

### Example 3: Integration with Electrum

```python
from cltv_lib.builders.unified.generic import build_contract
from cltv_lib.services.wallet_integration_service import WalletIntegrationService
from cltv_lib.services.formatting_service import FormattingService

# Build contract and integrate with wallet
contract_result = build_contract('payment_channel', {
    'locktime': 600000,
    'sender': '02abc123...',
    'receiver': '03def456...',
    'refund_delay': 1000,
}, 'taproot', 'mainnet')

# Register in wallet
wallet_service = WalletIntegrationService()
wallet_service.register_addresses(wallet, [contract_result['address']], 'payment_channel')

# Get balance
balance = wallet_service.get_wallet_balance(wallet, 'payment_channel')
print(f"Payment channel balance: {balance['confirmed']} SAT")

# Format for display
formatter = FormattingService()
print(f"Address: {contract_result['address']}")
print(f"Type: {formatter.get_script_display_name('payment_channel')}")
```

### Example 4: Error Handling

```python
from cltv_lib.builders.unified.generic import build_contract
from cltv_lib.exceptions import BuildError, ValidationError

try:
    # This will fail due to invalid locktime
    result = build_contract('hodl', {
        'locktime': 100000,  # Too early
        'pubkey': '02abc123...',
    }, 'taproot', 'mainnet')
    
except BuildError as e:
    print(f"Build failed: {e}")
except ValidationError as e:
    print(f"Validation failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Error Handling

### Exception Types

- `CLTVError`: Base exception for all CLTV errors
- `ValidationError`: Parameter validation errors
- `StorageError`: Database operation failures
- `WalletError`: Wallet integration issues
- `NetworkError`: Network-related problems
- `BuildError`: Contract building failures
- `SweepError`: Contract sweeping issues
- `LockedError`: Contract not yet spendable

### Best Practices

1. Always validate inputs before processing
2. Use specific exception types for better error handling
3. Provide meaningful error messages to users
4. Log errors for debugging purposes
5. Handle edge cases gracefully

### Error Recovery

```python
from cltv_lib.exceptions import StorageError, ValidationError

def save_contract_safely(wallet, contract_data):
    try:
        # Validate data
        validate_script_type(contract_data['script_type'], contract_data)
        
        # Build contract
        result = build_contract(**contract_data)
        
        # Save to wallet
        storage.save_address(wallet, result)
        
        return True
        
    except ValidationError as e:
        print(f"Invalid contract data: {e}")
        return False
    except StorageError as e:
        print(f"Storage failed: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
```

---

This API reference covers all the major functionality of the CLTV Plugin. For more detailed information about specific components, refer to the inline documentation in the source code.