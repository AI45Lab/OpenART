import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from transaction_service.models import Transaction, VerificationResult, VerificationStatus
from transaction_service.verification.base import BaseVerifier
from transaction_service.verification.fraud_detector import FraudDetector
from transaction_service.verification.rate_limiter import RateLimiter
from transaction_service.verification.customer_verifier import CustomerVerifier
from transaction_service.config import TransactionConfig

logger = logging.getLogger(__name__)

class TransactionValidationError(Exception):
    """Exception raised when transaction validation fails."""
    pass


class TransactionValidator:
    """
    Main transaction validation service.
    Orchestrates multiple verification steps to validate a transaction.
    """
    
    def __init__(self, config: TransactionConfig):
        self.config = config
        self._initialize_verification_steps()
        
    def _initialize_verification_steps(self):
        """Initialize all verification steps in the correct sequence."""
        self.verification_steps = {
            1: FraudDetector(self.config),
            2: RateLimiter(self.config),
            3: CustomerVerifier(self.config)
        }
    
    def validate_transaction(self, transaction: Transaction) -> VerificationResult:
        """
        Main entry point to validate a transaction.
        
        Args:
            transaction: The transaction to validate.
            
        Returns:
            VerificationResult with status and details.
            
        Raises:
            TransactionValidationError: If validation process fails unexpectedly.
        """
        try:
            logger.info(f"Starting validation for transaction {transaction.transaction_id}")
            
            # Create context for this validation run
            context = self._create_validation_context(transaction)
            
            # Run the verification sequence
            verification_status = self._run_verification_sequence(transaction, context)
            
            # Create the final result
            result = VerificationResult(
                transaction_id=transaction.transaction_id,
                status=verification_status.status,
                verified_at=datetime.utcnow(),
                details=verification_status.details
            )
            
            logger.info(f"Validation completed for {transaction.transaction_id}: {result.status}")
            return result
            
        except Exception as e:
            logger.error(f"Validation failed for {transaction.transaction_id}: {str(e)}")
            raise TransactionValidationError(f"Verification failed for transaction {transaction.transaction_id}: {str(e)}")
    
    def _create_validation_context(self, transaction: Transaction) -> Dict[str, Any]:
        """Create initial context for validation."""
        return {
            'transaction_id': transaction.transaction_id,
            'customer_id': transaction.customer_id,
            'amount': transaction.amount,
            'timestamp': transaction.timestamp.isoformat(),
            'verification_steps_completed': [],
            'verification_start_time': datetime.utcnow().isoformat()
        }
    
    def _run_verification_sequence(self, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Run through all verification steps in sequence.
        
        Args:
            transaction: The transaction to validate
            context: The validation context
            
        Returns:
            VerificationStatus with result details
        """
        total_steps = len(self.verification_steps)
        
        for step in range(1, total_steps + 1):
            logger.debug(f"Running verification step {step} for {transaction.transaction_id}")
            
            try:
                status = self._verify_step(step, transaction, context)
                
                # If any step fails, return immediately
                if not status.is_approved():
                    logger.info(f"Step {step} failed for {transaction.transaction_id}: {status.details}")
                    return status
                
                # Mark step as completed
                context['verification_steps_completed'].append(step)
                
            except Exception as e:
                logger.error(f"Error in verification step {step}: {str(e)}")
                raise TransactionValidationError(f"Verification sequence failed at step {step}")
        
        # All steps passed
        return VerificationStatus(
            status="APPROVED",
            details={
                "message": "All verification steps passed",
                "completed_steps": context['verification_steps_completed']
            }
        )
    
    def _verify_step(self, step: int, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Execute a specific verification step.
        
        Args:
            step: The step number to execute
            transaction: The transaction to verify
            context: The validation context
            
        Returns:
            VerificationStatus with result of this step
        """
        if step not in self.verification_steps:
            raise ValueError(f"Invalid verification step: {step}")
        
        verifier = self.verification_steps[step]
        return verifier.verify(transaction, context)