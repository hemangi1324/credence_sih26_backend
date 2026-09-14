# Adaptive Large Neighborhood Search (ALNS)

This document outlines the ALNS Optimization Layer (Step 7).

## 1. Core Principle
ALNS acts as a metaheuristic search layer wrapped around the existing CP-SAT optimizer and TDSP Train Impact Evaluator.
- **CP-SAT** guarantees hard constraints (dependencies, overlapping tracks, exact-once assignment).
- **ALNS** navigates the neighborhood space to find combinations that minimize Train Delay and Maximize Priority.
- **TDSP** accurately scores the train impact of any feasible solution found.

## 2. Solution Representation
The state is kept in `ALNSSolution` which tracks:
- `selected_blocks` (list of CandidateBlock dictionaries)
- `deferred_jobs`
- Derived metrics like `objective_cost`, `train_delay`, `priority_weighted_train_impact`, and `possession_minutes`.

## 3. Destroy Operators
Destroy operators strip a portion (e.g. 10-30%) of blocks from the current solution to create an unassigned void.
- **Random Removal**: Randomly removes blocks to encourage exploration.
- **Worst Contribution Removal**: Removes blocks that consume high possession time but deliver very low maintenance priority.
- **High Train Impact Removal**: Removes blocks directly identified by the TDSP evaluator as causing massive cascading train delays.

## 4. Repair Operators & Feasibility
Instead of inventing heuristic insertion logic that could violate critical safety constraints (e.g. interlocking dependencies), ALNS uses the original CP-SAT engine for **Neighborhood Repair**.
- The preserved blocks are constrained as hard locks (`x_c == 1`).
- The CP-SAT engine is given a tiny time-limit (1 second) to optimally fit the stripped/unassigned jobs back into the remaining timeline using available diverse candidates.
- **Repair Strategies** adjust the CP-SAT objective weights right before repair:
  - **Greedy Priority Repair**: Forces the repair step to aggressively prefer high-priority jobs.
  - **Least Impact Repair**: Forces the repair step to aggressively reject assignments that overlap with known trains.

## 5. Acceptance Criterion (Simulated Annealing)
We use a standard Simulated Annealing acceptance curve.
- Better solutions are always accepted.
- Worse solutions are accepted with probability $e^{-\Delta / T}$.
- Temperature decays via a cooling rate.

## 6. Adaptive Operator Weights
Operators that discover a new global best, or consistently improve the solution, receive positive reinforcement scores. Their selection probability adapts dynamically during the run, making the algorithm explainable.

## 7. Synthetic Data Limitation
The current synthetic dataset contains only 38 single-job candidates and zero diverse multi-job candidates. Because candidate diversity is precisely 1-to-1, CP-SAT trivially proves the exact global optimum on the very first run. Consequently, ALNS will correctly report **No Improvement**, as the search space has already been perfectly solved. Small unit test fixtures demonstrate the search behavior independently of the synthetic data sparsity.
