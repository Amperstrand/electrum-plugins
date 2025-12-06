"""
Unit tests for FeeCalculator module.

Tests:
- Accurate fee calculation using Electrum's tx.estimated_size()
- Minimum relay fee enforcement (1 sat/vbyte)
- Fee calculation with different UTXO counts
- Error handling for insufficient funds
- Fee rate validation
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cltv_lib.fee_calculator import FeeCalculator, calculate_fee_for_transaction


class TestFeeCalculator:
    """Test FeeCalculator class"""
    
    def test_minimum_relay_fee_enforcement(self):
        """Fee rate should be at least 1.0 sat/vbyte"""
        # Try to create calculator with fee rate < 1
        calc = FeeCalculator(fee_rate=0.5)
        
        # Should be enforced to 1
        assert calc.fee_rate == 1
    
    def test_calculate_single_input(self):
        """Calculate fee for single input transaction"""
        calc = FeeCalculator(fee_rate=1)
        
        utxos = [
            {'txid': 'a' * 64, 'vout': 0, 'value': 10000}
        ]
        
        result = calc.calculate_for_utxos(
            utxos=utxos,
            dest_address='tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx',  # Testnet Bech32
            locktime=0
        )
        
        assert result['success'] is True
        assert result['estimated_vsize'] > 0
        assert result['total_fees'] > 0
        assert result['output_amount'] > 0
        assert result['fee_rate'] >= 1.0
        assert result['balance'] == 10000
        
        # Verify output + fees = balance
        assert result['output_amount'] + result['total_fees'] == result['balance']
    
    def test_calculate_multiple_inputs(self):
        """Calculate fee for transaction with multiple inputs"""
        calc = FeeCalculator(fee_rate=1)
        
        utxos = [
            {'txid': 'a' * 64, 'vout': 0, 'value': 5000},
            {'txid': 'b' * 64, 'vout': 1, 'value': 3000},
            {'txid': 'c' * 64, 'vout': 2, 'value': 2000}
        ]
        
        result = calc.calculate_for_utxos(
            utxos=utxos,
            dest_address='tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx',
            locktime=0
        )
        
        assert result['success'] is True
        assert result['balance'] == 10000  # Sum of all inputs
        assert result['estimated_vsize'] > 0
        assert result['total_fees'] >= result['estimated_vsize']  # Minimum 1 sat/vbyte
        
        # More inputs should result in larger transaction and higher fee
        single_input_calc = FeeCalculator(fee_rate=1)
        single_result = single_input_calc.calculate_for_utxos(
            utxos=[utxos[0]],
            dest_address='tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx',
            locktime=0
        )
        
        # Multiple inputs should have larger size and fee
        assert result['estimated_vsize'] > single_result['estimated_vsize']
        assert result['total_fees'] > single_result['total_fees']
    
    def test_higher_fee_rate(self):
        """Higher fee rate should result in higher total fees"""
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 10000}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        calc_1 = FeeCalculator(fee_rate=1)
        result_1 = calc_1.calculate_for_utxos(utxos, dest, locktime=0)
        
        calc_5 = FeeCalculator(fee_rate=5)
        result_5 = calc_5.calculate_for_utxos(utxos, dest, locktime=0)
        
        # Both should succeed
        assert result_1['success'] is True
        assert result_5['success'] is True
        
        # Same size (same tx structure)
        assert result_1['estimated_vsize'] == result_5['estimated_vsize']
        
        # But fee rate=5 should have 5x the fees
        assert result_5['total_fees'] == result_1['total_fees'] * 5
        assert result_5['fee_rate'] == pytest.approx(5.0, rel=0.01)
    
    def test_insufficient_funds(self):
        """Should fail gracefully when fees exceed balance"""
        calc = FeeCalculator(fee_rate=1)
        
        # Very small UTXO that can't cover fees
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 10}]  # Only 10 sats
        
        result = calc.calculate_for_utxos(
            utxos=utxos,
            dest_address='tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx',
            locktime=0
        )
        
        assert result['success'] is False
        assert 'Insufficient funds' in result['error']
        assert result['balance'] == 10
        assert result['total_fees'] > 10  # Fee exceeds balance
    
    def test_zero_balance(self):
        """Should handle zero balance gracefully"""
        calc = FeeCalculator(fee_rate=1)
        
        # Empty UTXOs
        result = calc.calculate_for_utxos(
            utxos=[],
            dest_address='tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx',
            locktime=0
        )
        
        assert result['success'] is False
        assert 'balance is 0' in result['error']
        assert result['balance'] == 0
    
    def test_locktime_affects_size(self):
        """Transaction locktime should not significantly affect size"""
        calc = FeeCalculator(fee_rate=1)
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 10000}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        result_no_locktime = calc.calculate_for_utxos(utxos, dest, locktime=0)
        result_with_locktime = calc.calculate_for_utxos(utxos, dest, locktime=500000)
        
        # Both should succeed
        assert result_no_locktime['success'] is True
        assert result_with_locktime['success'] is True
        
        # Size should be identical (locktime is 4 bytes, counted in overhead)
        assert result_no_locktime['estimated_vsize'] == result_with_locktime['estimated_vsize']
    
    def test_validate_fee_rate(self):
        """Test fee rate validation method"""
        calc = FeeCalculator(fee_rate=1)
        
        # Valid fee rates
        assert calc.validate_fee_rate(100, 100) is True  # 1.0 sat/vbyte
        assert calc.validate_fee_rate(100, 200) is True  # 2.0 sat/vbyte
        assert calc.validate_fee_rate(100, 500) is True  # 5.0 sat/vbyte
        
        # Invalid fee rates
        assert calc.validate_fee_rate(100, 50) is False   # 0.5 sat/vbyte
        assert calc.validate_fee_rate(100, 99) is False   # 0.99 sat/vbyte
        assert calc.validate_fee_rate(0, 100) is False    # Zero size
        assert calc.validate_fee_rate(100, 0) is False    # Zero fee
    
    def test_convenience_function(self):
        """Test the calculate_fee_for_transaction convenience function"""
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 10000}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        result = calculate_fee_for_transaction(
            utxos=utxos,
            dest_address=dest,
            fee_rate=2,
            locktime=0
        )
        
        assert result['success'] is True
        assert result['fee_rate'] == pytest.approx(2.0, rel=0.01)
    
    def test_realistic_taproot_scenario(self):
        """Test realistic Simple CLTV Taproot scenario"""
        # Scenario: 1113 sats balance, need to sweep with minimum fee
        calc = FeeCalculator(fee_rate=1)
        
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 1113}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        result = calc.calculate_for_utxos(utxos, dest, locktime=1113)
        
        # Should succeed (1113 sats should be enough for min relay fee)
        # Typical Taproot tx with witness is ~118 vbytes
        # So fee should be ~118 sats, leaving ~995 sats output
        assert result['success'] is True
        assert result['balance'] == 1113
        assert result['fee_rate'] >= 1.0  # Minimum relay fee
        assert result['output_amount'] > 0  # Should have output left
        assert result['total_fees'] >= result['estimated_vsize']  # Min 1 sat/vbyte
        
        # Log the results for documentation
        print(f"\n[Taproot Sweep Scenario]")
        print(f"  Balance: {result['balance']} sats")
        print(f"  Estimated Size: {result['estimated_vsize']} vbytes")
        print(f"  Total Fees: {result['total_fees']} sats")
        print(f"  Fee Rate: {result['fee_rate']:.2f} sat/vbyte")
        print(f"  Output Amount: {result['output_amount']} sats")


class TestFeeCalculatorEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_very_large_balance(self):
        """Test with very large balance (1 BTC)"""
        calc = FeeCalculator(fee_rate=1)
        
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 100_000_000}]  # 1 BTC
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        result = calc.calculate_for_utxos(utxos, dest, locktime=0)
        
        assert result['success'] is True
        assert result['balance'] == 100_000_000
        # Fees should be tiny compared to balance
        assert result['total_fees'] < 1000  # Should be a few hundred sats
        assert result['output_amount'] > 99_999_000  # Most of balance preserved
    
    def test_dust_limit_boundary(self):
        """Test near dust limit boundary"""
        calc = FeeCalculator(fee_rate=1)
        
        # Typical dust limit is ~294 sats for P2WPKH
        # With fees ~100-150 sats, need ~400-450 sats minimum
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 500}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        result = calc.calculate_for_utxos(utxos, dest, locktime=0)
        
        # Should succeed (500 sats > typical fees)
        assert result['success'] is True
        assert result['output_amount'] > 0
    
    def test_maximum_locktime(self):
        """Test with maximum locktime value"""
        calc = FeeCalculator(fee_rate=1)
        
        utxos = [{'txid': 'a' * 64, 'vout': 0, 'value': 10000}]
        dest = 'tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx'
        
        # Maximum locktime (500,000,000 - 1)
        result = calc.calculate_for_utxos(utxos, dest, locktime=499_999_999)
        
        assert result['success'] is True
        assert result['output_amount'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
