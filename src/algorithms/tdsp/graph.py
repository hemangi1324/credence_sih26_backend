from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class Edge:
    track_id: str
    from_station: str
    to_station: str
    normal_travel_time_min: int
    speed_limit_kmph: float
    distance_km: float

class RailwayGraph:
    def __init__(self, stations: list, track_sections: list):
        self.stations = {s.station_id: s for s in stations}
        
        # adjacency list: from_station -> list of Edges
        self.edges = {}
        # track mapping: track_id -> Edge
        self.tracks = {}
        
        for ts in track_sections:
            # We assume bidirectional for the prototype unless direction explicitly says 'UP'/'DOWN'
            # The synthetic data might have UP/DOWN tracks connecting the same stations.
            
            # Forward edge
            e_fwd = Edge(
                track_id=ts.track_id,
                from_station=ts.from_station_id,
                to_station=ts.to_station_id,
                normal_travel_time_min=ts.normal_travel_time_min,
                speed_limit_kmph=ts.speed_limit_kmph,
                distance_km=ts.distance_km
            )
            self._add_edge(e_fwd)
            
            # If the data relies on directionality, we should respect it.
            # But the prompt says: "If a reverse direction exists in the data, treat it according to the actual track records."
            # So we only add the directed edge from `from_station_id` to `to_station_id` based on the database.
            
    def _add_edge(self, edge: Edge):
        if edge.from_station not in self.edges:
            self.edges[edge.from_station] = []
        self.edges[edge.from_station].append(edge)
        self.tracks[edge.track_id] = edge
        
    def get_outgoing_edges(self, station_id: str) -> List[Edge]:
        return self.edges.get(station_id, [])

    def get_edge(self, track_id: str) -> Optional[Edge]:
        return self.tracks.get(track_id)
