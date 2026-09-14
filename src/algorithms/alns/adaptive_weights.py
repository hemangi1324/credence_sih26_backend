import random
from typing import List, Dict

class OperatorManager:
    def __init__(self, op_names: List[str], config):
        self.config = config
        self.op_names = op_names
        self.weights = {name: 1.0 for name in op_names}
        self.scores = {name: 0.0 for name in op_names}
        self.counts = {name: 0 for name in op_names}
        
        self.stats = {name: {'selections': 0, 'feasible': 0, 'accepted': 0, 'improvements': 0, 'global_best': 0} for name in op_names}

    def select_operator(self, rng: random.Random) -> str:
        total_weight = sum(self.weights.values())
        if total_weight == 0:
            return rng.choice(self.op_names)
            
        r = rng.uniform(0, total_weight)
        cumulative = 0.0
        for name, weight in self.weights.items():
            cumulative += weight
            if r <= cumulative:
                self.counts[name] += 1
                self.stats[name]['selections'] += 1
                return name
        return self.op_names[-1]

    def update_score(self, op_name: str, reward_type: str):
        if reward_type == 'global_best':
            self.scores[op_name] += self.config.score_global_best
            self.stats[op_name]['global_best'] += 1
        elif reward_type == 'improvement':
            self.scores[op_name] += self.config.score_improvement
            self.stats[op_name]['improvements'] += 1
        elif reward_type == 'accepted':
            self.scores[op_name] += self.config.score_accepted
            self.stats[op_name]['accepted'] += 1
        elif reward_type == 'feasible':
            self.stats[op_name]['feasible'] += 1
        else:
            self.scores[op_name] += self.config.score_rejected

    def decay_weights(self):
        for name in self.op_names:
            if self.counts[name] > 0:
                avg_score = self.scores[name] / self.counts[name]
                self.weights[name] = (1 - self.config.weight_decay) * self.weights[name] + self.config.weight_decay * avg_score
            self.scores[name] = 0.0
            self.counts[name] = 0
