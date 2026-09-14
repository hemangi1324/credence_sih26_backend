# Time-Dependent Train Impact (TDSP)

This document outlines the design and implementation of the Time-Dependent Shortest Path (TDSP) Train Impact module (Step 6).

## 1. Why TDSP is Needed
Railway maintenance blocks inherently consume track capacity. While Step 5's CP-SAT solver uses a fast static timetable overlap heuristic to approximate disruption, it doesn't account for complex train dynamics: a train might wait for a block to clear, or it might be rerouted through a different path. TDSP precisely estimates this true operational delay by simulating the train's journey through a time-evolving network.

## 2. Difference Between Normal Shortest Path and TDSP
In a static Dijkstra algorithm, edge costs (travel times) are constant. In **TDSP**, the availability of an edge depends on the arrival time at the node. If a train reaches a track while it is blocked for maintenance, the effective cost of traversing that track increases because the train must wait until the block ends (if waiting is permitted).

## 3. Graph Representation
- **Nodes**: Railway Stations (`station_id`).
- **Edges**: Track Sections connecting stations (`track_id`, `normal_travel_time_min`).
The synthetic data provides basic station-to-station connections.

## 4. State Representation
The state in the pathfinder is represented as:
`(arrival_time_min, current_station_id, path_so_far)`
The priority queue expands the earliest arrival time first.

## 5. Time-Dependent Edge Availability
A Candidate Block defines an unavailable interval for a specific track. 
For a candidate spanning `[start, end]` on `track_id`:
- A train arriving at the starting station at time $t$ cannot traverse `track_id` if $start \le t < end$. 
- Note: This prototype abstracts the exact train position to the track section level.

## 6. Waiting Model
Trains are allowed to wait at a station for a block to clear. 
If a train arrives at $t$ and the block ends at $end$:
- The departure time becomes $end$.
- The delay accumulates. 
If the accumulated delay exceeds `train.max_allowed_delay_min`, the route is marked as **infeasible**.

## 7. Rerouting Model
If a train is flagged with `can_be_rerouted = True` and waiting causes delay, the TDSP pathfinder searches for alternative sequences of tracks. If an alternative path arrives earlier than waiting on the original path, the train is marked as **rerouted**.
*Limitation: Not all physical paths are operationally valid (due to signalling/interlocking). The prototype routes based strictly on the provided track adjacency.*

## 8. Train Priority Weighting
The raw delay (in minutes) is recorded objectively. However, the `impact_score` formula incorporates `train_priority`:
`impact_score = (delay_min * waiting_penalty) + (delay_min * priority * priority_weight)`
This means delaying an Express Train (high priority) generates a significantly worse impact score than delaying a Freight Train.

## 9. Difference from Step 5
- **Step 5 (CP-SAT)**: Simple binary/linear overlap check inside the constraint solver. Fast, but rigid.
- **Step 6 (TDSP)**: Advanced simulation allowing rerouting and waiting.

## 10. Future Integration (ALNS)
Currently, TDSP evaluates the schedule after CP-SAT finishes. In future steps, an Adaptive Large Neighborhood Search (ALNS) metaheuristic will iteratively generate schedules, pass them to TDSP to get exact train delays, and then use that feedback to intelligently destroy and repair the schedule.

## 11. Limitations Caused by Synthetic Data
The current synthetic timetable is sparsely populated and deliberately spaced out. Therefore, running the TDSP engine against the actual scheduled candidate blocks may result in `0` affected trains, correctly indicating that the generated maintenance windows successfully avoided all scheduled traffic. Unit tests with forced conflicts validate the routing logic independently of the sparse mock data.
