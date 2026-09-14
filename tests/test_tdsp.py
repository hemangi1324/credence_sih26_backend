import pytest
import datetime
from src.algorithms.tdsp.graph import RailwayGraph, Edge
from src.algorithms.tdsp.pathfinder import TimeDependentPathFinder
from src.algorithms.tdsp.evaluator import TrainRouteEvaluator, Config
from src.algorithms.tdsp.models import TrainJourneyBaseline

class MockObj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def setup_test_graph():
    stations = [
        MockObj(station_id='A'),
        MockObj(station_id='B'),
        MockObj(station_id='C'),
        MockObj(station_id='D')
    ]
    tracks = [
        MockObj(track_id='T_AB', from_station_id='A', to_station_id='B', normal_travel_time_min=10, speed_limit_kmph=100, distance_km=10),
        MockObj(track_id='T_BD', from_station_id='B', to_station_id='D', normal_travel_time_min=10, speed_limit_kmph=100, distance_km=10),
        MockObj(track_id='T_AC', from_station_id='A', to_station_id='C', normal_travel_time_min=8, speed_limit_kmph=100, distance_km=10),
        MockObj(track_id='T_CD', from_station_id='C', to_station_id='D', normal_travel_time_min=12, speed_limit_kmph=100, distance_km=10)
    ]
    return RailwayGraph(stations, tracks)

def setup_test_evaluator(graph):
    trains = [
        MockObj(train_id='TR1', origin_station_id='A', destination_station_id='D', max_allowed_delay_min=30, can_be_rerouted=True, train_priority=2)
    ]
    timetable = [
        MockObj(train_id='TR1', sequence_no=1, track_id='T_AB', entry_time='10:00', exit_time='10:10'),
        MockObj(train_id='TR1', sequence_no=2, track_id='T_BD', entry_time='10:10', exit_time='10:20')
    ]
    return TrainRouteEvaluator(graph, trains, timetable, Config())

def test_no_block():
    graph = setup_test_graph()
    evaluator = setup_test_evaluator(graph)
    
    # Empty block intervals
    res = evaluator.evaluate_train_impact('TR1', {}, 'CAND1')
    assert res.delay_min == 0
    assert res.rerouted is False
    assert res.route_feasible is True

def test_blocked_with_waiting():
    graph = setup_test_graph()
    evaluator = setup_test_evaluator(graph)
    
    # Block T_BD from 10:05 to 10:30
    blocks = {'T_BD': [(10*60 + 5, 10*60 + 30)]}
    
    # Train is not allowed to reroute for this test
    evaluator.trains['TR1'].can_be_rerouted = False
    
    res = evaluator.evaluate_train_impact('TR1', blocks, 'CAND1')
    
    # Train reaches T_BD at 10:10. Block is active until 10:30.
    # Train waits until 10:30, travels 10 min -> arrives 10:40
    # Baseline arrival is 10:20. Delay = 20 min.
    assert res.delay_min == 20
    assert res.rerouted is False
    assert res.route_feasible is True
    assert res.reason == "Delayed by 20 min due to waiting."

def test_blocked_with_rerouting():
    graph = setup_test_graph()
    evaluator = setup_test_evaluator(graph)
    
    # Block T_BD from 10:05 to 10:30
    blocks = {'T_BD': [(10*60 + 5, 10*60 + 30)]}
    
    # Train CAN reroute
    evaluator.trains['TR1'].can_be_rerouted = True
    
    res = evaluator.evaluate_train_impact('TR1', blocks, 'CAND1')
    
    # Reroute path: A -> C -> D. Travel time = 8 + 12 = 20 min.
    # Departure 10:00 -> Arrival 10:20. Baseline arrival 10:20. Delay = 0 min.
    assert res.delay_min == 0
    assert res.rerouted is True
    assert res.route_feasible is True

def test_blocked_exceeds_delay():
    graph = setup_test_graph()
    evaluator = setup_test_evaluator(graph)
    
    # Block T_BD from 10:05 to 12:00 (120 mins)
    blocks = {'T_BD': [(10*60 + 5, 12*60 + 0)]}
    
    # Train cannot reroute
    evaluator.trains['TR1'].can_be_rerouted = False
    evaluator.trains['TR1'].max_allowed_delay_min = 30
    
    res = evaluator.evaluate_train_impact('TR1', blocks, 'CAND1')
    
    # Waiting causes delay > 30 min -> Infeasible
    assert res.route_feasible is False
    assert res.delay_exceeded is True
    assert res.reason == "Train route is infeasible or exceeds max allowed delay."

def test_evaluate_schedule():
    graph = setup_test_graph()
    evaluator = setup_test_evaluator(graph)
    evaluator.trains['TR1'].can_be_rerouted = False
    
    schedule_blocks = [
        {'track_id': 'T_BD', 'start_time': '10:05', 'end_time': '10:30'}
    ]
    
    sched_res = evaluator.evaluate_schedule('SCHED_1', schedule_blocks)
    
    assert sched_res.total_trains_evaluated == 1
    assert sched_res.affected_trains == 1
    assert sched_res.total_delay_min == 20
    assert sched_res.max_delay_min == 20
