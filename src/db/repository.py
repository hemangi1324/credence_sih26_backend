from sqlalchemy.orm import Session
from src.db import models

class DataRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_stations(self):
        return self.db.query(models.Station).all()

    def get_tracks(self):
        return self.db.query(models.TrackSection).all()

    def get_trains(self):
        return self.db.query(models.Train).all()

    def get_train_timetable(self):
        return self.db.query(models.TrainTimetable).all()

    def get_assets(self):
        return self.db.query(models.Asset).all()

    def get_maintenance_jobs(self):
        return self.db.query(models.MaintenanceJob).all()

    def get_block_requests(self):
        return self.db.query(models.BlockRequest).all()

    def get_track_availability(self):
        return self.db.query(models.TrackAvailability).all()

    def get_resources(self):
        return self.db.query(models.Resource).all()

    def get_job_dependencies(self):
        return self.db.query(models.MaintenanceDependency).all()

    def get_compatibility_rules(self):
        return self.db.query(models.CompatibilityRule).all()

    def get_job_resources(self):
        return self.db.query(models.JobResource).all()
        
    # Joined queries
    def get_jobs_with_assets(self):
        return self.db.query(models.MaintenanceJob).join(models.Asset).all()
        
    def get_jobs_with_block_requests(self):
        return self.db.query(models.MaintenanceJob, models.BlockRequest)\
            .join(models.BlockRequest, models.MaintenanceJob.job_id == models.BlockRequest.job_id).all()
            
    def get_jobs_with_resources(self):
        return self.db.query(models.MaintenanceJob, models.Resource)\
            .join(models.JobResource, models.MaintenanceJob.job_id == models.JobResource.job_id)\
            .join(models.Resource, models.JobResource.resource_id == models.Resource.resource_id).all()
