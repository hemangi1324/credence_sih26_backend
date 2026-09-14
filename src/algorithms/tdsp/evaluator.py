import datetime
from typing import List, Dict, Tuple, Any, Optional
from .models import TrainJourneyBaseline, TrainImpactResult, CandidateImpactResult, ScheduleImpactResult
from .graph import RailwayGraph
from .pathfinder import TimeDependentPathFinder

def time_to_min(t):
    if isinstance(t, str):
        try:
            parts = t.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        except:
            return 0
    if not t: return 0
    return t.hour * 60 + t.minute

def min_to_time(m):
    m = int(m) % 1440
    return datetime.time(m // 60, m % 60)

class Config:
    def __init__(self):
        self.waiting_penalty = 1.0
        self.rerouting_penalty = 5.0
        self.infeasibility_penalty = 1000.0
        self.priority_weight = 10.0

class TrainRouteEvaluator:
    def __init__(self, graph: RailwayGraph, trains: list, train_timetable: list, config: Config = None):
        self.graph = graph
        self.trains = {t.train_id: t for t in trains}
        self.timetable = train_timetable
        self.config = config or Config()
        self.pathfinder = TimeDependentPathFinder(graph)
        
        # Group timetable by train_id and sort by sequence
        self.train_routes = {}
        for row in self.timetable:
            if row.train_id not in self.train_routes:
                self.train_routes[row.train_id] = []
            self.train_routes[row.train_id].append(row)
            
        for t_id in self.train_routes:
            self.train_routes[t_id].sort(key=lambda x: getattr(x, 'sequence_no', 0))

    def get_baseline_journey(self, train_id: str) -> Optional[TrainJourneyBaseline]:
        route = self.train_routes.get(train_id)
        if not route:
            return None
            
        train = self.trains.get(train_id)
        if not train:
            return None
            
        first_leg = route[0]
        last_leg = route[-1]
        
        dep_time = time_to_min(first_leg.entry_time)
        arr_time = time_to_min(last_leg.exit_time)
        
        if arr_time < dep_time:
            arr_time += 1440 # Simple cross-midnight fix for prototype
            
        duration = arr_time - dep_time
        track_seq = [leg.track_id for leg in route]
        
        return TrainJourneyBaseline(
            train_id=train_id,
            origin=train.origin_station_id,
            destination=train.destination_station_id,
            scheduled_departure=min_to_time(dep_time),
            scheduled_arrival=min_to_time(arr_time),
            planned_duration_min=duration,
            track_sequence=track_seq
        )

    def evaluate_train_impact(self, train_id: str, blocked_intervals: Dict[str, List[Tuple[int, int]]], context_id: str) -> TrainImpactResult:
        baseline = self.get_baseline_journey(train_id)
        if not baseline:
            return None
            
        train = self.trains.get(train_id)
        max_delay = getattr(train, 'max_allowed_delay_min', 60) or 60
        can_reroute = getattr(train, 'can_be_rerouted', False)
        priority = getattr(train, 'train_priority', 1) or 1
        
        # First, check if the baseline route is affected
        affected = False
        current_time = time_to_min(baseline.scheduled_departure)
        
        simulated_arrival = current_time
        route_feasible = True
        
        for track_id in baseline.track_sequence:
            edge = self.graph.get_edge(track_id)
            if not edge:
                route_feasible = False
                break
                
            # Check blocks
            edge_blocks = blocked_intervals.get(track_id, [])
            for b_start, b_end in edge_blocks:
                if b_start <= current_time < b_end:
                    affected = True
                    current_time = max(current_time, b_end) # waiting
                    
            current_time += edge.normal_travel_time_min
            simulated_arrival = current_time
            
        if not affected:
            return TrainImpactResult(
                train_id=train_id,
                candidate_id=context_id,
                baseline_arrival=baseline.scheduled_arrival,
                new_arrival=baseline.scheduled_arrival,
                delay_min=0,
                rerouted=False,
                route_feasible=True,
                max_allowed_delay_min=max_delay,
                delay_exceeded=False,
                train_priority=priority,
                impact_score=0.0,
                reason="No overlap with maintenance block."
            )
            
        # The route was affected. We calculate delay.
        baseline_arr_min = time_to_min(baseline.scheduled_arrival)
        # Handle cross-midnight for baseline
        if baseline_arr_min < time_to_min(baseline.scheduled_departure):
            baseline_arr_min += 1440
            
        delay = simulated_arrival - baseline_arr_min
        
        wait_delay = delay if route_feasible else float('inf')
        
        reroute_delay = float('inf')
        reroute_arrival = None
        
        if can_reroute:
            path, r_arr = self.pathfinder.find_shortest_path(
                origin=baseline.origin,
                destination=baseline.destination,
                start_time_min=time_to_min(baseline.scheduled_departure),
                blocked_intervals=blocked_intervals,
                wait_allowed=True
            )
            if path is not None:
                reroute_delay = r_arr - baseline_arr_min
                reroute_arrival = r_arr
                
        # Compare options
        best_delay = min(wait_delay, reroute_delay)
        
        if best_delay > max_delay:
            # Infeasible
            impact_score = self.config.infeasibility_penalty + (priority * self.config.priority_weight * max_delay)
            return TrainImpactResult(
                train_id=train_id,
                candidate_id=context_id,
                baseline_arrival=baseline.scheduled_arrival,
                new_arrival=min_to_time(simulated_arrival),
                delay_min=delay if route_feasible else max_delay,
                rerouted=False,
                route_feasible=False,
                max_allowed_delay_min=max_delay,
                delay_exceeded=True,
                train_priority=priority,
                impact_score=impact_score,
                reason="Train route is infeasible or exceeds max allowed delay."
            )
            
        if reroute_delay < wait_delay:
            # Rerouting is better
            impact_score = (reroute_delay * self.config.waiting_penalty) + self.config.rerouting_penalty + (reroute_delay * priority * self.config.priority_weight)
            return TrainImpactResult(
                train_id=train_id,
                candidate_id=context_id,
                baseline_arrival=baseline.scheduled_arrival,
                new_arrival=min_to_time(reroute_arrival),
                delay_min=reroute_delay,
                rerouted=True,
                route_feasible=True,
                max_allowed_delay_min=max_delay,
                delay_exceeded=False,
                train_priority=priority,
                impact_score=impact_score,
                reason=f"Rerouted path found with {reroute_delay} min delay."
            )
        else:
            # Waiting is better or equal
            impact_score = (wait_delay * self.config.waiting_penalty) + (wait_delay * priority * self.config.priority_weight)
            return TrainImpactResult(
                train_id=train_id,
                candidate_id=context_id,
                baseline_arrival=baseline.scheduled_arrival,
                new_arrival=min_to_time(simulated_arrival),
                delay_min=wait_delay,
                rerouted=False,
                route_feasible=True,
                max_allowed_delay_min=max_delay,
                delay_exceeded=False,
                train_priority=priority,
                impact_score=impact_score,
                reason=f"Delayed by {wait_delay} min due to waiting."
            )

    def evaluate_schedule(self, schedule_id: str, blocks: list) -> ScheduleImpactResult:
        # blocks is a list of dicts with 'track_id', 'start_time', 'end_time'
        blocked_intervals = {}
        for b in blocks:
            tid = b.get('track_id')
            s_min = time_to_min(b.get('start_time') or b.get('proposed_start'))
            e_min = time_to_min(b.get('end_time') or b.get('proposed_end'))
            if s_min > e_min: e_min += 1440
            
            if tid not in blocked_intervals:
                blocked_intervals[tid] = []
            blocked_intervals[tid].append((s_min, e_min))
            
        result = ScheduleImpactResult(schedule_id=schedule_id)
        
        for t_id in self.train_routes:
            impact = self.evaluate_train_impact(t_id, blocked_intervals, schedule_id)
            if impact:
                result.total_trains_evaluated += 1
                if impact.delay_min > 0 or not impact.route_feasible:
                    result.affected_trains += 1
                    result.total_delay_min += impact.delay_min
                    result.max_delay_min = max(result.max_delay_min, impact.delay_min)
                    if impact.rerouted:
                        result.rerouted_trains += 1
                    if not impact.route_feasible:
                        result.infeasible_trains += 1
                        
                    result.priority_weighted_delay += (impact.delay_min * impact.train_priority)
                    result.total_impact_score += impact.impact_score
                    result.train_results.append(impact)
                    
        if result.affected_trains > 0:
            result.average_delay_min = result.total_delay_min / result.affected_trains
            
        return result
