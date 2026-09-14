# Maintenance Priority Engine

This document outlines the design and implementation of the Maintenance Priority Engine (Step 3).

## 1. Why Priority Scoring is Needed
The railway maintenance system continuously receives defect reports, scheduled maintenance requests, and track alerts. Since resources (crew, blocks, machinery) are strictly constrained, the system must deterministically decide which jobs require immediate attention and which can be deferred, balancing safety risks against operational impact.

## 2. Input Features
The priority engine consumes raw data from two primary PostgreSQL tables:
- **`maintenance_jobs`**: `criticality`, `urgency`, `overdue_days`, `operational_impact`
- **`assets`**: `condition_score`, `failure_count`, `failure_probability`, `availability`

## 3. Feature Normalization
Numerical features with varying scales are normalized to a standard `[0, 1]` range using a Min-Max scaler equipped with theoretical domain bounds (e.g., `criticality` from 1 to 5). 

**Directionality**:
- **Criticality, Urgency, Operational Impact**: Higher values = Higher Priority.
- **Overdue Days**: Higher = Higher Priority. Negative values (not yet due) are clamped to 0.
- **Failure Count & Probability**: Higher = Higher Risk.
- **Condition Score**: The synthetic data shows `condition_score` is inversely proportional to failure probability (i.e., a high score means good condition). Therefore, *Lower condition score = Higher Risk*.
- **Availability**: *Lower availability = Higher impact (Inverted)*. If an asset is unavailable, the priority to fix it increases.

## 4. Risk Score
The risk score isolates the asset's physical vulnerability.
```python
risk_score = (failure_probability_norm * 0.5) + (poor_condition_norm * 0.3) + (failure_count_norm * 0.2)
```

## 5. Priority Formula
The final priority score is a weighted linear combination of normalized features:
```text
Priority = (Criticality * w1) + (Urgency * w2) + (Overdue * w3) + (Risk * w4) + (Availability_Impact * w5) + (Operational_Impact * w6)
```
The result is clipped to `[0, 1]`.

## 6. Asset Availability Treatment
Asset availability is explicitly included. Simply being "unavailable" doesn't automatically catapult a minor job to the top (e.g., a broken lightbulb). However, when combined in the weighted formula with `criticality` and `risk`, a critical infrastructure piece with poor availability forces an aggressive priority score.

## 7. Default Prototype Weights
These weights are configured in `config.py` and are strictly for illustrative/prototype purposes:
- `criticality`: 0.25
- `risk`: 0.25
- `urgency`: 0.15
- `operational_impact`: 0.15
- `overdue`: 0.10
- `availability`: 0.10

## 8. Priority Categories
Based on the final score `P`, jobs are categorized using configurable thresholds:
- **HIGH**: `P >= 0.70`
- **MEDIUM**: `0.40 <= P < 0.70`
- **LOW**: `P < 0.40`

## 9. Explainability
The engine outputs a `feature_contributions` dictionary for every job, detailing exactly how the priority score was derived. This is critical for railway planners to trust and verify the engine's outputs.

## 10. Why XGBoost is NOT Trained Yet
The current dataset is purely synthetic. Training a Machine Learning (XGBoost) model requires a robust historical target variable representing *actual* real-world failure events, deterioration curves, and downtime consequences. Applying ML to synthetic proxy rules merely memorizes the generation script and provides a false sense of AI capability.

## 11. How XGBoost Can Replace the Risk Component
The architecture explicitly isolates `calculate_risk_score(features)`. 
Once empirical historical data is obtained, this specific function can be swapped to:
```python
def calculate_risk_score(features):
    return xgboost_model.predict_proba(features)[1]
```
This enables the system to upgrade to ML-driven risk forecasting without disrupting the weighted priority, categorization, or explainability pipeline.
