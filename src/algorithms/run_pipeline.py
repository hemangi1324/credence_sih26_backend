import sys
import os
import json
import traceback

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import pandas as pd
from src.algorithms.priority.priority_engine import PriorityEngine
from src.algorithms.blocks.generator import generate_candidate_blocks
from src.algorithms.scheduler.scheduler import CPSATScheduler
from src.algorithms.tdsp.graph import RailwayGraph
from src.algorithms.tdsp.evaluator import TrainRouteEvaluator

class MockObj:
    def __init__(self, d):
        self.__dict__.update(d)
        
    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

def main():
    try:
        data_dir = os.path.join(os.path.dirname(__file__), '../../data')
        
        # Load Data
        jobs_df = pd.read_csv(os.path.join(data_dir, '07_maintenance_jobs.csv')).where(pd.notnull, None)
        assets_df = pd.read_csv(os.path.join(data_dir, '06_assets.csv')).where(pd.notnull, None)
        requests_df = pd.read_csv(os.path.join(data_dir, '11_block_requests.csv')).where(pd.notnull, None)
        rules_df = pd.read_csv(os.path.join(data_dir, '09_compatibility_rules.csv')).where(pd.notnull, None)
        avail_df = pd.read_csv(os.path.join(data_dir, '12_track_availability.csv')).where(pd.notnull, None)
        job_res_df = pd.read_csv(os.path.join(data_dir, '13_job_resources.csv')).where(pd.notnull, None)
        deps_df = pd.read_csv(os.path.join(data_dir, '08_maintenance_dependencies.csv')).where(pd.notnull, None)
        resources_df = pd.read_csv(os.path.join(data_dir, '10_resources.csv')).where(pd.notnull, None)
        stations_df = pd.read_csv(os.path.join(data_dir, '01_stations.csv')).where(pd.notnull, None)
        tracks_df = pd.read_csv(os.path.join(data_dir, '02_track_sections.csv')).where(pd.notnull, None)
        trains_df = pd.read_csv(os.path.join(data_dir, '04_trains.csv')).where(pd.notnull, None)
        timetable_df = pd.read_csv(os.path.join(data_dir, '05_train_timetable.csv')).where(pd.notnull, None)

        trains = [MockObj(t) for t in trains_df.to_dict('records')]
        timetable = [MockObj(t) for t in timetable_df.to_dict('records')]
        stations = [MockObj(s) for s in stations_df.to_dict('records')]
        tracks = [MockObj(t) for t in tracks_df.to_dict('records')]

        # Priority
        jobs_with_assets = []
        for _, row in jobs_df.iterrows():
            j = row.to_dict()
            a_df = assets_df[assets_df['asset_id'] == j['asset_id']]
            if not a_df.empty:
                jobs_with_assets.append((MockObj(j), MockObj(a_df.iloc[0].to_dict())))
                
        engine = PriorityEngine()
        ranked_jobs = engine.rank_maintenance_jobs(jobs_with_assets)
        priority_map = {item['job_id']: item['priority_score'] for item in ranked_jobs}
        
        jobs = []
        for j_dict in jobs_df.to_dict('records'):
            obj = MockObj(j_dict)
            obj.priority_score = priority_map.get(obj.job_id, 0.5)
            jobs.append(obj)
            
        requests = [MockObj(r) for r in requests_df.to_dict('records')]
        assets = [MockObj(a) for a in assets_df.to_dict('records')]
        rules = [MockObj(r) for r in rules_df.to_dict('records')]
        availabilities = []
        job_resources = [MockObj(r) for r in job_res_df.to_dict('records')]
        dependencies = [MockObj(r) for r in deps_df.to_dict('records')]
        resources = [MockObj(r) for r in resources_df.to_dict('records')]
        
        # Scheduler & Candidate Generator
        # Redirect stdout to avoid breaking JSON
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        
        candidates = generate_candidate_blocks(
            ranked_jobs, requests, assets, rules, availabilities, job_resources, dependencies
        )
        
        # Scheduler was already instantiated under redirected stdout
        scheduler = CPSATScheduler(
            jobs=jobs, candidates=candidates, dependencies=dependencies, resources=resources,
            job_resources=job_resources, track_avail=availabilities,
            train_timetable=timetable, trains=trains
        )
        sched_result = scheduler.solve()
        
        sys.stdout = old_stdout
        
        if sched_result['solver_status'] not in ['OPTIMAL', 'FEASIBLE']:
            raise Exception(f"Scheduler failed with status {sched_result['solver_status']}")
            
        selected_blocks = sched_result['selected_blocks']
        
        # Block Formatting
        formatted_blocks = []
        for b in selected_blocks:
            formatted_blocks.append({
                'id': b['candidate_id'],
                'track': b['track_id'],
                'chainageStart': b['chainage_start'],
                'chainageEnd': b['chainage_end'],
                'startTime': b['start_time'].isoformat() if hasattr(b['start_time'], 'isoformat') else str(b['start_time']),
                'endTime': b['end_time'].isoformat() if hasattr(b['end_time'], 'isoformat') else str(b['end_time']),
                'duration': b['duration_min'],
                'departments': b['departments'],
                'jobIds': b['job_ids'],
                'priority': b['priority_score'],
                'status': 'AI-OPTIMIZED',
                'trainImpact': b['train_impact']
            })

        # TDSP
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        
        graph = RailwayGraph(stations, tracks)
        evaluator = TrainRouteEvaluator(graph, trains, timetable)
        impact_result = evaluator.evaluate_schedule("SCHED-FINAL", selected_blocks)
        
        sys.stdout = old_stdout

        train_impacts = []
        for tr in impact_result.train_results:
            train_impacts.append({
                'train_id': tr.train_id,
                'baseline_arrival': tr.baseline_arrival.isoformat() if hasattr(tr.baseline_arrival, 'isoformat') else str(tr.baseline_arrival),
                'new_arrival': tr.new_arrival.isoformat() if hasattr(tr.new_arrival, 'isoformat') else str(tr.new_arrival),
                'delay': tr.delay_min,
                'rerouted': tr.rerouted,
                'feasible': tr.route_feasible,
                'impact': tr.impact_score,
                'reason': tr.reason
            })

        high_priority_jobs = sum(1 for j in jobs if j.priority_score > 0.7)

        # Output JSON
        result = {
            "status": "success",
            "summary": {
                "jobs": len(jobs),
                "high_priority_jobs": high_priority_jobs,
                "candidate_blocks": len(candidates),
                "scheduled": sched_result['metrics']['scheduled_jobs'],
                "deferred": sched_result['metrics']['deferred_jobs'],
                "selected_blocks": sched_result['metrics']['total_blocks'],
                "affected_trains": impact_result.affected_trains,
                "total_train_delay": impact_result.total_delay_min,
                "priority_weighted_impact": impact_result.priority_weighted_delay
            },
            "schedule": formatted_blocks,
            "train_impact": train_impacts,
            "deferred_jobs": sched_result['deferred_jobs'],
            "analytics": {
                "jobsByDepartment": {},
                "scheduledVsDeferred": {
                    "scheduled": sched_result['metrics']['scheduled_jobs'],
                    "deferred": sched_result['metrics']['deferred_jobs']
                }
            }
        }
        
        # Ensure we output ONLY JSON
        print(json.dumps(result))

    except Exception as e:
        sys.stdout = sys.__stdout__ # restore stdout
        error_result = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()
