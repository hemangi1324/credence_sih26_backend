import math
import random

def accept_solution(current_cost: float, candidate_cost: float, temperature: float, rng: random.Random) -> bool:
    """Simulated Annealing acceptance criterion"""
    if candidate_cost < current_cost:
        return True
    
    if temperature <= 0:
        return False
        
    diff = candidate_cost - current_cost
    prob = math.exp(-diff / temperature)
    
    return rng.random() < prob
