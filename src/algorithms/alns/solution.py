from copy import deepcopy
from typing import List, Dict, Any, Optional

class ALNSSolution:
    def __init__(self):
        self.selected_blocks = []  # List of dicts representing candidate blocks
        self.deferred_jobs = []    # List of job dicts
        self.unassigned_jobs = []  # Jobs stripped during destroy phase, pending repair
        
        # Derived metrics
        self.scheduled_priority_sum = 0.0
        self.deferred_priority_sum = 0.0
        self.num_blocks = 0
        self.possession_minutes = 0
        
        # TDSP metrics
        self.train_delay = 0
        self.priority_weighted_train_impact = 0.0
        self.affected_trains = 0
        self.infeasible_trains = 0
        
        self.objective_cost = 0.0

    def copy(self):
        new_sol = ALNSSolution()
        new_sol.selected_blocks = deepcopy(self.selected_blocks)
        new_sol.deferred_jobs = deepcopy(self.deferred_jobs)
        new_sol.unassigned_jobs = deepcopy(self.unassigned_jobs)
        
        new_sol.scheduled_priority_sum = self.scheduled_priority_sum
        new_sol.deferred_priority_sum = self.deferred_priority_sum
        new_sol.num_blocks = self.num_blocks
        new_sol.possession_minutes = self.possession_minutes
        
        new_sol.train_delay = self.train_delay
        new_sol.priority_weighted_train_impact = self.priority_weighted_train_impact
        new_sol.affected_trains = self.affected_trains
        new_sol.infeasible_trains = self.infeasible_trains
        
        new_sol.objective_cost = self.objective_cost
        return new_sol
