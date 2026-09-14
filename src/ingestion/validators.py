def validate_data(dfs):
    errors = []
    
    # Extract dataframes
    stations_df = dfs.get('01_stations.csv')
    tracks_df = dfs.get('02_track_sections.csv')
    trains_df = dfs.get('04_trains.csv')
    assets_df = dfs.get('06_assets.csv')
    jobs_df = dfs.get('07_maintenance_jobs.csv')
    block_reqs_df = dfs.get('11_block_requests.csv')
    resources_df = dfs.get('10_resources.csv')
    job_resources_df = dfs.get('13_job_resources.csv')
    deps_df = dfs.get('08_maintenance_dependencies.csv')
    timetable_df = dfs.get('05_train_timetable.csv')
    
    # 1. Duplicate IDs
    if stations_df is not None and stations_df['station_id'].duplicated().any():
        errors.append("Duplicate primary keys found in stations")
    if tracks_df is not None and tracks_df['track_id'].duplicated().any():
        errors.append("Duplicate primary keys found in tracks")
        
    # 2. Maintenance jobs referring to missing assets
    if jobs_df is not None and assets_df is not None:
        missing_assets = set(jobs_df['asset_id']) - set(assets_df['asset_id'])
        if missing_assets:
            errors.append(f"Maintenance jobs refer to missing assets: {missing_assets}")
            
    # 3. Block requests referring to missing jobs/tracks
    if block_reqs_df is not None:
        if jobs_df is not None:
            missing_jobs = set(block_reqs_df['job_id'].dropna()) - set(jobs_df['job_id'])
            if missing_jobs:
                errors.append(f"Block requests refer to missing jobs: {missing_jobs}")
        if tracks_df is not None:
            missing_tracks = set(block_reqs_df['track_id']) - set(tracks_df['track_id'])
            if missing_tracks:
                errors.append(f"Block requests refer to missing tracks: {missing_tracks}")
                
    # 4. Timetable records referring to missing trains/tracks
    if timetable_df is not None:
        if trains_df is not None:
            missing_trains = set(timetable_df['train_id']) - set(trains_df['train_id'])
            if missing_trains:
                errors.append(f"Timetable refers to missing trains: {missing_trains}")
        if tracks_df is not None:
            missing_tracks = set(timetable_df['track_id']) - set(tracks_df['track_id'])
            if missing_tracks:
                errors.append(f"Timetable refers to missing tracks: {missing_tracks}")
                
    # 5. Job resources missing refs
    if job_resources_df is not None:
        if resources_df is not None:
            missing_res = set(job_resources_df['resource_id']) - set(resources_df['resource_id'])
            if missing_res:
                errors.append(f"Job resources refer to missing resource_id: {missing_res}")
        if jobs_df is not None:
            missing_jobs = set(job_resources_df['job_id']) - set(jobs_df['job_id'])
            if missing_jobs:
                errors.append(f"Job resources refer to missing job_id: {missing_jobs}")
                
    # 6. Negative durations in jobs
    if jobs_df is not None and 'duration_min' in jobs_df.columns:
        if (jobs_df['duration_min'] < 0).any():
            errors.append("Negative durations found in maintenance_jobs")
            
    # 7. Invalid chainage ranges in block requests
    if block_reqs_df is not None:
        invalid_chainage = block_reqs_df[block_reqs_df['chainage_start_km'] > block_reqs_df['chainage_end_km']]
        if not invalid_chainage.empty:
            errors.append("Block requests found with chainage_start_km > chainage_end_km")
            
    return errors
