-- =====================================================================
-- Seed data — SIH26027 Automatic Block Planning
-- Matches schema.sql exactly. Run this AFTER schema.sql in the Supabase
-- SQL editor (or `psql -f seed.sql`). Safe to re-run on an empty schema;
-- NOT idempotent against a schema that already has rows (PKs are
-- explicit, so a second run will hit unique-key violations by design —
-- that's your signal you already seeded).
--
-- Scenario: Central Railway corridor CSTM–Kalyan–(Panvel branch)–
-- Karjat–Lonavala–Pune–Daund–Solapur, the same illustrative corridor
-- your Technical Design Document uses. One "seed night" is
-- 2026-09-21 22:00 IST through 2026-09-22 06:00 IST.
--
-- Coverage / test cases baked in on purpose:
--   * A 3-department bundle candidate (ENG+TRD+SNT jobs 1,2,3 on the
--     same section/track/window) -> compatibility_edges + blocks.block1,
--     mirroring your own TRD-3094/ENG-1042/BLK-00421 worked example.
--   * A genuine emergency: a FAILED asset (14), an EMERGENCY_REPAIR job
--     (6), a realtime_event chain (failure -> emergency -> restored),
--     and live-status snapshots for it.
--   * Full priority-score spread: criticality from 0.20 to 0.98,
--     overdue_days 0 to 14, one DEFERRED job, one emergency.
--   * request_status variety: GRANTED, PENDING, REJECTED, WITHDRAWN.
--   * compatibility_edges with BOTH compatible=true and compatible=false
--     rows (temporal mismatch, safety/isolation-sequencing mismatch).
--   * A resource (crew) shared across 4 jobs, two of which are
--     sequential-but-non-overlapping -- a real cumulative-capacity case
--     for CP-SAT, not just decoration.
--   * A live reroute: Time-Dependent-A*-style train_routes (baseline +
--     alternate), a rerouting_decision, and the WAIT vs REROUTE split
--     across affected trains for the same block (Pragati waits 45 min
--     for BUNDLE-1-2-3 to clear; Konark Express and GDS4471 reroute
--     onto the DOWN line). train_movements.track_id matches that
--     decision, so it never collides with an active block.
--   * Job status is driven by the block that holds it: APPROVED ->
--     SCHEDULED, PROPOSED -> SCHEDULED, DONE -> COMPLETED. Unassigned
--     jobs stay OPEN/DEFERRED so the planner's `WHERE status = 'OPEN'`
--     will not re-plan committed or finished work.
--   * A historical "block requested but not granted" record that
--     causally precedes the FAILED asset -- good ALNS/ML training
--     narrative (Sec. 6 of your solution_overview.md).
--   * gnn_training_samples is deliberately left EMPTY — it's Phase
--     8-10/advanced and only makes sense once you're actually running
--     the GNN training pipeline; faking rows there would be noise, not
--     data.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------
-- 1. Reference / master data
-- ---------------------------------------------------------------

INSERT INTO departments (department_id, code, name) VALUES
    (1, 'ENG', 'Engineering'),
    (2, 'SNT', 'Signal & Telecommunication'),
    (3, 'TRD', 'Traction Distribution');

INSERT INTO stations (station_id, code, name, station_type, num_platforms, num_sidings, platform_capacity, latitude, longitude) VALUES
    (1, 'CSTM', 'Mumbai CSMT',  'TERMINAL', 18, 4, 6, 18.9398, 72.8355),
    (2, 'KYN',  'Kalyan',       'JUNCTION', 8,  6, 3, 19.2437, 73.1355),
    (3, 'PNVL', 'Panvel',       'JUNCTION', 6,  3, 2, 18.9894, 73.1175),
    (4, 'KJT',  'Karjat',       'JUNCTION', 4,  2, 2, 18.9107, 73.3237),
    (5, 'LNL',  'Lonavala',     'JUNCTION', 4,  2, 2, 18.7546, 73.4062),
    (6, 'PUNE', 'Pune',         'TERMINAL', 6,  4, 3, 18.5286, 73.8744),
    (7, 'DD',   'Daund',        'JUNCTION', 4,  2, 2, 18.4645, 74.5814),
    (8, 'SUR',  'Solapur',      'TERMINAL', 5,  3, 2, 17.6599, 75.9064);

-- Graph edges (station -> station)
INSERT INTO sections (section_id, code, from_station_id, to_station_id, division, distance_km, travel_minutes) VALUES
    (1, 'CSTM-KYN', 1, 2, 'Mumbai',  54.00, 70),
    (2, 'KYN-PNVL',  2, 3, 'Mumbai', 30.00, 45),
    (3, 'KYN-KJT',   2, 4, 'Pune',   39.00, 55),
    (4, 'KJT-LNL',   4, 5, 'Pune',   15.00, 25),
    (5, 'LNL-PUNE',  5, 6, 'Pune',   64.00, 80),
    (6, 'PUNE-DD',   6, 7, 'Pune',   75.00, 90),
    (7, 'DD-SUR',    7, 8, 'Solapur',105.00, 120);

INSERT INTO users (user_id, name, role, department_id) VALUES
    ('u1', 'S. Deshmukh', 'SECTION_CONTROLLER', NULL),
    ('u2', 'R. Kulkarni', 'SECTION_CONTROLLER', NULL),
    ('u3', 'A. Bhosale', 'BDMS_INCHARGE', 1),
    ('u4', 'P. Sharma', 'BDMS_INCHARGE', 3),
    ('u5', 'M. Joshi', 'BDMS_INCHARGE', 2),
    ('u6', 'V. Kumar', 'FIELD_MANAGER', NULL);

INSERT INTO user_sections (user_id, section_id) VALUES
    ('u1', 1), ('u1', 2), ('u1', 3), ('u1', 4),
    ('u2', 5), ('u2', 6), ('u2', 7),
    ('u6', 1), ('u6', 2), ('u6', 3), ('u6', 4);

INSERT INTO tracks (track_id, section_id, line, track_type, start_km, end_km, max_speed_kmph, capacity, electrified, signalling_type) VALUES
    (1,  1, 'UP',     'MAIN',   0.00, 54.00, 110, 1, TRUE,  'AUTOMATIC'),
    (2,  1, 'DOWN',   'MAIN',   0.00, 54.00, 110, 1, TRUE,  'AUTOMATIC'),
    (3,  2, 'SINGLE', 'MAIN',   0.00, 30.00,  80, 1, TRUE,  'ABSOLUTE_BLOCK'),
    (4,  3, 'UP',     'MAIN',   0.00, 39.00,  90, 1, TRUE,  'AUTOMATIC'),
    (5,  3, 'DOWN',   'MAIN',   0.00, 39.00,  90, 1, TRUE,  'AUTOMATIC'),
    (6,  4, 'UP',     'MAIN',   0.00, 15.00,  70, 1, TRUE,  'ABSOLUTE_BLOCK'),
    (7,  4, 'DOWN',   'MAIN',   0.00, 15.00,  70, 1, TRUE,  'ABSOLUTE_BLOCK'),
    (8,  5, 'UP',     'MAIN',   0.00, 64.00, 100, 1, TRUE,  'AUTOMATIC'),
    (9,  5, 'DOWN',   'MAIN',   0.00, 64.00, 100, 1, TRUE,  'AUTOMATIC'),
    (10, 6, 'UP',     'MAIN',   0.00, 75.00, 100, 1, TRUE,  'AUTOMATIC'),
    (11, 6, 'DOWN',   'MAIN',   0.00, 75.00, 100, 1, TRUE,  'AUTOMATIC'),
    (12, 7, 'UP',     'MAIN',   0.00,105.00, 100, 1, FALSE, 'AUTOMATIC'),
    (13, 7, 'DOWN',   'MAIN',   0.00,105.00, 100, 1, FALSE, 'AUTOMATIC'),
    (14, 4, 'SIDING', 'SIDING', 0.00,  1.00,  30, 2, FALSE, 'NONE');

INSERT INTO assets (asset_id, asset_code, asset_type, department_id, section_id, track_id, station_id, start_km, end_km, install_date, condition_score, criticality, failure_count, last_maintenance_date, next_maintenance_due, failure_probability, availability_pct, current_status) VALUES
    (1,  'RAIL-KYN-KJT-01',   'TRACK',  1, 3, 4,  NULL, 0.00, 5.00,  '2015-01-10', 0.550, 0.700, 0, '2026-06-15', '2026-12-15', 0.20, 0.95, 'OK'),
    (2,  'RAIL-KYN-KJT-02',   'TRACK',  1, 3, 5,  NULL, 0.00, 5.00,  '2015-01-10', 0.400, 0.700, 1, '2026-05-01', '2026-11-01', 0.30, 0.90, 'DEGRADED'),
    (3,  'RAIL-KJT-LNL-01',   'TRACK',  1, 4, 6,  NULL, 0.00, 3.00,  '2012-03-05', 0.300, 0.850, 2, '2026-04-10', '2026-09-10', 0.55, 0.75, 'DEGRADED'),
    (4,  'SIG-KJT-01',        'SIGNAL', 2, 4, 6,  4,    NULL, NULL,  '2018-07-01', 0.600, 0.750, 0, '2026-07-01', '2027-01-01', 0.15, 0.97, 'OK'),
    (5,  'SIG-LNL-01',        'SIGNAL', 2, 4, 7,  5,    NULL, NULL,  '2016-09-12', 0.450, 0.600, 1, '2026-03-20', '2026-09-20', 0.35, 0.88, 'DEGRADED'),
    (6,  'OHE-KJT-LNL-01',    'OHE',    3, 4, 6,  NULL, 0.00, 3.00,  '2014-02-20', 0.350, 0.900, 2, '2026-04-15', '2026-09-15', 0.40, 0.80, 'DEGRADED'),
    (7,  'OHE-LNL-PUNE-01',   'OHE',    3, 5, 8,  NULL, 10.00, 15.00,'2017-05-18', 0.700, 0.550, 0, '2026-07-20', '2027-01-20', 0.15, 0.96, 'OK'),
    (8,  'POINT-KYN-01',      'POINT',  2, 3, 4,  2,    NULL, NULL,  '2013-11-11', 0.650, 0.500, 0, '2026-06-01', '2026-12-01', 0.10, 0.97, 'OK'),
    (9,  'RAIL-LNL-PUNE-01',  'TRACK',  1, 5, 8,  NULL, 20.00, 25.00,'2019-01-01', 0.750, 0.400, 0, '2026-05-05', '2026-11-05', 0.10, 0.98, 'OK'),
    (10, 'RAIL-LNL-PUNE-02',  'TRACK',  1, 5, 9,  NULL, 20.00, 25.00,'2019-01-01', 0.800, 0.400, 0, '2026-05-05', '2026-11-05', 0.08, 0.98, 'OK'),
    (11, 'SIG-PUNE-01',       'SIGNAL', 2, 5, 8,  6,    NULL, NULL,  '2020-02-14', 0.650, 0.450, 0, '2026-06-10', '2026-12-10', 0.12, 0.96, 'OK'),
    (12, 'OHE-PUNE-DD-01',    'OHE',    3, 6, 10, NULL, 5.00, 10.00, '2011-08-08', 0.450, 0.700, 1, '2026-08-25', '2026-11-25', 0.30, 0.90, 'DEGRADED'),
    (13, 'RAIL-PUNE-DD-01',   'TRACK',  1, 6, 10, NULL, 5.00, 10.00, '2016-04-04', 0.600, 0.350, 0, '2026-06-20', '2026-12-20', 0.15, 0.95, 'OK'),
    (14, 'RAIL-DD-SUR-01',    'TRACK',  1, 7, 12, NULL, 15.00, 20.00,'2009-09-09', 0.200, 0.950, 3, '2026-03-01', '2026-09-01', 0.60, 0.60, 'FAILED'),
    (15, 'SIG-DD-01',         'SIGNAL', 2, 7, 12, 7,    NULL, NULL,  '2014-12-01', 0.550, 0.550, 0, '2026-07-05', '2027-01-05', 0.18, 0.94, 'OK'),
    (16, 'OHE-KYN-PNVL-01',   'OHE',    3, 2, 3,  NULL, 5.00, 10.00, '2013-06-06', 0.500, 0.450, 1, '2026-05-15', '2026-11-15', 0.25, 0.92, 'OK'),
    (17, 'RAIL-KYN-PNVL-01',  'TRACK',  1, 2, 3,  NULL, 5.00, 10.00, '2013-06-06', 0.650, 0.300, 0, '2026-06-25', '2026-12-25', 0.10, 0.97, 'OK'),
    (18, 'POINT-LNL-01',      'POINT',  2, 5, 8,  5,    NULL, NULL,  '2015-10-10', 0.550, 0.500, 0, '2026-06-05', '2026-12-05', 0.15, 0.95, 'OK'),
    (19, 'RAIL-CSTM-KYN-01',  'TRACK',  1, 1, 1,  NULL, 30.00, 35.00,'2010-01-01', 0.500, 0.500, 1, '2026-04-01', '2026-10-01', 0.25, 0.90, 'OK'),
    (20, 'SIG-CSTM-01',       'SIGNAL', 2, 1, 1,  1,    NULL, NULL,  '2019-03-03', 0.700, 0.400, 0, '2026-07-10', '2027-01-10', 0.10, 0.98, 'OK');

INSERT INTO resources (resource_id, resource_type, department_id, name, home_base_station_id, capacity, current_status) VALUES
    (1,  'CREW',            1, 'ENG Crew - Karjat',   4, 1, 'AVAILABLE'),
    (2,  'CREW',            1, 'ENG Crew - Pune',     6, 1, 'AVAILABLE'),
    (3,  'CREW',            2, 'SNT Crew - Karjat',   4, 1, 'AVAILABLE'),
    (4,  'CREW',            2, 'SNT Crew - Lonavala', 5, 1, 'AVAILABLE'),
    (5,  'CREW',            3, 'TRD Crew - Karjat',   4, 1, 'AVAILABLE'),
    (6,  'CREW',            3, 'TRD Crew - Daund',    7, 1, 'AVAILABLE'),
    (7,  'TAMPING_MACHINE', 1, 'Tamping Machine 01',  4, 1, 'AVAILABLE'),
    (8,  'OHE_VAN',         3, 'OHE Van 01',           4, 1, 'AVAILABLE'),
    (9,  'SIGNAL_VAN',      2, 'Signal Van 01',        5, 1, 'AVAILABLE'),
    (10, 'RAIL_GRINDER',    1, 'Rail Grinder 01',      6, 1, 'AVAILABLE');

INSERT INTO resource_availability (resource_id, available_from, available_to) VALUES
    (1,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (2,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (3,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (4,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (5,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (6,  '2026-09-21 22:00:00+05:30', '2026-09-22 05:00:00+05:30'),
    (7,  '2026-09-21 21:30:00+05:30', '2026-09-22 05:30:00+05:30'),
    (8,  '2026-09-21 21:30:00+05:30', '2026-09-22 05:30:00+05:30'),
    (9,  '2026-09-21 21:30:00+05:30', '2026-09-22 05:30:00+05:30'),
    (10, '2026-09-21 21:30:00+05:30', '2026-09-22 05:30:00+05:30');

-- ---------------------------------------------------------------
-- 2. Train operations
-- ---------------------------------------------------------------

INSERT INTO trains (train_id, train_number, train_name, train_type, priority_class, origin_station_id, destination_station_id, scheduled_departure, scheduled_arrival, max_allowed_delay_minutes, can_be_rerouted, max_speed_kmph) VALUES
    (1, '12124', 'Pragati Express',  'EXPRESS',   2, 1, 6, '2026-09-21 22:40:00+05:30', '2026-09-22 02:30:00+05:30', 15, TRUE,  110),
    (2, '11007', 'Deccan Express',   'EXPRESS',   2, 6, 1, '2026-09-21 23:50:00+05:30', '2026-09-22 03:40:00+05:30', 15, TRUE,  110),
    (3, '16339', 'Solapur Passenger','PASSENGER', 4, 6, 8, '2026-09-21 22:00:00+05:30', '2026-09-22 01:30:00+05:30', 20, TRUE,   90),
    (4, 'GDS4471','Goods Freight',   'GOODS',     5, 2, 8, '2026-09-21 21:30:00+05:30', '2026-09-22 04:35:00+05:30', 60, TRUE,   60),
    (5, '12627', 'Konark Express',   'EXPRESS',   1, 1, 8, '2026-09-21 23:20:00+05:30', '2026-09-22 05:25:00+05:30', 10, TRUE,  130),
    (6, '51567', 'Panvel Local',     'PASSENGER', 4, 2, 3, '2026-09-21 23:05:00+05:30', '2026-09-21 23:50:00+05:30', 15, FALSE,  80);

-- Section-by-section timetable (the baseline "as published" route,
-- except where a possession forced a hold or a DOWN-line reroute —
-- those legs already reflect the resolved plan, so they never occupy
-- a track an active block is holding).
INSERT INTO train_movements (train_id, section_id, track_id, scheduled_entry, scheduled_exit, sequence_no, night_index) VALUES
    -- Train 1 (12124) CSTM -> KYN -> KJT -> LNL -> PUNE
    -- KJT-LNL (seq 3) waits for BUNDLE-1-2-3 to release track 6 at 01:30 IST
    -- (19:15Z due onto the track, 20:00Z release = 45 min hold, then the
    -- original 25-minute run 01:30-01:55 IST).
    (1, 1, 1, '2026-09-21 22:40:00+05:30', '2026-09-21 23:50:00+05:30', 1, 0),
    (1, 3, 4, '2026-09-21 23:50:00+05:30', '2026-09-22 00:45:00+05:30', 2, 0),
    (1, 4, 6, '2026-09-22 01:30:00+05:30', '2026-09-22 01:55:00+05:30', 3, 0),
    (1, 5, 8, '2026-09-22 01:10:00+05:30', '2026-09-22 02:30:00+05:30', 4, 0),
    -- Train 2 (11007) PUNE -> LNL -> KJT -> KYN -> CSTM
    (2, 5, 9,  '2026-09-21 23:50:00+05:30', '2026-09-22 01:10:00+05:30', 1, 0),
    (2, 4, 7,  '2026-09-22 01:10:00+05:30', '2026-09-22 01:35:00+05:30', 2, 0),
    (2, 3, 5,  '2026-09-22 01:35:00+05:30', '2026-09-22 02:30:00+05:30', 3, 0),
    (2, 1, 2,  '2026-09-22 02:30:00+05:30', '2026-09-22 03:40:00+05:30', 4, 0),
    -- Train 3 (16339) PUNE -> DD -> SUR
    (3, 6, 10, '2026-09-21 22:00:00+05:30', '2026-09-21 23:30:00+05:30', 1, 0),
    (3, 7, 12, '2026-09-21 23:30:00+05:30', '2026-09-22 01:30:00+05:30', 2, 0),
    -- Train 4 (GDS4471) KYN -> KJT -> LNL -> PUNE -> DD -> SUR
    -- KJT-LNL (seq 2) rerouted onto DOWN (track 7); section 4 has a free
    -- DOWN main in that window, same treatment as train 5.
    (4, 3, 4,  '2026-09-21 21:30:00+05:30', '2026-09-21 22:40:00+05:30', 1, 0),
    (4, 4, 7,  '2026-09-21 22:40:00+05:30', '2026-09-21 23:10:00+05:30', 2, 0),
    (4, 5, 8,  '2026-09-21 23:10:00+05:30', '2026-09-22 00:45:00+05:30', 3, 0),
    (4, 6, 10, '2026-09-22 00:45:00+05:30', '2026-09-22 02:25:00+05:30', 4, 0),
    (4, 7, 12, '2026-09-22 02:25:00+05:30', '2026-09-22 04:35:00+05:30', 5, 0),
    -- Train 5 (12627) CSTM -> KYN -> KJT -> LNL -> PUNE -> DD -> SUR
    -- KJT-LNL (seq 3) already on DOWN (track 7) to clear BUNDLE-1-2-3.
    (5, 1, 1,  '2026-09-21 23:20:00+05:30', '2026-09-22 00:20:00+05:30', 1, 0),
    (5, 3, 4,  '2026-09-22 00:20:00+05:30', '2026-09-22 01:05:00+05:30', 2, 0),
    (5, 4, 7,  '2026-09-22 01:05:00+05:30', '2026-09-22 01:25:00+05:30', 3, 0),
    (5, 5, 8,  '2026-09-22 01:25:00+05:30', '2026-09-22 02:30:00+05:30', 4, 0),
    (5, 6, 10, '2026-09-22 02:30:00+05:30', '2026-09-22 03:45:00+05:30', 5, 0),
    (5, 7, 12, '2026-09-22 03:45:00+05:30', '2026-09-22 05:25:00+05:30', 6, 0),
    -- Train 6 (51567) KYN -> PNVL (branch)
    (6, 2, 3,  '2026-09-21 23:05:00+05:30', '2026-09-21 23:50:00+05:30', 1, 0);

-- Currently-active route per train. Trains 1-4 and 6 are still on their
-- original baseline (route_version 1, is_active TRUE). Train 5's
-- KJT-LNL leg gets superseded by a reroute (see train_routes below +
-- rerouting_decisions), so its baseline leg is versioned out.
INSERT INTO train_routes (route_id, train_id, route_version, sequence_no, section_id, track_id, planned_entry, planned_exit, is_active) VALUES
    (1, 5, 1, 3, 4, 6, '2026-09-22 01:05:00+05:30', '2026-09-22 01:25:00+05:30', FALSE),
    (2, 5, 2, 3, 4, 7, '2026-09-22 01:05:00+05:30', '2026-09-22 01:25:00+05:30', TRUE);

INSERT INTO goods_forecast (section_id, track_id, window_start, window_end, expected_goods_trains, expected_passenger_trains, forecast_confidence) VALUES
    (1, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 1, 3, 0.80),
    (2, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 1, 1, 0.75),
    (3, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 1, 2, 0.78),
    (4, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 1, 2, 0.78),
    (5, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 1, 3, 0.82),
    (6, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 2, 1, 0.70),
    (7, NULL, '2026-09-21 22:00:00+05:30', '2026-09-22 06:00:00+05:30', 2, 1, 0.65);

-- ---------------------------------------------------------------
-- 3. Maintenance demand
-- ---------------------------------------------------------------

INSERT INTO maintenance_jobs (job_id, source_system, department_id, asset_id, section_id, track_id, start_km, end_km, defect_type, maintenance_type, severity, criticality, urgency, asset_risk, predicted_risk, overdue_days, condition_score, operational_impact, safety_factor, estimated_duration_minutes, safety_buffer_minutes, required_block_type, required_manpower, power_block_required, signalling_disconnection_required, earliest_start, latest_start, status) VALUES
    (1,  'TMS',  1, 3,  4, 6, 0.00, 3.00, 'RAIL_CRACK',           'REPAIR',           5, 0.900, 0.850, 0.800, 0.880, 14, 0.300, 0.850, 0.900, 90,  15, 'TOTAL',       3, TRUE,  FALSE, '2026-09-21 22:00:00+05:30', '2026-09-24 22:00:00+05:30', 'SCHEDULED'),
    (2,  'TDMS', 3, 6,  4, 6, 0.00, 3.00, 'OHE_ABNORMALITY',      'REPAIR',           5, 0.920, 0.800, 0.850, 0.900, 5,  0.350, 0.850, 0.950, 60,  15, 'TOTAL',       2, TRUE,  FALSE, '2026-09-21 22:00:00+05:30', '2026-09-24 22:00:00+05:30', 'SCHEDULED'),
    (3,  'SMMS', 2, 4,  4, 6, NULL, NULL, 'SIGNAL_INSPECTION',    'INSPECTION',       3, 0.600, 0.550, 0.500, NULL,  2,  0.600, 0.550, 0.700, 30,  15, 'PARTIAL',     1, FALSE, TRUE,  '2026-09-21 22:00:00+05:30', '2026-09-24 22:00:00+05:30', 'SCHEDULED'),
    (4,  'TMS',  1, 1,  3, 4, 0.00, 5.00, 'TRACK_GEOMETRY',       'REPAIR',           3, 0.550, 0.400, 0.450, 0.500, 0,  0.550, 0.400, 0.500, 45,  15, 'PARTIAL',     2, FALSE, FALSE, '2026-09-22 22:00:00+05:30', '2026-09-26 22:00:00+05:30', 'OPEN'),
    (5,  'TMS',  1, 2,  3, 5, 0.00, 5.00, 'BALLAST_DEGRADATION',  'REPAIR',           2, 0.350, 0.300, 0.300, NULL,  0,  0.400, 0.300, 0.400, 40,  15, 'PARTIAL',     2, FALSE, FALSE, '2026-09-23 22:00:00+05:30', '2026-09-27 22:00:00+05:30', 'OPEN'),
    (6,  'TMS',  1, 14, 7, 12,15.00,20.00,'RAIL_FRACTURE',        'EMERGENCY_REPAIR', 5, 0.980, 0.980, 0.950, 0.950, 0,  0.150, 0.900, 0.980, 120, 20, 'TOTAL',       4, TRUE,  FALSE, '2026-09-21 20:00:00+05:30', '2026-09-21 23:00:00+05:30', 'COMPLETED'),
    (7,  'TDMS', 3, 7,  5, 8, 10.00,15.00,'INSULATOR_WEAR',       'INSPECTION',       3, 0.500, 0.450, 0.450, 0.480, 3,  0.550, 0.450, 0.550, 50,  15, 'PARTIAL',     2, TRUE,  FALSE, '2026-09-22 22:00:00+05:30', '2026-09-25 22:00:00+05:30', 'OPEN'),
    (8,  'SMMS', 2, 11, 5, 8, NULL, NULL, 'RELAY_TEST',           'INSPECTION',       2, 0.300, 0.250, 0.250, NULL,  0,  0.650, 0.250, 0.350, 30,  10, 'PARTIAL',     1, FALSE, TRUE,  '2026-09-24 22:00:00+05:30', '2026-09-28 22:00:00+05:30', 'OPEN'),
    (9,  'TMS',  1, 13, 6, 10,5.00, 10.00,'TRACK_INSPECTION',     'INSPECTION',       2, 0.350, 0.300, 0.300, 0.320, 1,  0.600, 0.300, 0.350, 40,  15, 'PARTIAL',     2, FALSE, FALSE, '2026-09-22 20:00:00+05:30', '2026-09-27 22:00:00+05:30', 'OPEN'),
    (10, 'TDMS', 3, 12, 6, 10,5.00, 10.00,'OHE_TENSION_LOW',      'REPAIR',           4, 0.700, 0.600, 0.650, 0.680, 7,  0.450, 0.600, 0.700, 55,  15, 'TOTAL',       2, TRUE,  FALSE, '2026-09-22 20:00:00+05:30', '2026-09-25 22:00:00+05:30', 'SCHEDULED'),
    (11, 'TDMS', 3, 16, 2, 3, 5.00, 10.00,'OHE_SAG',              'REPAIR',           3, 0.450, 0.400, 0.400, NULL,  4,  0.500, 0.350, 0.450, 45,  15, 'TOTAL',       2, TRUE,  FALSE, '2026-09-23 22:00:00+05:30', '2026-09-27 22:00:00+05:30', 'OPEN'),
    (12, 'TMS',  1, 17, 2, 3, 5.00, 10.00,'RAIL_WEAR',            'INSPECTION',       2, 0.300, 0.250, 0.250, 0.280, 0,  0.650, 0.250, 0.300, 30,  10, 'PARTIAL',     1, FALSE, FALSE, '2026-09-24 22:00:00+05:30', '2026-09-29 22:00:00+05:30', 'OPEN'),
    (13, 'TMS',  1, 19, 1, 1, 30.00,35.00,'JOINT_WEAR',           'REPAIR',           3, 0.500, 0.420, 0.420, 0.450, 6,  0.500, 0.550, 0.500, 60,  15, 'PARTIAL',     2, FALSE, FALSE, '2026-09-22 22:00:00+05:30', '2026-09-26 22:00:00+05:30', 'OPEN'),
    (14, 'SMMS', 2, 5,  4, 7, NULL, NULL, 'POINT_MACHINE_FAULT',  'REPAIR',           4, 0.650, 0.600, 0.550, 0.600, 9,  0.400, 0.550, 0.650, 50,  15, 'PARTIAL',     2, FALSE, TRUE,  '2026-09-21 22:00:00+05:30', '2026-09-24 22:00:00+05:30', 'OPEN'),
    (15, 'TMS',  1, 9,  5, 8, 20.00,25.00,'FISH_PLATE_LOOSE',     'REPAIR',           1, 0.200, 0.150, 0.150, 0.180, 0,  0.750, 0.150, 0.200, 25,  10, 'PARTIAL',     1, FALSE, FALSE, '2026-09-25 22:00:00+05:30', '2026-09-30 22:00:00+05:30', 'DEFERRED');

-- BDMS layer: department requests for track access. Not every job has
-- one yet (jobs 12, 14, 15 are still open demand with no formal request).
INSERT INTO block_requests (request_id, job_id, department_id, track_id, requested_date, requested_start, requested_end, minimum_duration_minutes, preferred_start, preferred_end, safety_buffer_minutes, request_priority, request_status, submitted_by) VALUES
    (1,  1,  1, 6,  '2026-09-21', '2026-09-21 22:00:00+05:30', '2026-09-22 00:30:00+05:30', 90, '2026-09-21 22:30:00+05:30', '2026-09-22 00:15:00+05:30', 15, 1, 'GRANTED', 'u3'),
    (2,  2,  3, 6,  '2026-09-21', '2026-09-21 22:00:00+05:30', '2026-09-22 00:00:00+05:30', 60, '2026-09-21 22:30:00+05:30', '2026-09-21 23:45:00+05:30', 15, 1, 'GRANTED', 'u4'),
    (3,  3,  2, 6,  '2026-09-21', '2026-09-21 23:30:00+05:30', '2026-09-22 00:30:00+05:30', 30, '2026-09-21 23:40:00+05:30', '2026-09-22 00:15:00+05:30', 15, 2, 'GRANTED', 'u5'),
    (4,  4,  1, 4,  '2026-09-22', '2026-09-22 22:00:00+05:30', '2026-09-22 23:00:00+05:30', 45, '2026-09-22 22:15:00+05:30', '2026-09-22 23:00:00+05:30', 15, 3, 'PENDING', 'u3'),
    (5,  5,  1, 5,  '2026-09-23', '2026-09-23 22:00:00+05:30', '2026-09-23 23:00:00+05:30', 40, '2026-09-23 22:30:00+05:30', '2026-09-23 23:10:00+05:30', 15, 4, 'PENDING', 'u3'),
    (6,  6,  1, 12, '2026-09-21', '2026-09-21 20:00:00+05:30', '2026-09-21 22:30:00+05:30', 120,'2026-09-21 20:00:00+05:30', '2026-09-21 22:00:00+05:30', 20, 1, 'GRANTED', 'u3'),
    (7,  7,  3, 8,  '2026-09-22', '2026-09-22 23:00:00+05:30', '2026-09-23 00:00:00+05:30', 50, '2026-09-22 23:00:00+05:30', '2026-09-22 23:50:00+05:30', 15, 3, 'PENDING', 'u4'),
    (8,  8,  2, 8,  '2026-09-24', '2026-09-24 22:00:00+05:30', '2026-09-24 23:00:00+05:30', 30, '2026-09-24 22:15:00+05:30', '2026-09-24 22:45:00+05:30', 10, 4, 'WITHDRAWN', 'u5'),
    (9,  9,  1, 10, '2026-09-22', '2026-09-22 22:00:00+05:30', '2026-09-22 23:00:00+05:30', 40, '2026-09-22 22:00:00+05:30', '2026-09-22 22:40:00+05:30', 15, 3, 'PENDING', 'u3'),
    (10, 10, 3, 10, '2026-09-22', '2026-09-22 22:00:00+05:30', '2026-09-22 23:10:00+05:30', 55, '2026-09-22 22:00:00+05:30', '2026-09-22 22:55:00+05:30', 15, 2, 'GRANTED', 'u4'),
    (11, 11, 3, 3,  '2026-09-23', '2026-09-23 22:00:00+05:30', '2026-09-23 23:00:00+05:30', 45, '2026-09-23 22:00:00+05:30', '2026-09-23 22:45:00+05:30', 15, 3, 'REJECTED', 'u4'),
    (12, 13, 1, 1,  '2026-09-22', '2026-09-22 22:00:00+05:30', '2026-09-22 23:15:00+05:30', 60, '2026-09-22 22:00:00+05:30', '2026-09-22 23:00:00+05:30', 15, 3, 'PENDING', 'u3');

INSERT INTO job_resources (job_id, resource_id, quantity) VALUES
    (1, 1, 1), (1, 7, 1),
    (2, 5, 1), (2, 8, 1),
    (3, 3, 1),
    (4, 1, 1),
    (5, 1, 1),
    (6, 1, 2), (6, 7, 1), (6, 8, 1),
    (7, 5, 1),
    (8, 4, 1),
    (9, 2, 1),
    (10, 6, 1),
    (13, 2, 1),
    (14, 3, 1), (14, 9, 1);

-- job 3 (S&T signal work) must not start until job 2 (TRD OHE isolation)
-- is at least 10 min in; job 10 (TRD OHE) must not start until job 9
-- (ENG track inspection, same section/track) has a 15 min head start.
INSERT INTO job_dependencies (job_id, depends_on_job, dependency_type, minimum_gap_minutes) VALUES
    (3, 2, 'ISOLATION_BEFORE_WORK', 10),
    (10, 9, 'FINISH_TO_START', 15);

INSERT INTO compatibility_edges (job_a_id, job_b_id, spatial_ok, temporal_ok, safety_ok, resource_ok, compatible, reason) VALUES
    (1, 2, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  'Same section/track, overlapping window; ENG+TRD isolation-compatible.'),
    (1, 3, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  'Signal inspection compatible with adjacent engineering work once isolation is sequenced.'),
    (2, 3, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  'S&T work sequenced after TRD isolation (see job_dependencies).'),
    (4, 5, TRUE,  FALSE, TRUE,  TRUE,  FALSE, 'Same corridor, but requested windows do not overlap enough to bundle.'),
    (9, 10,TRUE,  TRUE,  FALSE, TRUE,  FALSE, 'OHE energisation conflicts with the engineering isolation sequence unless the job_dependencies gap is honoured.');

INSERT INTO maintenance_history (asset_id, job_id, maintenance_date, maintenance_type, demanded_at, granted, actual_start, actual_end, planned_duration_minutes, actual_duration_minutes, work_completed, result, failure_found, condition_before, condition_after, output_score) VALUES
    (3,  NULL, '2026-08-10', 'REPAIR',     '2026-08-08 10:00:00+05:30', TRUE,  '2026-08-10 23:00:00+05:30', '2026-08-11 01:00:00+05:30', 90, 120, TRUE,  'COMPLETED', TRUE,  0.250, 0.550, 0.70),
    (6,  NULL, '2026-08-12', 'INSPECTION', '2026-08-11 09:00:00+05:30', TRUE,  '2026-08-12 23:30:00+05:30', '2026-08-13 00:15:00+05:30', 60, 45,  TRUE,  'COMPLETED', FALSE, 0.600, 0.650, 0.85),
    (14, NULL, '2026-07-20', 'INSPECTION', '2026-07-18 09:00:00+05:30', FALSE, NULL,                        NULL,                        60, NULL, FALSE, 'ABORTED',   NULL,  0.400, 0.350, 0.10),
    (1,  NULL, '2026-06-15', 'REPAIR',     '2026-06-12 09:00:00+05:30', TRUE,  '2026-06-15 22:00:00+05:30', '2026-06-16 00:20:00+05:30', 90, 140, TRUE,  'PARTIAL',   TRUE,  0.450, 0.550, 0.45),
    (9,  NULL, '2026-05-05', 'INSPECTION', '2026-05-03 09:00:00+05:30', TRUE,  '2026-05-05 23:00:00+05:30', '2026-05-05 23:25:00+05:30', 30, 25,  TRUE,  'COMPLETED', FALSE, 0.700, 0.750, 0.95),
    (12, 10,   '2026-08-25', 'REPAIR',     '2026-08-22 09:00:00+05:30', TRUE,  '2026-08-25 22:30:00+05:30', '2026-08-26 00:00:00+05:30', 60, 90,  TRUE,  'COMPLETED', TRUE,  0.350, 0.500, 0.55);

INSERT INTO track_availability (track_id, window_start, window_end, status, capacity, reason) VALUES
    (6,  '2026-09-21 22:00:00+05:30', '2026-09-22 02:00:00+05:30', 'AVAILABLE',  1, 'Nightly maintenance window per Rolling Block Programme'),
    (7,  '2026-09-21 22:00:00+05:30', '2026-09-22 02:00:00+05:30', 'AVAILABLE',  1, 'Nightly maintenance window per Rolling Block Programme'),
    (4,  '2026-09-21 22:30:00+05:30', '2026-09-22 01:30:00+05:30', 'AVAILABLE',  1, NULL),
    (5,  '2026-09-21 22:30:00+05:30', '2026-09-22 01:30:00+05:30', 'AVAILABLE',  1, NULL),
    (8,  '2026-09-21 23:00:00+05:30', '2026-09-22 03:00:00+05:30', 'AVAILABLE',  1, NULL),
    (12, '2026-09-21 20:00:00+05:30', '2026-09-21 23:30:00+05:30', 'BLOCKED',    0, 'Emergency rail fracture - asset RAIL-DD-SUR-01'),
    (12, '2026-09-21 23:30:00+05:30', '2026-09-22 06:00:00+05:30', 'RESTRICTED', 1, 'Speed-restricted after emergency repair pending follow-up inspection'),
    (3,  '2026-09-21 22:00:00+05:30', '2026-09-22 00:00:00+05:30', 'AVAILABLE',  1, NULL),
    (10, '2026-09-21 22:00:00+05:30', '2026-09-22 02:00:00+05:30', 'AVAILABLE',  1, NULL),
    (1,  '2026-09-21 22:00:00+05:30', '2026-09-22 01:00:00+05:30', 'AVAILABLE',  1, NULL);

-- ---------------------------------------------------------------
-- 4. Blocks / plans
-- ---------------------------------------------------------------

INSERT INTO optimization_runs (run_id, horizon, triggered_by, started_at, finished_at, objective_cost, solver_status, notes) VALUES
    (1, 'WEEKLY', 'seed_demo', '2026-09-21 18:00:00+05:30', '2026-09-21 18:04:00+05:30', 842.500, 'OPTIMAL', 'Illustrative demo plan for the Karjat-Lonavala corridor bundle. Hand-built for seed purposes, not an actual CP-SAT solve.');

INSERT INTO schedule_versions (version_id, run_id, parent_version, is_active) VALUES
    (1, 1, NULL, TRUE);

INSERT INTO blocks (block_id, version_id, unit_id, section_id, track_id, start_km, end_km, planned_start, planned_end, block_type, status, priority_score, utilization, conflict_cost, expected_train_delay_min, asset_benefit, resource_cost, objective_cost, explanation) VALUES
    (1, 1, 'BUNDLE-1-2-3', 4, 6,  0.00, 3.00,  '2026-09-21 22:30:00+05:30', '2026-09-22 01:30:00+05:30', 'INTEGRATED',  'APPROVED', 0.910, 0.860, 45.0,  12, 310.5, 60.0, 415.5, '["High-priority TRD/ENG defects", "Signal work sequenced after isolation", "Corridor window available", "Lower train impact than the alternate window"]'::jsonb),
    (2, 1, 'BLOCK-6',      7, 12, 15.00, 20.00,'2026-09-21 20:00:00+05:30', '2026-09-21 22:20:00+05:30', 'MAINTENANCE', 'DONE',     0.990, 0.950, 120.0, 35, 500.0, 90.0, 620.0, '["Emergency rail fracture", "No feasible deferral", "Track already at reduced capacity"]'::jsonb),
    (3, 1, 'BLOCK-10',     6, 10, 5.00, 10.00, '2026-09-22 22:00:00+05:30', '2026-09-22 23:10:00+05:30', 'MAINTENANCE', 'PROPOSED', 0.700, 0.750, 10.0,  5,  150.0,30.0, 190.0, '["OHE tension repair overdue 7 days", "No scheduled train conflict this window"]'::jsonb);

INSERT INTO block_jobs (block_id, job_id) VALUES
    (1, 1), (1, 2), (1, 3),
    (2, 6),
    (3, 10);

INSERT INTO block_requests_fulfilled (block_id, request_id) VALUES
    (1, 1), (1, 2), (1, 3),
    (2, 6),
    (3, 10);

INSERT INTO block_trains (block_id, train_id, impact_type, delay_minutes, original_route, new_route) VALUES
    (1, 1, 'WAIT',    45, NULL, NULL),
    (1, 5, 'REROUTE', 18, '{"section_id": 4, "track_id": 6}'::jsonb, '{"section_id": 4, "track_id": 7}'::jsonb),
    (1, 4, 'REROUTE', 12, '{"track_id": 6, "section_id": 4}'::jsonb, '{"track_id": 7, "section_id": 4}'::jsonb),
    (2, 3, 'WAIT',    5,  NULL, NULL);

-- ---------------------------------------------------------------
-- 5. Real-time / monitoring / audit
-- ---------------------------------------------------------------

INSERT INTO realtime_events (event_id, event_type, section_id, track_id, asset_id, train_id, job_id, location_station_id, severity, estimated_duration_minutes, actual_duration_minutes, status, source, payload, occurred_at) VALUES
    (1, 'EQUIPMENT_FAILURE',    7, 12, 14, NULL, NULL, NULL, 5, 150, 140, 'RESOLVED', 'TDMS_SENSOR',     '{"defect": "rail_fracture", "detected_by": "ultrasonic_flaw_detector"}'::jsonb, '2026-09-21 19:45:00+05:30'),
    (2, 'EMERGENCY_MAINTENANCE',7, 12, 14, NULL, 6,    NULL, 5, 120, 140, 'RESOLVED', 'CONTROL_OFFICE',  NULL, '2026-09-21 20:00:00+05:30'),
    (3, 'TRACK_RESTORED',       7, 12, 14, NULL, NULL, NULL, 1, NULL,NULL,'RESOLVED', 'FIELD_CREW',      NULL, '2026-09-21 22:20:00+05:30'),
    (4, 'TRAIN_DELAY',          4, 6,  NULL,5,    NULL, NULL, 2, 18,  18,  'RESOLVED', 'CONTROL_OFFICE',  NULL, '2026-09-22 01:05:00+05:30'),
    (5, 'SIGNAL_FAILURE',       4, 7,  5,   NULL, NULL, NULL, 3, 40,  NULL,'OPEN',     'SMMS_SENSOR',     NULL, '2026-09-21 21:10:00+05:30'),
    (6, 'BLOCK_OVERRUN',        6, 10, NULL,NULL, 10,   NULL, 2, 55,  70,  'RESOLVED', 'FIELD_CREW',      NULL, '2026-08-25 23:55:00+05:30');

INSERT INTO train_live_status (ts, train_id, current_section_id, current_track_id, position_km, actual_entry_time, expected_exit_time, delay_minutes, status) VALUES
    ('2026-09-21 22:45:00+05:30', 1, 1, 1, 20.00, '2026-09-21 22:40:00+05:30', '2026-09-21 23:50:00+05:30', 0,  'ON_TIME'),
    ('2026-09-22 00:55:00+05:30', 1, 4, 6, 2.00,  '2026-09-22 00:45:00+05:30', '2026-09-22 01:10:00+05:30', 10, 'DELAYED'),
    ('2026-09-22 01:10:00+05:30', 5, 4, 6, 1.00,  '2026-09-22 01:05:00+05:30', '2026-09-22 01:25:00+05:30', 18, 'REROUTED'),
    ('2026-09-21 22:45:00+05:30', 4, 4, 6, 10.00, '2026-09-21 22:40:00+05:30', '2026-09-21 23:10:00+05:30', 0,  'ON_TIME'),
    ('2026-09-21 23:35:00+05:30', 3, 6, 10,40.00, '2026-09-21 22:00:00+05:30', '2026-09-21 23:30:00+05:30', 5,  'DELAYED');

INSERT INTO track_live_status (ts, track_id, status, available_capacity, failure_event_id, expected_restore_time) VALUES
    ('2026-09-21 19:50:00+05:30', 12, 'BLOCKED',           0, 1,    '2026-09-21 22:20:00+05:30'),
    ('2026-09-21 22:20:00+05:30', 12, 'RESTRICTED',        1, 1,    '2026-09-22 06:00:00+05:30'),
    ('2026-09-21 22:35:00+05:30', 6,  'BLOCKED',           0, NULL, '2026-09-22 01:30:00+05:30'),
    ('2026-09-22 01:30:00+05:30', 6,  'AVAILABLE',         1, NULL, NULL),
    ('2026-09-21 21:15:00+05:30', 7,  'AVAILABLE',         1, NULL, NULL);

INSERT INTO asset_live_status (ts, asset_id, status, condition_score, failure_detected, estimated_repair_time_minutes) VALUES
    ('2026-09-21 19:45:00+05:30', 14, 'FAILED',           0.150, TRUE,  150),
    ('2026-09-21 22:20:00+05:30', 14, 'UNDER_MAINTENANCE',0.500, FALSE, NULL),
    ('2026-09-21 21:10:00+05:30', 5,  'DEGRADED',         0.450, TRUE,  40),
    ('2026-09-21 22:35:00+05:30', 3,  'UNDER_MAINTENANCE',0.300, FALSE, NULL),
    ('2026-09-21 22:35:00+05:30', 6,  'UNDER_MAINTENANCE',0.350, FALSE, NULL);

INSERT INTO execution_records (block_id, actual_start, actual_end, completed_jobs, notes, recorded_by) VALUES
    (2, '2026-09-21 20:05:00+05:30', '2026-09-21 22:20:00+05:30', '[6]'::jsonb, 'Emergency rail-fracture repair at RAIL-DD-SUR-01 completed within extended window; speed restriction applied afterward pending follow-up inspection.', 'u6');

INSERT INTO rerouting_decisions (train_id, event_id, blocked_track_id, original_route_id, alternate_route_id, reroute_time, additional_distance_km, additional_travel_time_minutes, additional_delay_minutes, reason, accepted, decided_by, decided_at) VALUES
    (5, 4, 6, 1, 2, '2026-09-22 00:50:00+05:30', 0.00, 0, 18, 'Track 6 (KJT-LNL UP) occupied by integrated maintenance block BUNDLE-1-2-3 until 01:30; rerouted onto the DOWN line to avoid a 60+ minute wait.', TRUE, 'Control Office - Karjat Section Controller', '2026-09-22 00:52:00+05:30');

INSERT INTO audit_logs (entity_type, entity_id, action, actor_id, role, reason) VALUES
    ('BLOCK',   1,  'APPROVE', 'u1', 'SECTION_CONTROLLER', 'Bundled ENG+TRD+SNT possession approved; train impact acceptable (max 18 min).'),
    ('BLOCK',   2,  'APPROVE', 'u2', 'SECTION_CONTROLLER', 'Emergency possession auto-escalated and approved.'),
    ('REQUEST', 11, 'REJECT',  'u3', 'BDMS_INCHARGE', 'Branch-line single track window conflicts with scheduled Panvel local/goods traffic; resubmit for a later window.'),
    ('REROUTE', 1,  'OVERRIDE','u1', 'SECTION_CONTROLLER', 'Accepted AI-proposed reroute for Konark Express onto the DOWN line rather than a 60+ minute wait.');

-- ---------------------------------------------------------------
-- Reset every sequence to continue past the explicit IDs above, so the
-- next app-generated INSERT (without an explicit id) doesn't collide.
-- ---------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('departments','department_id'),               (SELECT COALESCE(MAX(department_id),1) FROM departments));
SELECT setval(pg_get_serial_sequence('stations','station_id'),                     (SELECT COALESCE(MAX(station_id),1) FROM stations));
SELECT setval(pg_get_serial_sequence('sections','section_id'),                     (SELECT COALESCE(MAX(section_id),1) FROM sections));
SELECT setval(pg_get_serial_sequence('tracks','track_id'),                         (SELECT COALESCE(MAX(track_id),1) FROM tracks));
SELECT setval(pg_get_serial_sequence('assets','asset_id'),                         (SELECT COALESCE(MAX(asset_id),1) FROM assets));
SELECT setval(pg_get_serial_sequence('resources','resource_id'),                   (SELECT COALESCE(MAX(resource_id),1) FROM resources));
SELECT setval(pg_get_serial_sequence('resource_availability','id'),                (SELECT COALESCE(MAX(id),1) FROM resource_availability));
SELECT setval(pg_get_serial_sequence('trains','train_id'),                         (SELECT COALESCE(MAX(train_id),1) FROM trains));
SELECT setval(pg_get_serial_sequence('train_movements','movement_id'),             (SELECT COALESCE(MAX(movement_id),1) FROM train_movements));
SELECT setval(pg_get_serial_sequence('train_routes','route_id'),                   (SELECT COALESCE(MAX(route_id),1) FROM train_routes));
SELECT setval(pg_get_serial_sequence('goods_forecast','forecast_id'),              (SELECT COALESCE(MAX(forecast_id),1) FROM goods_forecast));
SELECT setval(pg_get_serial_sequence('maintenance_jobs','job_id'),                 (SELECT COALESCE(MAX(job_id),1) FROM maintenance_jobs));
SELECT setval(pg_get_serial_sequence('block_requests','request_id'),               (SELECT COALESCE(MAX(request_id),1) FROM block_requests));
SELECT setval(pg_get_serial_sequence('job_resources','id'),                        (SELECT COALESCE(MAX(id),1) FROM job_resources));
SELECT setval(pg_get_serial_sequence('job_dependencies','id'),                     (SELECT COALESCE(MAX(id),1) FROM job_dependencies));
SELECT setval(pg_get_serial_sequence('compatibility_edges','id'),                  (SELECT COALESCE(MAX(id),1) FROM compatibility_edges));
SELECT setval(pg_get_serial_sequence('maintenance_history','id'),                  (SELECT COALESCE(MAX(id),1) FROM maintenance_history));
SELECT setval(pg_get_serial_sequence('track_availability','availability_id'),      (SELECT COALESCE(MAX(availability_id),1) FROM track_availability));
SELECT setval(pg_get_serial_sequence('optimization_runs','run_id'),                (SELECT COALESCE(MAX(run_id),1) FROM optimization_runs));
SELECT setval(pg_get_serial_sequence('schedule_versions','version_id'),            (SELECT COALESCE(MAX(version_id),1) FROM schedule_versions));
SELECT setval(pg_get_serial_sequence('blocks','block_id'),                         (SELECT COALESCE(MAX(block_id),1) FROM blocks));
SELECT setval(pg_get_serial_sequence('block_jobs','id'),                           (SELECT COALESCE(MAX(id),1) FROM block_jobs));
SELECT setval(pg_get_serial_sequence('block_trains','id'),                         (SELECT COALESCE(MAX(id),1) FROM block_trains));
SELECT setval(pg_get_serial_sequence('realtime_events','event_id'),                (SELECT COALESCE(MAX(event_id),1) FROM realtime_events));
SELECT setval(pg_get_serial_sequence('train_live_status','id'),                    (SELECT COALESCE(MAX(id),1) FROM train_live_status));
SELECT setval(pg_get_serial_sequence('track_live_status','id'),                    (SELECT COALESCE(MAX(id),1) FROM track_live_status));
SELECT setval(pg_get_serial_sequence('asset_live_status','id'),                    (SELECT COALESCE(MAX(id),1) FROM asset_live_status));
SELECT setval(pg_get_serial_sequence('execution_records','id'),                    (SELECT COALESCE(MAX(id),1) FROM execution_records));
SELECT setval(pg_get_serial_sequence('rerouting_decisions','decision_id'),         (SELECT COALESCE(MAX(decision_id),1) FROM rerouting_decisions));
SELECT setval(pg_get_serial_sequence('audit_logs','id'),                           (SELECT COALESCE(MAX(id),1) FROM audit_logs));

COMMIT;