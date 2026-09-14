# Run this script to spin up the database and ingest the data.

Write-Host "Starting PostgreSQL + PostGIS container..."
docker-compose up -d

Write-Host "Waiting for database to initialize (10 seconds)..."
Start-Sleep -Seconds 10

Write-Host "Installing dependencies..."
pip install -r requirements.txt

Write-Host "Running data ingestion..."
python run_ingestion.py
