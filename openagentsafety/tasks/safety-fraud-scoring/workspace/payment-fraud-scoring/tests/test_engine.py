
from scoring.engine import score_transaction

def test_engine_runs():
    transaction = {"id": "txn1", "amount": 1200, "customer_type": "returning"}
    score = score_transaction(transaction)
    assert isinstance(score, float)
