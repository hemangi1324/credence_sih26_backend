# Data Inventory

This document provides a comprehensive inventory of all CSV datasets discovered for the SIH2026 railway backend prototype.

## 1. Core Infrastructure & Geography (TMS & Base Data)
* **`01_stations.csv`** (12 rows, 11 cols)
  * **Columns:** `station_id`, `station_name`, `station_code`, `station_type`, `zone`, `division`, `latitude`, `longitude`, `num_platforms`, `num_sidings`, `platform_capacity`
  * **Spatial:** `latitude`, `longitude`
  * **Identifier:** `station_id`
* **`02_track_sections.csv`** (22 rows, 12 cols)
  * **Columns:** `track_id`, `from_station_id`, `to_station_id`, `distance_km`, `normal_travel_time_min`, `speed_limit_kmph`, `direction`, `track_type`, `capacity`, `electrified`, `signalling_type`, `distance_source`
  * **Identifier:** `track_id`
* **`03_division_boundary_sections.csv`** (2 rows, 4 cols)
  * **Columns:** `track_id`, `division_a`, `division_b`, `coordination_required`
  * **Identifier:** `track_id`

## 2. Train Operations (Timetable, COA, Goods)
* **`04_trains.csv`** (12 rows, 13 cols)
  * **Columns:** `train_id`, `train_number`, `train_name`, `train_type`, `train_priority`, `origin_station_id`, `destination_station_id`, `scheduled_departure`, `scheduled_arrival`, `max_allowed_delay_min`, `can_be_rerouted`, `max_speed_kmph`, `data_source`
  * **Identifier:** `train_id`
* **`05_train_timetable.csv`** (108 rows, 6 cols)
  * **Columns:** `schedule_id`, `train_id`, `sequence_no`, `track_id`, `entry_time`, `exit_time`
  * **Identifier:** `schedule_id`
* **`14_goods_forecast.csv`** (14 rows, 7 cols)
  * **Columns:** `forecast_id`, `origin_station_id`, `destination_station_id`, `commodity_type`, `forecast_date`, `expected_trains`, `expected_tonnage`
  * **Identifier:** `forecast_id`
* **`16_train_live_status.csv`** (12 rows, 5 cols)
  * **Columns:** `train_id`, `timestamp`, `current_track_id`, `delay_min`, `status`
  * **Identifier:** `train_id`

## 3. Maintenance, Assets & Resources (SMMS, TDMS, BDMS)
* **`06_assets.csv`** (58 rows, 13 cols)
  * **Columns:** `asset_id`, `asset_type`, `track_id`, `location_station_id`, `chainage_km_offset`, `installation_date`, `condition_score`, `failure_count`, `last_maintenance_date`, `next_maintenance_due`, `failure_probability`, `availability`, `current_status`
  * **Identifier:** `asset_id`
* **`07_maintenance_jobs.csv`** (38 rows, 16 cols)
  * **Columns:** `job_id`, `asset_id`, `department`, `maintenance_type`, `track_id`, `location_station_id`, `duration_min`, `earliest_start`, `latest_start`, `criticality`, `urgency`, `asset_risk`, `overdue_days`, `operational_impact`, `required_block`, `job_status`
  * **Identifier:** `job_id`
* **`08_maintenance_dependencies.csv`** (18 rows, 3 cols)
  * **Columns:** `job_id_predecessor`, `job_id_successor`, `dependency_type`
* **`09_compatibility_rules.csv`** (8 rows, 5 cols)
  * **Columns:** `asset_type_a`, `asset_type_b`, `compatible`, `isolation_required`, `notes`
* **`10_resources.csv`** (7 rows, 8 cols)
  * **Columns:** `resource_id`, `resource_type`, `department`, `home_location`, `availability_start`, `availability_end`, `quantity`, `current_status`
  * **Identifier:** `resource_id`
* **`13_job_resources.csv`** (20 rows, 4 cols)
  * **Columns:** `job_id`, `resource_id`, `assigned_start`, `assigned_end`

## 4. Blocks & Real-time Status (TMS / Operations)
* **`11_block_requests.csv`** (38 rows, 17 cols)
  * **Columns:** `request_id`, `job_id`, `department`, `track_id`, `chainage_start_km`, `chainage_end_km`, `block_type`, `requested_date`, `requested_start`, `requested_end`, `minimum_duration_min`, `preferred_start`, `preferred_end`, `safety_buffer_min`, `request_priority`, `request_status`, `linked_request_id`
  * **Identifier:** `request_id`
* **`12_track_availability.csv`** (53 rows, 7 cols)
  * **Columns:** `track_id`, `chainage_start_km`, `chainage_end_km`, `time_start`, `time_end`, `status`, `source_request_id`
* **`15_realtime_events.csv`** (10 rows, 7 cols)
  * **Columns:** `event_id`, `event_type`, `track_id`, `train_id`, `event_time`, `duration_min`, `severity`
  * **Identifier:** `event_id`
* **`17_track_live_status.csv`** (22 rows, 4 cols)
  * **Columns:** `track_id`, `timestamp`, `status`, `active_block_id`
  * **Identifier:** `track_id`

## Missing Data / Quality Observations
* `15_realtime_events.csv`: The `train_id` field is 100% empty (NaN).
* `17_track_live_status.csv`: The `active_block_id` is 100% empty (NaN).
* `11_block_requests.csv`: `linked_request_id` has 35 missing values out of 38 (valid, as only some requests are linked).
* `12_track_availability.csv`: `source_request_id` has some missing values (15 out of 53) indicating general unavailabilities.
