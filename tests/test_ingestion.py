import os
import pytest
from src.ingestion.validators import validate_data
from src.ingestion.load_csvs import load_data
import pandas as pd

def test_validation_logic():
    # Mock data to test validators
    mock_files = {
        '01_stations.csv': pd.DataFrame({'station_id': ['S1', 'S1']}), # Duplicate
        '07_maintenance_jobs.csv': pd.DataFrame({'job_id': ['J1'], 'asset_id': ['A2'], 'duration_min': [-10]}),
        '06_assets.csv': pd.DataFrame({'asset_id': ['A1']}), # A2 is missing
    }
    
    errors = validate_data(mock_files)
    assert len(errors) > 0
    
    error_strs = str(errors)
    assert "Duplicate primary keys" in error_strs
    assert "missing assets" in error_strs
    assert "Negative durations" in error_strs

def test_full_ingestion():
    # This test will run the ingestion on the actual data directory
    # Skip if database is not available
    from src.db.session import engine
    from sqlalchemy.exc import OperationalError
    
    try:
        with engine.connect() as conn:
            pass
    except OperationalError:
        pytest.skip("Database not available for ingestion test")
        
    data_dir = os.path.join(os.path.dirname(__file__), '../data')
    load_data(data_dir)
    
    from src.db.session import SessionLocal
    from src.db.models import Station
    
    db = SessionLocal()
    try:
        station_count = db.query(Station).count()
        assert station_count > 0, "Ingestion failed, no stations loaded"
    finally:
        db.close()
