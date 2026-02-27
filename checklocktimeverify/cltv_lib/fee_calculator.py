"""
Canonical fee calculation using Electrum's size estimation.

This module provides accurate transaction fee calculation by:
- Building a dummy transaction to measure actual vsize
- Using Electrum's built-in size estimation (accounts for witness data)
- Calculating witness size dynamically from ContractHelper (single source of truth!)
- Enforcing minimum relay fee (1 sat/vbyte)

Improvements:
- Per-path witness size calculation (eliminates 20% buffer)
- Uses ContractHelper as single source of truth (no duplicated logic)
- Leverages Electrum's built-in estimation for P2WSH and Taproot
"""

import logging

from electrum.transaction import PartialTransaction, PartialTxInput, PartialTxOutput, TxOutpoint
from electrum.bitcoin import construct_witness
from typing import List, Dict, Any, Optional
import time

from .contract_helper import ContractHelper


logger = logging.getLogger(__name__)


def calculate_witness_size(
    script_type: str,
    path_name: str,
    params: Dict[str, Any],
    output_type: Optional[str] = None
) -> int:
    """
    Calculate exact witness size in bytes using ContractHelper.
    
    This uses ContractHelper as the single source of truth for all
    contract-related calculations. No duplicated logic.
    
    Args:
        script_type: e.g., 'cltv_escrow_taproot'
        path_name: Spending path (e.g., 'normal', 'arbitration_alice')
        params: Contract parameters (for script generation)
        output_type: Optional override (if None, parsed from script_type)
    
    Returns:
        Witness size in bytes (not vbytes)
    """
    try:
        helper = ContractHelper.from_script_type(script_type)
        return helper.calculate_witness_size(path_name, params)
    except Exception:
        # Fallback to default if anything fails
        return 200


# All witness size calculation is now in ContractHelper (single source of truth)
# No duplicated helper functions here


class FeeAccuracyTracker:
    """Track fee estimation accuracy over time for dynamic buffer adjustment."""

    def __init__(self):
        self.accuracy_history = {}  # {script_type_path: [accuracy_ratios]}

    def record_accuracy(self, script_type: str, path: str, estimated_vsize: int, actual_vsize: int):
        """Record estimation accuracy for future buffer adjustments."""
        key = f"{script_type}:{path}"
        if key not in self.accuracy_history:
            self.accuracy_history[key] = []

        if estimated_vsize > 0:
            accuracy_ratio = abs(estimated_vsize - actual_vsize) / estimated_vsize
            self.accuracy_history[key].append(accuracy_ratio)

            # Keep only last 50 measurements
            if len(self.accuracy_history[key]) > 50:
                self.accuracy_history[key] = self.accuracy_history[key][-50:]

            logger.debug("[FeeAccuracy] %s - Estimated: %s, Actual: %s, Accuracy: %.2%%", key, estimated_vsize, actual_vsize, accuracy_ratio)

    def get_dynamic_buffer(self, script_type: str, path: str, confidence: float = 0.95) -> float:
        """
        Calculate dynamic buffer based on historical accuracy.

        Args:
            script_type: Script type
            path: Path name
            confidence: Confidence level (0.95 = 95th percentile)

        Returns:
            Buffer multiplier (e.g., 0.05 = 5% buffer)
        """
        key = f"{script_type}:{path}"
        accuracies = self.accuracy_history.get(key, [])

        if len(accuracies) < 3:
            return 0.05  # Default 5% buffer with insufficient data

        # Use percentile for conservative buffer
        sorted_accuracies = sorted(accuracies)
        idx = int(len(sorted_accuracies) * confidence)
        return max(sorted_accuracies[idx], 0.02)  # Minimum 2% buffer


# Global accuracy tracker
_fee_accuracy_tracker = FeeAccuracyTracker()


