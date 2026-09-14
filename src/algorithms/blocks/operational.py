def check_operational_compatibility(track_id: str, proposed_start, proposed_end, requested_date, track_availabilities: list) -> tuple[bool, str]:
    """
    Checks if the proposed block conflicts with known hard track unavailabilities.
    track_availabilities: list of TrackAvailability objects
    """
    if not proposed_start or not proposed_end or not requested_date:
        return True, "No specific proposed time bounds to check."
        
    for avail in track_availabilities:
        if avail.track_id != track_id:
            continue
            
        # Simplified time check for prototype
        # If the track is known to be unavailable ('blocked', etc.) and our proposed date/time overlaps
        if avail.status.startswith('blocked'):
            # Convert date+time to compare
            # For this prototype, we'll just check date overlap as a proxy if it's the same day
            avail_date = avail.time_start.date()
            if avail_date == requested_date:
                # If proposed start is inside the blocked window
                avail_start_time = avail.time_start.time()
                avail_end_time = avail.time_end.time()
                
                # Check overlap (naive time overlap assuming same day)
                if max(proposed_start, avail_start_time) < min(proposed_end, avail_end_time):
                    return False, f"Conflicts with existing block {avail.source_request_id}."
                    
    return True, "Operationally compatible (no known hard track conflicts)."
