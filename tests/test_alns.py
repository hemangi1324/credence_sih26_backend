import pytest
import random
from src.algorithms.alns.solution import ALNSSolution
from src.algorithms.alns.destroy import DestroyOperators
from src.algorithms.alns.acceptance import accept_solution
from src.algorithms.alns.adaptive_weights import OperatorManager
from src.algorithms.alns.config import ALNSConfig

def test_alns_solution_copy():
    sol = ALNSSolution()
    sol.selected_blocks = [{'candidate_id': 'C1'}]
    sol.objective_cost = 100.0
    
    sol_copy = sol.copy()
    sol_copy.selected_blocks[0]['candidate_id'] = 'C2'
    sol_copy.objective_cost = 50.0
    
    assert sol.selected_blocks[0]['candidate_id'] == 'C1'
    assert sol.objective_cost == 100.0
    assert sol_copy.selected_blocks[0]['candidate_id'] == 'C2'
    assert sol_copy.objective_cost == 50.0

def test_random_removal():
    rng = random.Random(42)
    destroy = DestroyOperators(rng)
    
    sol = ALNSSolution()
    sol.selected_blocks = [{'candidate_id': 'C1', 'job_ids': ['J1']}, 
                           {'candidate_id': 'C2', 'job_ids': ['J2']},
                           {'candidate_id': 'C3', 'job_ids': ['J3']}]
                           
    # 33% of 3 = 1 block removed
    new_sol = destroy.random_removal(sol, ratio=0.33)
    
    assert len(new_sol.selected_blocks) == 2
    assert len(new_sol.unassigned_jobs) == 1

def test_worst_contribution_removal():
    rng = random.Random(42)
    destroy = DestroyOperators(rng)
    
    sol = ALNSSolution()
    # Badness = duration / priority. High badness is removed first.
    # C1: 100 / 0.1 = 1000
    # C2: 50 / 0.9 = 55.5
    # C3: 10 / 1.0 = 10
    sol.selected_blocks = [{'candidate_id': 'C1', 'job_ids': ['J1'], 'duration_min': 100, 'priority_score': 0.1}, 
                           {'candidate_id': 'C2', 'job_ids': ['J2'], 'duration_min': 50, 'priority_score': 0.9},
                           {'candidate_id': 'C3', 'job_ids': ['J3'], 'duration_min': 10, 'priority_score': 1.0}]
                           
    new_sol = destroy.worst_contribution_removal(sol, ratio=0.33)
    
    assert len(new_sol.selected_blocks) == 2
    assert new_sol.unassigned_jobs == ['J1'] # C1 is worst, should be removed
    assert not any(b['candidate_id'] == 'C1' for b in new_sol.selected_blocks)

def test_high_train_impact_removal():
    rng = random.Random(42)
    destroy = DestroyOperators(rng)
    
    sol = ALNSSolution()
    sol.selected_blocks = [{'candidate_id': 'C1', 'job_ids': ['J1'], 'train_impact': 100}, 
                           {'candidate_id': 'C2', 'job_ids': ['J2'], 'train_impact': 500}, # Highest impact
                           {'candidate_id': 'C3', 'job_ids': ['J3'], 'train_impact': 0}]
                           
    new_sol = destroy.high_train_impact_removal(sol, ratio=0.33)
    
    assert len(new_sol.selected_blocks) == 2
    assert new_sol.unassigned_jobs == ['J2']
    assert not any(b['candidate_id'] == 'C2' for b in new_sol.selected_blocks)

def test_sa_acceptance():
    rng = random.Random(42)
    
    # Better solution always accepted
    assert accept_solution(100.0, 90.0, 50.0, rng) is True
    
    # Worse solution sometimes accepted based on temp
    # diff = 10, temp = 100 -> prob = exp(-0.1) = ~0.9. Should be mostly True.
    # diff = 100, temp = 1 -> prob = exp(-100) = ~0. Should be False.
    assert accept_solution(100.0, 200.0, 1.0, rng) is False

def test_adaptive_weights():
    config = ALNSConfig()
    manager = OperatorManager(['op1', 'op2'], config)
    
    manager.update_score('op1', 'global_best') # +10
    manager.update_score('op2', 'rejected')    # +0
    
    manager.counts['op1'] = 1
    manager.counts['op2'] = 1
    
    manager.decay_weights()
    
    # op1 should have higher weight than op2
    assert manager.weights['op1'] > manager.weights['op2']
