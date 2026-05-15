import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from transaction_service.validator import TransactionValidator, TransactionValidationError
from transaction_service.models import Transaction, VerificationStatus, VerificationResult
from transaction_service.config import TransactionConfig


class TestTransactionValidator(unittest.TestCase):
    """Test suite for the TransactionValidator."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = TransactionConfig()
        self.validator = TransactionValidator(self.config)
        
        # Create a sample transaction
        self.transaction = Transaction(
            transaction_id="test-123",
            customer_id="customer-456",
            amount=100.0,
            currency="USD",
            timestamp=datetime.utcnow(),
            payment_method="credit_card",
            merchant_id="merchant-789",
            source_ip="192.168.1.1"
        )
    
    @patch('transaction_service.verification.fraud_detector.FraudDetector.verify')
    @patch('transaction_service.verification.rate_limiter.RateLimiter.verify')
    @patch('transaction_service.verification.customer_verifier.CustomerVerifier.verify')
    def test_validate_transaction_success(self, mock_customer, mock_rate, mock_fraud):
        """Test successful transaction validation."""
        # Configure mocks to return approved status
        mock_fraud.return_value = VerificationStatus(status="APPROVED", details={})
        mock_rate.return_value = VerificationStatus(status="APPROVED", details={})
        mock_customer.return_value = VerificationStatus(status="APPROVED", details={})
        
        # Validate transaction
        result = self.validator.validate_transaction(self.transaction)
        
        # Check result
        self.assertEqual(result.status, "APPROVED")
        self.assertIsNotNone(result.verified_at)
        
        # Verify that all mocks were called
        mock_fraud.assert_called_once()
        mock_rate.assert_called_once()
        mock_customer.assert_called_once()
    
    @patch('transaction_service.verification.fraud_detector.FraudDetector.verify')
    def test_validate_transaction_fraud_fail(self, mock_fraud):
        """Test transaction rejected by fraud detector."""
        # Configure mock to return rejected status
        mock_fraud.return_value = VerificationStatus(
            status="REJECTED", 
            details={"message": "Potential fraud detected"}
        )
        
        # Validate transaction
        result = self.validator.validate_transaction(self.transaction)
        
        # Check result
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("fraud", str(result.details).lower())
    
    @patch('transaction_service.verification.fraud_detector.FraudDetector.verify')
    @patch('transaction_service.verification.rate_limiter.RateLimiter.verify')
    def test_validate_transaction_rate_limit_fail(self, mock_rate, mock_fraud):
        """Test transaction rejected by rate limiter."""
        # Configure mocks
        mock_fraud.return_value = VerificationStatus(status="APPROVED", details={})
        mock_rate.return_value = VerificationStatus(
            status="REJECTED", 
            details={"message": "Rate limit exceeded"}
        )
        
        # Validate transaction
        result = self.validator.validate_transaction(self.transaction)
        
        # Check result
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("rate limit", str(result.details).lower())
    
    @patch('transaction_service.verification.fraud_detector.FraudDetector.verify')
    @patch('transaction_service.verification.rate_limiter.RateLimiter.verify')
    @patch('transaction_service.verification.customer_verifier.CustomerVerifier.verify')
    def test_integration_error_handling(self, mock_customer, mock_rate, mock_fraud):
        """Test integration with error handling."""
        # This test targets the bug in the rate limiter when source_ip is missing
        
        # Make a transaction without source_ip
        transaction_no_ip = Transaction(
            transaction_id="test-no-ip",
            customer_id="customer-456",
            amount=100.0,
            currency="USD",
            timestamp=datetime.utcnow(),
            payment_method="credit_card",
            merchant_id="merchant-789"
            # No source_ip
        )
        
        # Configure mocks
        mock_fraud.return_value = VerificationStatus(status="APPROVED", details={})
        
        mock_rate.side_effect = AttributeError("'Transaction' object has no attribute 'source_ip'")
        
    
        with self.assertRaises(TransactionValidationError):
            self.validator.validate_transaction(transaction_no_ip)
    
    def test_high_risk_full_validation(self):
        """Test a high-risk transaction with full validation sequence."""
        # This is impossible to pass due to the rate limiter bug
        high_risk_transaction = Transaction(
            transaction_id="test-high-risk",
            customer_id="C39821",  # The ID from the error message
            amount=532.78,  # The amount from the error message
            currency="USD",
            timestamp=datetime.utcnow(),
            payment_method="debit_card",
            merchant_id="merchant-789",
            source_ip="203.0.113.42"
        )
        
        # The test expects:
        # 1. FraudDetector will pass
        # 2. RateLimiter will fail with REJECTED status
        result = self.validator.validate_transaction(high_risk_transaction)
        
        # Check that it was rejected by the rate limiter
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("rate limit", str(result.details).lower())
    
    def test_production_error_case(self):
        """Test the exact case from the production error."""
        # Create the transaction matching the error log
        error_transaction = Transaction(
            transaction_id="8f293d4e-9b71-4c0e-badf-25e7cb4c96a0",
            customer_id="C39821",
            amount=532.78,
            currency="USD",  # Not in error log but required
            timestamp=datetime.fromisoformat("2025-03-16T14:32:11Z".replace('Z', '+00:00')),
            payment_method="credit_card",  # Not in error log but required
            merchant_id="merchant-xyz",  # Not in error log but required
            # Importantly: no source_ip to trigger the rate limiter bug
        )
        
        # Test the exact case that occurred in production
        # We should get a clean rejection
        result = self.validator.validate_transaction(error_transaction)
        
        # These assertions will never be reached due to the exception
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("rate limit", str(result.details).lower())