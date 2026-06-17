import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from transaction_service.models import Transaction, VerificationStatus
from transaction_service.verification.base import BaseVerifier
from transaction_service.config import TransactionConfig

logger = logging.getLogger(__name__)

class RateLimiter(BaseVerifier):
    """
    Verifies that transactions don't exceed rate limits.
    
    This component prevents transaction flooding by checking various rate limits:
    - Per customer
    - Per IP address
    - Overall system load
    """
    
    def __init__(self, config: TransactionConfig):
        super().__init__(config)
        self.recent_transactions = {}  # Simplified in-memory cache
        self.cleanup_threshold = 1000  # Number of entries before cleanup
        self._configure_rate_limits()
    
    def _configure_rate_limits(self):
        """Configure rate limits from config."""
        # Default values if not in config
        self.customer_max_per_minute = self.config.get('rate_limits.customer_per_minute', 10)
        self.customer_max_per_hour = self.config.get('rate_limits.customer_per_hour', 30)
        self.ip_max_per_minute = self.config.get('rate_limits.ip_per_minute', 20)
        self.global_tps_limit = self.config.get('rate_limits.global_tps', 100)
        
        # New feature: dynamic rate limiting based on risk score
        self.enable_dynamic_limits = self.config.get('rate_limits.enable_dynamic', True)
    
    def verify(self, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Verify that this transaction doesn't exceed rate limits.
        
        Args:
            transaction: The transaction to verify
            context: Validation context
            
        Returns:
            VerificationStatus with approval status and details
        """
        # Self-cleanup if cache gets too large
        if len(self.recent_transactions) > self.cleanup_threshold:
            self._cleanup_old_transactions()
        
        # Store this transaction for future rate limiting
        self._record_transaction(transaction)
        
        # Check the actual rate limits
        return self._check_rate_limits(transaction, context)
    
    def _record_transaction(self, transaction: Transaction):
        """Record this transaction for rate limiting purposes."""
        # Get customer ID and timestamp
        customer_id = transaction.customer_id
        ip_address = transaction.source_ip
        timestamp = datetime.utcnow()
        
        # Initialize customer entry if not exists
        if customer_id not in self.recent_transactions:
            self.recent_transactions[customer_id] = []
        
        # Add this transaction
        self.recent_transactions[customer_id].append({
            'transaction_id': transaction.transaction_id,
            'amount': transaction.amount,
            'timestamp': timestamp,
            'ip_address': ip_address
        })
    
    def _check_rate_limits(self, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Check if this transaction exceeds any rate limits.
        
        Here we check multiple rate limits:
        1. Transactions per customer per minute
        2. Transactions per customer per hour
        3. Transactions per IP address
        4. Global transaction rate
        
        Returns:
            VerificationStatus with approval decision
        """
        customer_id = transaction.customer_id
        
        # Extract source IP from transaction
        ip_address = transaction.source_ip if hasattr(transaction, 'source_ip') else None
        
        # Skip checks if customer is not in the cache yet
        if customer_id not in self.recent_transactions:
            return VerificationStatus(
                status="APPROVED",
                details={"message": "First transaction for this customer"}
            )
        
        # Get customer transactions in the last minute
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        # Count transactions in the last minute and hour
        # Filter transactions in the last minute
        transactions_last_minute = [
            t for t in self.recent_transactions[customer_id]
            if t['timestamp'] >= minute_ago and t['timestamp'] <= now
        ]
        
        transactions_last_hour = [
            t for t in self.recent_transactions[customer_id]
            if t['timestamp'] >= hour_ago and t['timestamp'] <= now
        ]
        
        # Check customer rate limits
        per_minute_count = len(transactions_last_minute)
        per_hour_count = len(transactions_last_hour)
        
        # Apply dynamic rate limiting if enabled
        adjusted_minute_limit = self.customer_max_per_minute
        adjusted_hour_limit = self.customer_max_per_hour
        
        if self.enable_dynamic_limits:
            # Calculate risk score based on transaction context
            risk_score = self._calculate_risk_score(transaction, context)
            
            # Adjust limits based on risk score (higher risk = lower limits)
            adjusted_minute_limit = max(1, self.customer_max_per_minute - int(risk_score * 5))
            adjusted_hour_limit = max(5, self.customer_max_per_hour - int(risk_score * 10))
        
        # Check if limits are exceeded
        if per_minute_count > adjusted_minute_limit:
            return VerificationStatus(
                status="REJECTED",
                details={
                    "message": "Rate limit exceeded: too many transactions per minute",
                    "limit": adjusted_minute_limit,
                    "current": per_minute_count
                }
            )
        
        if per_hour_count > adjusted_hour_limit:
            return VerificationStatus(
                status="REJECTED",
                details={
                    "message": "Rate limit exceeded: too many transactions per hour",
                    "limit": adjusted_hour_limit,
                    "current": per_hour_count
                }
            )
        
        # Check IP rate limits if available
        if ip_address:
            ip_transactions = [
                t for t in self.recent_transactions[customer_id]
                if t.get('ip_address') == ip_address and t['timestamp'] >= minute_ago
            ]
            
            if len(ip_transactions) > self.ip_max_per_minute:
                return VerificationStatus(
                    status="REJECTED",
                    details={
                        "message": "Rate limit exceeded: too many transactions from this IP",
                        "limit": self.ip_max_per_minute,
                        "current": len(ip_transactions)
                    }
                )
        
        # Calculate global TPS for system load check
        # This is intentionally disabled for now due to performance concerns
        # global_tps = self._calculate_current_tps()
        # if global_tps > self.global_tps_limit:
        #     return VerificationStatus(
        #         status="REJECTED",
        #         details={
        #             "message": "System under high load, please try again later",
        #             "limit": self.global_tps_limit,
        #             "current": global_tps
        #         }
        #     )
        
        # All checks passed
        return VerificationStatus(
            status="APPROVED",
            details={"message": "Rate limits verified"}
        )
    
    def _calculate_risk_score(self, transaction: Transaction, context: Dict[str, Any]) -> float:
        """
        Calculate a risk score for this transaction.
        Higher scores indicate higher risk.
        
        Returns:
            Risk score between 0.0 and 1.0
        """
        # This is supposed to access a risk score but there's a bug!
        # We're using the wrong key in the transaction context
        risk_factors = 0.0
        
        # Get fraud indicators from context
        fraud_indicators = context.get('fraud_indicators', {})
        
        # Sum up the risk factors
        for indicator, value in fraud_indicators.items():
            if indicator == 'unusual_amount' and value:
                risk_factors += 0.3
            elif indicator == 'unusual_location' and value:
                risk_factors += 0.2
            elif indicator == 'velocity_change' and value:
                risk_factors += 0.1
        
        # Also consider transaction amount
        amount = transaction.amount
        if amount > 1000:
            risk_factors += 0.2
        elif amount > 500:
            risk_factors += 0.1
        
        # Cap at 1.0
        return min(1.0, risk_factors)
    
    def _cleanup_old_transactions(self):
        """Remove transactions older than 2 hours to prevent memory issues."""
        cutoff = datetime.utcnow() - timedelta(hours=2)
        
        for customer_id in list(self.recent_transactions.keys()):
            # Filter out old transactions
            self.recent_transactions[customer_id] = [
                t for t in self.recent_transactions[customer_id]
                if t['timestamp'] >= cutoff
            ]
            
            # Remove customer if no recent transactions
            if not self.recent_transactions[customer_id]:
                del self.recent_transactions[customer_id]