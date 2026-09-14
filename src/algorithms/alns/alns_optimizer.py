import random
import time
from .solution import ALNSSolution
from .destroy import DestroyOperators
from .repair import RepairOperators
from .feasibility import FeasibilityRepair
from .objective import calculate_objective
from .acceptance import accept_solution
from .adaptive_weights import OperatorManager
from .config import ALNSConfig
from src.algorithms.tdsp.evaluator import TrainRouteEvaluator

class ALNSOptimizer:
    def __init__(self, initial_schedule, feasibility: FeasibilityRepair, tdsp_evaluator: TrainRouteEvaluator, config: ALNSConfig = None):
        self.config = config or ALNSConfig()
        self.rng = random.Random(self.config.random_seed)
        
        self.feasibility = feasibility
        self.tdsp_evaluator = tdsp_evaluator
        
        self.destroy_ops = DestroyOperators(self.rng)
        self.repair_ops = RepairOperators(feasibility, self.rng)
        
        self.destroy_manager = OperatorManager(
            ['random_removal', 'worst_contribution_removal', 'high_train_impact_removal'], 
            self.config
        )
        self.repair_manager = OperatorManager(
            ['greedy_priority_repair', 'least_impact_repair', 'default_cp_sat_repair'], 
            self.config
        )
        
        # Build initial solution
        self.current_solution = ALNSSolution()
        self.current_solution.selected_blocks = initial_schedule['selected_blocks']
        self.current_solution.deferred_jobs = initial_schedule['deferred_jobs']
        self._evaluate_solution(self.current_solution)
        
        self.best_solution = self.current_solution.copy()
        
        self.temperature = self.config.initial_temperature
        
    def _evaluate_solution(self, sol: ALNSSolution):
        # 1. Basic metrics
        sol.scheduled_priority_sum = sum(b.get('priority_score', 0) for b in sol.selected_blocks)
        sol.deferred_priority_sum = sum(j.get('priority_score', 0) for j in sol.deferred_jobs)
        sol.num_blocks = len(sol.selected_blocks)
        sol.possession_minutes = sum(b.get('duration_min', 0) for b in sol.selected_blocks)
        
        # 2. TDSP Train Impact
        tdsp_res = self.tdsp_evaluator.evaluate_schedule("ALNS-EVAL", sol.selected_blocks)
        sol.train_delay = tdsp_res.total_delay_min
        sol.priority_weighted_train_impact = tdsp_res.priority_weighted_delay
        sol.affected_trains = tdsp_res.affected_trains
        sol.infeasible_trains = tdsp_res.infeasible_trains
        
        # 3. Objective
        calculate_objective(sol, self.config)

    def optimize(self):
        print(f"\n--- ALNS Optimization Started ---")
        print(f"Initial Cost: {self.current_solution.objective_cost:.2f}")
        
        start_time = time.time()
        
        for iteration in range(self.config.max_iterations):
            # 1. Select operators
            d_name = self.destroy_manager.select_operator(self.rng)
            r_name = self.repair_manager.select_operator(self.rng)
            
            # 2. Destroy
            d_func = getattr(self.destroy_ops, d_name)
            partial_sol = d_func(self.current_solution)
            
            # 3. Repair (and Feasibility)
            r_func = getattr(self.repair_ops, r_name)
            candidate_sol, feasible = r_func(partial_sol)
            
            if not feasible:
                self.destroy_manager.update_score(d_name, 'rejected')
                self.repair_manager.update_score(r_name, 'rejected')
                self._update_temperature()
                continue
                
            self.destroy_manager.update_score(d_name, 'feasible')
            self.repair_manager.update_score(r_name, 'feasible')
            
            # 4. TDSP & Objective Eval
            self._evaluate_solution(candidate_sol)
            
            # 5. Acceptance
            accepted = accept_solution(self.current_solution.objective_cost, candidate_sol.objective_cost, self.temperature, self.rng)
            
            reward_type = 'rejected'
            
            if accepted:
                self.current_solution = candidate_sol
                reward_type = 'accepted'
                
                if candidate_sol.objective_cost < self.current_solution.objective_cost:
                    reward_type = 'improvement'
                
                if candidate_sol.objective_cost < self.best_solution.objective_cost:
                    self.best_solution = candidate_sol.copy()
                    reward_type = 'global_best'
                    print(f"Iteration {iteration}: New Best Cost {self.best_solution.objective_cost:.2f} ({d_name} + {r_name})")
            
            self.destroy_manager.update_score(d_name, reward_type)
            self.repair_manager.update_score(r_name, reward_type)
            
            # 6. Weights & Temp Update
            if iteration > 0 and iteration % 10 == 0:
                self.destroy_manager.decay_weights()
                self.repair_manager.decay_weights()
                
            self._update_temperature()
            
        end_time = time.time()
        print(f"ALNS Finished in {end_time - start_time:.2f}s")
        print(f"Final Best Cost: {self.best_solution.objective_cost:.2f}")
        return self.best_solution

    def _update_temperature(self):
        self.temperature = max(self.config.minimum_temperature, self.temperature * self.config.cooling_rate)
