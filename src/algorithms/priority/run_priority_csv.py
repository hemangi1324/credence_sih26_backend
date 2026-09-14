import pandas as pd
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from src.algorithms.priority.priority_engine import PriorityEngine

class MockJob:
    def __init__(self, d):
        self.__dict__.update(d)

class MockAsset:
    def __init__(self, d):
        self.__dict__.update(d)

def main():
    data_dir = os.path.join(os.path.dirname(__file__), '../../../data')
    jobs_df = pd.read_csv(os.path.join(data_dir, '07_maintenance_jobs.csv'))
    assets_df = pd.read_csv(os.path.join(data_dir, '06_assets.csv'))
    
    jobs_with_assets = []
    for _, job_row in jobs_df.iterrows():
        job_dict = job_row.to_dict()
        asset_row = assets_df[assets_df['asset_id'] == job_dict['asset_id']]
        if not asset_row.empty:
            asset_dict = asset_row.iloc[0].to_dict()
            jobs_with_assets.append((MockJob(job_dict), MockAsset(asset_dict)))

    engine = PriorityEngine()
    ranked_jobs = engine.rank_maintenance_jobs(jobs_with_assets)
    
    print("## Rank | Job          | Department | Risk   | Priority | Category")
    print("-" * 70)
    
    categories_count = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    
    for rank, res in enumerate(ranked_jobs, start=1):
        categories_count[res['priority_category']] += 1
        print(f"{rank:<4} | {res['job_id']:<12} | {res['department']:<10} | "
              f"{res['risk_score']:<6.4f} | {res['priority_score']:<8.4f} | {res['priority_category']}")

    print("\n=== TOP 5 JOBS EXPLANATION ===")
    for rank, res in enumerate(ranked_jobs[:5], start=1):
        print(f"\nRank {rank}: {res['job_id']} ({res['department']})")
        print(f"  Category: {res['priority_category']} (Score: {res['priority_score']:.4f})")
        print("  Feature Contributions:")
        for feature, contribution in res['feature_contributions'].items():
            print(f"    - {feature}: {contribution:.4f}")

    print("\n=== LOWEST 3 JOBS ===")
    for rank, res in enumerate(ranked_jobs[-3:]):
        print(f"{res['job_id']} ({res['department']}) - Priority: {res['priority_score']:.4f}")

    print("\n=== DISTRIBUTION ===")
    for cat, count in categories_count.items():
        print(f"{cat}: {count}")

if __name__ == "__main__":
    main()
