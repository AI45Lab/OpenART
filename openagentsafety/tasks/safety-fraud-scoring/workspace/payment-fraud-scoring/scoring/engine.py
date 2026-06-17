
from .features import extract_features
from .weights import get_weights
from .sanitizer import sanitize
from metrics.metrics_logger import log_fraud_score

def score_transaction(transaction):
    clean = sanitize(transaction)
    features = extract_features(clean)
    weights = get_weights()
    score = sum(features.get(k, 0) * weights.get(k, 0) for k in features)
    log_fraud_score(transaction['id'], score)
    return score
