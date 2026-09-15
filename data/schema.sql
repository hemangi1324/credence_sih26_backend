-- =====================================================================
-- Automatic Block Planning — PostgreSQL + PostGIS schema (SIH26027)
-- Corrected / extended edition.
-- =====================================================================
--
-- WHAT CHANGED FROM THE PREVIOUS schema.sql (and why):
--
--  1. Added `block_requests` — the BDMS layer. Your own README (Sec. 2)
--     and updated_SIH_summary_DOC (Sec. 4.5) both insist Maintenance Job
--     ≠ Block Request ≠ Optimized Block as three distinct entities. The
--     old schema only had job -> block, silently collapsing the middle
--     entity.
--  2. Added `track_availability` — COA corridor/block availability. R1
--     explicitly requires ingesting this; there was no table for it at
--     all.
--  3. Added `train_live_status`, `track_live_status`, `asset_live_status`
--     — the real-time monitoring layer (README Sec. 18; TDD Sec. 33
--     "Live state") had nowhere to live. `realtime_events` is an
--     event LOG; it cannot answer "what is Track B's status right now",
--     which ALNS/A* need on every re-optimization.
--  4. Added `train_routes` + `rerouting_decisions` — a reroute produced
--     by Time-Dependent A* had nowhere to go that didn't overwrite the
--     original timetable in `train_movements`.
--  5. `maintenance_jobs` gained the actual inputs the priority formula
--     (TDD Sec. 13) needs — asset_risk, operational_impact,
--     safety_factor — plus writeback columns (priority_score,
--     priority_band, priority_explanation, priority_computed_at) so the
--     dashboard doesn't recompute on every read, while the raw inputs
--     stay the source of truth for re-derivation/audit.
--  6. `assets` gained criticality, failure_count, last/next maintenance
--     dates, failure_probability, availability_pct, current_status —
--     fields your own Sec. 9 job-schema JSON example already assumes
--     exist (`asset.criticality: 0.95`).
--  7. `trains` gained origin/destination, scheduled departure/arrival,
--     max_allowed_delay_minutes, can_be_rerouted, max_speed_kmph.
--  8. The track/time EXCLUDE constraint on `blocks` is now LIVE, not a
--     comment. This was the single biggest gap: your db-design notes
--     say overlap should be "enforced ... as a database-level exclusion
--     constraint" but the last version left it disabled, so nothing in
--     the database actually stopped a double-booking.
--  9. Added CHECK constraints on every normalized 0..1 score. A stray
--     4.2 or -0.5 in criticality/urgency/risk would silently corrupt
--     both the priority ranking and CP-SAT's objective — worth catching
--     at insert time, not at demo time.
-- 10. `goods_forecast` now separates goods vs. passenger counts and adds
--     forecast_confidence — a single flat `expected_trains` can't feed
--     the priority engine's train-dependency term or CP-SAT's
--     disruption-cost estimate.
-- 11. `job_dependencies` gained dependency_type + minimum_gap_minutes —
--     "isolation before work" and a plain finish-to-start precedence
--     are not the same constraint to CP-SAT.
-- 12. `compatibility_edges` now enforces job_a_id < job_b_id so a
--     symmetric pair is never stored twice in opposite order.
-- 13. Status / impact columns (`maintenance_jobs.status`,
--     `blocks.status`, `block_requests.request_status`,
--     `block_trains.impact_type`, `track_availability.status`) have
--     named CHECK constraints. A typo ('Open' vs 'OPEN') or an invented
--     state is rejected at insert time instead of silently desyncing
--     the planner (`WHERE status = 'OPEN'` would otherwise re-plan work
--     that is already SCHEDULED or COMPLETED).
-- 14. The blocks EXCLUDE constraint still stops two live blocks from
--     overlapping on one track. A BEFORE INSERT/UPDATE trigger on both
--     `train_movements` and `blocks` additionally forbids a scheduled
--     train from occupying a track that an active block is holding
--     (CANCELLED/REJECTED blocks are ignored). EXCLUDE cannot express
--     a cross-table invariant, so this is the hard integrity backstop:
--     the optimiser must reroute the train or move the block *before*
--     persisting. `v_job_block_status_mismatch` makes job/block status
--     desync queryable for CI / health checks.
--
-- GRAPH LAYER — where the "graph db" actually lives:
-- There is deliberately NO separate graph database here. Every edge the
-- algorithms need is already a foreign key in this schema:
--   TRAIN -travels_through-> SECTION     train_movements
--   JOB   -located_on->      ASSET       maintenance_jobs.asset_id
--   JOB   -belongs_to->      SECTION     maintenance_jobs.section_id
--   JOB   -requires->        RESOURCE    job_resources
--   JOB   -depends_on->      JOB         job_dependencies
--   JOB   -candidate_for->   BLOCK       compatibility_edges / block_jobs
--   BLOCK -affects->         TRAIN       block_trains
--   BLOCK -located_on->      SECTION     blocks.section_id
-- At optimizer runtime, the Python services build a NetworkX graph in
-- memory FROM these tables (one query per solve, cached) instead of
-- maintaining a second, independently-synced graph store — exactly what
-- your own Tech Stack table (TDD Sec. 32) specifies ("NetworkX for graph
-- prototyping"). Reach for Neo4j/a persisted graph DB only if you
-- outgrow "rebuild the graph from Postgres on each solve" — not before;
-- two sources of truth is a bug generator, not an architecture upgrade.
--
-- sections vs. tracks (deliberate split, not the doc's flat
-- track_sections): `sections` is the station-to-station GRAPH EDGE used
-- by A*/TDSP; `tracks` is the physical UP/DOWN/LOOP/SIDING line within
-- that edge, used by CP-SAT's track-exclusivity constraint. Your own
-- README Sec. 6.1 requires exclusivity on "the SAME TRACK" — that only
-- works if track is a distinct row from section, so this split stays.
--
-- Foreign keys default to RESTRICT (no ON DELETE CASCADE anywhere). For
-- a safety-critical scheduling system you want a delete on a parent row
-- to fail loudly, not silently fan out through blocks/audit history.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- needed for EXCLUDE ... USING gist on non-range types

-- Generic trigger to keep updated_at current on rows that get revised
-- after insert (jobs, requests, blocks, assets).
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------
-- 1. Reference / master data
-- ---------------------------------------------------------------

CREATE TABLE departments (
    department_id   SERIAL PRIMARY KEY,
    code            VARCHAR(10) UNIQUE NOT NULL,     -- ENG, SNT, TRD
    name            VARCHAR(100) NOT NULL
);

CREATE TABLE stations (
    station_id          SERIAL PRIMARY KEY,
    code                VARCHAR(10) UNIQUE NOT NULL,
    name                VARCHAR(100) NOT NULL,
    station_type        VARCHAR(20) NOT NULL DEFAULT 'HALT',  -- JUNCTION, TERMINAL, HALT, YARD
    num_platforms       SMALLINT DEFAULT 1,
    num_sidings         SMALLINT DEFAULT 0,
    platform_capacity   SMALLINT DEFAULT 1,                   -- trains that can berth simultaneously
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    geom                GEOGRAPHY(POINT, 4326)
);

-- A section is an EDGE in the railway graph (station -> station).
CREATE TABLE sections (
    section_id      SERIAL PRIMARY KEY,
    code            VARCHAR(20) UNIQUE NOT NULL,
    from_station_id INTEGER NOT NULL REFERENCES stations(station_id),
    to_station_id   INTEGER NOT NULL REFERENCES stations(station_id),
    division        VARCHAR(50),
    distance_km     NUMERIC(6,2) NOT NULL,
    travel_minutes  INTEGER NOT NULL,                 -- nominal night-running time; priority/optimizer
                                                        -- services key off this directly rather than
                                                        -- deriving per-track from distance/max_speed, so
                                                        -- it stays a plain, join-free lookup column.
    geom            GEOGRAPHY(LINESTRING, 4326),       -- PostGIS chainage geometry
    CHECK (from_station_id <> to_station_id)
);

CREATE TABLE tracks (
    track_id        SERIAL PRIMARY KEY,
    section_id      INTEGER NOT NULL REFERENCES sections(section_id),
    line            VARCHAR(20) NOT NULL,             -- UP / DOWN / LOOP / SIDING / YARD
    track_type      VARCHAR(20) NOT NULL DEFAULT 'MAIN',  -- MAIN, LOOP, SIDING, YARD
    start_km        NUMERIC(6,2),
    end_km          NUMERIC(6,2),
    max_speed_kmph  INTEGER,
    capacity        SMALLINT NOT NULL DEFAULT 1,      -- simultaneous trains this line can hold
                                                        -- (1 for a plain single line; sidings/yards > 1)
    electrified     BOOLEAN NOT NULL DEFAULT TRUE,
    signalling_type VARCHAR(30)                        -- ABSOLUTE_BLOCK, AUTOMATIC, TRACK_CIRCUIT, ...
);

CREATE TABLE assets (
    asset_id                SERIAL PRIMARY KEY,
    asset_code              VARCHAR(30) UNIQUE NOT NULL,
    asset_type              VARCHAR(30) NOT NULL,             -- TRACK, SIGNAL, OHE, POINT, ...
    department_id           INTEGER REFERENCES departments(department_id),
    section_id              INTEGER REFERENCES sections(section_id),
    track_id                INTEGER REFERENCES tracks(track_id),
    station_id              INTEGER REFERENCES stations(station_id),  -- for point assets (signal /
                                                                        -- interlocking gear) not tied
                                                                        -- to a linear chainage
    start_km                NUMERIC(6,2),
    end_km                  NUMERIC(6,2),
    install_date            DATE,
    condition_score         NUMERIC(4,3) CHECK (condition_score BETWEEN 0 AND 1),      -- latest known health
    criticality              NUMERIC(4,3) CHECK (criticality BETWEEN 0 AND 1),          -- asset-level importance,
                                                                                         -- independent of any one job
    failure_count            INTEGER NOT NULL DEFAULT 0,
    last_maintenance_date    DATE,
    next_maintenance_due     DATE,
    failure_probability      NUMERIC(4,3) CHECK (failure_probability BETWEEN 0 AND 1),
    availability_pct         NUMERIC(4,3) CHECK (availability_pct BETWEEN 0 AND 1),
    current_status           VARCHAR(20) NOT NULL DEFAULT 'OK',  -- OK, DEGRADED, FAILED, UNDER_MAINTENANCE
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (section_id IS NOT NULL OR track_id IS NOT NULL OR station_id IS NOT NULL)
);
CREATE TRIGGER trg_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE resources (
    resource_id             SERIAL PRIMARY KEY,
    resource_type           VARCHAR(30) NOT NULL,             -- CREW, TAMPING_MACHINE, OHE_VAN, ...
    department_id           INTEGER REFERENCES departments(department_id),
    name                    VARCHAR(100),
    home_base_station_id    INTEGER REFERENCES stations(station_id),
    capacity                INTEGER NOT NULL DEFAULT 1,
    current_status          VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'  -- AVAILABLE, IN_USE, OUT_OF_SERVICE
);

CREATE TABLE resource_availability (
    id              SERIAL PRIMARY KEY,
    resource_id     INTEGER NOT NULL REFERENCES resources(resource_id),
    available_from  TIMESTAMPTZ NOT NULL,
    available_to    TIMESTAMPTZ NOT NULL,
    CHECK (available_to > available_from)
);

-- ---------------------------------------------------------------
-- 2. Train operations
-- ---------------------------------------------------------------

CREATE TABLE trains (
    train_id                    SERIAL PRIMARY KEY,
    train_number                VARCHAR(10) UNIQUE NOT NULL,
    train_name                  VARCHAR(100),
    train_type                  VARCHAR(20) NOT NULL,             -- PASSENGER, EXPRESS, GOODS
    priority_class               SMALLINT NOT NULL DEFAULT 3,       -- 1 = highest (e.g. Rajdhani) .. 5 lowest
    origin_station_id            INTEGER REFERENCES stations(station_id),
    destination_station_id       INTEGER REFERENCES stations(station_id),
    scheduled_departure          TIMESTAMPTZ,
    scheduled_arrival            TIMESTAMPTZ,
    max_allowed_delay_minutes    INTEGER NOT NULL DEFAULT 15,       -- soft-constraint tolerance used by
                                                                     -- the A*/CP-SAT cost function
    can_be_rerouted               BOOLEAN NOT NULL DEFAULT TRUE,
    max_speed_kmph                INTEGER
);

-- Section-by-section scheduled occupation (NOT "Mumbai -> Pune" as one
-- row). This is the "train_timetable" of the design docs — required to
-- detect precise per-section conflicts with a candidate block.
CREATE TABLE train_movements (
    movement_id             SERIAL PRIMARY KEY,
    train_id                INTEGER NOT NULL REFERENCES trains(train_id),
    section_id              INTEGER NOT NULL REFERENCES sections(section_id),
    track_id                INTEGER REFERENCES tracks(track_id),
    scheduled_entry         TIMESTAMPTZ NOT NULL,
    scheduled_exit          TIMESTAMPTZ NOT NULL,
    scheduled_run_time_minutes INTEGER GENERATED ALWAYS AS (
        ROUND(EXTRACT(EPOCH FROM (scheduled_exit - scheduled_entry)) / 60)::INTEGER
    ) STORED,
    sequence_no             INTEGER NOT NULL,                 -- order of this section in the train's route
    night_index             SMALLINT NOT NULL DEFAULT 0,       -- which night of the weekly/monthly horizon
                                                                -- this run belongs to (0 = nearest night);
                                                                -- see the app layer's horizon-compression
                                                                -- logic (nights modelled back-to-back,
                                                                -- skipping idle daytime hours).
    CHECK (scheduled_exit > scheduled_entry)
);

-- The currently-active (possibly rerouted) version of each train's path,
-- kept separate from the original timetable in train_movements so a
-- reroute never overwrites the baseline plan it's being compared against.
CREATE TABLE train_routes (
    route_id        SERIAL PRIMARY KEY,
    train_id        INTEGER NOT NULL REFERENCES trains(train_id),
    route_version   INTEGER NOT NULL DEFAULT 1,
    sequence_no     INTEGER NOT NULL,
    section_id      INTEGER NOT NULL REFERENCES sections(section_id),
    track_id        INTEGER REFERENCES tracks(track_id),
    planned_entry   TIMESTAMPTZ NOT NULL,
    planned_exit    TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (planned_exit > planned_entry),
    UNIQUE (train_id, route_version, sequence_no)
);

CREATE TABLE goods_forecast (
    forecast_id                 SERIAL PRIMARY KEY,
    section_id                   INTEGER NOT NULL REFERENCES sections(section_id),
    track_id                     INTEGER REFERENCES tracks(track_id),
    window_start                  TIMESTAMPTZ NOT NULL,       -- doc's date + time_slot_start/end folded into
    window_end                    TIMESTAMPTZ NOT NULL,       -- one range, consistent with every other
                                                                -- availability window in this schema
    expected_goods_trains         INTEGER NOT NULL DEFAULT 0,
    expected_passenger_trains     INTEGER NOT NULL DEFAULT 0,
    expected_total_trains         INTEGER GENERATED ALWAYS AS (
        expected_goods_trains + expected_passenger_trains
    ) STORED,
    forecast_confidence           NUMERIC(4,3) CHECK (forecast_confidence BETWEEN 0 AND 1),
    CHECK (window_end > window_start)
);

-- ---------------------------------------------------------------
-- 3. Maintenance demand (normalized from TMS / SMMS / TDMS)
-- ---------------------------------------------------------------

CREATE TABLE maintenance_jobs (
    job_id                              SERIAL PRIMARY KEY,
    source_system                       VARCHAR(10) NOT NULL,   -- TMS, SMMS, TDMS
    department_id                       INTEGER NOT NULL REFERENCES departments(department_id),
    asset_id                            INTEGER NOT NULL REFERENCES assets(asset_id),
    section_id                          INTEGER NOT NULL REFERENCES sections(section_id),
    track_id                            INTEGER REFERENCES tracks(track_id),
    start_km                            NUMERIC(6,2),
    end_km                              NUMERIC(6,2),
    defect_type                         VARCHAR(50),
    maintenance_type                    VARCHAR(30),               -- INSPECTION, REPAIR, REPLACEMENT, ...
    severity                            SMALLINT NOT NULL CHECK (severity BETWEEN 1 AND 5),
    criticality                         NUMERIC(4,3) NOT NULL CHECK (criticality BETWEEN 0 AND 1),
    urgency                             NUMERIC(4,3) NOT NULL CHECK (urgency BETWEEN 0 AND 1),
    asset_risk                          NUMERIC(4,3) CHECK (asset_risk BETWEEN 0 AND 1),      -- raw/manual
                                                                                                -- risk input
    predicted_risk                      NUMERIC(4,3) CHECK (predicted_risk BETWEEN 0 AND 1),   -- filled by
                                                                                                -- XGBoost/RF
    overdue_days                        INTEGER NOT NULL DEFAULT 0,
    condition_score                     NUMERIC(4,3) CHECK (condition_score BETWEEN 0 AND 1),
    operational_impact                  NUMERIC(4,3) CHECK (operational_impact BETWEEN 0 AND 1),  -- asset-
                                                                                                     -- availability /
                                                                                                     -- train-dependency
                                                                                                     -- impact, normalized
    safety_factor                       NUMERIC(4,3) CHECK (safety_factor BETWEEN 0 AND 1),
    estimated_duration_minutes          INTEGER NOT NULL,
    safety_buffer_minutes               INTEGER NOT NULL DEFAULT 15,
    required_block_type                 VARCHAR(20),               -- TOTAL, PARTIAL, CORRIDOR, POWER_BLOCK
    required_manpower                   INTEGER NOT NULL DEFAULT 1,
    power_block_required                BOOLEAN NOT NULL DEFAULT FALSE,
    signalling_disconnection_required   BOOLEAN NOT NULL DEFAULT FALSE,
    earliest_start                      TIMESTAMPTZ,
    latest_start                        TIMESTAMPTZ,
    status                              VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    -- Written back by the priority service (TDD Sec. 13). The inputs
    -- above stay the single source of truth, so a score is always
    -- re-derivable/auditable rather than trusted blindly.
    priority_score                      NUMERIC(6,4),
    priority_band                       VARCHAR(10),               -- CRITICAL, HIGH, MEDIUM, LOW
    priority_explanation                JSONB,
    priority_computed_at                TIMESTAMPTZ,
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (latest_start IS NULL OR earliest_start IS NULL OR latest_start >= earliest_start),
    CONSTRAINT chk_jobs_status CHECK (status IN (
        'OPEN','SCHEDULED','IN_PROGRESS','COMPLETED','DEFERRED','CANCELLED'
    ))
);
CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON maintenance_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The BDMS layer: a department's ASK for infrastructure access so a job
-- can happen. Kept separate from maintenance_jobs (the demand) and from
-- blocks (the optimizer's granted supply) — see README Sec. 2.
CREATE TABLE block_requests (
    request_id                  SERIAL PRIMARY KEY,
    job_id                       INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    department_id                 INTEGER NOT NULL REFERENCES departments(department_id),
    track_id                      INTEGER NOT NULL REFERENCES tracks(track_id),
    requested_date                 DATE NOT NULL,
    requested_start                TIMESTAMPTZ NOT NULL,
    requested_end                  TIMESTAMPTZ NOT NULL,
    minimum_duration_minutes        INTEGER NOT NULL,
    preferred_start                 TIMESTAMPTZ,
    preferred_end                   TIMESTAMPTZ,
    safety_buffer_minutes            INTEGER NOT NULL DEFAULT 15,
    request_priority                 SMALLINT,                   -- department's own pre-optimizer ranking
    request_status                   VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (requested_end > requested_start),
    CONSTRAINT chk_block_requests_status CHECK (request_status IN (
        'PENDING','GRANTED','REJECTED','WITHDRAWN'
    ))
);
CREATE TRIGGER trg_requests_updated_at BEFORE UPDATE ON block_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE job_resources (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    resource_id     INTEGER NOT NULL REFERENCES resources(resource_id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    UNIQUE (job_id, resource_id)
);

CREATE TABLE job_dependencies (
    id                      SERIAL PRIMARY KEY,
    job_id                   INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    depends_on_job            INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    dependency_type            VARCHAR(30) NOT NULL DEFAULT 'FINISH_TO_START',  -- e.g. ISOLATION_BEFORE_WORK
    minimum_gap_minutes         INTEGER NOT NULL DEFAULT 0,
    CHECK (job_id <> depends_on_job)
);

-- Precomputed / cached compatibility candidates between two jobs.
CREATE TABLE compatibility_edges (
    id              SERIAL PRIMARY KEY,
    job_a_id        INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    job_b_id        INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    spatial_ok      BOOLEAN NOT NULL,
    temporal_ok     BOOLEAN NOT NULL,
    safety_ok       BOOLEAN NOT NULL,
    resource_ok     BOOLEAN NOT NULL,
    compatible      BOOLEAN NOT NULL,
    reason          TEXT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_a_id, job_b_id),
    CHECK (job_a_id < job_b_id)   -- store each unordered pair exactly once
);

CREATE TABLE maintenance_history (
    id                          SERIAL PRIMARY KEY,
    asset_id                     INTEGER NOT NULL REFERENCES assets(asset_id),
    job_id                        INTEGER REFERENCES maintenance_jobs(job_id),
    maintenance_date               DATE,
    maintenance_type                VARCHAR(30),
    demanded_at                      TIMESTAMPTZ,
    granted                          BOOLEAN,
    actual_start                     TIMESTAMPTZ,
    actual_end                       TIMESTAMPTZ,
    planned_duration_minutes          INTEGER,
    actual_duration_minutes           INTEGER,
    work_completed                    BOOLEAN,
    result                            VARCHAR(20),               -- COMPLETED, PARTIAL, ABORTED
    failure_found                     BOOLEAN,
    condition_before                  NUMERIC(4,3) CHECK (condition_before BETWEEN 0 AND 1),
    condition_after                   NUMERIC(4,3) CHECK (condition_after BETWEEN 0 AND 1),
    output_score                      NUMERIC(4,3) CHECK (output_score BETWEEN 0 AND 1)  -- "block
                                                                                            -- productivity":
                                                                                            -- useful output /
                                                                                            -- actual duration
);

-- COA: corridor/track availability windows, independent of any one job.
-- The optimizer's candidate time-windows come from intersecting this
-- with resource_availability and train_movements/goods_forecast.
CREATE TABLE track_availability (
    availability_id SERIAL PRIMARY KEY,
    track_id        INTEGER NOT NULL REFERENCES tracks(track_id),
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',
    capacity        SMALLINT DEFAULT 1,
    reason          VARCHAR(100),
    CHECK (window_end > window_start),
    CONSTRAINT chk_track_avail_status CHECK (status IN (
        'AVAILABLE','BLOCKED','RESTRICTED'
    ))
);

-- ---------------------------------------------------------------
-- 4. Blocks / plans (the optimizer's output)
-- ---------------------------------------------------------------

CREATE TABLE optimization_runs (
    run_id          SERIAL PRIMARY KEY,
    horizon         VARCHAR(10) NOT NULL,        -- WEEKLY, MONTHLY, WHATIF
    triggered_by    VARCHAR(50),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    objective_cost  NUMERIC(12,3),
    solver_status   VARCHAR(20),                 -- OPTIMAL, FEASIBLE, INFEASIBLE
    notes           TEXT
);

CREATE TABLE schedule_versions (
    version_id      SERIAL PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES optimization_runs(run_id),
    parent_version  INTEGER REFERENCES schedule_versions(version_id),
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE blocks (
    block_id                SERIAL PRIMARY KEY,
    version_id               INTEGER NOT NULL REFERENCES schedule_versions(version_id),
    unit_id                   VARCHAR(60),                      -- links back to the scheduling unit/bundle
                                                                   -- (app-layer optimizer) that produced this
                                                                   -- block; a bundled possession looks like
                                                                   -- "BUNDLE-<job_id>-<job_id>".
    section_id                INTEGER NOT NULL REFERENCES sections(section_id),
    track_id                  INTEGER REFERENCES tracks(track_id),
    start_km                  NUMERIC(6,2),
    end_km                    NUMERIC(6,2),
    planned_start              TIMESTAMPTZ NOT NULL,
    planned_end                TIMESTAMPTZ NOT NULL,
    block_type                 VARCHAR(20) NOT NULL DEFAULT 'MAINTENANCE',
    status                     VARCHAR(20) NOT NULL DEFAULT 'PROPOSED',
    priority_score              NUMERIC(6,3),
    utilization                 NUMERIC(4,3) CHECK (utilization BETWEEN 0 AND 1),
    conflict_cost                NUMERIC(12,3),                  -- priority-weighted train-disruption cost
                                                                   -- the optimizer minimized this block's
                                                                   -- start against
    expected_train_delay_min     INTEGER NOT NULL DEFAULT 0,
    asset_benefit                 NUMERIC(12,3),
    resource_cost                 NUMERIC(12,3),
    objective_cost                NUMERIC(12,3),
    explanation                   JSONB,                          -- ["Low passenger traffic", ...]
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (planned_end > planned_start),
    CONSTRAINT chk_blocks_status CHECK (status IN (
        'PROPOSED','APPROVED','REJECTED','EXECUTING','DONE','CANCELLED'
    )),
    -- Real, enforced double-booking guard: no track may be occupied by
    -- two live blocks at once. This is the exclusion constraint your own
    -- db-design notes call for — it was left as a comment before, so
    -- nothing in the database actually stopped an overlap.
    EXCLUDE USING gist (
        track_id WITH =,
        tstzrange(planned_start, planned_end) WITH &&
    ) WHERE (status NOT IN ('CANCELLED', 'REJECTED') AND track_id IS NOT NULL)
);
CREATE TRIGGER trg_blocks_updated_at BEFORE UPDATE ON blocks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE block_jobs (
    id              SERIAL PRIMARY KEY,
    block_id        INTEGER NOT NULL REFERENCES blocks(block_id),
    job_id          INTEGER NOT NULL REFERENCES maintenance_jobs(job_id),
    UNIQUE (block_id, job_id)
);

-- Traceability: which BDMS-style requests did this block actually
-- satisfy? (a bundled block can fulfil several requests at once)
CREATE TABLE block_requests_fulfilled (
    block_id        INTEGER NOT NULL REFERENCES blocks(block_id),
    request_id      INTEGER NOT NULL REFERENCES block_requests(request_id),
    PRIMARY KEY (block_id, request_id)
);

CREATE TABLE block_trains (
    id              SERIAL PRIMARY KEY,
    block_id        INTEGER NOT NULL REFERENCES blocks(block_id),
    train_id        INTEGER NOT NULL REFERENCES trains(train_id),
    impact_type     VARCHAR(20) NOT NULL,
    delay_minutes   INTEGER NOT NULL DEFAULT 0,
    original_route  JSONB,
    new_route       JSONB,
    UNIQUE (block_id, train_id),
    CONSTRAINT chk_block_trains_impact CHECK (impact_type IN (
        'NONE','WAIT','REROUTE','CANCELLED'
    ))
);

-- Cross-table guard: a train may not occupy a track that an active
-- block is holding (and vice versa). Enforced from BOTH sides so the
-- invariant holds no matter which row is written first. CANCELLED /
-- REJECTED blocks are ignored — they are not holding the track.
-- This is a hard integrity guard for the *planned* timetable. The
-- optimiser must resolve a conflict BEFORE writing (move the block, or
-- reroute the train onto another track and update
-- train_movements.track_id). The trigger is the backstop that
-- guarantees an unresolved conflict can never be silently persisted.
CREATE OR REPLACE FUNCTION assert_no_train_block_conflict()
RETURNS TRIGGER AS $$
DECLARE
    conflict_rec RECORD;
BEGIN
    IF TG_TABLE_NAME = 'train_movements' THEN
        IF NEW.track_id IS NULL THEN
            RETURN NEW;
        END IF;
        SELECT b.block_id, b.planned_start, b.planned_end, b.status
          INTO conflict_rec
          FROM blocks b
         WHERE b.track_id = NEW.track_id
           AND b.status NOT IN ('CANCELLED','REJECTED')
           AND tstzrange(b.planned_start, b.planned_end)
               && tstzrange(NEW.scheduled_entry, NEW.scheduled_exit)
         LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION
                'Train movement (train_id=%, track_id=%, % to %) conflicts with block_id=% (% to %, status=%). Reroute the train or move the block before persisting.',
                NEW.train_id, NEW.track_id, NEW.scheduled_entry, NEW.scheduled_exit,
                conflict_rec.block_id, conflict_rec.planned_start, conflict_rec.planned_end, conflict_rec.status
                USING ERRCODE = 'exclusion_violation';
        END IF;

    ELSIF TG_TABLE_NAME = 'blocks' THEN
        IF NEW.track_id IS NULL OR NEW.status IN ('CANCELLED','REJECTED') THEN
            RETURN NEW;
        END IF;
        SELECT tm.movement_id, tm.train_id, tm.scheduled_entry, tm.scheduled_exit
          INTO conflict_rec
          FROM train_movements tm
         WHERE tm.track_id = NEW.track_id
           AND tstzrange(tm.scheduled_entry, tm.scheduled_exit)
               && tstzrange(NEW.planned_start, NEW.planned_end)
         LIMIT 1;

        IF FOUND THEN
            RAISE EXCEPTION
                'Block (track_id=%, % to %) conflicts with scheduled train movement_id=% (train_id=%, % to %). Reroute the train or move the block before persisting.',
                NEW.track_id, NEW.planned_start, NEW.planned_end,
                conflict_rec.movement_id, conflict_rec.train_id,
                conflict_rec.scheduled_entry, conflict_rec.scheduled_exit
                USING ERRCODE = 'exclusion_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_train_movement_block_conflict
    BEFORE INSERT OR UPDATE ON train_movements
    FOR EACH ROW EXECUTE FUNCTION assert_no_train_block_conflict();

CREATE TRIGGER trg_block_train_movement_conflict
    BEFORE INSERT OR UPDATE ON blocks
    FOR EACH ROW EXECUTE FUNCTION assert_no_train_block_conflict();

-- Job status vs the status of the block holding it. The planner selects
-- work with `WHERE status = 'OPEN'`; a DONE/APPROVED block whose job is
-- still OPEN would be re-planned. This view makes the mismatch trivially
-- queryable in CI or a health check.
CREATE OR REPLACE VIEW v_job_block_status_mismatch AS
SELECT mj.job_id,
       mj.status        AS job_status,
       b.block_id,
       b.status         AS block_status,
       CASE
           WHEN b.status = 'DONE'      AND mj.status <> 'COMPLETED'   THEN 'job should be COMPLETED'
           WHEN b.status = 'EXECUTING' AND mj.status <> 'IN_PROGRESS' THEN 'job should be IN_PROGRESS'
           WHEN b.status = 'APPROVED'  AND mj.status <> 'SCHEDULED'   THEN 'job should be SCHEDULED'
           WHEN b.status = 'PROPOSED'  AND mj.status NOT IN ('OPEN','SCHEDULED') THEN 'job should be OPEN or SCHEDULED'
       END AS expected
FROM maintenance_jobs mj
JOIN block_jobs bj ON bj.job_id  = mj.job_id
JOIN blocks     b  ON b.block_id = bj.block_id
WHERE CASE
          WHEN b.status = 'DONE'      AND mj.status <> 'COMPLETED'   THEN TRUE
          WHEN b.status = 'EXECUTING' AND mj.status <> 'IN_PROGRESS' THEN TRUE
          WHEN b.status = 'APPROVED'  AND mj.status <> 'SCHEDULED'   THEN TRUE
          WHEN b.status = 'PROPOSED'  AND mj.status NOT IN ('OPEN','SCHEDULED') THEN TRUE
          ELSE FALSE
      END;

-- ---------------------------------------------------------------
-- 5. Real-time / monitoring / audit
--    (append-only / time-series style, per your db-design notes: these
--    support the continuous planned-vs-actual comparison, so the
--    services INSERT a new timestamped snapshot rather than UPDATE.)
-- ---------------------------------------------------------------

CREATE TABLE realtime_events (
    event_id                    SERIAL PRIMARY KEY,
    event_type                   VARCHAR(30) NOT NULL,  -- TRACK_FAILURE, SIGNAL_FAILURE, OHE_FAILURE,
                                                          -- TRAIN_DELAY, TRAIN_BREAKDOWN, BLOCK_OVERRUN,
                                                          -- EQUIPMENT_FAILURE, EMERGENCY_MAINTENANCE,
                                                          -- TRACK_RESTORED
    section_id                   INTEGER REFERENCES sections(section_id),
    track_id                      INTEGER REFERENCES tracks(track_id),
    asset_id                       INTEGER REFERENCES assets(asset_id),
    train_id                       INTEGER REFERENCES trains(train_id),
    job_id                          INTEGER REFERENCES maintenance_jobs(job_id),
    location_station_id              INTEGER REFERENCES stations(station_id),
    severity                         SMALLINT CHECK (severity BETWEEN 1 AND 5),
    estimated_duration_minutes        INTEGER,
    actual_duration_minutes            INTEGER,
    status                             VARCHAR(20) NOT NULL DEFAULT 'OPEN',  -- OPEN, RESOLVED
    source                              VARCHAR(30),                        -- which live feed raised this
    payload                             JSONB,
    occurred_at                         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE train_live_status (
    id                  BIGSERIAL PRIMARY KEY,
    ts                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    train_id            INTEGER NOT NULL REFERENCES trains(train_id),
    current_station_id  INTEGER REFERENCES stations(station_id),
    current_section_id  INTEGER REFERENCES sections(section_id),
    current_track_id    INTEGER REFERENCES tracks(track_id),
    position_km         NUMERIC(6,2),
    actual_entry_time   TIMESTAMPTZ,
    expected_exit_time  TIMESTAMPTZ,
    delay_minutes       INTEGER NOT NULL DEFAULT 0,
    status               VARCHAR(20) NOT NULL DEFAULT 'ON_TIME'  -- ON_TIME, DELAYED, HALTED, REROUTED
);

CREATE TABLE track_live_status (
    id                     BIGSERIAL PRIMARY KEY,
    ts                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    track_id               INTEGER NOT NULL REFERENCES tracks(track_id),
    status                  VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE',  -- AVAILABLE, BLOCKED, UNDER_MAINTENANCE
    available_capacity       SMALLINT,
    failure_event_id          INTEGER REFERENCES realtime_events(event_id),
    expected_restore_time      TIMESTAMPTZ
);

CREATE TABLE asset_live_status (
    id                              BIGSERIAL PRIMARY KEY,
    ts                              TIMESTAMPTZ NOT NULL DEFAULT now(),
    asset_id                         INTEGER NOT NULL REFERENCES assets(asset_id),
    status                            VARCHAR(20) NOT NULL DEFAULT 'OK',
    condition_score                   NUMERIC(4,3) CHECK (condition_score BETWEEN 0 AND 1),
    failure_detected                   BOOLEAN NOT NULL DEFAULT FALSE,
    estimated_repair_time_minutes       INTEGER
);

CREATE TABLE execution_records (
    id              SERIAL PRIMARY KEY,
    block_id        INTEGER NOT NULL REFERENCES blocks(block_id),
    actual_start    TIMESTAMPTZ,
    actual_end      TIMESTAMPTZ,
    completed_jobs  JSONB,
    notes           TEXT
);

CREATE TABLE rerouting_decisions (
    decision_id                      SERIAL PRIMARY KEY,
    train_id                          INTEGER NOT NULL REFERENCES trains(train_id),
    event_id                           INTEGER REFERENCES realtime_events(event_id),
    blocked_track_id                    INTEGER REFERENCES tracks(track_id),
    original_route_id                    INTEGER REFERENCES train_routes(route_id),
    alternate_route_id                    INTEGER REFERENCES train_routes(route_id),
    reroute_time                           TIMESTAMPTZ NOT NULL DEFAULT now(),
    additional_distance_km                  NUMERIC(6,2),
    additional_travel_time_minutes           INTEGER,
    additional_delay_minutes                  INTEGER,
    reason                                     TEXT,
    accepted                                    BOOLEAN,
    decided_by                                   VARCHAR(100),
    decided_at                                    TIMESTAMPTZ
);

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(30) NOT NULL,   -- BLOCK, JOB, REQUEST, REROUTE
    entity_id       INTEGER NOT NULL,
    action          VARCHAR(30) NOT NULL,   -- APPROVE, MODIFY, REJECT, OVERRIDE
    actor           VARCHAR(100) NOT NULL,
    role            VARCHAR(30),            -- PLANNER, CONTROL_OFFICE, MANAGEMENT, FIELD
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------
-- 6. OPTIONAL — advanced/Phase 8-10 (GNN-guided ALNS). Not required to
--    run priority scoring, CP-SAT, A* or standard ALNS. Populate only
--    once you actually build the GNN training pipeline (TDD Sec. 20-22).
-- ---------------------------------------------------------------

CREATE TABLE gnn_training_samples (
    sample_id       BIGSERIAL PRIMARY KEY,
    run_id          INTEGER REFERENCES optimization_runs(run_id),
    state_snapshot  JSONB NOT NULL,     -- graph-state features at decision time
    chosen_operator VARCHAR(30),        -- which destroy/repair operator was applied
    reward          NUMERIC(10,4),      -- (C_old - C_new) / C_old
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------
-- Indexes that matter for the optimizer / router hot paths
-- ---------------------------------------------------------------
CREATE INDEX idx_jobs_status         ON maintenance_jobs(status);
CREATE INDEX idx_jobs_section        ON maintenance_jobs(section_id);
CREATE INDEX idx_jobs_priority       ON maintenance_jobs(priority_score DESC);
CREATE INDEX idx_requests_job        ON block_requests(job_id);
CREATE INDEX idx_requests_status     ON block_requests(request_status);
CREATE INDEX idx_blocks_track_time   ON blocks(track_id, planned_start, planned_end);
CREATE INDEX idx_movements_section_t ON train_movements(section_id, scheduled_entry, scheduled_exit);
CREATE INDEX idx_routes_train_active ON train_routes(train_id, is_active);
CREATE INDEX idx_track_avail_track_t ON track_availability(track_id, window_start, window_end);
CREATE INDEX idx_events_time         ON realtime_events(occurred_at);
CREATE INDEX idx_train_live_latest   ON train_live_status(train_id, ts DESC);
CREATE INDEX idx_track_live_latest   ON track_live_status(track_id, ts DESC);
CREATE INDEX idx_asset_live_latest   ON asset_live_status(asset_id, ts DESC);
CREATE INDEX idx_history_asset       ON maintenance_history(asset_id);