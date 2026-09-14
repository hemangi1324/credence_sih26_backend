import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import pandas as pd
from src.algorithms.priority.priority_engine import PriorityEngine
from src.algorithms.blocks.generator import generate_candidate_blocks

class MockObj:
    def __init__(self, d):
        self.__dict__.update(d)

def main():
    data_dir = os.path.join(os.path.dirname(__file__), '../../../data')
    
    # Using pandas as fallback since docker is offline in this environment
    # In a real environment, we would use: DataRepository(SessionLocal())
    
    print("Loading data from database (CSV mock)...")
    jobs_df = pd.read_csv(os.path.join(data_dir, '07_maintenance_jobs.csv')).where(pd.notnull, None)
    assets_df = pd.read_csv(os.path.join(data_dir, '06_assets.csv')).where(pd.notnull, None)
    requests_df = pd.read_csv(os.path.join(data_dir, '11_block_requests.csv')).where(pd.notnull, None)
    rules_df = pd.read_csv(os.path.join(data_dir, '09_compatibility_rules.csv')).where(pd.notnull, None)
    avail_df = pd.read_csv(os.path.join(data_dir, '12_track_availability.csv')).where(pd.notnull, None)
    job_res_df = pd.read_csv(os.path.join(data_dir, '13_job_resources.csv')).where(pd.notnull, None)
    deps_df = pd.read_csv(os.path.join(data_dir, '08_maintenance_dependencies.csv')).where(pd.notnull, None)
    
    # 1. Run Priority Engine
    jobs_with_assets = []
    for _, row in jobs_df.iterrows():
        j = row.to_dict()
        a_df = assets_df[assets_df['asset_id'] == j['asset_id']]
        if not a_df.empty:
            jobs_with_assets.append((MockObj(j), MockObj(a_df.iloc[0].to_dict())))
            
    engine = PriorityEngine()
    ranked_jobs = engine.rank_maintenance_jobs(jobs_with_assets)
    
    # 2. Generate Candidate Blocks
    requests = [MockObj(r) for r in requests_df.to_dict('records')]
    assets = [MockObj(a) for a in assets_df.to_dict('records')]
    rules = [MockObj(r) for r in rules_df.to_dict('records')]
    availabilities = [] # Simplification for prototype execution without full datetime parsing
    job_resources = [MockObj(r) for r in job_res_df.to_dict('records')]
    dependencies = [MockObj(r) for r in deps_df.to_dict('records')]
    
    print("\nGenerating Candidate Blocks...")
    candidates = generate_candidate_blocks(
        ranked_jobs, requests, assets, rules, availabilities, job_resources, dependencies
    )
    
    # Metrics
    single_job_candidates = [c for c in candidates if len(c.job_ids) == 1]
    multi_job_candidates = [c for c in candidates if len(c.job_ids) > 1]
    cross_dept = [c for c in candidates if len(c.departments) > 1]
    isolation_req = [c for c in candidates if c.isolation_required]
    
    print(f"\nTotal maintenance jobs processed: {len(ranked_jobs)}")
    print(f"Total valid single-job candidates: {len(single_job_candidates)}")
    print(f"Total valid multi-job candidates: {len(multi_job_candidates)}")
    print(f"Number of cross-department candidates: {len(cross_dept)}")
    print(f"Number requiring isolation: {len(isolation_req)}")
    
    print("\n## Candidate | Track | Jobs | Departments | Priority | Isolation | Duration (m)")
    print("-" * 80)
    
    # Sort candidates by priority score descending
    candidates.sort(key=lambda x: x.priority_score, reverse=True)
    
    for c in candidates[:15]:
        dept_str = ",".join(c.departments)
        job_str = ",".join(c.job_ids)
        print(f"{c.candidate_id:<11} | {c.track_id:<14} | {job_str[:15]:<15} | {dept_str[:15]:<15} | "
              f"{c.priority_score:<8.4f} | {'Yes' if c.isolation_required else 'No':<9} | {c.duration_min}")

    if multi_job_candidates:
        print("\n=== TOP MULTI-JOB CANDIDATE EXPLANATION ===")
        top_multi = max(multi_job_candidates, key=lambda x: x.priority_score)
        print(f"Candidate: {top_multi.candidate_id}")
        print(f"Jobs Combined: {', '.join(top_multi.job_ids)}")
        print("Compatibility Reasons:")
        for reason in top_multi.compatibility_reasons:
            print(f"  - {reason}")

if __name__ == "__main__":
    main()
