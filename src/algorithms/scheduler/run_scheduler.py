import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import pandas as pd
from src.algorithms.priority.priority_engine import PriorityEngine
from src.algorithms.blocks.generator import generate_candidate_blocks
from src.algorithms.scheduler.scheduler import CPSATScheduler

class MockObj:
    def __init__(self, d):
        self.__dict__.update(d)

def main():
    data_dir = os.path.join(os.path.dirname(__file__), '../../../data')
    
    print("Loading data from database (CSV mock)...")
    jobs_df = pd.read_csv(os.path.join(data_dir, '07_maintenance_jobs.csv')).where(pd.notnull, None)
    assets_df = pd.read_csv(os.path.join(data_dir, '06_assets.csv')).where(pd.notnull, None)
    requests_df = pd.read_csv(os.path.join(data_dir, '11_block_requests.csv')).where(pd.notnull, None)
    rules_df = pd.read_csv(os.path.join(data_dir, '09_compatibility_rules.csv')).where(pd.notnull, None)
    avail_df = pd.read_csv(os.path.join(data_dir, '12_track_availability.csv')).where(pd.notnull, None)
    job_res_df = pd.read_csv(os.path.join(data_dir, '13_job_resources.csv')).where(pd.notnull, None)
    deps_df = pd.read_csv(os.path.join(data_dir, '08_maintenance_dependencies.csv')).where(pd.notnull, None)
    resources_df = pd.read_csv(os.path.join(data_dir, '10_resources.csv')).where(pd.notnull, None)
    
    # Train timetable might not exist yet, handle gracefully
    try:
        trains_df = pd.read_csv(os.path.join(data_dir, '04_trains.csv')).where(pd.notnull, None)
        timetable_df = pd.read_csv(os.path.join(data_dir, '05_train_timetable.csv')).where(pd.notnull, None)
        trains = [MockObj(t) for t in trains_df.to_dict('records')]
        timetable = [MockObj(t) for t in timetable_df.to_dict('records')]
    except Exception:
        trains = []
        timetable = []
    
    # 1. Run Priority Engine
    jobs_with_assets = []
    for _, row in jobs_df.iterrows():
        j = row.to_dict()
        a_df = assets_df[assets_df['asset_id'] == j['asset_id']]
        if not a_df.empty:
            jobs_with_assets.append((MockObj(j), MockObj(a_df.iloc[0].to_dict())))
            
    engine = PriorityEngine()
    ranked_jobs = engine.rank_maintenance_jobs(jobs_with_assets)
    
    # We need to map priority_score back to our MockObj jobs for the scheduler
    priority_map = {item['job_id']: item['priority_score'] for item in ranked_jobs}
    
    jobs = []
    for j_dict in jobs_df.to_dict('records'):
        obj = MockObj(j_dict)
        obj.priority_score = priority_map.get(obj.job_id, 0.5)
        jobs.append(obj)
    
    # 2. Generate Candidate Blocks
    requests = [MockObj(r) for r in requests_df.to_dict('records')]
    assets = [MockObj(a) for a in assets_df.to_dict('records')]
    rules = [MockObj(r) for r in rules_df.to_dict('records')]
    availabilities = [] # Simplification for prototype
    job_resources = [MockObj(r) for r in job_res_df.to_dict('records')]
    dependencies = [MockObj(r) for r in deps_df.to_dict('records')]
    resources = [MockObj(r) for r in resources_df.to_dict('records')]
    
    candidates = generate_candidate_blocks(
        ranked_jobs, requests, assets, rules, availabilities, job_resources, dependencies
    )
    
    print("\n==================================================")
    print("CP-SAT RAILWAY BLOCK SCHEDULER")
    print("==================================================")
    print(f"Jobs: {len(jobs)}")
    print(f"Candidates: {len(candidates)}")
    print("Solving...\n")
    
    scheduler = CPSATScheduler(
        jobs=jobs,
        candidates=candidates,
        dependencies=dependencies,
        resources=resources,
        job_resources=job_resources,
        track_avail=availabilities,
        train_timetable=timetable,
        trains=trains
    )
    
    result = scheduler.solve()
    
    print(f"Solver Status: {result['solver_status']}")
    print(f"Solve Time: {result['solve_time_seconds']:.2f} sec\n")
    
    if result['solver_status'] in ['OPTIMAL', 'FEASIBLE']:
        metrics = result['metrics']
        print(f"Scheduled Jobs: {metrics['scheduled_jobs']}")
        print(f"Deferred Jobs: {metrics['deferred_jobs']}")
        print(f"Selected Blocks: {metrics['total_blocks']}")
        
        # Calculate high priority stats (score > 0.7)
        high_prio_jobs = [j for j in jobs if j.priority_score > 0.7]
        high_prio_scheduled = sum(1 for j in jobs if j.priority_score > 0.7 and not any(d['job_id'] == j.job_id for d in result['deferred_jobs']))
        print(f"High Priority Scheduled: {high_prio_scheduled}/{len(high_prio_jobs)}")
        
        print(f"\nTotal Possession: {metrics['total_possession_minutes']} min")
        print(f"Train Impact: {metrics['total_train_impact']:.2f}")
        
        print("\nSELECTED BLOCKS")
        print("-" * 50)
        for b in result['selected_blocks'][:10]: # Print top 10
            print(f"Block {b['candidate_id']}")
            print(f"Track: {b['track_id']} ({b['chainage_start']}km - {b['chainage_end']}km)")
            print(f"Time: {b['start_time']} - {b['end_time']} ({b['duration_min']}m)")
            print(f"Jobs: {','.join(b['job_ids'])}")
            print(f"Departments: {','.join(b['departments'])}")
            print(f"Priority: {b['priority_score']:.4f}")
            print(f"Train Impact: {b['train_impact']}")
            print("")
            
        print("DEFERRED JOBS")
        print("-" * 50)
        for d in result['deferred_jobs'][:10]:
            print(f"{d['job_id']} (Priority: {d['priority_score']:.4f})")
            print(f"Reason: {d['reason']}\n")
    else:
        print("Model is INFEASIBLE or UNKNOWN.")

if __name__ == "__main__":
    main()
