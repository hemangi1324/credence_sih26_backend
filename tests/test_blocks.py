import pytest
from src.algorithms.blocks.spatial import check_spatial_compatibility
from src.algorithms.blocks.temporal import check_temporal_compatibility
from src.algorithms.blocks.resource import check_resource_compatibility
from src.algorithms.blocks.safety import check_safety_compatibility

class MockReq:
    def __init__(self, track_id, c_start, c_end, min_dur, req_date=None, start=None, end=None, p_start=None, p_end=None, safety=0):
        self.track_id = track_id
        self.chainage_start_km = c_start
        self.chainage_end_km = c_end
        self.minimum_duration_min = min_dur
        self.requested_date = req_date
        self.requested_start = start
        self.requested_end = end
        self.preferred_start = p_start
        self.preferred_end = p_end
        self.safety_buffer_min = safety

class MockJob:
    def __init__(self, asset_id):
        self.asset_id = asset_id

class MockAsset:
    def __init__(self, asset_type):
        self.asset_type = asset_type

class MockRule:
    def __init__(self, type_a, type_b, compatible, isolation):
        self.asset_type_a = type_a
        self.asset_type_b = type_b
        self.compatible = compatible
        self.isolation_required = isolation

def test_spatial_compatibility_same_track_close():
    req1 = MockReq('T1', 10.0, 12.0, 60)
    req2 = MockReq('T1', 11.0, 13.0, 60)
    ok, _ = check_spatial_compatibility([req1, req2])
    assert ok is True

def test_spatial_compatibility_same_track_far():
    req1 = MockReq('T1', 10.0, 12.0, 60)
    req2 = MockReq('T1', 20.0, 22.0, 60)
    ok, _ = check_spatial_compatibility([req1, req2])
    assert ok is False # > MAX_COMBINE_DISTANCE_KM (5.0)

def test_spatial_compatibility_different_tracks():
    req1 = MockReq('T1', 10.0, 12.0, 60)
    req2 = MockReq('T2', 10.0, 12.0, 60)
    ok, _ = check_spatial_compatibility([req1, req2])
    assert ok is False

def test_temporal_compatibility():
    req1 = MockReq('T1', 10.0, 12.0, 60, safety=10)
    req2 = MockReq('T1', 11.0, 13.0, 120, safety=15)
    ok, _, _, _, total_dur = check_temporal_compatibility([req1, req2])
    assert ok is True
    # Sequential duration: sum(min_dur) + max(safety) = 60 + 120 + 15 = 195
    assert total_dur == 195

def test_safety_compatibility_explicit_allow():
    jobs = [MockJob('A1'), MockJob('A2')]
    assets = {'A1': MockAsset('OHE'), 'A2': MockAsset('Rail')}
    rules = [MockRule('OHE', 'Rail', True, True)]
    
    ok, _, isolation = check_safety_compatibility(jobs, assets, rules)
    assert ok is True
    assert isolation is True

def test_safety_compatibility_explicit_deny():
    jobs = [MockJob('A1'), MockJob('A2')]
    assets = {'A1': MockAsset('OHE'), 'A2': MockAsset('Signal')}
    rules = [MockRule('OHE', 'Signal', False, True)]
    
    ok, _, isolation = check_safety_compatibility(jobs, assets, rules)
    assert ok is False

def test_safety_compatibility_no_rule():
    jobs = [MockJob('A1'), MockJob('A2')]
    assets = {'A1': MockAsset('OHE'), 'A2': MockAsset('Bridge')}
    rules = [] # No rules
    
    ok, _, isolation = check_safety_compatibility(jobs, assets, rules)
    assert ok is False # Conservative rejection
