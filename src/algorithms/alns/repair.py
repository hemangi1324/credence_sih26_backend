from .solution import ALNSSolution
from .feasibility import FeasibilityRepair
import random

class RepairOperators:
    def __init__(self, feasibility: FeasibilityRepair, rng: random.Random):
        self.feasibility = feasibility
        self.rng = rng

    def greedy_priority_repair(self, sol: ALNSSolution) -> tuple[ALNSSolution, bool]:
        """Repairs by configuring the underlying solver to heavily favor priority over all else"""
        original_prio = self.feasibility.scheduler.config.maintenance_priority_weight
        self.feasibility.scheduler.config.maintenance_priority_weight = 100000 
        new_sol, feasible = self.feasibility.repair_and_validate(sol)
        self.feasibility.scheduler.config.maintenance_priority_weight = original_prio
        return new_sol, feasible

    def least_impact_repair(self, sol: ALNSSolution) -> tuple[ALNSSolution, bool]:
        """Repairs by configuring the underlying solver to heavily penalize train impact"""
        original_impact = self.feasibility.scheduler.config.train_impact_weight
        self.feasibility.scheduler.config.train_impact_weight = 100000
        new_sol, feasible = self.feasibility.repair_and_validate(sol)
        self.feasibility.scheduler.config.train_impact_weight = original_impact
        return new_sol, feasible

    def default_cp_sat_repair(self, sol: ALNSSolution) -> tuple[ALNSSolution, bool]:
        """Standard balanced repair"""
        return self.feasibility.repair_and_validate(sol)
