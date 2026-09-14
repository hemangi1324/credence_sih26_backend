class ALNSConfig:
    def __init__(self):
        # SA params
        self.initial_temperature = 1000.0
        self.cooling_rate = 0.95
        self.minimum_temperature = 1.0
        self.max_iterations = 100
        self.random_seed = 42

        # Objective weights
        self.w_train = 1.0        # priority-weighted train impact
        self.w_defer = 1000.0     # deferred priority sum (huge penalty)
        self.w_blocks = 5.0       # number of blocks
        self.w_possession = 1.0   # possession minutes
        self.w_maintenance = 500.0 # scheduled priority sum (reward)

        # Adaptive weights scoring
        self.score_global_best = 10.0
        self.score_improvement = 5.0
        self.score_accepted = 2.0
        self.score_rejected = 0.0
        self.weight_decay = 0.8
