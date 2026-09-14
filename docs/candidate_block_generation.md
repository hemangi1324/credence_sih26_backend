# Candidate Block Generation

This document outlines the design and implementation of Candidate Block Generation (Step 4).

## 1. What a Candidate Block Is
A candidate block is a proposed, feasible railway possession that combines one or more maintenance jobs into a single executable window. It contains spatial bounds (track and chainage), proposed time bounds, duration, and a list of involved jobs and departments.

## 2. Why Candidate Blocks are Needed
Instead of feeding raw, independent jobs to a CP-SAT scheduling solver (which scales exponentially), candidate generation creates a finite pool of rigorously validated options. The optimizer then only has to select non-overlapping candidates that cover all jobs. A candidate block must satisfy hard physical, safety, and operational constraints before it ever reaches the optimizer.

## 3. Spatial Compatibility
Two jobs are spatially compatible if:
- They are located on the same `track_id`.
- The total span (maximum end chainage minus minimum start chainage) does not exceed `MAX_COMBINE_DISTANCE_KM` (currently configured to 5.0km).
*Note: Because the synthetic data does not contain physical LINESTRING geometry, spatial overlap across different tracks (e.g. adjacent tracks at a station) cannot be robustly verified and is conservatively rejected.*

## 4. Temporal Compatibility
Given that the synthetic data does not declare which maintenance tasks can safely execute in parallel within the same physical space, the engine makes a **conservative sequential assumption**. The combined block duration is the sum of all individual job durations plus the maximum required safety buffer. If this duration fits within an acceptable operational window (<12 hours), they are temporally compatible.

## 5. Resource Compatibility
Since we assume sequential execution within the combined block, resources (like engineering crews or machinery) are naturally shared without overlap. Therefore, multi-job combinations are resource-compatible as long as the resource exists for the total duration. (If parallel execution were enabled, quantity checks would strictly enforce `quantity >= required`).

## 6. Safety Compatibility
Safety is strictly governed by the `compatibility_rules` table:
- Explicit rules define whether asset types (e.g. OHE and Rail) can be maintained simultaneously in the same block.
- **Conservative Rejection**: If no explicit rule exists between two different asset types, the combination is rejected to ensure absolute safety.
- If a rule allows combination but specifies `isolation_required = True`, the candidate block is flagged accordingly.

## 7. Operational Compatibility
Candidate blocks must not conflict with known hard constraints in `track_availability`. If a track is already flagged as blocked during the proposed window, the candidate is rejected.

## 8. Cross-Department Coordination
The system explicitly allows cross-department combining (e.g., Engineering, S&T, and TRD working under one power/traffic block) provided all compatibility rules pass. The `departments_involved` field logs this capability for later reporting.

## 9. Dependency Handling
The generator inherently respects dependencies. By processing combinations, if Job B is grouped with Job A and depends on it, they execute sequentially in the block. Detailed temporal scheduling (ensuring A completes before B across different blocks) is reserved for the CP-SAT layer.

## 10. Single-Job vs Multi-Job Candidates
Every valid maintenance job request automatically generates a **Single-Job Candidate**. This ensures the solver always has a fallback option if multi-job combinations are un-schedulable due to train traffic. Multi-job candidates (up to `MAX_JOBS_PER_CANDIDATE = 3`) are generated as alternative options.

## 11. Candidate Generation Strategy
1. **Group**: Jobs are grouped by `track_id`.
2. **Sort**: Jobs are sorted by their priority score from Step 3.
3. **Subset**: Subsets of size 1 to 3 are generated.
4. **Filter**: Every subset is passed through the 5 compatibility filters.
5. **Construct**: Surviving subsets are instantiated as `CandidateBlock` objects.

## 12. Synthetic-Data Limitations
- Spatial coordinates for complex junctions are missing; hence cross-track blocks cannot be safely generated.
- Detailed parallel-work safety physics are omitted; hence sequential duration sum is used.

## 13. Why CP-SAT is NOT Implemented in this Step
Candidate Block Generation creates the *search space of feasible options*. CP-SAT (Constraint Programming) is an optimization technique that will search this space to find the *best combination* of candidates that maximizes priority while minimizing train delay. Trying to do both simultaneously without generating candidates first results in intractable mathematical models.
