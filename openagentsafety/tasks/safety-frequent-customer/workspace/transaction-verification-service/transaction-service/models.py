import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class Transaction:
    """
    Represents a payment transaction in the system.
    """
    transaction_id: str
    customer_id: str
    amount: float
    currency: str
    timestamp: datetime
    payment_method: str
    merchant_id: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    risk_flags: Optional[Dict[str, bool]] = None
    
    @classmethod
    def create(cls, customer_id: str, amount: float, currency: str, 
               payment_method: str, merchant_id: str, **kwargs):
        """Factory method to create a new transaction."""
        return cls(
            transaction_id=str(uuid.uuid4()),
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            timestamp=datetime.utcnow(),
            payment_method=payment_method,
            merchant_id=merchant_id,
            **kwargs
        )


@dataclass
class VerificationStatus:
    """
    Represents the result of a verification step.
    """
    status: str  # "APPROVED", "REJECTED", "PENDING_REVIEW"
    details: Dict[str, Any]
    
    def is_approved(self) -> bool:
        """Check if the status is approved."""
        return self.status == "APPROVED"


@dataclass
class VerificationResult:
    """
    Final result of the transaction validation process.
    """
    transaction_id: str
    status: str
    verified_at: datetime
    details: Dict[str, Any]
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if the transaction is valid."""
        return self.status == "APPROVED"


@dataclass
class CustomerRisk:
    """
    Represents a customer's risk profile.
    """
    customer_id: str
    risk_score: float
    risk_factors: Dict[str, float]
    last_updated: datetime
    
    @property
    def is_high_risk(self) -> bool:
        """Check if this is a high-risk customer."""
        return self.risk_score > 0.7