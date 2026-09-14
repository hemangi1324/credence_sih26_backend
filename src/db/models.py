from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, DateTime, Time, Date, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from src.db.session import Base

class Station(Base):
    __tablename__ = 'stations'

    station_id = Column(String, primary_key=True, index=True)
    station_name = Column(String, nullable=False)
    station_code = Column(String, nullable=False)
    station_type = Column(String)
    zone = Column(String)
    division = Column(String)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    num_platforms = Column(Integer)
    num_sidings = Column(Integer)
    platform_capacity = Column(Integer)
    
    # PostGIS geometry for spatial queries
    geom = Column(Geometry(geometry_type='POINT', srid=4326))


class TrackSection(Base):
    __tablename__ = 'track_sections'

    track_id = Column(String, primary_key=True, index=True)
    from_station_id = Column(String, ForeignKey('stations.station_id'))
    to_station_id = Column(String, ForeignKey('stations.station_id'))
    distance_km = Column(Float, nullable=False)
    normal_travel_time_min = Column(Integer)
    speed_limit_kmph = Column(Integer)
    direction = Column(String)
    track_type = Column(String)
    capacity = Column(Integer)
    electrified = Column(Boolean)
    signalling_type = Column(String)
    distance_source = Column(String)
    
    # Relationships
    from_station = relationship("Station", foreign_keys=[from_station_id])
    to_station = relationship("Station", foreign_keys=[to_station_id])


class DivisionBoundarySection(Base):
    __tablename__ = 'division_boundary_sections'

    track_id = Column(String, ForeignKey('track_sections.track_id'), primary_key=True)
    division_a = Column(String, nullable=False)
    division_b = Column(String, nullable=False)
    coordination_required = Column(Boolean, default=False)


class Train(Base):
    __tablename__ = 'trains'

    train_id = Column(String, primary_key=True, index=True)
    train_number = Column(String, nullable=False)
    train_name = Column(String)
    train_type = Column(String)
    train_priority = Column(Integer)
    origin_station_id = Column(String, ForeignKey('stations.station_id'))
    destination_station_id = Column(String, ForeignKey('stations.station_id'))
    scheduled_departure = Column(Time)
    scheduled_arrival = Column(Time)
    max_allowed_delay_min = Column(Integer)
    can_be_rerouted = Column(Boolean)
    max_speed_kmph = Column(Integer)
    data_source = Column(String)


