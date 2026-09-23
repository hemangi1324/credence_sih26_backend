const { Client } = require('pg');
const fs = require('fs');
const path = require('path');
const dotenv = require('dotenv');

dotenv.config({ path: path.join(__dirname, '../.env') });

const dbUrl = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/sih26';

async function seed() {
    const client = new Client({
        connectionString: dbUrl,
    });

    try {
        await client.connect();
        console.log('Connected to PostgreSQL database.');

        const backendDataDir = path.join(__dirname, '..', 'data');
        const schemaPath = path.join(backendDataDir, 'schema.sql');
        const seedSqlPath = path.join(backendDataDir, 'seed.sql');

        if (fs.existsSync(schemaPath)) {
            console.log('Running schema.sql...');
            const schemaSql = fs.readFileSync(schemaPath, 'utf8');
            await client.query(schemaSql);
            console.log('Schema executed successfully.');
        } else {
            console.warn('schema.sql not found at', schemaPath);
        }

        if (fs.existsSync(seedSqlPath)) {
            console.log('Running seed.sql...');
            const seedSql = fs.readFileSync(seedSqlPath, 'utf8');
            await client.query(seedSql);
            console.log('Seed data inserted successfully.');
        } else {
            console.warn('seed.sql not found at', seedSqlPath);
        }

    } catch (err) {
        console.error('Error during database seeding:', err.message);
    } finally {
        await client.end();
        console.log('Database connection closed.');
    }
}

seed();
