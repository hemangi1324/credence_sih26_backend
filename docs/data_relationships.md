# Entity Relationships

Based exclusively on the provided CSV files, the following relationships form the core data model.

## Primary Entities and Keys
* **Station** (`station_id`)
* **Track Section** (`track_id`)
* **Train** (`train_id`)
* **Asset** (`asset_id`)
* **Maintenance Job** (`job_id`)
* **Block Request** (`request_id`)
* **Resource** (`resource_id`)

## Relationships

```mermaid
erDiagram
    STATIONS ||--o{ TRACK_SECTIONS : "connects (from/to)"
    STATIONS ||--o{ ASSETS : "locates"
    STATIONS ||--o{ TRAINS : "origin/destination"
    STATIONS ||--o{ GOODS_FORECAST : "origin/destination"
    
    TRACK_SECTIONS ||--o{ ASSETS : "contains"
    TRACK_SECTIONS ||--o{ TRAIN_TIMETABLE : "traversed by"
    TRACK_SECTIONS ||--o{ TRACK_AVAILABILITY : "status of"
    TRACK_SECTIONS ||--o{ REALTIME_EVENTS : "affects"
    TRACK_SECTIONS ||--o{ BLOCK_REQUESTS : "requested on"
    
    TRAINS ||--o{ TRAIN_TIMETABLE : "follows"
    TRAINS ||--o{ TRAIN_LIVE_STATUS : "current status"
    
    ASSETS ||--o{ MAINTENANCE_JOBS : "requires"
    
    MAINTENANCE_JOBS ||--o{ BLOCK_REQUESTS : "initiates"
    MAINTENANCE_JOBS ||--o{ JOB_RESOURCES : "needs"
    MAINTENANCE_JOBS ||--o{ MAINTENANCE_DEPENDENCIES : "has predecessor/successor"
    
    RESOURCES ||--o{ JOB_RESOURCES : "assigned to"
    
    BLOCK_REQUESTS ||--o{ TRACK_AVAILABILITY : "generates"
```

## Spatial Joins and Calculations
In a spatial DB (PostGIS), the following elements will need to interact:
1. `01_stations.csv` contains `latitude` and `longitude`.
2. `02_track_sections.csv` connects stations, possessing a physical distance.
3. Assets, Blocks, and Events have `chainage_km` (or offset), which represents a linear distance along a `track_id` from its starting point.

When implementing CP-SAT or ALNS spatial checks, calculating train overlaps against block requests will require converting the temporal bounds of a train within a `track_id` (from `05_train_timetable.csv`) into a spatial-temporal bounding box using the track length and train speed.
