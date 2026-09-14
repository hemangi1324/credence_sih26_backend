import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import pandas as pd
from src.algorithms.priority.priority_engine import PriorityEngine
from src.algorithms.blocks.generator import generate_candidate_blocks
from src.algorithms.scheduler.scheduler import CPSATScheduler
from src.algorithms.tdsp.graph import RailwayGraph
from src.algorithms.tdsp.evaluator import TrainRouteEvaluator

class MockObj:
    def __init__(self, d):
        self.__dict__.update(d)

def main():
    data_dir = os.path.join(os.path.dirname(__file__), '../../../data')
    
    print("Loading data from database (CSV mock)...")
    try:
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
    except Exception as e:
        print(f"Failed to load data: {e}")
        return

    # Convert to mock objects
    trains = [MockObj(t) for t in trains_df.to_dict('records')]
    timetable = [MockObj(t) for t in timetable_df.to_dict('records')]
    stations = [MockObj(s) for s in stations_df.to_dict('records')]
    tracks = [MockObj(t) for t in tracks_df.to_dict('records')]

    # Run Priority
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
    
    candidates = generate_candidate_blocks(
        ranked_jobs, requests, assets, rules, availabilities, job_resources, dependencies
    )
    
    print("Running CP-SAT Scheduler...")
    scheduler = CPSATScheduler(
        jobs=jobs, candidates=candidates, dependencies=dependencies, resources=resources,
        job_resources=job_resources, track_avail=availabilities,
        train_timetable=timetable, trains=trains
    )
    sched_result = scheduler.solve()
    
    if sched_result['solver_status'] not in ['OPTIMAL', 'FEASIBLE']:
        print("Scheduler failed. Cannot run TDSP.")
        return
        
    selected_blocks = sched_result['selected_blocks']
    
    print("\nBuilding Railway Graph for TDSP...")
    graph = RailwayGraph(stations, tracks)
    
    print("Initializing TDSP Train Route Evaluator...")
    evaluator = TrainRouteEvaluator(graph, trains, timetable)
    
    print("\nEvaluating Schedule...")
    impact_result = evaluator.evaluate_schedule("SCHED-FINAL", selected_blocks)
    
    print("\n==================================================")
    print("TIME-DEPENDENT TRAIN IMPACT ANALYSIS")
    print("==================================================")
    print(f"Trains Evaluated: {impact_result.total_trains_evaluated}")
    print(f"\nAffected Trains: {impact_result.affected_trains}")
    print(f"Rerouted Trains: {impact_result.rerouted_trains}")
    print(f"Delayed Trains: {sum(1 for t in impact_result.train_results if t.delay_min > 0 and t.route_feasible)}")
    print(f"Infeasible Trains: {impact_result.infeasible_trains}")
    print(f"\nTotal Delay: {impact_result.total_delay_min} min")
    print(f"Average Delay: {impact_result.average_delay_min:.1f} min")
    print(f"Maximum Delay: {impact_result.max_delay_min} min")
    print(f"\nPriority Weighted Delay: {impact_result.priority_weighted_delay:.2f}")
    print(f"Total Impact Score: {impact_result.total_impact_score:.2f}")
    
    print("\nTRAIN IMPACT DETAILS")
    print("-" * 50)
    for tr in impact_result.train_results:
        print(f"Train: {tr.train_id}")
        print(f"Baseline Arrival: {tr.baseline_arrival}")
        print(f"New Arrival: {tr.new_arrival}")
        print(f"Delay: {tr.delay_min} min")
        print(f"Rerouted: {tr.rerouted}")
        print(f"Feasible: {tr.route_feasible}")
        print(f"Reason: {tr.reason}\n")
        
    if impact_result.affected_trains == 0:
        print("Note: The current synthetic timetable is sparse, resulting in 0 affected trains.")
        print("The TDSP algorithm correctly calculated the lack of temporal/spatial conflict.")

if __name__ == "__main__":
    main()
