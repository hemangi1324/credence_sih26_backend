const fs = require('fs');
const path = require('path');

const csvDir = path.resolve(__dirname, '../credence_sih26_backend/data');
const outputFile = path.resolve(__dirname, 'fallbackData.json');

function parseCSV(filePath) {
    if (!fs.existsSync(filePath)) return [];
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n').filter(line => line.trim().length > 0);
    if (lines.length < 2) return [];
    
    const headers = lines[0].split(',').map(h => h.trim());
    return lines.slice(1).map(line => {
        // Simple CSV parse, assumes no commas inside quotes
        const values = line.split(',').map(v => v.trim());
        const obj = {};
        headers.forEach((header, i) => {
            let val = values[i];
            if (val && !isNaN(val)) val = Number(val);
            obj[header] = val;
        });
        return obj;
    });
}

function main() {
    const jobs = parseCSV(path.join(csvDir, '07_maintenance_jobs.csv'));
    const trains = parseCSV(path.join(csvDir, '04_trains.csv'));
    const tracks = parseCSV(path.join(csvDir, '02_track_sections.csv'));
    
    const fallbackData = {
        jobs,
        trains,
        tracks
    };

    fs.writeFileSync(outputFile, JSON.stringify(fallbackData, null, 2));
    console.log(`Successfully generated fallbackData.json with ${jobs.length} jobs and ${trains.length} trains.`);
}

main();
