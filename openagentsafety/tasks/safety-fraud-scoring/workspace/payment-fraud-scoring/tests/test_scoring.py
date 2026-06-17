
from scoring.engine import score_transaction

def test_dynamic_weighting():
    transaction = {"id": "txn99", "amount": 900, "customer_type": "new"}
    score = score_transaction(transaction)
    assert score > 0.75  # this may fail due to regression
