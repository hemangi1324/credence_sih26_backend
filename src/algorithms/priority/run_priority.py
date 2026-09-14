import sys
import os

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.db.session import SessionLocal
from src.db.repository import DataRepository
from src.algorithms.priority.priority_engine import PriorityEngine

def main():
    print("Connecting to database to retrieve maintenance jobs and assets...")
    db = SessionLocal()
    repo = DataRepository(db)
    
    try:
        jobs_with_assets = repo.get_jobs_with_assets()
        
        if not jobs_with_assets:
            print("No maintenance jobs found in the database.")
            return
            
        print(f"Successfully retrieved {len(jobs_with_assets)} maintenance jobs.\n")
        
        # Initialize and run priority engine
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

        print("\n=== DISTRIBUTION ===")
        for cat, count in categories_count.items():
            print(f"{cat}: {count}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
