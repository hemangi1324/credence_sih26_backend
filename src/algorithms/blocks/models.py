from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import datetime

@dataclass
class CandidateBlock:
    candidate_id: str
    track_id: str
    chainage_start_km: float
    chainage_end_km: float
    proposed_start: datetime.time
    proposed_end: datetime.time
    duration_min: int
    job_ids: List[str]
    departments: List[str]
    request_ids: List[str]
    priority_score: float
    isolation_required: bool
    
    # Compatibility Flags
    spatial_compatible: bool = True
    temporal_compatible: bool = True
    resource_compatible: bool = True
    safety_compatible: bool = True
    operational_compatible: bool = True
    
    compatibility_reasons: List[str] = field(default_factory=list)
    
    @property
    def is_valid(self):
        return (self.spatial_compatible and self.temporal_compatible and 
                self.resource_compatible and self.safety_compatible and 
                self.operational_compatible)