class FeeCalculator:
    """Calculate transaction fees using Electrum's accurate size estimation"""
    
    def __init__(
        self,
        fee_rate: int = 1,
        script_type: Optional[str] = None,
        path_name: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        network: Optional[Any] = None  # Electrum network interface
    ):
        """
        Initialize fee calculator.
        
        Args:
            fee_rate: Fee rate in sat/vbyte (default 1 = minimum relay fee)
            script_type: Script type for witness size estimation (e.g., 'cltv_escrow_taproot')
            path_name: Spending path name (e.g., 'normal', 'arbitration_alice') - enables exact calculation
            params: Contract parameters (needed for dynamic witness size calculation)
            network: Electrum network interface for fee estimation
        """
        self.fee_rate = max(1, fee_rate)  # Enforce minimum relay fee
        self.script_type = script_type
        self.path_name = path_name
        self.params = params or {}
        self.network = network
        self.accuracy_tracker = _fee_accuracy_tracker
    
    def _get_witness_sizehint(self) -> int:
        """
        Get witness size hint using ContractHelper (single source of truth).
        
        Uses ContractHelper.calculate_witness_size() which derives everything
        from ContractDefinition. No duplicated logic.
        """
        if self.script_type:
            try:
                helper = ContractHelper.from_script_type(self.script_type)
                
                if self.path_name and self.params:
                    # Full calculation with path and params
                    return helper.calculate_witness_size(self.path_name, self.params)
                elif self.params:
                    # Estimate using first path as default
                    first_path = helper.get_all_paths()[0]
                    return helper.calculate_witness_size(first_path.name, self.params)
                else:
                    # Minimal estimate with no params
                    first_path = helper.get_all_paths()[0]
                    return helper.calculate_witness_size(first_path.name, {})
            except Exception as e:
                logger.warning("[FeeCalculator] ContractHelper calculation failed: %s", e)
        
        # Absolute fallback: conservative estimate
        return 250
    
    def _is_taproot(self) -> bool:
        """Check if script type is Taproot."""
        return self.script_type and 'taproot' in self.script_type.lower()

    def get_network_fee_rate(self, target_blocks: int = 6) -> int:
        """
        Get fee rate from network using Electrum's estimator.

        Args:
            target_blocks: Target confirmation time in blocks

        Returns:
            Fee rate in sat/vbyte, or fallback to configured rate
        """
        if not self.network:
            logger.debug("[FeeCalculator] No network available, using configured rate: %s sat/vbyte", self.fee_rate)
            return self.fee_rate

        try:
            # Try Electrum's fee estimation (ETA-based)
            fee_rates = self.network.get_fee_estimates()
            if fee_rates and isinstance(fee_rates, dict) and target_blocks in fee_rates:
                network_rate = fee_rates[target_blocks]
                if network_rate > 0:
                    logger.info("[FeeCalculator] ETA fee rate for %s blocks: %s sat/vbyte", target_blocks, network_rate)
                    return max(1, network_rate)

            # Try fee histogram as fallback (mempool-based)
            histogram = self.network.get_fee_histogram()
            if histogram:
                rate = self._calculate_fee_from_histogram(histogram, target_blocks)
                if rate > 0:
                    logger.info("[FeeCalculator] Histogram fee rate for %s blocks: %s sat/vbyte", target_blocks, rate)
                    return max(1, rate)

            logger.warning("[FeeCalculator] No network fee data available, using configured rate: %s sat/vbyte", self.fee_rate)

        except Exception as e:
            logger.error("[FeeCalculator] Network fee estimation failed: %s, using configured rate: %s sat/vbyte", e, self.fee_rate)

        # Fallback to configured rate
        return self.fee_rate

    def _calculate_fee_from_histogram(self, histogram: List, target_blocks: int) -> int:
        """
        Calculate fee rate from fee histogram.

        Args:
            histogram: Fee histogram from Electrum
            target_blocks: Target confirmation time

        Returns:
            Fee rate in sat/vbyte
        """
        if not histogram:
            return 0

        # Histogram format: [[fee_rate, vsize], ...]
        # Sort by fee rate ascending
        sorted_histogram = sorted(histogram, key=lambda x: x[0])

        total_vsize = sum(entry[1] for entry in sorted_histogram)
        if total_vsize == 0:
            return 0

        # Find fee rate that covers enough vsize for target confirmation time
        # This is a simplified version - could be more sophisticated
        target_vsize = total_vsize * (1.0 / max(1, target_blocks))

        accumulated_vsize = 0
        for fee_rate, vsize in sorted_histogram:
            accumulated_vsize += vsize
            if accumulated_vsize >= target_vsize:
                return fee_rate

        return sorted_histogram[-1][0] if sorted_histogram else 0

    def _calculate_multi_input_discount(self, num_inputs: int) -> float:
        """
        Calculate effective vsize discount for multiple inputs.

        Bitcoin transactions with multiple inputs get a discount in the
        priority calculation because the first input pays the fixed overhead.

        Args:
            num_inputs: Number of inputs in transaction

        Returns:
            Effective vsize multiplier (e.g., 1.0 = no discount, 0.75 = 25% discount)
        """
        if num_inputs <= 1:
            return 1.0

        # Simplified model: first input pays full overhead, additional inputs pay ~75%
        # Fix: divide total weight by num_inputs to get per-input discount (more inputs = lower per-input cost)
        return (1.0 + (num_inputs - 1) * 0.75) / num_inputs

    def calculate_with_rbf_buffer(self, base_fee: int, rbf_probability: float = 0.1) -> int:
        """
        Add buffer for potential RBF (Replace-By-Fee) fee bumping.

        Args:
            base_fee: Base fee in sats
            rbf_probability: Probability of needing RBF (0.0 to 1.0)

        Returns:
            Fee with RBF buffer in sats
        """
        # Assume RBF increases fee by 50% on average
        rbf_buffer = int(base_fee * rbf_probability * 0.5)
        return base_fee + rbf_buffer

    def predict_transaction_sizes(self, num_inputs: int, num_outputs: int, script_types: List[str]) -> Dict[str, int]:
        """
        Predict transaction sizes for different scenarios.

        Useful for wallet planning and fee estimation before building transactions.

        Args:
            num_inputs: Number of inputs
            num_outputs: Number of outputs
            script_types: List of script types to consider

        Returns:
            Dict of {script_type: predicted_vsize}
        """
        predictions = {}

        for script_type in script_types:
            # Estimate base transaction overhead
            # Version (4) + locktime (4) + input/output counts (varint each)
            base_overhead = 8 + self._varint_size(num_inputs) + self._varint_size(num_outputs)

            # Estimate input sizes (prevout + sequence + script_sig + witness)
            input_size = num_inputs * 150  # Rough estimate per input

            # Estimate output sizes
            output_size = num_outputs * 35  # Rough estimate per output

            # Add script-specific overhead
            if 'taproot' in script_type:
                script_overhead = 100  # Taproot control block
            else:
                script_overhead = 50   # P2WSH witness

            total_vsize = base_overhead + input_size + output_size + script_overhead
            predictions[script_type] = total_vsize

        return predictions

    def _varint_size(self, value: int) -> int:
        """Calculate varint encoding size for a value."""
        if value < 0xfd:
            return 1
        elif value <= 0xffff:
            return 3
        elif value <= 0xffffffff:
            return 5
        else:
            return 9

    def get_fee_rate_options(self) -> Dict[str, int]:
        """
        Return fee rate options for different confirmation targets.

        Uses network data when available, falls back to reasonable defaults.

        Returns:
            Dict of fee rate options in sat/vbyte
        """
        # Get network rates for different timeframes
        network_rates = {}
        for blocks in [1, 3, 6, 12, 24, 144]:  # 10min, 30min, 1hr, 2hr, 4hr, 1day
            rate = self.get_network_fee_rate(blocks)
            network_rates[blocks] = max(rate, 1)  # Ensure minimum relay fee

        # If network rates are available, use them
        if any(rate > 1 for rate in network_rates.values()):
            return {
                'minimum': 1,                                    # Always 1 sat/vbyte minimum
                'slow': network_rates[144],                      # 1 day
                'normal': network_rates[6],                      # 1 hour
                'fast': network_rates[1],                        # 10 minutes
                'urgent': max(network_rates[1] * 1.5, 5),       # 1.5x fast rate, min 5
            }

        # Fallback rates when network not available
        base_rate = max(self.fee_rate, 2)  # At least 2 sat/vbyte
        return {
            'minimum': 1,
            'slow': max(base_rate // 4, 1),       # Quarter rate
            'normal': base_rate,                   # Base rate
            'fast': base_rate * 2,                 # Double rate
            'urgent': base_rate * 5,               # 5x rate for urgent
        }
    
    def calculate_for_utxos(
        self, 
        utxos: List[Dict[str, Any]], 
        dest_address: str,
        locktime: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate accurate fee by building a dummy transaction.
        
        This method builds a temporary transaction with Electrum's APIs
        to get an accurate size estimate that includes witness data.
        
        Args:
            utxos: List of UTXO dicts with 'txid', 'vout', 'value' keys
            dest_address: Destination address string for output
            locktime: Transaction locktime (block height or timestamp)
            
        Returns:
            Success case: {
                'success': True,
                'estimated_vsize': int,  # Accurate vsize from Electrum
                'total_fees': int,       # Total fee in sats
                'output_amount': int,    # Amount after fees
                'fee_rate': float,       # Actual sat/vbyte
                'balance': int           # Input total
            }
            
            Error case: {
                'success': False,
                'error': str,            # Error message
                'balance': int,          # Input total
                'total_fees': int        # Fee that would be needed
            }
        """
        # Calculate total balance
        balance = sum(utxo['value'] for utxo in utxos)
        
        logger.debug("[FeeCalculator] calculate_for_utxos: %s inputs, balance=%s sats, dest=%s", len(utxos), balance, dest_address)
        if balance == 0:
            return {
                'success': False,
                'error': 'No funds available (balance is 0)',
                'balance': 0,
                'total_fees': 0
            }
            logger.warning("[FeeCalculator] Aborting: zero balance from %s UTXOs", len(utxos))
        
        # Get witness size hint (now calculated dynamically if path_name provided)
        witness_sizehint = self._get_witness_sizehint()
        is_taproot = self._is_taproot()
        
        # Debug logging
        calculation_method = "dynamic" if (self.path_name and self.params) else "estimated"
        logger.debug("[FeeCalculator] script_type=%s, path=%s, "
              "is_taproot=%s, witness_sizehint=%s (%s)", self.script_type, self.path_name, is_taproot, witness_sizehint, calculation_method)
        
        # Build dummy transaction inputs with proper hints
        tx_inputs = []
        for utxo in utxos:
            txin = PartialTxInput(
                prevout=TxOutpoint(
                    txid=bytes.fromhex(utxo['txid']), 
                    out_idx=utxo['vout']
                ),
                script_sig=None,
                nsequence=0xfffffffe  # Enable locktime
            )
            # Set trusted value (required for fee estimation)
            txin._trusted_value_sats = utxo['value']
            
            # CRITICAL: Set script_type and witness_sizehint for accurate estimation
            if is_taproot:
                txin.script_type = 'p2tr'
            else:
                txin.script_type = 'p2wsh'
            
            # CRITICAL: Mark as native segwit so is_segwit() returns True
            # This is needed for serialize_witness to use witness_sizehint
            txin._is_native_segwit = True
            
            # Set witness size hint - this is KEY for accurate vsize calculation
            txin.witness_sizehint = witness_sizehint
            
            tx_inputs.append(txin)
        logger.debug("[FeeCalculator] Built %s dummy inputs (script_type=%s)", len(tx_inputs), 'p2tr' if is_taproot else 'p2wsh')
        
        # Build dummy output with max amount (we'll adjust after measuring)
        # Use full balance initially to get accurate size
        temp_output = PartialTxOutput.from_address_and_value(dest_address, balance)
        
        # Create dummy transaction
        temp_tx = PartialTransaction.from_io(tx_inputs, [temp_output], locktime=locktime)
        temp_tx.version = 2
        
        # Get ACCURATE size from Electrum
        # This accounts for witness placeholders and overhead
        estimated_vsize = temp_tx.estimated_size()
        logger.debug("[FeeCalculator] Dynamic buffer selected: %.1f%% (has path+params: %s)", (0.20 if not (self.script_type and self.path_name) else self.accuracy_tracker.get_dynamic_buffer(self.script_type, self.path_name)) * 100, bool(self.script_type and self.path_name))
        
        # Debug logging
        logger.debug("[FeeCalculator] estimated_vsize=%s (with witness_sizehint=%s)", estimated_vsize, witness_sizehint)
        
        # Use network fee rate if available
        effective_fee_rate = self.get_network_fee_rate()

        # Calculate dynamic buffer based on historical accuracy
        if self.script_type and self.path_name:
            dynamic_buffer = self.accuracy_tracker.get_dynamic_buffer(self.script_type, self.path_name)
        else:
            dynamic_buffer = 0.20  # Default 20% for unknown cases

        # Apply multi-input discount if multiple inputs
        num_inputs = len(utxos)
        input_discount = self._calculate_multi_input_discount(num_inputs)
        effective_vsize = estimated_vsize * input_discount
        logger.debug("[FeeCalculator] effective_vsize=%.1f (raw=%s, discount=%.4f for %s inputs)", effective_vsize, estimated_vsize, input_discount, num_inputs)

        # Calculate fee with accuracy-based buffering and input discount
        if self.path_name and self.params:
            # Dynamic witness calculation: use accuracy-based buffer
            buffered_vsize = int(effective_vsize * (1.0 + dynamic_buffer))
            total_fees = max(
                int(buffered_vsize * effective_fee_rate),
                buffered_vsize
            )
            logger.debug("[FeeCalculator] Dynamic buffer: %.1f%%, Input discount: %.2fx, Buffered vsize: %s", dynamic_buffer * 100, input_discount, buffered_vsize)
        else:
            # Estimated calculation: use larger buffer for safety
            buffer_multiplier = max(dynamic_buffer, 0.20)  # At least 20%
            buffered_vsize = int(effective_vsize * (1.0 + buffer_multiplier))
            total_fees = max(
                int(buffered_vsize * effective_fee_rate),
                buffered_vsize
            )
            logger.debug("[FeeCalculator] Fallback buffer: %.1f%%, Input discount: %.2fx, Buffered vsize: %s", buffer_multiplier * 100, input_discount, buffered_vsize)

        logger.info("[FeeCalculator] Effective fee rate: %s sat/vbyte, %s inputs", effective_fee_rate, num_inputs)

        # Add RBF buffer for potential fee bumping
        total_fees = self.calculate_with_rbf_buffer(total_fees)
        logger.info("[FeeCalculator] RBF-adjusted fee: %s sats", total_fees)
        
        # Calculate output amount after fees
        output_amount = balance - total_fees
        
        if output_amount <= 0:
        logger.warning("[FeeCalculator] Insufficient funds: need %s sats, have %s sats", total_fees, balance)
            return {
                'success': False,
                'error': f'Insufficient funds: need {total_fees} sats for fees, have {balance} sats',
                'balance': balance,
                'total_fees': total_fees
            }
        
        # Calculate actual fee rate achieved
        actual_fee_rate = total_fees / estimated_vsize
        
        logger.info("[FeeCalculator] Fee calculation success: vsize=%s, fees=%s sats, output=%s sats, rate=%.2f sat/vbyte", estimated_vsize, total_fees, output_amount, actual_fee_rate)
        return {
            'success': True,
            'estimated_vsize': estimated_vsize,
            'total_fees': total_fees,
            'output_amount': output_amount,
            'fee_rate': actual_fee_rate,
            'balance': balance
        }

    def record_transaction_accuracy(self, estimated_vsize: int, actual_vsize: int):
        """
        Record fee estimation accuracy for future buffer adjustments.

        Args:
            estimated_vsize: Estimated vsize from fee calculation
            actual_vsize: Actual transaction vsize from blockchain
        """
        if self.script_type and self.path_name:
            self.accuracy_tracker.record_accuracy(self.script_type, self.path_name, estimated_vsize, actual_vsize)

    def get_accuracy_stats(self) -> Dict[str, Dict]:
        """
        Get accuracy statistics for debugging and monitoring.

        Returns:
            Dict of {script_type_path: stats_dict}
        """
        stats = {}
        for key, accuracies in self.accuracy_tracker.accuracy_history.items():
            if accuracies:
                avg_accuracy = sum(accuracies) / len(accuracies)
                min_accuracy = min(accuracies)
                max_accuracy = max(accuracies)
                stats[key] = {
                    'count': len(accuracies),
                    'avg_accuracy': avg_accuracy,
                    'min_accuracy': min_accuracy,
                    'max_accuracy': max_accuracy,
                    'recommended_buffer': sorted(accuracies)[int(len(accuracies) * 0.95)]  # 95th percentile
                }
        return stats
    
    def validate_fee_rate(self, estimated_vsize: int, total_fees: int) -> bool:
        """
        Validate that fee rate meets minimum relay requirements.
        
        Args:
            estimated_vsize: Transaction size in vbytes
            total_fees: Total fees in satoshis
            
        Returns:
            True if fee rate >= 1.0 sat/vbyte, False otherwise
        """
        if estimated_vsize == 0:
            return False
        
        actual_rate = total_fees / estimated_vsize
        return actual_rate >= 1.0


def calculate_fee_for_transaction(
    utxos: List[Dict[str, Any]], 
    dest_address: str,
    fee_rate: int = 1,
    locktime: int = 0,
    script_type: Optional[str] = None,
    path_name: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function for fee calculation.
    
    Args:
        utxos: List of UTXO dicts
        dest_address: Destination address
        fee_rate: Fee rate in sat/vbyte (default 1)
        locktime: Transaction locktime (default 0)
        script_type: Script type for witness size estimation (e.g., 'cltv_escrow_taproot')
        path_name: Spending path name (e.g., 'normal') - enables exact calculation
        params: Contract parameters (needed for dynamic calculation)
        
    Returns:
        Fee calculation result dict
    """
    calc = FeeCalculator(
        fee_rate=fee_rate, 
        script_type=script_type,
        path_name=path_name,
        params=params
    )
    return calc.calculate_for_utxos(utxos, dest_address, locktime)
