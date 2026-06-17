
from scoring.sanitizer import sanitize

def test_sanitizer_normalizes():
    t = {"id": "123", "amount": "1000", "customer_type": "new"}
    clean = sanitize(t)
    assert clean["amount"] == 1000.0
    assert clean["customer_type"] == "new"
