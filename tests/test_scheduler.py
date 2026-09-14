import pytest
from src.algorithms.scheduler.scheduler import CPSATScheduler, Config
from src.algorithms.blocks.models import CandidateBlock

class MockJob:
    def __init__(self, job_id, priority):
        self.job_id = job_id
        self.priority_score = priority

class MockDep:
    def __init__(self, pred, succ):
        self.job_id_predecessor = pred
        self.job_id_successor = succ

class MockTrackAvail:
    def __init__(self, t_id, status, start, end):
        self.track_id = t_id
        self.status = status
        self.time_start = start
        self.time_end = end

def test_scheduler_one_job():
    jobs = [MockJob("J1", 0.9)]
    cand = CandidateBlock(
        candidate_id="C1", track_id="T1", chainage_start_km=0.0, chainage_end_km=1.0,
        proposed_start=None, proposed_end=None, duration_min=60,
        job_ids=["J1"], departments=["Eng"], request_ids=["R1"],
        priority_score=0.9, isolation_required=False
    )
    
    sched = CPSATScheduler(jobs, [cand], [], [], [], [], [], [])
    res = sched.solve()
    
    assert res['solver_status'] == 'OPTIMAL'
    assert len(res['selected_blocks']) == 1
    assert len(res['deferred_jobs']) == 0

def test_scheduler_conflict():
    # Two candidates on same track, duration 600 each. Total horizon 1440.
    # If they are 800 each, they can't both fit (800+800 = 1600 > 1440).
    jobs = [MockJob("J1", 0.9), MockJob("J2", 0.8)]
    cand1 = CandidateBlock(
        candidate_id="C1", track_id="T1", chainage_start_km=0.0, chainage_end_km=1.0,
        proposed_start=None, proposed_end=None, duration_min=800,
        job_ids=["J1"], departments=["Eng"], request_ids=["R1"],
        priority_score=0.9, isolation_required=False
    )
    cand2 = CandidateBlock(
        candidate_id="C2", track_id="T1", chainage_start_km=2.0, chainage_end_km=3.0,
        proposed_start=None, proposed_end=None, duration_min=800,
        job_ids=["J2"], departments=["Eng"], request_ids=["R2"],
        priority_score=0.8, isolation_required=False
    )
    
    sched = CPSATScheduler(jobs, [cand1, cand2], [], [], [], [], [], [])
    res = sched.solve()
    
    assert res['solver_status'] == 'OPTIMAL'
    assert len(res['selected_blocks']) == 1
    assert len(res['deferred_jobs']) == 1
    # J1 should be scheduled because of higher priority
    assert res['selected_blocks'][0]['candidate_id'] == "C1"
    assert res['deferred_jobs'][0]['job_id'] == "J2"

def test_scheduler_dependency():
    jobs = [MockJob("J1", 0.5), MockJob("J2", 0.5)]
    cand1 = CandidateBlock(
        candidate_id="C1", track_id="T1", chainage_start_km=0.0, chainage_end_km=1.0,
        proposed_start=None, proposed_end=None, duration_min=100,
        job_ids=["J1"], departments=["Eng"], request_ids=["R1"],
        priority_score=0.5, isolation_required=False
    )
    cand2 = CandidateBlock(
        candidate_id="C2", track_id="T2", chainage_start_km=0.0, chainage_end_km=1.0,
        proposed_start=None, proposed_end=None, duration_min=100,
        job_ids=["J2"], departments=["Eng"], request_ids=["R2"],
        priority_score=0.5, isolation_required=False
    )
    
    deps = [MockDep("J1", "J2")]
    
    sched = CPSATScheduler(jobs, [cand1, cand2], deps, [], [], [], [], [])
    res = sched.solve()
    
    assert res['solver_status'] == 'OPTIMAL'
    b1 = next(b for b in res['selected_blocks'] if b['candidate_id'] == 'C1')
    b2 = next(b for b in res['selected_blocks'] if b['candidate_id'] == 'C2')
    
    # End of C1 must be <= Start of C2
    # time to int minutes:
    def t_to_m(t): return t.hour * 60 + t.minute
    assert t_to_m(b1['end_time']) <= t_to_m(b2['start_time'])
