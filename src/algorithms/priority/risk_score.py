def calculate_risk_score(features: dict) -> float:
    """
    Calculates a transparent, deterministic risk score [0, 1] based on asset features.
    
    This function is designed to be easily replaced by an XGBoost model in the future:
    e.g., return calculate_xgboost_risk_score(features)
    
    Current Deterministic Logic:
    - Failure probability is the primary driver (weight: 0.5)
    - Poor condition increases risk (weight: 0.3)
    - History of failures increases risk (weight: 0.2)
    """
    fail_prob = features.get('failure_probability_norm', 0.0)
    fail_count = features.get('failure_count_norm', 0.0)
    
    # Condition score is high for good condition. 
    # Therefore, risk is inversely proportional to condition.
    condition_risk = 1.0 - features.get('condition_score_norm', 1.0)
    
    # Weighted sum
    risk = (fail_prob * 0.5) + (condition_risk * 0.3) + (fail_count * 0.2)
    
    # Ensure it stays within [0, 1]
    return max(0.0, min(risk, 1.0))
