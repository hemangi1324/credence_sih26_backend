# CP-SAT Railway Block Scheduler

This document outlines the design and implementation of the CP-SAT Optimization module (Step 5).

## 1. Objective
The scheduler consumes validated `CandidateBlock` options generated in Step 4 and determines the optimal subset of blocks to execute. It explicitly balances maintenance priority against operational disruption and hard capacity constraints. 

## 2. Model Formulation
The problem is formulated as a Constraint Satisfaction and Optimization Problem using Google OR-Tools (CP-SAT).

### Decision Variables
- $x_c \in \{0, 1\}$: Equals 1 if candidate block $c$ is selected.
- $s_c \in [0, 1440]$: Integer variable representing the start time of candidate block $c$ (in minutes from midnight).
- $e_c \in [0, 1440]$: Integer variable representing the end time. $e_c = s_c + duration_c$.
- $I_c$: Optional interval variable spanning $[s_c, e_c]$, active only if $x_c = 1$.
- $d_j \in \{0, 1\}$: Equals 1 if maintenance job $j$ is deferred.

### Hard Constraints
1. **Job Coverage**: Every job $j$ must either be scheduled exactly once or explicitly deferred.
   $$ \sum_{c \ni j} x_c + d_j = 1 \quad \forall j \in Jobs $$
2. **Temporal / Track Conflicts**: For any two candidates $c_1, c_2$ on the same track, their intervals $I_{c_1}$ and $I_{c_2}$ must not overlap (using `AddNoOverlap`).
3. **Track Availability**: A selected candidate's interval cannot overlap with a known hard-blocked track window.
4. **Dependencies**: If Job B depends on Job A, and neither is deferred:
   $$ \text{End of selected candidate for A} \le \text{Start of selected candidate for B} $$
5. **Resource Capacity**: For any limited resource $R$, the concurrent demand of all selected candidates utilizing $R$ must never exceed its capacity (using `AddCumulative`).

### Objective Function (Soft Constraints)
The model maximizes a weighted sum of rewards and penalties:
$$ \text{Maximize} \quad \sum_{j} (Priority_j \cdot W_{prio} \cdot (1 - d_j)) - \sum_{j} (Penalty_{defer} \cdot d_j) - \sum_{c} (Impact_c \cdot W_{impact} \cdot x_c) - \sum_{c} (W_{blocks} \cdot x_c) $$

Where:
- $W_{prio}$: Reward for scheduling jobs.
- $Penalty_{defer}$: Severe penalty for deferring jobs (scales with priority, making high-priority jobs harder to defer).
- $Impact_c$: Train impact penalty (based on timetable overlap).
- $W_{blocks}$: Minor penalty to minimize unnecessary fragmentation of blocks.

## 3. Train Impact Approximation
In this prototype, train impact is not a full Time-Dependent Shortest Path (TDSP) network delay simulator. Instead, it measures naive spatial-temporal overlap:
- For a candidate block on track T spanning $[start, end]$.
- If a scheduled train on track T has an expected window $[entry, exit]$ that overlaps with $[start, end]$.
- $Impact += TrainPriority \times 10$.
This provides a gradient for the solver to prefer maintenance windows that avoid high-priority expresses. (A future Step will replace this with TDSP).

## 4. Deferral Mechanism
The solver does *not* force an infeasible schedule. If traffic, dependencies, or spatial conflicts make scheduling a job impossible within the horizon, $d_j$ becomes 1. The output explicitly details *why* a job was deferred (e.g., "Deferred because available windows conflict with scheduled train traffic or higher-priority maintenance.").

## 5. Synthetic-Data Limitations
- With the current synthetic dataset, there are 38 independent single-job candidates and extensive track overlap. The solver correctly identifies that accommodating all 38 jobs on overlapping tracks within 24 hours is physically impossible. Therefore, it optimally schedules ~24 non-conflicting high-priority jobs and explicitly defers the remaining ~14 low-priority conflicting jobs.
- The train timetable data is sparse in the mock, resulting in mostly 0.0 train impact scores. Real data will heavily activate the train conflict penalty.

## 6. Solver Interpretation
- **OPTIMAL**: The solver found the mathematically proven best schedule under the configured weights.
- **FEASIBLE**: A valid schedule was found, but the time limit expired before optimality could be proven.
- **INFEASIBLE**: Contradictory hard constraints exist. (Rare, given the deferral variables $d_j$).