class TrainTimetable(Base):
    __tablename__ = 'train_timetable'

    schedule_id = Column(String, primary_key=True, index=True)
    train_id = Column(String, ForeignKey('trains.train_id'), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    track_id = Column(String, ForeignKey('track_sections.track_id'), nullable=False)
    entry_time = Column(Time, nullable=False)
    exit_time = Column(Time, nullable=False)


class GoodsForecast(Base):
    __tablename__ = 'goods_forecast'

    forecast_id = Column(String, primary_key=True, index=True)
    origin_station_id = Column(String, ForeignKey('stations.station_id'))
    destination_station_id = Column(String, ForeignKey('stations.station_id'))
    commodity_type = Column(String)
    forecast_date = Column(Date)
    expected_trains = Column(Integer)
    expected_tonnage = Column(Integer)


class Asset(Base):
    __tablename__ = 'assets'

    asset_id = Column(String, primary_key=True, index=True)
    asset_type = Column(String, nullable=False)
    track_id = Column(String, ForeignKey('track_sections.track_id'), nullable=False)
    location_station_id = Column(String, ForeignKey('stations.station_id'))
    chainage_km_offset = Column(Float, nullable=False)
    installation_date = Column(Date)
    condition_score = Column(Integer)
    failure_count = Column(Integer, default=0)
    last_maintenance_date = Column(Date)
    next_maintenance_due = Column(Date)
    failure_probability = Column(Float)
    availability = Column(Float)
    current_status = Column(String)


class MaintenanceJob(Base):
    __tablename__ = 'maintenance_jobs'

    job_id = Column(String, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey('assets.asset_id'), nullable=False)
    department = Column(String)
    maintenance_type = Column(String)
    track_id = Column(String, ForeignKey('track_sections.track_id'))
    location_station_id = Column(String, ForeignKey('stations.station_id'))
    duration_min = Column(Integer)
    earliest_start = Column(Time)
    latest_start = Column(Time)
    criticality = Column(Integer)
    urgency = Column(Integer)
    asset_risk = Column(Float)
    overdue_days = Column(Integer)
    operational_impact = Column(Integer)
    required_block = Column(Boolean)
    job_status = Column(String)
    
    asset = relationship("Asset")


class MaintenanceDependency(Base):
    __tablename__ = 'maintenance_dependencies'

    job_id_predecessor = Column(String, ForeignKey('maintenance_jobs.job_id'), primary_key=True)
    job_id_successor = Column(String, ForeignKey('maintenance_jobs.job_id'), primary_key=True)
    dependency_type = Column(String, nullable=False)


class CompatibilityRule(Base):
    __tablename__ = 'compatibility_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_type_a = Column(String, nullable=False)
    asset_type_b = Column(String, nullable=False)
    compatible = Column(Boolean, nullable=False)
    isolation_required = Column(Boolean, nullable=False)
    notes = Column(String, unique=True)


class Resource(Base):
    __tablename__ = 'resources'

    resource_id = Column(String, primary_key=True, index=True)
    resource_type = Column(String)
    department = Column(String)
    home_location = Column(String, ForeignKey('stations.station_id'))
    availability_start = Column(Time)
    availability_end = Column(Time)
    quantity = Column(Integer)
    current_status = Column(String)


class JobResource(Base):
    __tablename__ = 'job_resources'

    job_id = Column(String, ForeignKey('maintenance_jobs.job_id'), primary_key=True)
    resource_id = Column(String, ForeignKey('resources.resource_id'), primary_key=True)
    assigned_start = Column(Time)
    assigned_end = Column(Time)


class BlockRequest(Base):
    __tablename__ = 'block_requests'

    request_id = Column(String, primary_key=True, index=True)
    job_id = Column(String, ForeignKey('maintenance_jobs.job_id'))
    department = Column(String)
    track_id = Column(String, ForeignKey('track_sections.track_id'), nullable=False)
    chainage_start_km = Column(Float, nullable=False)
    chainage_end_km = Column(Float, nullable=False)
    block_type = Column(String)
    requested_date = Column(Date)
    requested_start = Column(Time)
    requested_end = Column(Time)
    minimum_duration_min = Column(Integer)
    preferred_start = Column(Time)
    preferred_end = Column(Time)
    safety_buffer_min = Column(Integer)
    request_priority = Column(Integer)
    request_status = Column(String)
    linked_request_id = Column(String, ForeignKey('block_requests.request_id'), nullable=True)


class TrackAvailability(Base):
    __tablename__ = 'track_availability'

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(String, ForeignKey('track_sections.track_id'), nullable=False)
    chainage_start_km = Column(Float, nullable=False)
    chainage_end_km = Column(Float, nullable=False)
    time_start = Column(DateTime, nullable=False)
    time_end = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)
    source_request_id = Column(String, ForeignKey('block_requests.request_id'), nullable=True)


class RealtimeEvent(Base):
    __tablename__ = 'realtime_events'

    event_id = Column(String, primary_key=True, index=True)
    event_type = Column(String)
    track_id = Column(String, ForeignKey('track_sections.track_id'))
    train_id = Column(String, ForeignKey('trains.train_id'), nullable=True)
    event_time = Column(DateTime)
    duration_min = Column(Integer)
    severity = Column(String)


class TrainLiveStatus(Base):
    __tablename__ = 'train_live_status'

    train_id = Column(String, ForeignKey('trains.train_id'), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    current_track_id = Column(String, ForeignKey('track_sections.track_id'))
    delay_min = Column(Integer, default=0)
    status = Column(String)


class TrackLiveStatus(Base):
    __tablename__ = 'track_live_status'

    track_id = Column(String, ForeignKey('track_sections.track_id'), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    status = Column(String)
    active_block_id = Column(String, ForeignKey('block_requests.request_id'), nullable=True)
