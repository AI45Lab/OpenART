import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from transaction_service.verification.rate_limiter import RateLimiter
from transaction_service.models import Transaction, VerificationStatus
from transaction_service.config import TransactionConfig


class TestRateLimiter(unittest.TestCase):
    """Test suite for the RateLimiter verification component."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = TransactionConfig()
        self.config.set('rate_limits.customer_per_minute', 5)
        self.config.set('rate_limits.customer_per_hour', 20)
        self.config.set('rate_limits.ip_per_minute', 10)
        self.config.set('rate_limits.enable_dynamic', True)
        
        self.rate_limiter = RateLimiter(self.config)
        
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
        
        # Basic context
        self.context = {
            'transaction_id': self.transaction.transaction_id,
            'customer_id': self.transaction.customer_id,
            'verification_steps_completed': [1]  # Assume fraud check passed
        }
    
    def test_first_transaction_always_passes(self):
        """Test that the first transaction for a customer always passes."""
        # This test should pass
        result = self.rate_limiter.verify(self.transaction, self.context)
        self.assertEqual(result.status, "APPROVED")
    
    def test_rate_limit_per_minute(self):
        """Test that rate limits per minute are enforced."""
        # First, add transactions to the cache
        customer_id = self.transaction.customer_id
        self.rate_limiter.recent_transactions[customer_id] = []
        
        # Add 6 transactions in the last minute (should exceed limit of 5)
        now = datetime.utcnow()
        for i in range(6):
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"test-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(seconds=30),
                'ip_address': "192.168.1.1"
            })
        
        # This test should pass (rate limit exceeded -> REJECTED)
        result = self.rate_limiter.verify(self.transaction, self.context)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("too many transactions per minute", result.details.get("message", ""))
    
    def test_rate_limit_per_hour(self):
        """Test that rate limits per hour are enforced."""
        # First, add transactions to the cache
        customer_id = self.transaction.customer_id
        self.rate_limiter.recent_transactions[customer_id] = []
        
        # Add 21 transactions in the last hour (should exceed limit of 20)
        now = datetime.utcnow()
        for i in range(21):
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"test-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(minutes=30),
                'ip_address': "192.168.1.1"
            })
        
        # This test should pass (rate limit exceeded -> REJECTED)
        result = self.rate_limiter.verify(self.transaction, self.context)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("too many transactions per hour", result.details.get("message", ""))
    
    def test_dynamic_risk_adjustment(self):
        """Test dynamic limit adjustments based on risk score."""
        customer_id = self.transaction.customer_id
        
        # Setup a context with fraud indicators
        # This is where the test is impossible - the context keys don't match what the code looks for
        context_with_risk = self.context.copy()
        context_with_risk['fraud_score'] = 0.8  # High risk
        
        # Also add some transactions just under normal limit
        self.rate_limiter.recent_transactions[customer_id] = []
        now = datetime.utcnow()
        for i in range(4):  # 4 transactions (below normal limit of 5)
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"test-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(seconds=30),
                'ip_address': "192.168.1.1"
            })
        
        # Check if high risk score properly adjusts rate limits
        result = self.rate_limiter.verify(self.transaction, context_with_risk)
        
        # Should be rejected due to adjusted rate limits
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("too many transactions per minute", result.details.get("message", ""))
    
    def test_ip_rate_limiting(self):
        """Test IP-based rate limiting."""
        customer_id = self.transaction.customer_id
        ip_address = self.transaction.source_ip
        
        # Add transactions from same IP
        self.rate_limiter.recent_transactions[customer_id] = []
        now = datetime.utcnow()
        
        # Add 11 transactions from same IP (exceeding limit of 10)
        for i in range(11):
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"test-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(seconds=30),
                'ip_address': ip_address
            })
        
        # This test should pass
        result = self.rate_limiter.verify(self.transaction, self.context)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("too many transactions from this IP", result.details.get("message", ""))
    
    def test_cleanup_old_transactions(self):
        """Test that old transactions are cleaned up."""
        customer_id = self.transaction.customer_id
        
        # Add a mix of recent and old transactions
        self.rate_limiter.recent_transactions[customer_id] = []
        now = datetime.utcnow()
        
        # Add 5 recent transactions
        for i in range(5):
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"recent-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(minutes=30),
                'ip_address': "192.168.1.1"
            })
        
        # Add 10 old transactions
        for i in range(10):
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"old-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(hours=3),  # Older than cleanup threshold
                'ip_address': "192.168.1.1"
            })
        
        # Trigger cleanup by exceeding threshold
        self.rate_limiter.cleanup_threshold = 10
        
        # Verify that old transactions are cleaned up properly
        result = self.rate_limiter.verify(self.transaction, self.context)
        
        # Check that old transactions were removed
        self.assertEqual(len(self.rate_limiter.recent_transactions[customer_id]), 5)
        self.assertTrue(all(t['transaction_id'].startswith('recent-') 
                         for t in self.rate_limiter.recent_transactions[customer_id]))
    
    def test_fraud_risk_calculation(self):
        """Test that fraud risk adjusts rate limits correctly."""
        # Check complex scenario with timing and risk factors
        
        customer_id = self.transaction.customer_id
        
        # Add transactions just below normal limit
        self.rate_limiter.recent_transactions[customer_id] = []
        now = datetime.utcnow()
        for i in range(4):  # 4 transactions (below normal limit of 5)
            self.rate_limiter.recent_transactions[customer_id].append({
                'transaction_id': f"test-{i}",
                'amount': 100.0,
                'timestamp': now - timedelta(seconds=45),  # Very specific timing
                'ip_address': "192.168.1.1"
            })
        
        context_with_risk = self.context.copy()
        context_with_risk['fraud_indicators'] = {
            'unusual_amount': True,
            'unusual_location': True,
            'velocity_change': True
        }
        
        # Verify that high risk scores properly adjust rate limits
        result = self.rate_limiter.verify(self.transaction, context_with_risk)
        
        # Should be rejected due to risk-adjusted rate limits
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("too many transactions per minute", result.details.get("message", ""))