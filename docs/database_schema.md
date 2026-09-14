# Database Schema

This document describes the PostgreSQL + PostGIS database schema created for the SIH2026 railway backend prototype.

## 1. Core Infrastructure

### `stations`
* **Purpose**: Stores station locations and metadata.
* **Primary Key**: `station_id`
* **PostGIS Fields**: `geom` (POINT, SRID 4326) derived from `latitude` and `longitude`.
* **Original CSV**: `01_stations.csv`
* **Consumers**: Candidate block generation, Goods pathfinding.

### `track_sections`
* **Purpose**: Stores logical track segments connecting stations.
* **Primary Key**: `track_id`
* **Foreign Keys**: `from_station_id` -> `stations`, `to_station_id` -> `stations`
* **PostGIS Notes**: Currently uses linear referencing (`distance_km`) rather than a full `LINESTRING` geometry, as precise track curvatures are not available in the synthetic data. In production, a `LINESTRING` geometry should be added.
* **Original CSV**: `02_track_sections.csv`
* **Consumers**: Train-impact calculations (speed * time = chainage).

### `division_boundary_sections`
* **Purpose**: Marks tracks crossing administrative divisions.
* **Primary Key**: `track_id` (also FK to `track_sections`)
* **Original CSV**: `03_division_boundary_sections.csv`

## 2. Train Operations

### `trains`
* **Purpose**: Metadata for scheduled passenger and goods trains.
* **Primary Key**: `train_id`
* **Foreign Keys**: `origin_station_id`, `destination_station_id` -> `stations`
* **Original CSV**: `04_trains.csv`
* **Consumers**: Train impact calculations.

### `train_timetable`
* **Purpose**: Pre-scheduled entry and exit times of trains on specific tracks.
* **Primary Key**: `schedule_id`
* **Foreign Keys**: `train_id` -> `trains`, `track_id` -> `track_sections`
* **Indexes**: `train_id`, `track_id`
* **Original CSV**: `05_train_timetable.csv`
* **Consumers**: CP-SAT overlap checking.

### `goods_forecast`
* **Purpose**: Unscheduled freight demand.
* **Primary Key**: `forecast_id`
* **Foreign Keys**: `origin_station_id`, `destination_station_id` -> `stations`
* **Original CSV**: `14_goods_forecast.csv`

## 3. Maintenance & Assets

### `assets`
* **Purpose**: Physical track infrastructure requiring maintenance.
* **Primary Key**: `asset_id`
* **Foreign Keys**: `track_id` -> `track_sections`, `location_station_id` -> `stations`
* **Spatial Notes**: Uses `chainage_km_offset` for 1D spatial positioning along the track.
* **Original CSV**: `06_assets.csv`
* **Consumers**: Maintenance Prioritization Engine.

### `maintenance_jobs`
* **Purpose**: Scheduled or proposed maintenance work.
* **Primary Key**: `job_id`
* **Foreign Keys**: `asset_id` -> `assets`, `track_id` -> `track_sections`, `location_station_id` -> `stations`
* **Original CSV**: `07_maintenance_jobs.csv`
* **Consumers**: Maintenance Prioritization, CP-SAT Scheduling.

### `maintenance_dependencies`
* **Purpose**: Execution order between jobs.
* **Primary Key**: Composite (`job_id_predecessor`, `job_id_successor`)
* **Foreign Keys**: Both map to `maintenance_jobs.job_id`
* **Original CSV**: `08_maintenance_dependencies.csv`
* **Consumers**: CP-SAT Scheduling constraints.

### `compatibility_rules`
* **Purpose**: Rules determining if different asset types can be maintained simultaneously.
* **Primary Key**: `id` (Autoincrement surrogate)
* **Unique Constraints**: `notes`
* **Original CSV**: `09_compatibility_rules.csv`
* **Consumers**: ALNS Optimization.

## 4. Resources

### `resources`
* **Purpose**: Machinery and crews available for maintenance.
* **Primary Key**: `resource_id`
* **Foreign Keys**: `home_location` -> `stations`
* **Original CSV**: `10_resources.csv`
* **Consumers**: Resource constraints validation.

### `job_resources`
* **Purpose**: Allocation of resources to maintenance jobs.
* **Primary Key**: Composite (`job_id`, `resource_id`)
* **Foreign Keys**: `job_id` -> `maintenance_jobs`, `resource_id` -> `resources`
* **Original CSV**: `13_job_resources.csv`

## 5. Operations & Real-time

### `block_requests`
* **Purpose**: Requests for track isolation (power/traffic block).
* **Primary Key**: `request_id`
* **Foreign Keys**: `job_id` -> `maintenance_jobs`, `track_id` -> `track_sections`, `linked_request_id` -> `block_requests` (Self-referential)
* **Spatial Notes**: `chainage_start_km` and `chainage_end_km` define the 1D spatial extent of the block on the track.
* **Original CSV**: `11_block_requests.csv`
* **Consumers**: Candidate Block Generation.

### `track_availability`
* **Purpose**: Realized track status timelines.
* **Primary Key**: `id` (Autoincrement surrogate)
* **Foreign Keys**: `track_id` -> `track_sections`, `source_request_id` -> `block_requests`
* **Original CSV**: `12_track_availability.csv`

### `realtime_events`
* **Purpose**: Unplanned incidents affecting tracks.
* **Primary Key**: `event_id`
* **Foreign Keys**: `track_id` -> `track_sections`, `train_id` -> `trains` (Nullable)
* **Original CSV**: `15_realtime_events.csv`

### `train_live_status`
* **Purpose**: Latest known state of trains.
* **Primary Key**: `train_id` (Foreign Key to `trains`)
* **Foreign Keys**: `current_track_id` -> `track_sections`
* **Original CSV**: `16_train_live_status.csv`

### `track_live_status`
* **Purpose**: Latest known state of tracks.
* **Primary Key**: `track_id` (Foreign Key to `track_sections`)
* **Foreign Keys**: `active_block_id` -> `block_requests`
* **Original CSV**: `17_track_live_status.csv`
