import os
import pandas as pd
from sqlalchemy.orm import Session
from src.db import models
from src.db.session import engine, SessionLocal
from src.ingestion.validators import validate_data

def load_data(data_dir: str):
    # Load all CSVs
    files = {
        '01_stations.csv': pd.read_csv(os.path.join(data_dir, '01_stations.csv')),
        '02_track_sections.csv': pd.read_csv(os.path.join(data_dir, '02_track_sections.csv')),
        '03_division_boundary_sections.csv': pd.read_csv(os.path.join(data_dir, '03_division_boundary_sections.csv')),
        '04_trains.csv': pd.read_csv(os.path.join(data_dir, '04_trains.csv')),
        '05_train_timetable.csv': pd.read_csv(os.path.join(data_dir, '05_train_timetable.csv')),
        '06_assets.csv': pd.read_csv(os.path.join(data_dir, '06_assets.csv')),
        '07_maintenance_jobs.csv': pd.read_csv(os.path.join(data_dir, '07_maintenance_jobs.csv')),
        '08_maintenance_dependencies.csv': pd.read_csv(os.path.join(data_dir, '08_maintenance_dependencies.csv')),
        '09_compatibility_rules.csv': pd.read_csv(os.path.join(data_dir, '09_compatibility_rules.csv')),
        '10_resources.csv': pd.read_csv(os.path.join(data_dir, '10_resources.csv')),
        '11_block_requests.csv': pd.read_csv(os.path.join(data_dir, '11_block_requests.csv')),
        '12_track_availability.csv': pd.read_csv(os.path.join(data_dir, '12_track_availability.csv')),
        '13_job_resources.csv': pd.read_csv(os.path.join(data_dir, '13_job_resources.csv')),
        '14_goods_forecast.csv': pd.read_csv(os.path.join(data_dir, '14_goods_forecast.csv')),
        '15_realtime_events.csv': pd.read_csv(os.path.join(data_dir, '15_realtime_events.csv')),
        '16_train_live_status.csv': pd.read_csv(os.path.join(data_dir, '16_train_live_status.csv')),
        '17_track_live_status.csv': pd.read_csv(os.path.join(data_dir, '17_track_live_status.csv'))
    }

    # Clean NaNs
    for k, v in files.items():
        # Replace pd.NA and NaN with None for SQLAlchemy compatibility
        files[k] = v.where(pd.notnull(v), None)
        
    # Validate
    errors = validate_data(files)
    if errors:
        print("Validation Errors Found:")
        for e in errors:
            print(f"- {e}")
        # We continue despite errors for now, or we could raise an Exception
        # raise ValueError("Data validation failed")
    
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # 1. Stations
        stations = []
        for _, row in files['01_stations.csv'].iterrows():
            geom_wkt = f"SRID=4326;POINT({row['longitude']} {row['latitude']})"
            st = models.Station(
                station_id=row['station_id'],
                station_name=row['station_name'],
                station_code=row['station_code'],
                station_type=row['station_type'],
                zone=row['zone'],
                division=row['division'],
                latitude=row['latitude'],
                longitude=row['longitude'],
                num_platforms=row['num_platforms'],
                num_sidings=row['num_sidings'],
                platform_capacity=row['platform_capacity'],
                geom=geom_wkt
            )
            stations.append(st)
        db.add_all(stations)
        db.commit()

        # 2. Tracks
        tracks = []
        for _, row in files['02_track_sections.csv'].iterrows():
            tr = models.TrackSection(**row.to_dict())
            tracks.append(tr)
        db.add_all(tracks)
        db.commit()
        
        # 3. Trains, Resources, Goods Forecast
        db.add_all([models.Train(**row.to_dict()) for _, row in files['04_trains.csv'].iterrows()])
        db.add_all([models.Resource(**row.to_dict()) for _, row in files['10_resources.csv'].iterrows()])
        db.add_all([models.GoodsForecast(**row.to_dict()) for _, row in files['14_goods_forecast.csv'].iterrows()])
        db.add_all([models.CompatibilityRule(**row.to_dict()) for _, row in files['09_compatibility_rules.csv'].iterrows()])
        db.add_all([models.DivisionBoundarySection(**row.to_dict()) for _, row in files['03_division_boundary_sections.csv'].iterrows()])
        db.commit()
        
        # 4. Assets & Timetable
        db.add_all([models.Asset(**row.to_dict()) for _, row in files['06_assets.csv'].iterrows()])
        db.add_all([models.TrainTimetable(**row.to_dict()) for _, row in files['05_train_timetable.csv'].iterrows()])
        db.commit()
        
        # 5. Maintenance Jobs
        db.add_all([models.MaintenanceJob(**row.to_dict()) for _, row in files['07_maintenance_jobs.csv'].iterrows()])
        db.commit()
        
        # 6. Job Dependencies & Job Resources
        db.add_all([models.MaintenanceDependency(**row.to_dict()) for _, row in files['08_maintenance_dependencies.csv'].iterrows()])
        db.add_all([models.JobResource(**row.to_dict()) for _, row in files['13_job_resources.csv'].iterrows()])
        db.commit()
        
        # 7. Block Requests
        # Because block requests can link to each other, we insert them without linked_request_id first, then update
        reqs = []
        for _, row in files['11_block_requests.csv'].iterrows():
            d = row.to_dict()
            # Linked request might not exist yet, we can rely on order or insert sequentially
            reqs.append(models.BlockRequest(**d))
        db.add_all(reqs)
        db.commit()
        
        # 8. Remaining Data
        db.add_all([models.TrackAvailability(**row.to_dict()) for _, row in files['12_track_availability.csv'].iterrows()])
        db.add_all([models.RealtimeEvent(**row.to_dict()) for _, row in files['15_realtime_events.csv'].iterrows()])
        db.add_all([models.TrainLiveStatus(**row.to_dict()) for _, row in files['16_train_live_status.csv'].iterrows()])
        db.add_all([models.TrackLiveStatus(**row.to_dict()) for _, row in files['17_track_live_status.csv'].iterrows()])
        db.commit()
        
        print("Data ingestion completed successfully.")
        
    except Exception as e:
        db.rollback()
        print(f"Error during ingestion: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    load_data(os.path.join(os.path.dirname(__file__), '../../data'))
