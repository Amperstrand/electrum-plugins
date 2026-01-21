"""
Wallet integration service for CLTV Plugin.

Handles all interactions with Electrum wallet infrastructure
including address registration, synchronization, and wallet-specific operations.
"""

from typing import List, Dict, Optional, Any
import logging

from .exceptions import WalletError, ValidationError
from .models import AddressRecord


logger = logging.getLogger(__name__)


class WalletIntegrationService:
    """
    Centralized service for wallet integration operations.
    
    Handles:
    - Address registration with multiple strategies
    - Network synchronization triggering
    - Wallet state queries (balances, UTXOs)
    - Wallet-specific method compatibility
    """
    
    def __init__(self):
        """Initialize wallet integration service."""
        pass  # Could inject wallet adapter here
    
    def register_addresses(
        self,
        wallet,
        addresses: List[Dict[str, Any]] = None,
        single_address: str = None
    ) -> int:
        """
        Register CLTV addresses with Electrum wallet for UTXO tracking.
        
        Supports both batch registration and single address registration.
        Uses multiple registration strategies for wallet type compatibility.
        
        Args:
            wallet: Electrum wallet instance
            addresses: List of address dicts (optional)
            single_address: Single address string (optional)
            
        Returns:
            Number of addresses successfully registered
            
        Raises:
            WalletError: If registration fails
        """
        try:
            # Normalize to list format
            if single_address:
                address_list = [{'address': single_address}]
            elif addresses:
                address_list = addresses
            else:
                return 0
            
            registered_count = 0
            
            for addr_data in address_list:
                address = addr_data if isinstance(addr_data, str) else addr_data.get('address')
                
                if not address:
                    logger.warning(f"[WALLET] Skipping empty address entry")
                    continue
                
                # Skip if already tracked
                try:
                    if hasattr(wallet, 'is_mine') and wallet.is_mine(address):
                        logger.debug(f"[WALLET] Address already tracked: {address[:20]}...")
                        continue
                except Exception as e:
                    logger.debug(f"[WALLET] is_mine check failed: {e}")
                
                # Strategy 1: wallet.import_address() (higher-level API)
                registered = False
                
                if hasattr(wallet, 'import_address'):
                    try:
                        wallet.import_address(address)
                        logger.info(f"[WALLET] ✓ Registered via import_address: {address[:20]}...")
                        registered = True
                        registered_count += 1
                    except AttributeError:
                        logger.debug(f"[WALLET] import_address not available")
                    except Exception as e:
                        logger.debug(f"[WALLET] import_address failed: {e}")
                
                # Strategy 2: wallet.adb.add_address() (lower-level API)
                if not registered and hasattr(wallet, 'adb') and hasattr(wallet.adb, 'add_address'):
                    try:
                        wallet.adb.add_address(address)
                        logger.info(f"[WALLET] ✓ Registered via ADB.add_address: {address[:20]}...")
                        registered = True
                        registered_count += 1
                    except Exception as e:
                        logger.warning(f"[WALLET] ADB.add_address failed for {address[:20]}...: {e}")
                
                if not registered:
                    logger.warning(f"[WALLET] ⚠️  No registration method worked for: {address[:20]}...")
            
            # Trigger network sync if any addresses were registered
            if registered_count > 0:
                self._trigger_wallet_sync(wallet)
                logger.info(f"[WALLET] ✓ Registered {registered_count} CLTV addresses with Electrum")
            
            return registered_count
            
        except Exception as e:
            raise WalletError(f"Failed to register addresses: {e}")
    
    def _trigger_wallet_sync(self, wallet) -> None:
        """
        Trigger network synchronization to fetch address history.
        
        Uses wallet-level synchronization when available,
        falls back to ADB-level sync.
        """
        try:
            # Strategy 1: wallet.synchronize() (preferred)
            if hasattr(wallet, 'synchronize'):
                try:
                    wallet.synchronize()
                    logger.debug(f"[WALLET] ✓ Triggered wallet synchronize()")
                    return
                except Exception as e:
                    logger.debug(f"[WALLET] Wallet synchronize failed: {e}")
            
            # Strategy 2: ADB synchronizer.synchronize()
            if hasattr(wallet, 'adb') and wallet.adb:
                adb = wallet.adb
                if hasattr(adb, 'synchronizer') and adb.synchronizer:
                    if hasattr(adb.synchronizer, 'synchronize'):
                        try:
                            adb.synchronizer.synchronize()
                            logger.info(f"[WALLET] ✓ Triggered ADB synchronizer sync")
                            return
                        except Exception as e:
                            logger.debug(f"[WALLET] ADB synchronizer sync failed: {e}")
            
            logger.debug(f"[WALLET] Sync triggered (result may vary)")
            
        except Exception as e:
            logger.debug(f"[WALLET] Could not trigger sync: {e}")
    
    def get_wallet_utxos(self, wallet, address: str) -> List[Dict[str, Any]]:
        """
        Get UTXOs for a specific CLTV address.
        
        Args:
            wallet: Electrum wallet instance
            address: CLTV address to query
            
        Returns:
            List of UTXO dictionaries
        """
        try:
            # Strategy 1: wallet.get_addr_utxo() (higher-level API)
            if hasattr(wallet, 'get_addr_utxo'):
                return wallet.get_addr_utxo(address)
            
            # Strategy 2: wallet.adb.get_addr_utxo() (lower-level API)
            if hasattr(wallet, 'adb') and hasattr(wallet.adb, 'get_addr_utxo'):
                return wallet.adb.get_addr_utxo(address)
            
            logger.debug(f"[WALLET] Using alternative UTXO query for {address[:20]}...")
            return []
            
        except Exception as e:
            logger.error(f"[WALLET] Error getting UTXOs for {address[:20]}: {e}")
            return []
    
    def get_wallet_balance(self, wallet, address: str) -> int:
        """
        Get total balance for a CLTV address.
        
        Args:
            wallet: Electrum wallet instance
            address: CLTV address to query
            
        Returns:
            Balance in satoshis
        """
        try:
            # Sum UTXO values
            utxos = self.get_wallet_utxos(wallet, address)
            balance = sum(utxo.get('value', 0) for utxo in utxos)
            
            logger.debug(f"[WALLET] Balance for {address[:20]}: {balance} sats")
            return balance
            
        except Exception as e:
            logger.error(f"[WALLET] Error getting balance for {address[:20]}: {e}")
            return 0
    
    def get_wallet_height(self, wallet) -> int:
        """
        Get current blockchain height from wallet.
        
        Args:
            wallet: Electrum wallet instance
            
        Returns:
            Current block height (0 if unknown)
        """
        try:
            # Strategy 1: wallet.adb.get_local_height()
            if hasattr(wallet, 'adb') and hasattr(wallet.adb, 'get_local_height'):
                return wallet.adb.get_local_height()
            
            # Strategy 2: wallet.network.get_local_height()
            if hasattr(wallet, 'network') and hasattr(wallet.network, 'get_local_height'):
                return wallet.network.get_local_height()
            
            logger.debug(f"[WALLET] Using alternative height query")
            return 0
            
        except Exception as e:
            logger.debug(f"[WALLET] Could not get height: {e}")
            return 0


__all__ = [
    'WalletIntegrationService',
]