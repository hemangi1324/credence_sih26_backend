import random
from .solution import ALNSSolution

class DestroyOperators:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def random_removal(self, sol: ALNSSolution, ratio: float = 0.2) -> ALNSSolution:
        new_sol = sol.copy()
        if not new_sol.selected_blocks:
            return new_sol
            
        num_remove = max(1, int(len(new_sol.selected_blocks) * ratio))
        remove_indices = self.rng.sample(range(len(new_sol.selected_blocks)), num_remove)
        
        removed_blocks = [new_sol.selected_blocks[i] for i in remove_indices]
        
        # Remove from selected
        new_sol.selected_blocks = [b for i, b in enumerate(new_sol.selected_blocks) if i not in remove_indices]
        
        # Extract jobs from removed blocks
        for b in removed_blocks:
            for j_id in b.get('job_ids', []):
                new_sol.unassigned_jobs.append(j_id)
                
        return new_sol

    def worst_contribution_removal(self, sol: ALNSSolution, ratio: float = 0.2) -> ALNSSolution:
        """Removes blocks that have high duration but low priority score"""
        new_sol = sol.copy()
        if not new_sol.selected_blocks:
            return new_sol
            
        def block_badness(b):
            duration = b.get('duration_min', 0)
            priority = b.get('priority_score', 0.1)
            if priority == 0: priority = 0.001
            return duration / priority # High duration, low priority = bad
            
        sorted_indices = sorted(range(len(new_sol.selected_blocks)), 
                                key=lambda i: block_badness(new_sol.selected_blocks[i]), 
                                reverse=True)
                                
        num_remove = max(1, int(len(new_sol.selected_blocks) * ratio))
        remove_indices = sorted_indices[:num_remove]
        
        removed_blocks = [new_sol.selected_blocks[i] for i in remove_indices]
        new_sol.selected_blocks = [b for i, b in enumerate(new_sol.selected_blocks) if i not in remove_indices]
        
        for b in removed_blocks:
            for j_id in b.get('job_ids', []):
                new_sol.unassigned_jobs.append(j_id)
                
        return new_sol

    def high_train_impact_removal(self, sol: ALNSSolution, ratio: float = 0.2) -> ALNSSolution:
        new_sol = sol.copy()
        if not new_sol.selected_blocks:
            return new_sol
            
        sorted_indices = sorted(range(len(new_sol.selected_blocks)), 
                                key=lambda i: new_sol.selected_blocks[i].get('train_impact', 0.0), 
                                reverse=True)
                                
        num_remove = max(1, int(len(new_sol.selected_blocks) * ratio))
        remove_indices = sorted_indices[:num_remove]
        
        removed_blocks = [new_sol.selected_blocks[i] for i in remove_indices]
        new_sol.selected_blocks = [b for i, b in enumerate(new_sol.selected_blocks) if i not in remove_indices]
        
        for b in removed_blocks:
            for j_id in b.get('job_ids', []):
                new_sol.unassigned_jobs.append(j_id)
                
        return new_sol
