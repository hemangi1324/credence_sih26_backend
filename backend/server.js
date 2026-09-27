const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const dotenv = require('dotenv');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');

dotenv.config({ path: path.join(__dirname, '../.env') });

const app = express();
const port = process.env.PORT || 5000;

app.use(cors({
    origin: [process.env.FRONTEND_URL, 'http://localhost:5173'].filter(Boolean)
}));
app.use(express.json());

// ── DB connection (use individual fields to handle special chars in password) ──
const pool = new Pool({
    host: process.env.DB_HOST || process.env.POSTGRES_HOST,
    port: parseInt(process.env.DB_PORT || process.env.POSTGRES_PORT || '5432'),
    database: process.env.DB_NAME || process.env.POSTGRES_DB,
    user: process.env.DB_USER || process.env.POSTGRES_USER,
    password: process.env.DB_PASSWORD || process.env.POSTGRES_PASSWORD,
    ...(process.env.DB_SSL === 'true' ? { ssl: { rejectUnauthorized: false } } : {})
});

// ── Pipeline cache ────────────────────────────────────────────────────────────
let cachedPlanningResult = null;
const CACHE_FILE = path.join(__dirname, 'pipeline_cache.json');
let fallbackData = { jobs: [] };

try {
    if (fs.existsSync(path.join(__dirname, 'fallbackData.json'))) {
        fallbackData = JSON.parse(fs.readFileSync(path.join(__dirname, 'fallbackData.json'), 'utf8'));
    }
} catch(e) {}

if (fs.existsSync(CACHE_FILE)) {
    try {
        cachedPlanningResult = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
        console.log('Loaded planning result from cache file.');
    } catch (err) {
        console.error('Error reading cache file:', err.message);
    }
}

// ── Bootstrap DB tables ───────────────────────────────────────────────────────
async function bootstrapDB() {
    try {
        await pool.query(`
            CREATE TABLE IF NOT EXISTS block_status_log (
                id SERIAL PRIMARY KEY,
                block_id VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                approved_by VARCHAR(128),
                notes TEXT,
                modified_start_time VARCHAR(10),
                modified_end_time VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW()
            );

            DROP TABLE IF EXISTS block_requests CASCADE;
            CREATE TABLE block_requests (
                id VARCHAR(32) PRIMARY KEY,
                department VARCHAR(64) NOT NULL,
                maintenance_type VARCHAR(128) NOT NULL,
                track VARCHAR(64) NOT NULL,
                asset VARCHAR(128) NOT NULL,
                preferred_date VARCHAR(20),
                requested_duration INTEGER,
                preferred_window_start VARCHAR(10),
                preferred_window_end VARCHAR(10),
                required_manpower INTEGER DEFAULT 5,
                machinery TEXT,
                priority VARCHAR(20) DEFAULT 'Medium',
                safety_buffer BOOLEAN DEFAULT TRUE,
                depends_on_job BOOLEAN DEFAULT FALSE,
                requires_isolation BOOLEAN DEFAULT FALSE,
                notes TEXT,
                submitted_by VARCHAR(128),
                submitted_at TIMESTAMP DEFAULT NOW(),
                status VARCHAR(32) DEFAULT 'DEMANDED'
            );

            CREATE TABLE IF NOT EXISTS block_execution (
                id SERIAL PRIMARY KEY,
                block_id VARCHAR(64) NOT NULL,
                status VARCHAR(32) DEFAULT 'NOT_STARTED',
                progress INTEGER DEFAULT 0,
                actual_start TIMESTAMP,
                actual_end TIMESTAMP,
                crew INTEGER DEFAULT 0,
                notes TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS live_events (
                id VARCHAR(64) PRIMARY KEY,
                type VARCHAR(64) NOT NULL,
                severity VARCHAR(20) NOT NULL,
                title VARCHAR(256) NOT NULL,
                description TEXT,
                location VARCHAR(128),
                status VARCHAR(32) DEFAULT 'OPEN',
                affected_trains TEXT[],
                affected_blocks TEXT[],
                estimated_resolution TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        `);
        console.log('DB tables bootstrapped successfully.');
    } catch (e) {
        console.error('Error bootstrapping DB tables:', e.message);
    }
}
bootstrapDB();

