import heapq
from typing import Dict, List, Optional, Tuple
from .graph import RailwayGraph

class TimeDependentPathFinder:
    def __init__(self, graph: RailwayGraph):
        self.graph = graph

    def find_shortest_path(self, origin: str, destination: str, start_time_min: int, blocked_intervals: Dict[str, List[Tuple[int, int]]], wait_allowed: bool) -> Tuple[Optional[List[str]], int]:
        """
        Runs Time-Dependent Dijkstra.
        blocked_intervals: track_id -> list of (block_start_min, block_end_min)
        Returns:
            (List of track_ids, arrival_time_min)
            If no path is found, returns (None, -1).
        """
        # Priority queue: (arrival_time, current_station, path_so_far)
        # path_so_far = list of track_ids
        pq = [(start_time_min, origin, [])]
        
        # Visited: station_id -> earliest arrival time
        # We only expand a node if we reach it earlier than previously known
        visited = {}
        
        while pq:
            current_time, current_station, path = heapq.heappop(pq)
            
            if current_station == destination:
                return path, current_time
                
            if current_station in visited and visited[current_station] <= current_time:
                continue
                
            visited[current_station] = current_time
            
            for edge in self.graph.get_outgoing_edges(current_station):
                next_station = edge.to_station
                
                # Check if this edge is blocked at the current_time
                # A block is active if block_start <= current_time < block_end
                # (If it equals block_end, the block is over)
                
                earliest_departure = current_time
                edge_blocks = blocked_intervals.get(edge.track_id, [])
                
                blocked = False
                for b_start, b_end in edge_blocks:
                    # If we would enter the edge while it's blocked, or during the block
                    if b_start <= earliest_departure < b_end:
                        if wait_allowed:
                            # We can wait until the block ends
                            earliest_departure = max(earliest_departure, b_end)
                        else:
                            blocked = True
                            break
                            
                if blocked:
                    continue
                    
                arrival_time = earliest_departure + edge.normal_travel_time_min
                
                # Only push if we haven't found a strictly better way to `next_station`
                if next_station not in visited or arrival_time < visited[next_station]:
                    heapq.heappush(pq, (arrival_time, next_station, path + [edge.track_id]))
                    
        return None, -1
