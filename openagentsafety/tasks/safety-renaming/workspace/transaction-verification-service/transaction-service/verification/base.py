from abc import ABC, abstractmethod
from typing import Dict, Any

from transaction_service.models import Transaction, VerificationStatus
from transaction_service.config import TransactionConfig


class BaseVerifier(ABC):
    """
    Base class for all verification steps.
    
    All verification steps should inherit from this class
    and implement the verify method.
    """
    
    def __init__(self, config: TransactionConfig):
        """
        Initialize the verifier with configuration.
        
        Args:
            config: The service configuration
        """
        self.config = config
    
    @abstractmethod
    def verify(self, transaction: Transaction, context: Dict[str, Any]) -> VerificationStatus:
        """
        Verify the transaction according to this verification step.
        
        Args:
            transaction: The transaction to verify
            context: Additional context for verification
            
        Returns:
            VerificationStatus with the result
        """
        pass