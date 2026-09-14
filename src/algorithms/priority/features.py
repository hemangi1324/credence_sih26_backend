def normalize_min_max(value, min_val, max_val, invert=False):
    """
    Normalizes a value to [0, 1] based on min_val and max_val.
    If invert is True, 0 becomes 1 and 1 becomes 0.
    """
    if value is None:
        return 0.0
    
    if max_val == min_val:
        return 0.0
        
    val = max(min_val, min(value, max_val))
    norm = (val - min_val) / (max_val - min_val)
    
    if invert:
        return 1.0 - norm
    return norm

class FeatureNormalizer:
    def __init__(self):
        # We define expected minimum and maximum bounds for the prototype data.
        # This prevents issues with extreme outliers in production.
        self.bounds = {
            'criticality': (1, 5),
            'urgency': (1, 5),
            'operational_impact': (1, 5),
            'overdue_days': (0, 60),  # Negative overdue handled by clamping to 0
            'failure_count': (0, 10),
            'condition_score': (0, 100),
            'failure_probability': (0.0, 1.0),
            'availability': (0.0, 1.0)
        }

    def prepare_job_features(self, job, asset):
        """
        Combines job and asset information into a standardized [0, 1] feature dictionary.
        
        Directions:
        - criticality: Higher -> Higher priority (Score 1 = Critical)
        - urgency: Higher -> Higher priority
        - overdue_days: Higher -> Higher priority (negative days are 0)
        - operational_impact: Higher -> Higher priority
        - failure_count: Higher -> Higher risk
        - condition_score: Lower -> Higher risk (Inverted during risk calculation)
        - failure_probability: Higher -> Higher risk
        - availability: Lower -> Higher availability impact (Inverted)
        """
        
        # Job features
        crit_norm = normalize_min_max(job.criticality, *self.bounds['criticality'])
        urg_norm = normalize_min_max(job.urgency, *self.bounds['urgency'])
        op_impact_norm = normalize_min_max(job.operational_impact, *self.bounds['operational_impact'])
        
        # Overdue days (clamp negative to 0)
        overdue = job.overdue_days if job.overdue_days is not None else 0
        overdue_norm = normalize_min_max(max(0, overdue), *self.bounds['overdue_days'])
        
        # Asset features
        fail_count_norm = normalize_min_max(asset.failure_count, *self.bounds['failure_count'])
        # condition score: high is good, low is bad. We keep it as is, and invert it in risk calculation
        condition_norm = normalize_min_max(asset.condition_score, *self.bounds['condition_score'])
        fail_prob_norm = normalize_min_max(asset.failure_probability, *self.bounds['failure_probability'])
        
        # Availability: low availability = high priority impact (so we invert it)
        # i.e. if availability is 0.2 (20%), the impact score is 0.8.
        availability_impact = normalize_min_max(asset.availability, *self.bounds['availability'], invert=True)

        return {
            'criticality_norm': crit_norm,
            'urgency_norm': urg_norm,
            'overdue_norm': overdue_norm,
            'operational_impact_norm': op_impact_norm,
            'failure_count_norm': fail_count_norm,
            'condition_score_norm': condition_norm,
            'failure_probability_norm': fail_prob_norm,
            'availability_impact_norm': availability_impact
        }
