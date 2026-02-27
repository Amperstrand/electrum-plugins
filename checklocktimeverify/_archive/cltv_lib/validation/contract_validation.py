"""
Validation registry for CLTV Plugin contracts.

Centralized contract validation system that consolidates
all validation rules in one location for type safety
and consistency.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
import logging

from .models import ValidationError
from .contracts import CONTRACTS


logger = logging.getLogger(__name__)


@dataclass
class ValidationRule:
    """Validation rule configuration."""
    
    name: str
    validator: Callable[[Any], None]
    description: str
    error_message: str
    is_required: bool = True


class ContractValidationRegistry:
    """
    Centralized registry for contract validation rules.
    
    Stores all validation rules and provides methods to:
    - Register new rules
    - Validate contracts against rules
    - Get all available contract types
    - Query rules by contract type
    """
    
    def __init__(self):
        """Initialize validation registry."""
        self._rules: {}
        self._contract_rules: Dict[str, List[str]] = {}
        self._param_validators: Dict[str, ValidationRule] = {}
        
        # Register built-in rules
        self._register_built_in_rules()
    
    def _register_built_in_rules(self) -> None:
        """Register all built-in validation rules."""
        
        # Rule: Script type must have cltv_ prefix
        self.register_rule(
            name="script_type_format",
            validator=lambda data: isinstance(data.get('script_type', ''), str) and 
                            data['script_type'].startswith('cltv_'),
            description="Script type must start with 'cltv_'",
            error_message="Script type must start with 'cltv_' prefix",
            is_required=True,
        )
        
        # Rule: Locktime must be positive integer
        self.register_rule(
            name="positive_locktime",
            validator=lambda data: self._get_nested_value(data, 'params', 'locktime') is not None and
                            isinstance(self._get_nested_value(data, 'params', 'locktime'), int) and
                            self._get_nested_value(data, 'params', 'locktime') > 0,
            description="Locktime must be a positive integer greater than 0",
            error_message="Locktime must be > 0 blocks",
            is_required=True,
        )
        
        # Rule: Pubkeys must be valid hex strings
        self.register_rule(
            name="valid_pubkey_format",
            validator=lambda data: self._validate_pubkeys(data),
            description="At least one valid public key (66 or 130 characters) required",
            error_message="No valid public keys found",
            is_required=False,
        )
        
        # Rule: For escrow contracts, specific key combinations
        self.register_rule(
            name="escrow_key_presence",
            validator=lambda data: 'escrow' in data.get('script_type', '').lower() and
                            self._validate_escrow_keys(data),
            description="Escrow contracts require alice, bob, and lenny keys",
            error_message="Escrow contracts require 3 party keys: alice, bob, lenny",
            is_required=False,
        )
        
        # Rule: Data hash must be valid hex for data publishing
        self.register_rule(
            name="data_hash_format",
            validator=lambda data: 'data_publishing' in data.get('script_type', '').lower() and
                            'data_hash' in data.get('params', {}) and
                            isinstance(data['params']['data_hash'], str) and
                            len(data['params']['data_hash']) == 64,
            description="Data hash must be 64-character hex string",
            error_message="Data hash must be 64 hex characters",
            is_required=False,
        )
        
        # Register contract-specific rules
        for contract_name, contract in CONTRACTS.items():
            self._register_contract_rules(contract_name, contract)
    
    def _register_contract_rules(self, contract_name: str, contract: Any) -> None:
        """Register validation rules for a specific contract."""
        
        # Register required params from contract definition
        required_params = contract.get_required_param_names()
        
        for param_name in required_params:
            self.register_rule(
                name=f"{contract_name}_{param_name}_required",
                validator=lambda data: param_name in self._get_nested_value(data, 'params', {}),
                description=f"{contract_name.title()} contract requires '{param_name}' parameter",
                error_message=f"{contract_name.title()} contract requires '{param_name}' parameter",
                is_required=True,
            )
        
        # Register parameter type validations from contract definition
        for param_spec in contract.params:
            if param_spec.validation:
                self.register_param_type_validation(
                    contract_name=contract_name,
                    param_name=param_spec.name,
                    param_spec=param_spec,
                )
    
    def register_param_type_validation(
        self,
        contract_name: str,
        param_name: str,
        param_spec: Any,
    ) -> None:
        """Register a parameter type validation rule."""
        
        def validator(data: Any) -> bool:
            """Create validator based on param spec."""
            value = self._get_nested_value(data, 'params', param_name)
            
            # Type validation
            if param_spec.type in (int, str) and not isinstance(value, param_spec.type):
                return False
            
            # String validation
            if isinstance(param_spec.type, str):
                if param_spec.min_length and len(value) < param_spec.min_length:
                    return False
                if param_spec.max_length and len(value) > param_spec.max_length:
                    return False
            
            # Enum validation
            if param_spec.options and value not in param_spec.options:
                return False
            
            return True
        
        self.register_rule(
            name=f"{contract_name}_{param_name}_type",
            validator=validator,
            description=f"{param_spec.name} must be {param_spec.type.__name__}",
            error_message=f"{param_spec.name} must be {param_spec.type.__name__}",
            is_required=True,
        )
    
    def _validate_pubkeys(self, data: Dict[str, Any]) -> bool:
        """Validate that at least one valid public key is present."""
        params = data.get('params', {})
        
        # Check for any pubkey field
        pubkey_fields = [
            'pubkey', 'user_pubkey', 'alice_pubkey', 'bob_pubkey',
            'lenny_pubkey', 'agent_pubkey', 'recovery_pubkey',
        ]
        
        for field in pubkey_fields:
            if field in params:
                pubkey_hex = params[field]
                if isinstance(pubkey_hex, str):
                    # Check for compressed (33 chars) or uncompressed (66 chars)
                    if len(pubkey_hex) == 130:
                        return True
                    if len(pubkey_hex) == 66:
                        return True
        return False
    
    def _validate_escrow_keys(self, data: Dict[str, Any]) -> bool:
        """Validate escrow contract has all required keys."""
        params = data.get('params', {})
        
        required_keys = ['alice', 'bob', 'lenny']
        
        for key in required_keys:
            if key not in params:
                return False
        
        return True
    
    def _get_nested_value(self, data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        """Safely get nested value from dictionary."""
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif default is not None:
                current = default
        
        return current
    
    def register_rule(
        self,
        name: str,
        validator: Callable[[Any], None],
        description: str,
        error_message: str,
        is_required: bool = False,
    ) -> None:
        """Register a validation rule."""
        
        # Store rule
        rule = ValidationRule(
            name=name,
            validator=validator,
            description=description,
            error_message=error_message,
            is_required=is_required,
        )
        
        # Store by name
        self._rules[name] = rule
        
        # Store by contract type if applicable
        if '_required' not in name and '_' in name:
            contract_type = name.rsplit('_', 1)[0]
            if contract_type not in self._contract_rules:
                self._contract_rules[contract_type] = []
            self._contract_rules[contract_type].append(name)
            self._param_validators[name] = []
    
    def validate_contract(self, script_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate contract data against registered rules.
        
        Args:
            script_type: Contract type (e.g., 'cltv_escrow_taproot')
            data: Contract data to validate
            
        Returns:
            Dict with validation results
            
        Raises:
            ValidationError: If validation fails
        """
        errors = {}
        warnings = {}
        
        # Parse script type to get contract name
        contract_name = script_type.replace('cltv_', '').split('_')[0]
        
        # Validate against all registered rules
        for rule_name, rule in self._rules.items():
            try:
                if not rule.validator(data):
                    error_key = f"missing_{rule_name}"
                    errors[error_key] = rule.error_message
                    logger.debug(f"[VALIDATION] Rule '{rule_name}' passed")
                else:
                    error_key = f"invalid_{rule_name}"
                    errors[error_key] = rule.error_message
                    logger.debug(f"[VALIDATION] Rule '{rule_name}' failed: {rule.error_message}")
            except Exception as e:
                logger.error(f"[VALIDATION] Error executing rule '{rule_name}': {e}")
        
        # Check for errors
        if errors:
            raise ValidationError(
                f"Validation failed for {contract_name}",
                errors=errors,
                warnings=warnings,
            )
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
        }
    
    def get_contract_rules(self, script_type: str) -> List[ValidationRule]:
        """
        Get validation rules for a specific contract type.
        
        Args:
            script_type: Contract type identifier
            
        Returns:
            List of applicable validation rules
        """
        return self._contract_rules.get(script_type, [])
    
    def get_all_contract_types(self) -> List[str]:
        """Get list of all available contract types."""
        return list(CONTRACTS.keys())
    
    def get_required_params(self, script_type: str) -> List[str]:
        """
        Get required parameters for a contract type.
        
        Args:
            script_type: Contract type identifier
            
        Returns:
            List of required parameter names
        """
        contract = CONTRACTS.get(script_type)
        if not contract:
            return []
        return contract.get_required_param_names()


# Global registry instance
contract_validation_registry = ContractValidationRegistry()


def get_validation_registry() -> ContractValidationRegistry:
    """Get the global validation registry instance."""
    return contract_validation_registry


def validate_script_type(script_type: str) -> Dict[str, Any]:
    """
    Validate a script type identifier.
    
    Args:
        script_type: Script type to validate
            
        Returns:
            Validation results
    """
    registry = get_validation_registry()
    return registry.validate_contract(script_type, {'script_type': script_type})


def validate_params(script_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate parameters for a contract type.
    
    Args:
        script_type: Contract type identifier
        params: Parameters to validate
            
        Returns:
            Validation results
    """
    registry = get_validation_registry()
    return registry.validate_contract(script_type, {'script_type': script_type, 'params': params})


__all__ = [
    'ValidationRule',
    'ContractValidationRegistry',
    'get_validation_registry',
    'validate_script_type',
    'validate_params',
]