from .solution import ALNSSolution
from .config import ALNSConfig

def calculate_objective(sol: ALNSSolution, config: ALNSConfig) -> float:
    cost = 0.0
    
    # Minimize train impact
    cost += config.w_train * sol.priority_weighted_train_impact
    
    # Minimize deferrals
    cost += config.w_defer * sol.deferred_priority_sum
    
    # Minimize blocks and possession time
    cost += config.w_blocks * sol.num_blocks
    cost += config.w_possession * sol.possession_minutes
    
    # Maximize scheduled maintenance (subtract from cost)
    cost -= config.w_maintenance * sol.scheduled_priority_sum
    
    sol.objective_cost = cost
    return cost
