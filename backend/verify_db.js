const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const csvDir = path.resolve(__dirname, '../credence_sih26_backend/data');

async function main() {
  console.log('--- DB VS CSV CONSISTENCY CHECK ---');
  
  const tables = [
    { db: 'stations', csv: '01_stations.csv' },
    { db: 'track_sections', csv: '02_track_sections.csv' },
    { db: 'trains', csv: '03_trains.csv' },
    { db: 'maintenance_jobs', csv: '07_maintenance_jobs.csv' },
    { db: 'block_requests', csv: '11_block_requests.csv' }
  ];

  for (const t of tables) {
    let dbCount = -1;
    try {
      const res = await pool.query('SELECT COUNT(*) FROM ' + t.db);
      dbCount = parseInt(res.rows[0].count);
    } catch(e) { console.error('Error querying ' + t.db, e.message); }
    
    let csvCount = -1;
    try {
      const csvPath = path.join(csvDir, t.csv);
      if (fs.existsSync(csvPath)) {
        const content = fs.readFileSync(csvPath, 'utf8');
        csvCount = content.split('\n').filter(line => line.trim().length > 0).length - 1; // subtract header
      }
    } catch(e) { console.error('Error reading ' + t.csv, e.message); }
    
    console.log(t.db.padEnd(25) + ' | DB: ' + dbCount.toString().padEnd(5) + ' | CSV: ' + csvCount.toString());
  }
  process.exit(0);
}
main();
