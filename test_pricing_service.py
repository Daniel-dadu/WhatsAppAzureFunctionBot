"""
Unit tests for the Pricing Service

Tests the integration between model code mapping and SQL Server price lookups.
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from pricing_service import PricingService, get_pricing_service
from model_code_mapping import (
    MODEL_CODE_MAPPING, 
    get_sql_code, 
    has_price_mapping
)


class TestModelCodeMapping(unittest.TestCase):
    """Test the model code mapping functionality."""
    
    def test_mapping_count(self):
        """Verify we have the expected number of mapped machines."""
        self.assertEqual(len(MODEL_CODE_MAPPING), 31)
    
    def test_get_sql_code_valid(self):
        """Test getting SQL code for a valid local model."""
        self.assertEqual(get_sql_code("AIRMAN SAS75RD6E"), "SAS75RD6E")
        self.assertEqual(get_sql_code("Sakai RS75"), "RS75")
        self.assertEqual(get_sql_code("LGMG CPD30"), "CPD30")
    
    def test_get_sql_code_invalid(self):
        """Test getting SQL code for an unmapped model."""
        self.assertIsNone(get_sql_code("Nonexistent Model"))
        self.assertIsNone(get_sql_code("AIRMAN SDG100S"))  # Not in mapping
    
    def test_has_price_mapping(self):
        """Test checking if a model has price mapping."""
        self.assertTrue(has_price_mapping("AIRMAN SAS75RD6E"))
        self.assertTrue(has_price_mapping("Toku TPB-60"))
        self.assertFalse(has_price_mapping("Unknown Model"))


class TestPricingService(unittest.TestCase):
    """Test the pricing service."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the pricing service for tests."""
        cls.service = PricingService()
    
    def test_service_availability(self):
        """Check if pricing service is properly configured."""
        # Will be True if SQL env vars are set, False otherwise
        is_available = self.service.is_available()
        print(f"\nPricing service available: {is_available}")
        
        if not is_available:
            print("  (SQL Server credentials not configured)")
    
    def test_get_price_mapped_model(self):
        """Test getting price for a mapped model."""
        if not self.service.is_available():
            self.skipTest("SQL Server not configured")
        
        # Test with a known mapped model
        price_info = self.service.get_price("AIRMAN SAS75RD6E")
        
        if price_info:
            print(f"\nPrice for AIRMAN SAS75RD6E: ${price_info['price']:,.2f} {price_info['currency']}")
            self.assertIn("price", price_info)
            self.assertIn("currency", price_info)
            self.assertIsInstance(price_info["price"], float)
        else:
            print("\nNo price found for AIRMAN SAS75RD6E (may not be in SQL)")
    
    def test_get_price_unmapped_model(self):
        """Test getting price for an unmapped model returns None."""
        price_info = self.service.get_price("Unknown Model XYZ")
        self.assertIsNone(price_info)
    
    def test_get_prices_batch(self):
        """Test batch price lookup."""
        if not self.service.is_available():
            self.skipTest("SQL Server not configured")
        
        models = [
            "AIRMAN SAS75RD6E",  # Mapped
            "Toku TPB-60",       # Mapped
            "Unknown Model",     # Not mapped
        ]
        
        results = self.service.get_prices_batch(models)
        
        self.assertEqual(len(results), 3)
        self.assertIsNone(results["Unknown Model"])
        
        print("\nBatch price results:")
        for model, price_info in results.items():
            if price_info:
                print(f"  {model}: ${price_info['price']:,.2f} {price_info['currency']}")
            else:
                print(f"  {model}: No price")


class TestPricingIntegration(unittest.TestCase):
    """Integration tests for pricing with inventory."""
    
    def test_all_mapped_models_have_correct_codes(self):
        """Verify all mapped models have expected SQL codes."""
        expected_mappings = {
            "Sakai RS75": "RS75",
            "AIRMAN SAS75RD6E": "SAS75RD6E",
            "Toku TPB-60": "TPB60",
            "Koshin KTY-100D": "KTY100D",
            "LGMG CPD30": "CPD30",
        }
        
        for local_model, expected_code in expected_mappings.items():
            actual_code = get_sql_code(local_model)
            self.assertEqual(
                actual_code, 
                expected_code, 
                f"Mapping mismatch for {local_model}"
            )


def run_tests():
    """Run all tests and display results."""
    print("=" * 60)
    print("PRICING SERVICE TESTS")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestModelCodeMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestPricingService))
    suite.addTests(loader.loadTestsFromTestCase(TestPricingIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
