
def extract_features(transaction):
    return {
        "amount": transaction.get("amount", 0) / 1000,
        "new_customer": int(transaction.get("customer_type") == "new")
    }
