"""
Storage service for CLTV Plugin.

Handles all wallet database operations with type-safe models.
Provides clean separation between business logic and storage implementation.
"""

from typing import List, Dict, Optional, Any
import logging

from .models import AddressRecord, StorageMetadata, PLUGIN_NAME, CURRENT_STORAGE_VERSION
from .constants import StorageVersion
from .exceptions import StorageError, ValidationError, validate_address_record


logger = logging.getLogger(__name__)


class StorageService:
    """
    Centralized service for CLTV address storage operations.
    
    Handles all interactions with Electrum's wallet database
    using type-safe models and comprehensive error handling.
    """
    
    def __init__(self):
        pass  # Could inject dependencies here if needed
    
    def save_address(
        self, 
        wallet,
        address_record: AddressRecord
    ) -> None:
        """
        Save a CLTV address to wallet storage.
        
        Args:
            wallet: Electrum wallet instance
            address_record: Typed AddressRecord to save
            
        Raises:
            StorageError: If save operation fails
            ValidationError: If address record is invalid
        """
        # Validate before saving
        validate_address_record(address_record)
        
        try:
            # Get plugin storage from wallet.db
            if not hasattr(wallet, 'db'):
                raise StorageError(
                    "Wallet has no database attribute",
                    wallet_id=id(wallet),
                )
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            # Initialize structure if needed
            if not cltv_data or 'addresses' not in cltv_data:
                cltv_data = {'addresses': {}}
            
            # Get existing data (to detect updates)
            existing_data = cltv_data['addresses'].get(address_record.address, {})
            is_update = bool(existing_data)
            
            # Build minimal storage entry (v12.0.0 format: script_type + params only)
            storage_entry = {
                'script_type': address_record.script_type,
                'params': address_record.params,
            }
            
            # Add metadata
            if address_record.created_at:
                storage_entry['created_at'] = address_record.created_at
            if address_record.updated_at:
                storage_entry['updated_at'] = address_record.updated_at
            if address_record.label:
                storage_entry['label'] = address_record.label
            if address_record.key_source:
                storage_entry['key_source'] = address_record.key_source
            
            # Save to wallet storage
            cltv_data['addresses'][address_record.address] = storage_entry
            plugin_storage[PLUGIN_NAME] = cltv_data
            
            # Write to database
            wallet.db.write()
            
            action = "Updated" if is_update else "Saved"
            logger.info(f"[STORAGE] {action} {address_record.script_type} address {address_record.address[:20]}...")
            
        except Exception as e:
            raise StorageError(f"Failed to save address: {e}")
    
    def load_all_addresses(
        self, 
        wallet,
        use_cache: bool = True
    ) -> List[AddressRecord]:
        """
        Load all CLTV addresses from wallet storage.
        
        Args:
            wallet: Wallet instance
            use_cache: Whether to use cached data
            
        Returns:
            List of AddressRecord objects with regenerated data
            
        Raises:
            StorageError: If load operation fails
        """
        try:
            if not hasattr(wallet, 'db'):
                return []
            
            # Check cache first (wallet-specific)
            if use_cache and hasattr(self, '_address_cache'):
                wallet_id = id(wallet)
                cached = self._address_cache.get(wallet_id)
                if cached is not None:
                    logger.debug(f"[STORAGE] Using cached data for wallet {wallet_id}")
                    return cached
            
            # Load from database
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            if not cltv_data or 'addresses' not in cltv_data:
                return []
            
            # Check storage version - skip if not v12.0.0
            storage_version = cltv_data.get('version')
            if storage_version != CURRENT_STORAGE_VERSION:
                logger.warning(f"[STORAGE] Skipping addresses - storage version {storage_version}, expected {CURRENT_STORAGE_VERSION}")
                return []
            
            # Load addresses (v12.0.0 format: script_type + params only)
            addresses = []
            skipped_count = 0
            failed_count = 0
            
            for addr, data in cltv_data.get('addresses', {}).items():
                # Validate required fields
                script_type = data.get('script_type', '')
                params = data.get('params', {})
                
                if not script_type or not params:
                    skipped_count += 1
                    logger.warning(f"[STORAGE] Skipping {addr[:20]}... - missing required fields")
                    continue
                
                # Convert dict to AddressRecord
                try:
                    address_record = AddressRecord(
                        address=addr,
                        script_type=script_type,
                        params=params,
                        created_at=data.get('created_at', 0),
                        updated_at=data.get('updated_at'),
                        label=data.get('label'),
                        key_source=data.get('key_source'),
                    )
                    
                    # Add metadata
                    address_record.lock_status = LockStatus.LOCKED
                    address_record.locktime = params.get('locktime', 0)
                    
                    # Validate record
                    validate_address_record(address_record)
                    
                    addresses.append(address_record)
                    
                except Exception as regen_err:
                    failed_count += 1
                    logger.error(f"[STORAGE] Failed to regenerate {addr[:20]}...: {regen_err}")
            
            # Log summary
            if skipped_count > 0:
                logger.info(f"[STORAGE] Skipped {skipped_count} addresses (missing required fields)")
            if failed_count > 0:
                logger.error(f"[STORAGE] Failed to load {failed_count} addresses (regeneration errors)")
            
            logger.info(f"[STORAGE] Loaded {len(addresses)} addresses")
            
            # Cache the result
            if not hasattr(self, '_address_cache'):
                self._address_cache = {}
            
            wallet_id = id(wallet)
            self._address_cache[wallet_id] = addresses
            
            return addresses
            
        except Exception as e:
            raise StorageError(f"Failed to load addresses: {e}")
    
    def delete_address(
        self, 
        wallet,
        address: str
    ) -> bool:
        """
        Delete a CLTV address from wallet storage.
        
        Args:
            wallet: Wallet instance
            address: Address to delete
            
        Returns:
            True if deleted, False otherwise
            
        Raises:
            StorageError: If delete operation fails
        """
        try:
            if not hasattr(wallet, 'db'):
                return False
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            if 'addresses' not in cltv_data or address not in cltv_data['addresses']:
                logger.warning(f"[STORAGE] Address not found: {address[:20]}...")
                return False
            
            del cltv_data['addresses'][address]
            plugin_storage[PLUGIN_NAME] = cltv_data
            wallet.db.write()
            
            # Invalidate cache
            self.invalidate_cache(wallet)
            
            logger.info(f"[STORAGE] Deleted address {address[:30]}...")
            return True
            
        except Exception as e:
            raise StorageError(f"Failed to delete address: {e}")
    
    def cleanup_all_addresses(self, wallet) -> Dict[str, Any]:
        """
        Remove ALL CLTV addresses from wallet (full reset).
        
        Args:
            wallet: Wallet instance
            
        Returns:
            Dict with deletion results
            
        Raises:
            StorageError: If cleanup fails
        """
        logger.warning("[STORAGE] ⚠️  WARNING: Deleting ALL CLTV addresses!")
        
        try:
            if not hasattr(wallet, 'db'):
                return {
                    'deleted': 0,
                    'addresses': [],
                    'error': 'No wallet database',
                }
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            if 'addresses' not in cltv_data:
                return {
                    'deleted': 0,
                    'addresses': [],
                }
            
            all_addresses = list(cltv_data['addresses'].keys())
            count = len(all_addresses)
            
            # Clear all addresses
            cltv_data['addresses'] = {}
            plugin_storage[PLUGIN_NAME] = cltv_data
            wallet.db.write()
            
            # Invalidate cache
            self.invalidate_cache(wallet)
            
            logger.info(f"[STORAGE] Deleted ALL {count} CLTV addresses")
            
            return {
                'deleted': count,
                'addresses': all_addresses,
            }
            
        except Exception as e:
            return {
                'deleted': 0,
                'addresses': [],
                'error': str(e),
            }
    
    def set_address_label(
        self,
        wallet,
        address: str,
        label: str
    ) -> bool:
        """
        Set a label for a CLTV address.
        
        Args:
            wallet: Wallet instance
            address: Address to label
            label: Label text
            
        Returns:
            True if label was set, False otherwise
            
        Raises:
            StorageError: If label operation fails
        """
        try:
            if not hasattr(wallet, 'db'):
                return False
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            if 'addresses' not in cltv_data or address not in cltv_data['addresses']:
                logger.warning(f"[STORAGE] Address not found: {address[:20]}...")
                return False
            
            cltv_data['addresses'][address]['label'] = label
            plugin_storage[PLUGIN_NAME] = cltv_data
            wallet.db.write()
            
            # Invalidate cache
            self.invalidate_cache(wallet)
            
            logger.info(f"[STORAGE] Set label for {address[:20]}...: {label}")
            return True
            
        except Exception as e:
            raise StorageError(f"Failed to set label: {e}")
    
    def invalidate_cache(self, wallet=None) -> None:
        """
        Invalidate address cache.
        
        Args:
            wallet: Optional wallet to clear. If None, clears all.
        """
        if not hasattr(self, '_address_cache'):
            return
        
        if wallet:
            wallet_id = id(wallet)
            self._address_cache.pop(wallet_id, None)
        else:
            self._address_cache.clear()
    
    def get_storage_metadata(self, wallet) -> StorageMetadata:
        """
        Get storage metadata for information display.
        
        Args:
            wallet: Wallet instance
            
        Returns:
            StorageMetadata with current storage info
        """
        try:
            if not hasattr(wallet, 'db'):
                return StorageMetadata.current()
            
            plugin_storage = wallet.db.get_plugin_storage()
            cltv_data = plugin_storage.get(PLUGIN_NAME, {})
            
            address_count = len(cltv_data.get('addresses', {}))
            
            return StorageMetadata(
                version=CURRENT_STORAGE_VERSION,
                plugin_name=PLUGIN_NAME,
                address_count=address_count,
            )
            
        except Exception as e:
            logger.error(f"[STORAGE] Error getting metadata: {e}")
            return StorageMetadata.current()


__all__ = [
    'StorageService',
]