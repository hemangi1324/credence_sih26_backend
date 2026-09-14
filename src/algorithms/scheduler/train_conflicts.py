import datetime

def estimate_train_impact(block_track_id: str, block_start: datetime.time, block_end: datetime.time, train_timetable: list, trains_dict: dict) -> float:
    """
    Estimates train impact penalty based on timetable overlap.
    Returns a float representing the penalty score.
    """
    impact_score = 0.0
    
    if not block_start or not block_end:
        return impact_score
        
    for sched in train_timetable:
        if sched.track_id != block_track_id:
            continue
            
        train = trains_dict.get(sched.train_id)
        if not train:
            continue
            
        entry = sched.entry_time
        exit = sched.exit_time
        
        def parse_t(t_val):
            if isinstance(t_val, str):
                try:
                    parts = t_val.split(':')
                    return datetime.time(int(parts[0]), int(parts[1]))
                except:
                    return datetime.time(0, 0)
            return t_val
            
        entry = parse_t(entry)
        exit = parse_t(exit)
        
        # Check if [block_start, block_end] overlaps with [entry, exit]
        if entry and exit:
            if max(block_start, entry) < min(block_end, exit):
                # Overlap detected!
                priority = train.train_priority or 1
                # Penalty scales with train priority (e.g., 5 is high priority)
                # Let's say: 10 penalty points per priority level
                impact_score += (priority * 10.0)
                
    return impact_score
