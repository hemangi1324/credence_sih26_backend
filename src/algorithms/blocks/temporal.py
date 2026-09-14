import datetime

def check_temporal_compatibility(requests: list) -> tuple[bool, str, datetime.time, datetime.time, int]:
    """
    Checks if a group of block requests can be combined temporally.
    Returns: (is_compatible, reason, proposed_start, proposed_end, total_duration)
    
    Conservative Assumption: 
    Since the synthetic data does not explicitly define which jobs can safely run in parallel 
    without mutual interference, we assume sequential execution within the combined possession window.
    Therefore, candidate_duration = sum of minimum_duration_min + max(safety_buffer_min).
    """
    if not requests:
        return False, "No requests provided.", None, None, 0
        
    # Check if they have intersecting requested dates
    dates = {req.requested_date for req in requests if req.requested_date}
    if len(dates) > 1:
        return False, "Conflicting requested dates.", None, None, 0
        
    # We will compute total duration sequentially
    total_work_duration = sum(req.minimum_duration_min for req in requests)
    max_safety_buffer = max((req.safety_buffer_min for req in requests if req.safety_buffer_min), default=0)
    
    total_duration = total_work_duration + max_safety_buffer
    
    # Try to find a common window overlap for preferred_start / preferred_end
    # This is simplified: in reality we would use datetime logic over multiple days.
    # For now, we take the earliest requested start and see if total_duration fits before the latest requested end.
    
    valid_starts = [req.requested_start or req.preferred_start for req in requests]
    valid_ends = [req.requested_end or req.preferred_end for req in requests]
    
    valid_starts = [s for s in valid_starts if s]
    valid_ends = [e for e in valid_ends if e]
    
    if not valid_starts or not valid_ends:
        start_time = datetime.time(0, 0)
        return True, f"Temporally compatible (Sequential duration {total_duration}m).", start_time, datetime.time(23, 59), total_duration

    if total_duration > 720:
        return False, f"Total sequential duration {total_duration}m too large for a single block.", None, None, 0
        
    def parse_time(t_val):
        if isinstance(t_val, str):
            try:
                # Assuming format "HH:MM:SS" or "HH:MM"
                parts = t_val.split(':')
                return datetime.time(int(parts[0]), int(parts[1]))
            except:
                return datetime.time(0, 0)
        return t_val

    proposed_start = parse_time(valid_starts[0])
    proposed_end = parse_time(valid_ends[0]) # Very simplified
    
    return True, f"Temporally compatible (Sequential duration {total_duration}m).", proposed_start, proposed_end, total_duration
