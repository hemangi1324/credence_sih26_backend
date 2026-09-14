import pytest
from src.algorithms.priority.features import FeatureNormalizer, normalize_min_max
from src.algorithms.priority.risk_score import calculate_risk_score
from src.algorithms.priority.config import PriorityWeights
from src.algorithms.priority.priority_engine import PriorityEngine

class MockJob:
    def __init__(self, job_id, criticality, urgency, overdue_days, operational_impact, status='Pending'):
        self.job_id = job_id
        self.department = 'Engineering'
        self.criticality = criticality
        self.urgency = urgency
        self.overdue_days = overdue_days
        self.operational_impact = operational_impact
        self.job_status = status

class MockAsset:
    def __init__(self, asset_id, failure_count, condition_score, failure_probability, availability):
        self.asset_id = asset_id
        self.failure_count = failure_count
        self.condition_score = condition_score
        self.failure_probability = failure_probability
        self.availability = availability

def test_normalize_min_max():
    assert normalize_min_max(50, 0, 100) == 0.5
    assert normalize_min_max(150, 0, 100) == 1.0
    assert normalize_min_max(-10, 0, 100) == 0.0
    assert normalize_min_max(50, 0, 100, invert=True) == 0.5
    assert normalize_min_max(0, 0, 100, invert=True) == 1.0
    assert normalize_min_max(None, 0, 100) == 0.0

def test_feature_normalization():
    normalizer = FeatureNormalizer()
    job = MockJob('J1', 5, 5, 30, 5) # Max priority
    asset = MockAsset('A1', 10, 0, 1.0, 0.0) # Max risk, min availability
    
    features = normalizer.prepare_job_features(job, asset)
    assert features['criticality_norm'] == 1.0
    assert features['overdue_norm'] == 0.5 # 30 / 60
    assert features['condition_score_norm'] == 0.0
    assert features['availability_impact_norm'] == 1.0 # Inverted 0.0

def test_risk_score():
    features_high_risk = {
        'failure_probability_norm': 1.0,
        'condition_score_norm': 0.0, # poor condition
        'failure_count_norm': 1.0
    }
    assert calculate_risk_score(features_high_risk) == 1.0

    features_low_risk = {
        'failure_probability_norm': 0.0,
        'condition_score_norm': 1.0, # excellent condition
        'failure_count_norm': 0.0
    }
    assert calculate_risk_score(features_low_risk) == 0.0

def test_priority_engine():
    engine = PriorityEngine()
    
    # High priority job
    job1 = MockJob('J1', 5, 5, 60, 5)
    asset1 = MockAsset('A1', 10, 0, 1.0, 0.0)
    
    # Low priority job
    job2 = MockJob('J2', 1, 1, 0, 1)
    asset2 = MockAsset('A2', 0, 100, 0.0, 1.0)
    
    ranked = engine.rank_maintenance_jobs([(job1, asset1), (job2, asset2)])
    
    assert len(ranked) == 2
    assert ranked[0]['job_id'] == 'J1'
    assert ranked[0]['priority_category'] == 'HIGH'
    assert ranked[0]['priority_score'] > 0.9
    
    assert ranked[1]['job_id'] == 'J2'
    assert ranked[1]['priority_category'] == 'LOW'
    assert ranked[1]['priority_score'] < 0.2

def test_changing_weights():
    # If we make overdue the ONLY factor
    weights = PriorityWeights(criticality=0, urgency=0, overdue=1, risk=0, availability=0, operational_impact=0)
    engine = PriorityEngine(weights=weights)
    
    job1 = MockJob('J1', 1, 1, 60, 1) # Overdue = max
    asset1 = MockAsset('A1', 0, 100, 0.0, 1.0)
    
    job2 = MockJob('J2', 5, 5, 0, 5) # Overdue = 0
    asset2 = MockAsset('A2', 10, 0, 1.0, 0.0)
    
    ranked = engine.rank_maintenance_jobs([(job1, asset1), (job2, asset2)])
    
    # J1 should win because overdue is the only weight
    assert ranked[0]['job_id'] == 'J1'
    assert ranked[0]['priority_score'] == 1.0
    assert ranked[1]['priority_score'] == 0.0
