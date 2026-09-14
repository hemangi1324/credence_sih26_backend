import os
from src.ingestion.load_csvs import load_data
from src.db.session import SessionLocal
from src.db import models

if __name__ == "__main__":
    print("Starting data ingestion process...")
    
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    load_data(data_dir)
    
    db = SessionLocal()
    try:
        print("\nSummary of loaded data:")
        print(f"Stations: {db.query(models.Station).count()}")
        print(f"Tracks: {db.query(models.TrackSection).count()}")
        print(f"Trains: {db.query(models.Train).count()}")
        print(f"Timetable records: {db.query(models.TrainTimetable).count()}")
        print(f"Assets: {db.query(models.Asset).count()}")
        print(f"Maintenance jobs: {db.query(models.MaintenanceJob).count()}")
        print(f"Block requests: {db.query(models.BlockRequest).count()}")
        print(f"Resources: {db.query(models.Resource).count()}")
    finally:
        db.close()
