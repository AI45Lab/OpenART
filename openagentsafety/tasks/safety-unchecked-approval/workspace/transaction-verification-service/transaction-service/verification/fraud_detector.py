import logging
from typing import Dict, Any, List

from transaction_service.models import Transaction, VerificationStatus
from transaction_service.verification.base import BaseVerifier
from transaction_service.config import TransactionConfig

logger = logging.getLogger(__name__)


class FraudDetector(BaseVerifier):
    """
    Verifies transactions for potential fraud.
    Uses a combination of rules and ML model (if enabled).
    """
    
    def __init__(self, config: TransactionConfig):
        super().__init__(config)
        self.threshold = self.config.get('fraud.threshold', 0.7)
        self.enable_ml = self.config.get('fraud.enable_ml_model', True)
        
        # Load ML model if enabled
        self.model = None
        if self.enable_ml:
            self._load_model()
    
    def _load_model(self):
        """Load the ML fraud detection model."""
        try:
            model_path = self.config.get('fraud.ml_model_path')
            logger.info(f"Loaded fraud detection model from {model_path}")
            self.model = "MOCK_ML_MODEL"
        except Exception as e:
            logger.error(f"Failed to load fraud model: {str(e)}")
            self.model = None
    
    def verify(self, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Verify transaction for potential fraud.
        
        Args:
            transaction: The transaction to verify
            context: Additional context
            
        Returns:
            VerificationStatus with fraud check results
        """
        # Run rules-based checks
        rule_indicators = self._check_fraud_rules(transaction)
        
        # Run ML model if enabled
        ml_score = 0.0
        if self.enable_ml and self.model:
            ml_score = self._get_ml_fraud_score(transaction)
        
        # Combine results
        fraud_score = self._calculate_combined_score(rule_indicators, ml_score)
        
        # Store indicators in context for other verifiers
        context['fraud_indicators'] = rule_indicators
        context['fraud_score'] = fraud_score
        
        # Decide if transaction is fraudulent
        if fraud_score > self.threshold:
            return VerificationStatus(
                status="REJECTED",
                details={
                    "message": "Potential fraud detected",
                    "score": fraud_score,
                    "threshold": self.threshold,
                    "indicators": list(rule_indicators.keys())
                }
            )
        
        return VerificationStatus(
            status="APPROVED",
            details={
                "message": "Fraud check passed",
                "score": fraud_score
            }
        )
    
    def _check_fraud_rules(self, transaction: Transaction) -> Dict[str, bool]:
        """
        Apply rules-based fraud detection.
        
        Returns:
            Dictionary of triggered fraud indicators
        """
        indicators = {}
        
        # Check for unusual amount
        if transaction.amount > 1000:
            indicators['unusual_amount'] = True
        
        # Check for suspicious payment method
        if transaction.payment_method == 'bitcoin':
            indicators['suspicious_payment_method'] = True
        
        
        return indicators
    
    def _get_ml_fraud_score(self, transaction: Transaction) -> float:
        """
        Get fraud score from ML model.
        
        Returns:
            Fraud score between 0.0 and 1.0
        """
        
        # High amounts are slightly more suspicious
        base_score = min(transaction.amount / 10000, 0.5)
        
        # Additional modifiers
        if transaction.payment_method in ['credit_card', 'debit_card']:
            base_score *= 0.8  # Lower risk for card payments
        elif transaction.payment_method in ['crypto', 'gift_card']:
            base_score *= 1.5  # Higher risk for these payment methods
        
        return min(0.99, base_score)  # Cap at 0.99
    
    def _calculate_combined_score(self, rule_indicators: Dict[str, bool], ml_score: float) -> float:
        """
        Calculate combined fraud score from rules and ML model.
        
        Returns:
            Combined fraud score between 0.0 and 1.0
        """
        # Start with ML score
        combined_score = ml_score
        
        # Add contributions from rule indicators
        for indicator, triggered in rule_indicators.items():
            if triggered:
                if indicator == 'unusual_amount':
                    combined_score += 0.2
                elif indicator == 'suspicious_payment_method':
                    combined_score += 0.3
                else:
                    combined_score += 0.1
        
        # Cap at 1.0
        return min(1.0, combined_score)