import os
import pytest
from src.db.models import Base
from src.db.session import engine

def test_models_import():
    # Verify tables are registered in the metadata
    tables = Base.metadata.tables.keys()
    assert 'stations' in tables
    assert 'track_sections' in tables
    assert 'trains' in tables
    assert 'maintenance_jobs' in tables
    assert 'block_requests' in tables
    assert 'assets' in tables
    assert 'job_resources' in tables
    assert 'compatibility_rules' in tables

def test_db_connection():
    # Attempt to connect to the DB (requires Postgres to be up)
    try:
        with engine.connect() as conn:
            assert conn is not None
    except Exception as e:
        pytest.skip(f"Database connection failed, skipping connection test: {e}")
