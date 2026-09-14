# Algorithm Data Requirements

This document maps out which dataset columns will be consumed by each stage of the backend algorithm pipeline.

## 1. Maintenance Prioritization
* **Objective:** Rank incoming maintenance tasks dynamically based on safety, impact, and due dates.
* **Datasets Consumed:**
  * `07_maintenance_jobs.csv`: `criticality`, `urgency`, `asset_risk`, `overdue_days`, `operational_impact`
  * `06_assets.csv`: `condition_score`, `failure_probability`, `failure_count`, `next_maintenance_due`

## 2. Candidate Block Generation
* **Objective:** Produce valid time windows for track blocks based on track layouts and asset spatial properties.
* **Datasets Consumed:**
  * `11_block_requests.csv`: `track_id`, `minimum_duration_min`, `chainage_start_km`, `chainage_end_km`, `requested_start`, `requested_end`
  * `02_track_sections.csv`: `capacity`, `speed_limit_kmph`, `distance_km`
  * `06_assets.csv`: `chainage_km_offset` (for precise asset location matching)

## 3. Train-Impact Evaluation / Conflict Checking
* **Objective:** Determine which scheduled trains or goods paths would be disrupted by a proposed maintenance block.
* **Datasets Consumed:**
  * `05_train_timetable.csv`: `track_id`, `entry_time`, `exit_time`
  * `04_trains.csv`: `train_priority`, `max_speed_kmph`, `max_allowed_delay_min`
  * `14_goods_forecast.csv`: `expected_trains`, `origin_station_id`, `destination_station_id` (Will need route-building to check overlaps)
  * *Note: Precise conflict detection requires interpolating train position inside a track using `speed_limit_kmph` and `distance_km` since timetables are track-level.*

## 4. Resource Constraints Validation
* **Objective:** Ensure personnel, machinery, and materials are available when scheduling blocks.
* **Datasets Consumed:**
  * `10_resources.csv`: `availability_start`, `availability_end`, `quantity`, `home_location`
  * `13_job_resources.csv`: Connects `job_id` to `resource_id`
  * `01_stations.csv`: Distances between `home_location` and `location_station_id` of the job.

## 5. CP-SAT Scheduling & ALNS Optimization
* **Objective:** Formulate a constraint programming or adaptive large neighborhood search model to output the optimal multi-department block schedule.
* **Datasets Consumed:**
  * `07_maintenance_jobs.csv` & `11_block_requests.csv` (Target variables and bounds)
  * `08_maintenance_dependencies.csv`: Precedence and overlap constraints (`job_id_predecessor`, `job_id_successor`, `dependency_type`)
  * `09_compatibility_rules.csv`: Departmental joint-block compatibility (`asset_type_a`, `asset_type_b`, `compatible`, `isolation_required`)
  * `12_track_availability.csv`: Hard constraints on track status (existing blocks)
