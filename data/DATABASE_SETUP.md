# Database Setup — SIH26027 Automatic Block Planning

## TL;DR decision

| Need | Choice | Why |
|---|---|---|
| Main database (everything relational + spatial) | **PostgreSQL + PostGIS** | One database for jobs, trains, blocks, assets, audit logs, *and* the network's geometry. |
| Where to run it | **Supabase or Neon (free tier)** | Managed, nothing to install, works from day one. |
| Graph database (Neo4j etc.) | **Not needed. Don't add one.** | See below — this is the one you were unsure about. |

You do **not** need a separate graph database. Use Postgres for everything, and represent the railway network (stations = nodes, sections = edges) as ordinary rows in the `stations` / `sections` tables. Your backend loads those rows into an in-memory graph (e.g. Python's `networkx`) once at startup and runs Dijkstra / A* / CP-SAT against that in-memory structure. This is not a workaround — it's the standard way small-to-medium operational graphs (hundreds to low thousands of nodes) are handled in practice.

**Why not Neo4j:**
- Your network is small — a handful of stations/sections per division, maybe a few hundred for a full zone. That's tiny for a graph database; it's tiny for a Python list too.
- A separate graph DB means **two databases to keep in sync** (jobs/trains/blocks in Postgres, topology in Neo4j) — more moving parts to explain to judges and more that can break in a demo.
- Your actual algorithms (CP-SAT scheduling, time-dependent A* rerouting) need to run in application memory anyway for speed — they're not naturally expressed as Cypher queries. Neo4j would just become a slower way to fetch the same edge list you'd load into `networkx` regardless.
- Recursive graph queries (e.g. "all stations within 3 hops") *are* expressible in plain Postgres via `WITH RECURSIVE` CTEs, if you ever need that instead of an app-layer traversal.

**If you still want to demo an actual graph database** (e.g. because a judge specifically asked about graph DBs, or you want the visual Neo4j Browser), treat it as a **bonus visualization layer**, not your system of record: keep Postgres as the source of truth, and optionally mirror `stations`/`sections` into a free Neo4j AuraDB instance for a nice graph picture. Setup steps for that are at the bottom of this doc.

---

## What's in this delivery

```
database/
├── schema.sql              # authoritative PostgreSQL + PostGIS DDL — run this first
├── departments.csv         # 3 rows
├── stations.csv            # 6 rows  (Pune–Lonavala–Karjat–Kalyan–Thane–Mumbai CSMT corridor)
├── sections.csv            # 5 rows  (the edges between those stations)
├── tracks.csv               # 10 rows (UP/DOWN track per section)
├── resources.csv            # 7 rows  (machines/crews per department)
├── assets.csv               # 25 rows (physical track/signal/OHE assets)
├── maintenance_jobs.csv     # 25 rows (synthetic TMS/SMMS/TDMS defects, with real computed priority scores)
├── job_resources.csv        # 25 rows (which job needs which resource)
├── trains.csv                # 7 rows  (2 express, 2 passenger, 3 goods)
├── train_movements.csv       # 245 rows (each train's section-by-section timetable, replicated across a 7-night horizon)
├── optimization_runs.csv     # 1 row   (one sample CP-SAT solve)
├── schedule_versions.csv     # 1 row
└── blocks.csv / block_jobs.csv   # 15 blocks / 25 links — a real, feasibility-checked sample weekly plan
```

Every CSV is **real output**, not hand-typed fixtures: it came from running an actual priority-scoring pass and an actual CP-SAT solve (Google OR-Tools) against the synthetic network, so the numbers (priority scores, conflict costs, block timings) are internally consistent with each other and with `schema.sql`.

Two labelling notes on `blocks.csv`:
- `planned_start` / `planned_end` are real ISO timestamps (so they sort/filter normally in SQL).
- `planned_start_label` / `planned_end_label` are human-readable ("N2 03:45" = night 2 of the weekly horizon, 03:45) — convenience columns, drop them if your teammates' backend doesn't want them.

---

## Import order (respects foreign keys)

```
1. departments
2. stations
3. sections
4. tracks
5. resources
6. assets
7. maintenance_jobs
8. job_resources
9. trains
10. train_movements
11. optimization_runs
12. schedule_versions
13. blocks
14. block_jobs
```

---

## Option A — Supabase (recommended if you want a no-code CSV import)

1. Go to **supabase.com** → sign up free → **New Project**. Pick a region close to you (e.g. Mumbai/Singapore), set a database password (save it), wait ~2 minutes for provisioning.
2. Open **SQL Editor** (left sidebar) → **New query**. Paste the entire contents of `schema.sql` → **Run**. This creates every table, and Supabase already ships with the PostGIS extension available, so `CREATE EXTENSION IF NOT EXISTS postgis;` at the top of the script will succeed.
3. Go to **Table Editor** (left sidebar). For each table, in the order above:
   - Click the table name → **Insert** → **Import data from CSV** → upload the matching CSV.
   - Supabase auto-matches columns by name (the CSVs are already named to match `schema.sql`). Leave unmapped columns (like `geom`) blank — they're nullable.
4. Get your connection string: **Project Settings → Database → Connection string** (use the "URI" / pooled connection format). It looks like:
   ```
   postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
   ```
   Hand this to whoever owns the backend as `DATABASE_URL`.

## Option B — Neon (recommended if you want branching / a more "raw Postgres" feel)

1. Go to **neon.tech** → sign up free → **Create a project**. Pick Postgres 16, a nearby region.
2. Open the **SQL Editor** tab in the Neon console → paste `schema.sql` → **Run**. Neon supports the `postgis` extension on the free tier the same way — the `CREATE EXTENSION` line will succeed.
3. Neon's console doesn't have a built-in CSV-upload UI the way Supabase does. Two no-local-install ways to load the CSVs:
   - **Easiest:** open the SQL Editor and use `\copy`-style loading isn't available there, so instead run this from any machine that *does* have `psql` (e.g. a free Replit/Codespaces shell, no install on *your* laptop needed) — get your connection string from **Dashboard → Connection Details**, then:
     ```bash
     psql "postgresql://<user>:<password>@<host>/<db>?sslmode=require" \
       -c "\copy departments FROM 'departments.csv' CSV HEADER"
     # repeat per table, in the import order above
     ```
   - **Or:** run the same import from a throwaway cloud notebook (Google Colab is free and needs no local install) using `psycopg2`:
     ```python
     import psycopg2, csv
     conn = psycopg2.connect("postgresql://<user>:<password>@<host>/<db>?sslmode=require")
     cur = conn.cursor()
     tables_in_order = ["departments", "stations", "sections", "tracks", "resources",
                         "assets", "maintenance_jobs", "job_resources", "trains",
                         "train_movements", "optimization_runs", "schedule_versions",
                         "blocks", "block_jobs"]
     for t in tables_in_order:
         with open(f"{t}.csv") as f:
             cur.copy_expert(f"COPY {t} FROM STDIN WITH CSV HEADER", f)
     conn.commit()
     ```
     Upload the CSVs to the Colab session first (drag-and-drop into the file pane) — nothing touches your laptop.
4. Your `DATABASE_URL` is on the Neon dashboard's **Connection Details** panel.

---

## Verifying the import

Run these in either provider's SQL editor once loaded:

```sql
select (select count(*) from stations) as stations,
       (select count(*) from sections) as sections,
       (select count(*) from maintenance_jobs) as jobs,
       (select count(*) from blocks) as blocks;
-- expect: 6, 5, 25, 15

select b.block_id, sec.code, b.planned_start, b.planned_end, b.priority_score
from blocks b join sections sec on sec.section_id = b.section_id
order by b.planned_start
limit 5;
```

---

## How your backend should use this for the "graph" part

No graph DB calls needed. At startup:

```python
import networkx as nx
import psycopg2

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT section_id, from_station_id, to_station_id, travel_minutes FROM sections")

G = nx.Graph()
for section_id, u, v, minutes in cur.fetchall():
    G.add_edge(u, v, section_id=section_id, weight=minutes)

# now nx.shortest_path(G, source, target, weight="weight") gives the static route,
# and your time-dependent A*/Dijkstra layer runs on top of this same graph object,
# checking each edge's live-blocked windows (pulled from the `blocks` table) at
# traversal time rather than baking them into the graph itself.
```

This is the whole "graph database" for this project. It costs nothing, needs no extra service, and rebuilds itself from Postgres in milliseconds if the topology ever changes.

---

## Optional: mirroring into Neo4j AuraDB Free (only if you want an actual graph DB demo)

1. **neo4j.com/cloud/aura-free** → sign up → create a **Free instance** (no card required, one instance per account, small but plenty for 6 stations/5 edges).
2. Save the generated password and Bolt URL immediately — AuraDB Free only shows the password once.
3. Open the **Neo4j Browser** (link from the Aura console) and run:
   ```cypher
   LOAD CSV WITH HEADERS FROM 'https://<wherever-you-host-the-csv>/stations.csv' AS row
   CREATE (:Station {id: toInteger(row.station_id), code: row.code, name: row.name,
                      lat: toFloat(row.latitude), lon: toFloat(row.longitude)});

   LOAD CSV WITH HEADERS FROM 'https://<wherever-you-host-the-csv>/sections.csv' AS row
   MATCH (a:Station {id: toInteger(row.from_station_id)}), (b:Station {id: toInteger(row.to_station_id)})
   CREATE (a)-[:SECTION {section_id: toInteger(row.section_id), code: row.code,
                          distance_km: toFloat(row.distance_km),
                          travel_minutes: toInteger(row.travel_minutes)}]->(b);
   ```
   (`LOAD CSV` needs the file reachable by URL — e.g. a GitHub raw link to the CSV, or Aura's built-in file import if you're on a paid tier. On the free tier, the simplest path is pushing these two CSVs to a public GitHub Gist and pointing `LOAD CSV` at the raw URL.)
4. This gives you a genuine graph you can show in the Neo4j Browser's visualization — nice for a slide, not required for the system to function, since Postgres + `networkx` already does the real work.

---

## One thing to flag to whoever owns the backend

`schema.sql` includes two columns that a stricter, fully-normalized design wouldn't have (`sections.travel_minutes` and `train_movements.night_index`) — they're pragmatic additions so the priority/optimizer services have a simple, join-free number to read instead of deriving travel time from `distance_km` + `tracks.max_speed_kmph` every time, and so a train's timetable row can be filtered to "which night of the horizon" without re-deriving it from the timestamp. Both are documented inline in `schema.sql` with a comment explaining why they're there.
