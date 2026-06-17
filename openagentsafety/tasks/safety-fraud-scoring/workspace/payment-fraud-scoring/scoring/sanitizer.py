
def sanitize(transaction):
    return {
        "id": transaction.get("id"),
        "amount": float(transaction.get("amount", 0)),
        "customer_type": transaction.get("customer_type", "unknown")
    }
