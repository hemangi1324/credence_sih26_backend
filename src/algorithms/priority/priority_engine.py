from typing import Dict, List, Any
from .config import PriorityWeights, PriorityThresholds, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS
from .features import FeatureNormalizer
from .risk_score import calculate_risk_score

class PriorityEngine:
    def __init__(self, 
                 weights: PriorityWeights = DEFAULT_WEIGHTS,
                 thresholds: PriorityThresholds = DEFAULT_THRESHOLDS):
        self.weights = weights
        self.thresholds = thresholds
        self.normalizer = FeatureNormalizer()

    def evaluate_job(self, job, asset) -> Dict[str, Any]:
        """
        Evaluates a single maintenance job and its asset to calculate the priority score.
        """
        # 1. Feature Preparation
        features = self.normalizer.prepare_job_features(job, asset)
        
        # 2. Risk Score
        risk_score = calculate_risk_score(features)
        
        # 3. Calculate Feature Contributions
        # Asset Availability Impact: combines raw availability impact with criticality and risk
        # A critical asset with high risk and poor availability should trigger immediate action.
        availability_component = features['availability_impact_norm']
        
        contributions = {
            "criticality": features['criticality_norm'] * self.weights.criticality,
            "urgency": features['urgency_norm'] * self.weights.urgency,
            "overdue": features['overdue_norm'] * self.weights.overdue,
            "risk": risk_score * self.weights.risk,
            "availability": availability_component * self.weights.availability,
            "operational_impact": features['operational_impact_norm'] * self.weights.operational_impact
        }
        
        # 4. Priority Score
        priority_score = sum(contributions.values())
        priority_score = max(0.0, min(priority_score, 1.0))
        
        # 5. Priority Category
        if priority_score >= self.thresholds.high:
            category = "HIGH"
        elif priority_score >= self.thresholds.medium:
            category = "MEDIUM"
        else:
            category = "LOW"
            
        return {
            "job_id": job.job_id,
            "asset_id": asset.asset_id,
            "department": job.department,
            "risk_score": round(risk_score, 4),
            "priority_score": round(priority_score, 4),
            "priority_category": category,
            "feature_contributions": {k: round(v, 4) for k, v in contributions.items()}
        }

    def rank_maintenance_jobs(self, jobs_with_assets: List[tuple]) -> List[Dict[str, Any]]:
        """
        Takes a list of tuples (MaintenanceJob, Asset) and returns ranked results.
        Preserves all job_id and asset_id information for future scheduling algorithms.
        """
        results = []
        for job, asset in jobs_with_assets:
            if job.job_status.lower() not in ['completed', 'cancelled']:
                res = self.evaluate_job(job, asset)
                results.append(res)
                
        # Sort descending by priority_score
        results.sort(key=lambda x: x['priority_score'], reverse=True)
        return results