// ─────────────────────────────────────────────────────────────────────────────
// USERS API
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/users', async (req, res) => {
    try {
        const result = await pool.query('SELECT user_id, name, role, department_id FROM users');
        res.json(result.rows);
    } catch (e) {
        console.error('Error fetching users:', e.message);
        res.status(500).json({ error: 'Failed to fetch users' });
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// HELPER: get latest block status from DB (overrides pipeline cache status)
// ─────────────────────────────────────────────────────────────────────────────
async function getBlockStatusOverrides() {
    try {
        // Get the latest status per block_id from block_status_log
        const result = await pool.query(`
            SELECT DISTINCT ON (block_id) block_id, status, approved_by, notes, modified_start_time, modified_end_time, created_at
            FROM block_status_log
            ORDER BY block_id, created_at DESC
        `);
        const map = {};
        for (const row of result.rows) {
            map[row.block_id] = row;
        }
        return map;
    } catch (e) {
        return {};
    }
}

// ── Helper: merge pipeline blocks with DB status overrides ───────────────────
async function getEnrichedBlocks() {
    const blocks = cachedPlanningResult?.schedule || [];
    const overrides = await getBlockStatusOverrides();
    return blocks.map(b => {
        const ov = overrides[b.id];
        if (ov) {
            return {
                ...b,
                status: ov.status,
                approvedBy: ov.approved_by,
                approvalNotes: ov.notes,
                startTime: ov.modified_start_time || b.startTime,
                endTime: ov.modified_end_time || b.endTime,
            };
        }
        return b;
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// ENDPOINTS
// ─────────────────────────────────────────────────────────────────────────────

// HEALTH CHECK
app.get('/api/health', async (req, res) => {
    let dbStatus = 'disconnected';
    try {
        const r = await pool.query('SELECT 1');
        if (r.rowCount > 0) dbStatus = 'connected';
    } catch (e) {
        console.error('DB Health Check Failed:', e.message);
    }
    res.json({ status: 'ok', database: dbStatus, algorithms: 'available' });
});

// USERS
app.get('/api/users', async (req, res) => {
    try {
        const result = await pool.query('SELECT user_id, name, role, department_id FROM users ORDER BY name');
        res.json(result.rows);
    } catch (e) {
        console.error('Error fetching users:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// ── DASHBOARD ─────────────────────────────────────────────────────────────────
app.get('/api/dashboard', async (req, res) => {
    const blocks = await getEnrichedBlocks();
    const pendingApprovals = blocks.filter(b => b.status === 'AI-OPTIMIZED' || b.status === 'PROPOSED').length;
    const approvedBlocks = blocks.filter(b => b.status === 'APPROVED').length;

    if (cachedPlanningResult && cachedPlanningResult.summary) {
        return res.json({
            maintenanceJobs: cachedPlanningResult.summary.jobs || 0,
            highPriorityJobs: cachedPlanningResult.summary.high_priority_jobs || 0,
            scheduledJobs: cachedPlanningResult.summary.scheduled || 0,
            deferredJobs: cachedPlanningResult.summary.deferred || 0,
            candidateBlocks: cachedPlanningResult.summary.candidate_blocks || 0,
            selectedBlocks: cachedPlanningResult.summary.selected_blocks || 0,
            approvedBlocks,
            pendingApprovals,
            affectedTrains: cachedPlanningResult.summary.affected_trains || 0,
            totalTrainDelay: cachedPlanningResult.summary.total_train_delay || 0,
            priorityWeightedImpact: cachedPlanningResult.summary.priority_weighted_impact || 0,
            source: cachedPlanningResult.source || 'cached_result'
        });
    }
    res.json({
        maintenanceJobs: 38, highPriorityJobs: 12, scheduledJobs: 24, deferredJobs: 14,
        candidateBlocks: 38, selectedBlocks: 24, approvedBlocks, pendingApprovals,
        affectedTrains: 6, totalTrainDelay: 976, priorityWeightedImpact: 3281,
        source: 'synthetic_fallback'
    });
});

// ── MAINTENANCE JOBS ──────────────────────────────────────────────────────────
app.get('/api/jobs', async (req, res) => {
    try {
        const result = await pool.query(`
            SELECT
                job_id as id, asset_id as asset, department,
                maintenance_type as "maintenanceType", track_id as track,
                location_station_id, duration as "estimatedDuration",
                criticality, urgency, asset_risk as "assetRisk",
                overdue_days as "overdueDays", operational_impact as "operationalImpact",
                priority_score as "priorityScore", priority_category as priority,
                job_status as status, due_date as "dueDate",
                required_manpower as "requiredManpower", machinery, notes
            FROM maintenance_jobs
            ORDER BY priority_score DESC NULLS LAST
        `);
        const jobs = result.rows.map(r => ({ ...r, dependencies: [] }));
        res.json(jobs);
    } catch (e) {
        console.error('DB query failed for /api/jobs:', e.message);
        const fallbackJobs = (fallbackData.jobs || []).map(j => ({
            id: j.job_id, asset: j.asset_id, department: j.department,
            maintenanceType: j.maintenance_type, track: j.track_id,
            location_station_id: j.location_station_id,
            estimatedDuration: j.duration_min || j.duration,
            criticality: j.criticality, urgency: j.urgency,
            assetRisk: j.asset_risk, overdueDays: j.overdue_days,
            operationalImpact: j.operational_impact,
            priorityScore: j.priority_score || (Math.random() * 0.5 + 0.3).toFixed(4),
            priority: j.priority_category || (j.criticality > 3 ? 'HIGH' : 'MEDIUM'),
            status: j.job_status, dueDate: j.due_date || "2026-08-30",
            requiredManpower: j.required_manpower || 5,
            machinery: j.machinery || 'N/A', notes: j.notes || '', dependencies: []
        }));
        res.json(fallbackJobs);
    }
});

// ── JOB DETAILS ───────────────────────────────────────────────────────────────
app.get('/api/jobs/:id', async (req, res) => {
    try {
        const result = await pool.query(`
            SELECT
                job_id as id, asset_id as asset, department,
                maintenance_type as "maintenanceType", track_id as track,
                location_station_id, duration as "estimatedDuration",
                criticality, urgency, asset_risk as "assetRisk",
                overdue_days as "overdueDays", operational_impact as "operationalImpact",
                priority_score as "priorityScore", priority_category as priority,
                job_status as status, due_date as "dueDate",
                required_manpower as "requiredManpower", machinery, notes
            FROM maintenance_jobs WHERE job_id = $1
        `, [req.params.id]);
        if (result.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
        res.json({ ...result.rows[0], dependencies: [] });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── BLOCKS LIST (with DB status overrides) ────────────────────────────────────
app.get('/api/blocks', async (req, res) => {
    const blocks = await getEnrichedBlocks();
    if (blocks.length > 0) return res.json(blocks);
    res.json([]);
});

// ── BLOCK DETAIL (with joined job details) ────────────────────────────────────
app.get('/api/blocks/:id', async (req, res) => {
    const blocks = await getEnrichedBlocks();
    const block = blocks.find(b => b.id === req.params.id);
    if (!block) return res.status(404).json({ error: 'Block not found' });

    // Join job details from DB
    let jobDetails = [];
    if (block.jobIds && block.jobIds.length > 0) {
        try {
            const placeholders = block.jobIds.map((_, i) => `$${i + 1}`).join(',');
            const jobResult = await pool.query(`
                SELECT
                    job_id as id, asset_id as asset, department,
                    maintenance_type as "maintenanceType", track_id as track,
                    location_station_id, duration as "estimatedDuration",
                    criticality, urgency, asset_risk as "assetRisk",
                    overdue_days as "overdueDays", operational_impact as "operationalImpact",
                    priority_score as "priorityScore", priority_category as priority,
                    job_status as status, due_date as "dueDate",
                    required_manpower as "requiredManpower", machinery, notes
                FROM maintenance_jobs WHERE job_id IN (${placeholders})
            `, block.jobIds);
            jobDetails = jobResult.rows.map(r => ({ ...r, dependencies: [] }));
        } catch (e) {
            console.error('Failed to join job details for block:', e.message);
        }
    }

    // Build whyThisSlot from job data
    const whyThisSlot = [
        `Scheduled during low-traffic window (${block.startTime}–${block.endTime})`,
        `${block.departments?.join(' + ')} jobs are spatially compatible on ${block.track}`,
        block.jobIds?.length > 1 ? `Bundling ${block.jobIds.length} jobs reduces repeated track possession` : 'Optimal time slot with minimal train conflict',
        `Train impact score: ${block.trainImpact ?? 0} minutes`,
        'Safety buffer requirements satisfied by CP-SAT solver',
    ];

    // Build alternatives from the block's time window (derived)
    const [startH, startM] = (block.startTime || '23:00:00').split(':').map(Number);
    const alternatives = [
        {
            label: 'Option A (Recommended)',
            startTime: block.startTime?.substring(0,5) || '23:00',
            endTime: block.endTime?.substring(0,5) || '02:00',
            delay: block.trainImpact ?? 0,
            recommended: true,
        },
        {
            label: 'Option B (+2h later)',
            startTime: `${String((startH + 2) % 24).padStart(2,'0')}:${String(startM).padStart(2,'0')}`,
            endTime: `${String((startH + 2 + Math.ceil((block.duration || 60)/60)) % 24).padStart(2,'0')}:${String(startM).padStart(2,'0')}`,
            delay: (block.trainImpact ?? 0) + 30,
            recommended: false,
        },
        {
            label: 'Option C (Next day)',
            startTime: block.startTime?.substring(0,5) || '23:00',
            endTime: block.endTime?.substring(0,5) || '02:00',
            delay: (block.trainImpact ?? 0) + 60,
            recommended: false,
        },
    ];

    res.json({
        ...block,
        jobDetails,
        whyThisSlot,
        alternatives,
        safetyBuffer: 10,
        bundled: (block.jobIds?.length || 0) > 1,
        bundledCount: block.jobIds?.length || 1,
        resources: {
            manpower: jobDetails.reduce((sum, j) => sum + (j.requiredManpower || 5), 0),
            machinery: [...new Set(jobDetails.map(j => j.machinery).filter(Boolean))],
            available: true,
        },
        affectedTrains: (cachedPlanningResult?.train_impact || [])
            .filter(t => t.train_impact > 0)
            .slice(0, 3)
            .map(t => ({
                trainNumber: t.train_id,
                action: 'WAIT',
                delay: t.delay || 0,
                reroutingStatus: t.rerouted ? 'ACCEPTED' : 'NOT_REQUIRED',
            })),
        section: block.track?.split('-').slice(1).join('-') || 'Unknown',
        createdAt: new Date().toISOString(),
        optimizationSource: 'CP-SAT',
        assetBenefit: block.priority > 0.6 ? 'High' : block.priority > 0.4 ? 'Medium' : 'Low',
        operationalImpact: block.trainImpact > 50 ? 'High' : block.trainImpact > 10 ? 'Medium' : 'Low',
        expectedDelay: block.trainImpact || 0,
    });
});

// ── APPROVE / REJECT / MODIFY BLOCK ──────────────────────────────────────────
app.patch('/api/blocks/:id/status', async (req, res) => {
    const { status, approvedBy, notes, modifiedStartTime, modifiedEndTime, actor_id } = req.body;
    const validStatuses = ['APPROVED', 'REJECTED', 'MODIFIED', 'PROPOSED', 'AI-OPTIMIZED'];
    if (!status || !validStatuses.includes(status)) {
        return res.status(400).json({ error: 'Invalid status. Must be one of: ' + validStatuses.join(', ') });
    }
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        
        await client.query(`
            INSERT INTO block_status_log (block_id, status, approved_by, notes, modified_start_time, modified_end_time)
            VALUES ($1, $2, $3, $4, $5, $6)
        `, [req.params.id, status, approvedBy || 'Section Controller', notes || null, modifiedStartTime || null, modifiedEndTime || null]);
        
        if (actor_id) {
            const userRes = await client.query('SELECT role FROM users WHERE user_id = $1', [actor_id]);
            const role = userRes.rows[0]?.role || 'UNKNOWN';
            let action = status === 'APPROVED' ? 'APPROVE' : (status === 'REJECTED' ? 'REJECT' : 'MODIFY');
            
            await client.query(`
                INSERT INTO audit_logs (entity_type, entity_id, action, actor_id, role, reason)
                VALUES ($1, $2, $3, $4, $5, $6)
            `, ['BLOCK', 0, action, actor_id, role, notes || `Status changed to ${status}`]);
        }

        await client.query('COMMIT');

        // Also update in cache so next read reflects change immediately
        if (cachedPlanningResult?.schedule) {
            cachedPlanningResult.schedule = cachedPlanningResult.schedule.map(b =>
                b.id === req.params.id ? { ...b, status, approvedBy: approvedBy || 'Section Controller' } : b
            );
            fs.writeFileSync(CACHE_FILE, JSON.stringify(cachedPlanningResult, null, 2));
        }

        res.json({ success: true, blockId: req.params.id, status, approvedBy: approvedBy || 'Section Controller' });
    } catch (e) {
        await client.query('ROLLBACK');
        console.error('Error updating block status:', e.message);
        res.status(500).json({ error: e.message });
    } finally {
        client.release();
    }
});

// ── SCHEDULE ──────────────────────────────────────────────────────────────────
app.get('/api/schedule', async (req, res) => {
    const blocks = await getEnrichedBlocks();
    res.json({
        blocks,
        deferredJobs: cachedPlanningResult?.deferred_jobs || []
    });
});

// ── TRAINS ────────────────────────────────────────────────────────────────────
app.get('/api/trains', async (req, res) => {
    if (cachedPlanningResult && cachedPlanningResult.train_impact) {
        return res.json(cachedPlanningResult.train_impact.map(t => ({
            id: t.train_id,
            number: t.train_id,
            name: t.train_type ? `${t.train_type} ${t.train_id}` : `Train ${t.train_id}`,
            type: t.train_type || 'Express',
            delay: t.delay || 0,
            currentStatus: t.feasible === false ? 'DELAYED' : (t.delay > 60 ? 'DELAYED' : 'ON_TIME'),
            reroutingStatus: t.rerouted ? 'ACCEPTED' : 'NONE',
            baselineArrival: t.baseline_arrival || '',
            newArrival: t.new_arrival || '',
            currentSection: t.route ? t.route[0] : 'Unknown',
            affectedBlockId: t.affected_block || null,
            reroutingEligible: (t.delay || 0) > 30,
            scheduledArrival: t.baseline_arrival || '',
            scheduledDeparture: t.baseline_arrival || '',
            originalRoute: t.route ? t.route.slice(0,-1).map((s, i) => ({
                from: s, to: t.route[i+1], track: 'N/A', duration: 0
            })) : [],
            currentRoute: t.route ? t.route.slice(0,-1).map((s, i) => ({
                from: s, to: t.route[i+1], track: 'N/A', duration: 0
            })) : [],
            scheduledOccupation: [],
        })));
    }
    const fallbackTrains = (fallbackData.trains || []).map(t => ({
        id: t.train_id, number: t.train_id,
        name: t.train_type ? `${t.train_type} ${t.train_id}` : `Train ${t.train_id}`,
        type: t.train_type || 'Express', delay: 0,
        currentStatus: 'ON_TIME', reroutingStatus: 'NONE',
        currentSection: 'Unknown', reroutingEligible: false,
        originalRoute: [], currentRoute: [], scheduledOccupation: [],
    }));
    res.json(fallbackTrains);
});

// ── ANALYTICS ─────────────────────────────────────────────────────────────────
app.get('/api/analytics', async (req, res) => {
    if (cachedPlanningResult && cachedPlanningResult.analytics) {
        return res.json(cachedPlanningResult.analytics);
    }
    res.json({
        jobsByDepartment: {},
        scheduledVsDeferred: { scheduled: 0, deferred: 0 },
        trainDelayDistribution: [],
        overdueTrend: [
            { date: 'Aug 01', value: 24 }, { date: 'Aug 07', value: 21 },
            { date: 'Aug 14', value: 18 }, { date: 'Aug 21', value: 11 },
            { date: 'Aug 28', value: 6 }
        ],
        disruptions: [
            { type: 'Track failures', events: 14, avgRecoveryMin: 45 },
            { type: 'Block overruns', events: 8, avgRecoveryMin: 30 },
            { type: 'Train delays', events: 22, avgRecoveryMin: 15 },
            { type: 'Signal faults', events: 11, avgRecoveryMin: 20 }
        ]
    });
});

// ── BLOCK REQUESTS ────────────────────────────────────────────────────────────
app.post('/api/requests', async (req, res) => {
    const {
        department, maintenanceType, track, asset, preferredDate,
        requestedDuration, preferredWindowStart, preferredWindowEnd,
        requiredManpower, machinery, priority, safetyBuffer,
        dependsOnJob, requiresIsolation, notes, actor_id
    } = req.body;

    if (!department || !maintenanceType || !track || !asset) {
        return res.status(400).json({ error: 'Missing required fields: department, maintenanceType, track, asset' });
    }

    const id = `REQ-${Date.now().toString(36).toUpperCase()}`;
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        await client.query(`
            INSERT INTO block_requests (
                id, department, maintenance_type, track, asset, preferred_date,
                requested_duration, preferred_window_start, preferred_window_end,
                required_manpower, machinery, priority, safety_buffer,
                depends_on_job, requires_isolation, notes, submitted_by, status
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,'DEMANDED')
        `, [id, department, maintenanceType, track, asset, preferredDate,
            requestedDuration || 60, preferredWindowStart || '22:00', preferredWindowEnd || '04:00',
            requiredManpower || 5, machinery || 'N/A', priority || 'Medium',
            safetyBuffer !== false, dependsOnJob || false, requiresIsolation || false,
            notes || '', actor_id || null]);
            
        if (actor_id) {
            const userRes = await client.query('SELECT role FROM users WHERE user_id = $1', [actor_id]);
            const role = userRes.rows[0]?.role || 'UNKNOWN';
            
            await client.query(`
                INSERT INTO audit_logs (entity_type, entity_id, action, actor_id, role, reason)
                VALUES ($1, $2, $3, $4, $5, $6)
            `, ['REQUEST', 0, 'CREATE', actor_id, role, 'Block request submitted']);
        }
            
        await client.query('COMMIT');

        res.json({
            id, department, maintenanceType, track, asset, status: 'DEMANDED',
            submittedAt: new Date().toISOString(), submittedBy: actor_id
        });
    } catch (e) {
        await client.query('ROLLBACK');
        console.error('Error saving block request:', e.message);
        res.status(500).json({ error: e.message });
    } finally {
        client.release();
    }
});

app.get('/api/requests', async (req, res) => {
    try {
        const result = await pool.query(`
            SELECT id, department, maintenance_type as "maintenanceType", track, asset,
                   preferred_date as "preferredDate", requested_duration as "requestedDuration",
                   preferred_window_start as "preferredWindowStart", preferred_window_end as "preferredWindowEnd",
                   required_manpower as "requiredManpower", machinery, priority,
                   safety_buffer as "safetyBuffer", depends_on_job as "dependsOnJob",
                   requires_isolation as "requiresIsolation", notes, submitted_by as "submittedBy",
                   submitted_at as "submittedAt", status
            FROM block_requests
            ORDER BY submitted_at DESC
        `);
        res.json(result.rows);
    } catch (e) {
        console.error('Error fetching block requests:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// ── LIVE EVENTS ───────────────────────────────────────────────────────────────
app.get('/api/events', async (req, res) => {
    // Return stored events from DB
    try {
        const dbResult = await pool.query(`
            SELECT id, type, severity, title, description, location,
                   status, affected_trains as "affectedTrains",
                   affected_blocks as "affectedBlocks",
                   estimated_resolution as "estimatedResolution",
                   created_at as "timestamp"
            FROM live_events
            WHERE status != 'RESOLVED'
            ORDER BY created_at DESC
            LIMIT 20
        `);

        // Derive synthetic events from current train delays if no real events exist
        let events = dbResult.rows.map(e => ({
            ...e,
            affectedTrains: e.affectedTrains || [],
            affectedBlocks: e.affectedBlocks || [],
            systemImpact: {
                trainsAffected: (e.affectedTrains || []).length,
                blocksOverrunning: (e.affectedBlocks || []).length,
                routeRecalculations: 1,
                safetyViolations: 0
            },
            timeline: [
                { time: new Date(e.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }), description: e.description, isAlert: true },
                { time: 'Auto', description: 'System monitoring active', isAlert: false }
            ]
        }));

        // Also derive events from high-delay trains in pipeline
        if (cachedPlanningResult?.train_impact) {
            const highDelayTrains = cachedPlanningResult.train_impact.filter(t => (t.delay || 0) > 60);
            if (highDelayTrains.length > 0 && events.length === 0) {
                const trainIds = highDelayTrains.map(t => t.train_id);
                const now = new Date();
                events.push({
                    id: 'EV-SYS-001',
                    type: 'TRAIN_DELAY',
                    severity: highDelayTrains.some(t => t.delay > 120) ? 'HIGH' : 'MEDIUM',
                    title: `${highDelayTrains.length} train(s) with significant delay`,
                    description: `Trains ${trainIds.slice(0,3).join(', ')} are delayed by 60+ minutes due to scheduled maintenance blocks.`,
                    location: 'NGP-BSL Corridor',
                    status: 'OPEN',
                    timestamp: now.toISOString(),
                    affectedTrains: trainIds,
                    affectedBlocks: cachedPlanningResult.schedule?.filter(b => b.trainImpact > 60).map(b => b.id) || [],
                    systemImpact: {
                        trainsAffected: highDelayTrains.length,
                        blocksOverrunning: 0,
                        routeRecalculations: highDelayTrains.length,
                        safetyViolations: 0,
                    },
                    timeline: [
                        { time: now.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' }), description: `${highDelayTrains.length} trains showing delay > 60 min`, isAlert: true },
                        { time: 'Auto', description: 'Pipeline analysis detected delay pattern', isAlert: false },
                    ]
                });
            }
        }

        res.json(events);
    } catch (e) {
        console.error('Error fetching events:', e.message);
        res.json([]);
    }
});

app.post('/api/events', async (req, res) => {
    const { id, type, severity, title, description, location, affectedTrains, affectedBlocks } = req.body;
    const eventId = id || `EV-${Date.now().toString(36).toUpperCase()}`;
    try {
        await pool.query(`
            INSERT INTO live_events (id, type, severity, title, description, location, affected_trains, affected_blocks)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE SET status = 'OPEN', updated_at = NOW()
        `, [eventId, type, severity, title, description, location,
            affectedTrains || [], affectedBlocks || []]);
        res.json({ id: eventId, status: 'OPEN' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.patch('/api/events/:id/status', async (req, res) => {
    const { status } = req.body;
    try {
        await pool.query('UPDATE live_events SET status=$1, updated_at=NOW() WHERE id=$2', [status, req.params.id]);
        res.json({ success: true });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── FIELD EXECUTION ───────────────────────────────────────────────────────────
app.get('/api/field/active-block', async (req, res) => {
    // Return the most recently approved block that is not yet completed
    const blocks = await getEnrichedBlocks();
    const approved = blocks.filter(b => b.status === 'APPROVED');

    if (approved.length === 0) {
        return res.status(404).json({ error: 'No approved block available for field execution' });
    }

    const block = approved[0];

    // Get execution state from DB if it exists
    let execState = { status: 'NOT_STARTED', progress: 0 };
    try {
        const execResult = await pool.query(
            'SELECT status, progress, actual_start, actual_end, crew, notes FROM block_execution WHERE block_id=$1 ORDER BY id DESC LIMIT 1',
            [block.id]
        );
        if (execResult.rows.length > 0) execState = execResult.rows[0];
    } catch (e) {}

    // Fetch job details
    let jobDetails = [];
    if (block.jobIds && block.jobIds.length > 0) {
        try {
            const placeholders = block.jobIds.map((_, i) => `$${i + 1}`).join(',');
            const jobResult = await pool.query(`
                SELECT job_id as id, department, maintenance_type as "maintenanceType",
                       asset_id as asset, required_manpower as "requiredManpower", machinery
                FROM maintenance_jobs WHERE job_id IN (${placeholders})
            `, block.jobIds);
            jobDetails = jobResult.rows.map(j => ({
                department: j.department,
                description: j.maintenanceType,
                tasks: [
                    `Prepare equipment for ${j.maintenanceType}`,
                    `Execute ${j.maintenanceType} on ${j.asset}`,
                    `Verify completion and safety clearance`,
                    `Submit completion report`,
                ]
            }));
        } catch (e) {}
    }

    if (jobDetails.length === 0) {
        jobDetails = [{
            department: block.departments?.[0] || 'Engineering',
            description: 'Maintenance Work',
            tasks: ['Prepare site', 'Execute maintenance', 'Safety check', 'Report completion']
        }];
    }

    res.json({
        blockId: block.id,
        track: block.track,
        location: block.track,
        startTime: block.startTime || '',
        endTime: block.endTime || '',
        status: execState.status || 'NOT_STARTED',
        progress: execState.progress || 0,
        actualStart: execState.actual_start || null,
        actualEnd: execState.actual_end || null,
        crew: execState.crew || jobDetails.reduce((sum, _) => sum + 5, 0),
        machinery: block.departments?.join(', ') || 'N/A',
        safetyBuffer: 10,
        jobs: jobDetails,
    });
});

app.patch('/api/field/:blockId/progress', async (req, res) => {
    const { progress, status, crew, notes, actor_id } = req.body;
    const { blockId } = req.params;
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        // Upsert execution record
        await client.query(`
            INSERT INTO block_execution (block_id, progress, status, crew, notes, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT DO NOTHING
        `, [blockId, progress || 0, status || 'IN_PROGRESS', crew || 0, notes || '']);

        await client.query(`
            UPDATE block_execution SET progress=$2, status=$3, updated_at=NOW()
            WHERE block_id=$1
        `, [blockId, progress || 0, status || 'IN_PROGRESS']);
        
        if (actor_id) {
            const userRes = await client.query('SELECT role FROM users WHERE user_id = $1', [actor_id]);
            const role = userRes.rows[0]?.role || 'UNKNOWN';
            
            await client.query(`
                INSERT INTO audit_logs (entity_type, entity_id, action, actor_id, role, reason)
                VALUES ($1, $2, $3, $4, $5, $6)
            `, ['BLOCK', 0, 'MODIFY', actor_id, role, `Field progress updated to ${progress}%`]);
        }

        await client.query('COMMIT');

        res.json({ success: true, blockId, progress, status });
    } catch (e) {
        await client.query('ROLLBACK');
        console.error('Error updating field progress:', e.message);
        res.status(500).json({ error: e.message });
    } finally {
        client.release();
    }
});

app.post('/api/field/:blockId/start', async (req, res) => {
    const { blockId } = req.params;
    try {
        await pool.query(`
            INSERT INTO block_execution (block_id, status, progress, actual_start, updated_at)
            VALUES ($1, 'IN_PROGRESS', 0, NOW(), NOW())
            ON CONFLICT DO NOTHING
        `, [blockId]);
        await pool.query(`
            UPDATE block_execution SET status='IN_PROGRESS', actual_start=NOW(), updated_at=NOW()
            WHERE block_id=$1
        `, [blockId]);
        // Mark block as ACTIVE
        await pool.query(`
            INSERT INTO block_status_log (block_id, status, approved_by, notes)
            VALUES ($1, 'ACTIVE', 'Field Team', 'Work started')
        `, [blockId]);
        if (cachedPlanningResult?.schedule) {
            cachedPlanningResult.schedule = cachedPlanningResult.schedule.map(b =>
                b.id === blockId ? { ...b, status: 'ACTIVE' } : b
            );
            fs.writeFileSync(CACHE_FILE, JSON.stringify(cachedPlanningResult, null, 2));
        }
        res.json({ success: true, blockId, status: 'IN_PROGRESS' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.post('/api/field/:blockId/complete', async (req, res) => {
    const { blockId } = req.params;
    try {
        await pool.query(`
            UPDATE block_execution SET status='COMPLETED', progress=100, actual_end=NOW(), updated_at=NOW()
            WHERE block_id=$1
        `, [blockId]);
        // Mark block as COMPLETED in status log
        await pool.query(`
            INSERT INTO block_status_log (block_id, status, approved_by, notes)
            VALUES ($1, 'COMPLETED', 'Field Team', 'Work completed in field')
        `, [blockId]);
        if (cachedPlanningResult?.schedule) {
            cachedPlanningResult.schedule = cachedPlanningResult.schedule.map(b =>
                b.id === blockId ? { ...b, status: 'COMPLETED' } : b
            );
            fs.writeFileSync(CACHE_FILE, JSON.stringify(cachedPlanningResult, null, 2));
        }
        res.json({ success: true, blockId, status: 'COMPLETED' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.post('/api/field/:blockId/issue', async (req, res) => {
    const { blockId } = req.params;
    const { issueType, notes } = req.body;
    try {
        await pool.query(`
            INSERT INTO live_events (id, type, severity, title, description, location, affected_blocks, status)
            VALUES ($1, 'TRACK_FAILURE', 'HIGH', $2, $3, $4, $5, 'OPEN')
        `, [
            `EV-FIELD-${Date.now().toString(36).toUpperCase()}`,
            `Field Issue: ${issueType}`,
            `${issueType} reported during block execution. ${notes || ''}`,
            blockId,
            [blockId]
        ]);
        res.json({ success: true, blockId, issueType });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── PLANNING PIPELINE ─────────────────────────────────────────────────────────
app.post('/api/planning/run', (req, res) => {
    const pythonPath = process.env.PYTHON_PATH || 'python';
    const algoDir = process.env.ALGORITHM_DIR || '../src/algorithms';
    const scriptPath = path.resolve(__dirname, algoDir, 'run_pipeline.py');

    console.log(`Executing Python script: ${pythonPath} ${scriptPath}`);

    execFile(pythonPath, [scriptPath], { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
        if (error) {
            console.error('Python execution error:', error.message);
            let fallbackResult = cachedPlanningResult || {
                status: "success", source: "synthetic_fallback",
                summary: { jobs: 38, scheduled: 24, deferred: 14, selected_blocks: 24, total_train_delay: 976, affected_trains: 6 },
                schedule: [], train_impact: [], deferred_jobs: []
            };
            return res.json(fallbackResult);
        }
        try {
            const jsonStart = stdout.indexOf('{');
            const jsonEnd = stdout.lastIndexOf('}');
            if (jsonStart === -1 || jsonEnd === -1) throw new Error("No JSON found in Python output");
            const jsonStr = stdout.substring(jsonStart, jsonEnd + 1);
            const result = JSON.parse(jsonStr);
            result.source = 'live_pipeline';
            cachedPlanningResult = result;
            fs.writeFileSync(CACHE_FILE, JSON.stringify(result, null, 2));
            res.json(result);
        } catch (parseError) {
            console.error('Error parsing Python output:', parseError.message);
            res.status(500).json({ status: 'error', message: 'Failed to parse algorithm output' });
        }
    });
});

app.listen(port, () => {
    console.log(`Backend server running on port ${port}`);
});
