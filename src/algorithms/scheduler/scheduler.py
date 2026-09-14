import time
from ortools.sat.python import cp_model
from typing import List, Dict, Any

from .utils import time_to_minutes, minutes_to_time
from .train_conflicts import estimate_train_impact

class Config:
    def __init__(self, time_limit_seconds=30, num_workers=4, random_seed=42):
        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers
        self.random_seed = random_seed
        
        self.maintenance_priority_weight = 1000
        self.train_impact_weight = 1
        self.defer_penalty = 5000
        self.block_count_penalty = 10
        self.duration_penalty = 1

class CPSATScheduler:
    def __init__(self, jobs, candidates, dependencies, resources, job_resources, track_avail, train_timetable, trains, config=None):
        self.jobs = jobs
        self.candidates = candidates
        self.dependencies = dependencies
        self.resources = resources
        self.job_resources = job_resources
        self.track_avail = track_avail
        self.train_timetable = train_timetable
        self.trains_dict = {t.train_id: t for t in trains}
        
        self.config = config or Config()
        self.model = cp_model.CpModel()
        
        self.horizon = 1440 # 24 hours in minutes
        
        # Variables
        self.x_c = {} # candidate selected
        self.start_c = {} # candidate start
        self.end_c = {} # candidate end
        self.interval_c = {} # candidate interval
        
        self.d_j = {} # job deferred
        
        self.job_to_candidates = {j.job_id: [] for j in jobs}
        
        # Build mappings
        for c in candidates:
            for j_id in c.job_ids:
                if j_id in self.job_to_candidates:
                    self.job_to_candidates[j_id].append(c)

    def build_model(self):
        self._create_variables()
        self._add_job_coverage_constraints()
        self._add_temporal_and_track_constraints()
        self._add_dependency_constraints()
        self._add_resource_constraints()
        self._create_objective()

    def _create_variables(self):
        for c in self.candidates:
            cid = c.candidate_id
            self.x_c[cid] = self.model.NewBoolVar(f"x_{cid}")
            
            # Start and End domains
            s_min = 0
            s_max = self.horizon - c.duration_min
            
            # If there's a proposed window, constrain to it.
            # Step 4 outputs proposed_start / end based on requested bounds.
            if c.proposed_start:
                s_min = max(s_min, time_to_minutes(c.proposed_start))
            if c.proposed_end:
                s_max = min(s_max, time_to_minutes(c.proposed_end) - c.duration_min)
                
            if s_min > s_max:
                s_max = s_min # Let the solver prove infeasibility or we just bound it safely
                
            self.start_c[cid] = self.model.NewIntVar(s_min, s_max, f"start_{cid}")
            self.end_c[cid] = self.model.NewIntVar(s_min + c.duration_min, s_max + c.duration_min, f"end_{cid}")
            
            self.interval_c[cid] = self.model.NewOptionalIntervalVar(
                self.start_c[cid], c.duration_min, self.end_c[cid], self.x_c[cid], f"interval_{cid}"
            )
            
        for j in self.jobs:
            self.d_j[j.job_id] = self.model.NewBoolVar(f"d_{j.job_id}")

    def _add_job_coverage_constraints(self):
        # sum(x_c for c containing j) + d_j == 1
        for j in self.jobs:
            cands = self.job_to_candidates[j.job_id]
            self.model.Add(sum(self.x_c[c.candidate_id] for c in cands) + self.d_j[j.job_id] == 1)

    def _add_temporal_and_track_constraints(self):
        # NoOverlap for candidates on the same track
        track_to_candidates = {}
        for c in self.candidates:
            track_to_candidates.setdefault(c.track_id, []).append(c)
            
        for track_id, cands in track_to_candidates.items():
            if len(cands) > 1:
                # We enforce NoOverlap constraint on intervals for the same track
                self.model.AddNoOverlap([self.interval_c[c.candidate_id] for c in cands])
                
        # Track Availability Hard Constraints
        # A candidate must not overlap with a known blocked period.
        for c in self.candidates:
            for avail in self.track_avail:
                if avail.track_id == c.track_id and avail.status.startswith('blocked'):
                    b_start = time_to_minutes(avail.time_start.time())
                    b_end = time_to_minutes(avail.time_end.time())
                    
                    if b_end <= b_start: 
                        b_end = 1440 # crosses midnight simplification
                    
                    # If x_c is true, interval cannot overlap [b_start, b_end]
                    # This means either end_c <= b_start OR start_c >= b_end
                    
                    # We can use boolean logic
                    before_block = self.model.NewBoolVar(f"{c.candidate_id}_before_{b_start}")
                    after_block = self.model.NewBoolVar(f"{c.candidate_id}_after_{b_end}")
                    
                    self.model.Add(self.end_c[c.candidate_id] <= b_start).OnlyEnforceIf(before_block)
                    self.model.Add(self.start_c[c.candidate_id] >= b_end).OnlyEnforceIf(after_block)
                    
                    # Either before or after if selected
                    self.model.AddBoolOr([before_block, after_block]).OnlyEnforceIf(self.x_c[c.candidate_id])

    def _add_dependency_constraints(self):
        # A -> B means A finishes before B starts
        # Since A and B might have multiple candidate options, and they might be deferred
        
        # d_j_A or d_j_B == 1 means we don't enforce (if deferred, it's irrelevant or we can just say if both are scheduled)
        for dep in self.dependencies:
            A = dep.job_id_predecessor
            B = dep.job_id_successor
            
            cands_A = self.job_to_candidates.get(A, [])
            cands_B = self.job_to_candidates.get(B, [])
            
            if not cands_A or not cands_B:
                continue
                
            # If both are selected, end of selected A <= start of selected B
            # Since exact 1 candidate is selected for A (if not deferred), we can sum their start/ends
            
            # Create variables for the actual start/end of A and B
            end_A_val = self.model.NewIntVar(0, self.horizon, f"end_val_{A}")
            start_B_val = self.model.NewIntVar(0, self.horizon, f"start_val_{B}")
            
            # Map candidate variables to job variables
            for cA in cands_A:
                self.model.Add(end_A_val == self.end_c[cA.candidate_id]).OnlyEnforceIf(self.x_c[cA.candidate_id])
            for cB in cands_B:
                self.model.Add(start_B_val == self.start_c[cB.candidate_id]).OnlyEnforceIf(self.x_c[cB.candidate_id])
                
            # Enforce end_A <= start_B only if both are not deferred
            both_scheduled = self.model.NewBoolVar(f"both_scheduled_{A}_{B}")
            self.model.AddBoolAnd([self.d_j[A].Not(), self.d_j[B].Not()]).OnlyEnforceIf(both_scheduled)
            self.model.AddBoolOr([self.d_j[A], self.d_j[B]]).OnlyEnforceIf(both_scheduled.Not())
            
            self.model.Add(end_A_val <= start_B_val).OnlyEnforceIf(both_scheduled)

    def _add_resource_constraints(self):
        # To strictly enforce resource capacities without knowing exactly when candidates start,
        # we can use cumulative constraints.
        # But we only need to constrain candidates that use the same resource.
        
        resource_capacity = {r.resource_id: r.quantity for r in self.resources if r.quantity is not None}
        
        cands_by_resource = {}
        for c in self.candidates:
            res_used = set()
            for j_id in c.job_ids:
                for jr in self.job_resources:
                    if jr.job_id == j_id:
                        res_used.add(jr.resource_id)
            for res_id in res_used:
                cands_by_resource.setdefault(res_id, []).append(c.candidate_id)
                
        for res_id, cid_list in cands_by_resource.items():
            if res_id not in resource_capacity:
                continue
            capacity = resource_capacity[res_id]
            # Add Cumulative constraint for intervals of these candidates
            intervals = [self.interval_c[cid] for cid in cid_list]
            demands = [1 for _ in cid_list] # Assuming each job demands 1 unit.
            
            self.model.AddCumulative(intervals, demands, capacity)

    def _create_objective(self):
        # We want to MAXIMIZE priority, MINIMIZE deferrals, MINIMIZE blocks
        objective_terms = []
        
        job_priority = {j.job_id: getattr(j, 'priority_score', 0.5) for j in self.jobs}
        
        # 1. Maintenance Priority Reward
        # For each job, if it's scheduled (d_j == 0), we get a reward
        for j in self.jobs:
            scheduled_var = self.d_j[j.job_id].Not()
            reward = int(job_priority[j.job_id] * self.config.maintenance_priority_weight)
            objective_terms.append(reward * scheduled_var)
            
        # 2. Deferral Penalty
        for j in self.jobs:
            penalty = int(self.config.defer_penalty * (1.0 + job_priority[j.job_id]))
            objective_terms.append(-penalty * self.d_j[j.job_id])
            
        # 3. Block Count Penalty
        for c in self.candidates:
            objective_terms.append(-self.config.block_count_penalty * self.x_c[c.candidate_id])
            
        # 4. Duration Penalty
        for c in self.candidates:
            objective_terms.append(-self.config.duration_penalty * c.duration_min * self.x_c[c.candidate_id])
            
        # 5. Train Impact Penalty (Approximation using average impact across the candidate's static window)
        # We pre-calculate a static train impact based on the proposed start/end to keep the model linear.
        # CP-SAT doesn't easily support variable-driven lookups without complex element constraints.
        for c in self.candidates:
            if c.proposed_start and c.proposed_end:
                impact = estimate_train_impact(c.track_id, c.proposed_start, c.proposed_end, self.train_timetable, self.trains_dict)
                penalty = int(impact * self.config.train_impact_weight)
                objective_terms.append(-penalty * self.x_c[c.candidate_id])

        self.model.Maximize(sum(objective_terms))

    def solve(self):
        self.build_model()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.time_limit_seconds
        solver.parameters.num_search_workers = self.config.num_workers
        solver.parameters.random_seed = self.config.random_seed
        
        start_time = time.time()
        status = solver.Solve(self.model)
        solve_time = time.time() - start_time
        
        return self._format_result(solver, status, solve_time)

    def _format_result(self, solver, status, solve_time):
        status_name = solver.StatusName(status)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            selected_blocks = []
            for c in self.candidates:
                if solver.Value(self.x_c[c.candidate_id]):
                    s_val = solver.Value(self.start_c[c.candidate_id])
                    e_val = solver.Value(self.end_c[c.candidate_id])
                    
                    impact = 0.0
                    if c.proposed_start and c.proposed_end:
                        impact = estimate_train_impact(c.track_id, c.proposed_start, c.proposed_end, self.train_timetable, self.trains_dict)
                    
                    block = {
                        "candidate_id": c.candidate_id,
                        "track_id": c.track_id,
                        "chainage_start": c.chainage_start_km,
                        "chainage_end": c.chainage_end_km,
                        "start_time": minutes_to_time(s_val),
                        "end_time": minutes_to_time(e_val),
                        "duration_min": c.duration_min,
                        "job_ids": c.job_ids,
                        "departments": c.departments,
                        "priority_score": c.priority_score,
                        "train_impact": impact,
                        "isolation_required": c.isolation_required
                    }
                    selected_blocks.append(block)
                    
            deferred_jobs = []
            for j in self.jobs:
                if solver.Value(self.d_j[j.job_id]):
                    # Provide a basic explanation
                    cands = self.job_to_candidates[j.job_id]
                    if not cands:
                        reason = "Deferred because no valid candidate blocks were generated."
                    else:
                        reason = "Deferred because available windows conflict with scheduled train traffic or higher-priority maintenance."
                        
                    deferred_jobs.append({
                        "job_id": j.job_id,
                        "priority_score": getattr(j, 'priority_score', 0.0),
                        "reason": reason
                    })
                    
            return {
                "solver_status": status_name,
                "objective_value": solver.ObjectiveValue(),
                "best_bound": solver.BestObjectiveBound(),
                "solve_time_seconds": solve_time,
                "selected_blocks": selected_blocks,
                "deferred_jobs": deferred_jobs,
                "metrics": {
                    "total_jobs": len(self.jobs),
                    "scheduled_jobs": len(self.jobs) - len(deferred_jobs),
                    "deferred_jobs": len(deferred_jobs),
                    "total_blocks": len(selected_blocks),
                    "total_possession_minutes": sum(b["duration_min"] for b in selected_blocks),
                    "total_train_impact": sum(b["train_impact"] for b in selected_blocks)
                }
            }
        else:
            return {
                "solver_status": status_name,
                "objective_value": None,
                "best_bound": None,
                "solve_time_seconds": solve_time,
                "selected_blocks": [],
                "deferred_jobs": [{"job_id": j.job_id, "priority_score": getattr(j, 'priority_score', 0.0), "reason": "Solver infeasible"} for j in self.jobs],
                "metrics": {}
            }
