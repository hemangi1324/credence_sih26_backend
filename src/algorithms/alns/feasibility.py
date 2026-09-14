from src.algorithms.scheduler.scheduler import CPSATScheduler
from typing import List, Dict, Any
from .solution import ALNSSolution
from ortools.sat.python import cp_model

class FeasibilityRepair:
    def __init__(self, jobs, candidates, dependencies, resources, job_resources, track_avail, train_timetable, trains, config=None):
        self.jobs = jobs
        self.candidates = candidates
        self.dependencies = dependencies
        self.resources = resources
        self.job_resources = job_resources
        self.track_avail = track_avail
        self.train_timetable = train_timetable
        self.trains = trains
        
        # We instantiate a base CP-SAT scheduler. 
        self.scheduler = CPSATScheduler(
            jobs, candidates, dependencies, resources, job_resources, track_avail, train_timetable, trains, config
        )

    def repair_and_validate(self, partial_sol: ALNSSolution) -> ALNSSolution:
        """
        Takes a partial ALNS solution. Fixes the selection of existing blocks,
        and uses CP-SAT to optimally place the unassigned_jobs (if possible) or defer them.
        """
        # Re-build the model fresh for this neighborhood evaluation.
        # This is fast since the synthetic graph is small, but constrained by partial_sol
        self.scheduler.model = cp_model.CpModel()
        self.scheduler.build_model()
        
        # Add constraints to lock in the partial solution
        selected_cids = {b['candidate_id'] for b in partial_sol.selected_blocks}
        
        for c in self.scheduler.candidates:
            if c.candidate_id in selected_cids:
                # Force this block to be selected
                self.scheduler.model.Add(self.scheduler.x_c[c.candidate_id] == 1)
            else:
                # To prevent CP-SAT from just doing global search and discarding our destroy operator,
                # we must restrict it. It can ONLY select candidates that cover the unassigned jobs
                # AND it cannot select candidates that cover already-scheduled jobs unless they were part of selected_blocks.
                # Actually, simpler: Any job NOT in unassigned_jobs or deferred_jobs is already scheduled by selected_blocks.
                pass
                
        # To make it a true repair step, we want to allow the solver to pick from candidates for the unassigned_jobs.
        # So we just let CP-SAT solve with the `x_c == 1` constraints for the preserved blocks.
        # This automatically validates feasibility and optimally places unassigned jobs!
        
        # Reduce time limit since it's a neighborhood search
        self.scheduler.config.time_limit_seconds = 1
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.scheduler.config.time_limit_seconds
        
        status = solver.Solve(self.scheduler.model)
        
        res = self.scheduler._format_result(solver, status, 0.0)
        
        new_sol = ALNSSolution()
        if res['solver_status'] in ['OPTIMAL', 'FEASIBLE']:
            new_sol.selected_blocks = res['selected_blocks']
            new_sol.deferred_jobs = res['deferred_jobs']
            # We don't populate unassigned_jobs, it's fully repaired.
            return new_sol, True
            
        return partial_sol, False
