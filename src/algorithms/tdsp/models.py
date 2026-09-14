import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class TrainJourneyBaseline:
    train_id: str
    origin: str
    destination: str
    scheduled_departure: datetime.time
    scheduled_arrival: datetime.time
    planned_duration_min: int
    track_sequence: List[str]

@dataclass
class TrainImpactResult:
    train_id: str
    candidate_id: str  # or 'schedule_id'
    baseline_arrival: datetime.time
    new_arrival: datetime.time
    delay_min: int
    rerouted: bool
    route_feasible: bool
    max_allowed_delay_min: int
    delay_exceeded: bool
    train_priority: int
    impact_score: float
    reason: str

@dataclass
class CandidateImpactResult:
    candidate_id: str
    affected_trains: List[str] = field(default_factory=list)
    affected_train_count: int = 0
    total_delay_min: int = 0
    max_delay_min: int = 0
    rerouted_train_count: int = 0
    infeasible_train_count: int = 0
    priority_weighted_delay: float = 0.0
    impact_score: float = 0.0
    train_details: List[TrainImpactResult] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "candidate_id": self.candidate_id,
            "affected_train_count": self.affected_train_count,
            "total_delay_min": self.total_delay_min,
            "max_delay_min": self.max_delay_min,
            "rerouted_train_count": self.rerouted_train_count,
            "infeasible_train_count": self.infeasible_train_count,
            "priority_weighted_delay": self.priority_weighted_delay,
            "impact_score": self.impact_score
        }

@dataclass
class ScheduleImpactResult:
    schedule_id: str
    total_trains_evaluated: int = 0
    affected_trains: int = 0
    total_delay_min: int = 0
    average_delay_min: float = 0.0
    max_delay_min: int = 0
    rerouted_trains: int = 0
    infeasible_trains: int = 0
    priority_weighted_delay: float = 0.0
    total_impact_score: float = 0.0
    train_results: List[TrainImpactResult] = field(default_factory=list)
