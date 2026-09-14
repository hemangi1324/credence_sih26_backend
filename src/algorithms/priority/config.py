from dataclasses import dataclass

@dataclass
class PriorityWeights:
    criticality: float = 0.25
    urgency: float = 0.15
    overdue: float = 0.10
    risk: float = 0.25
    availability: float = 0.10
    operational_impact: float = 0.15
    
    def __post_init__(self):
        total = sum([self.criticality, self.urgency, self.overdue, self.risk, self.availability, self.operational_impact])
        # Normalize weights to sum to 1.0 just in case
        self.criticality /= total
        self.urgency /= total
        self.overdue /= total
        self.risk /= total
        self.availability /= total
        self.operational_impact /= total

@dataclass
class PriorityThresholds:
    high: float = 0.70
    medium: float = 0.40

# Default Prototype configuration (ILLUSTRATIVE PURPOSES ONLY)
DEFAULT_WEIGHTS = PriorityWeights()
DEFAULT_THRESHOLDS = PriorityThresholds()
