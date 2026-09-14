MAX_COMBINE_DISTANCE_KM = 5.0

def check_spatial_compatibility(requests: list) -> tuple[bool, str]:
    """
    Checks if a group of block requests can be combined spatially.
    Rule:
    - Must be on the same track_id
    - The bounding box (min_chainage, max_chainage) span should not exceed MAX_COMBINE_DISTANCE_KM, 
      OR they should explicitly overlap.
    """
    if not requests:
        return False, "No requests provided."

    track_id = requests[0].track_id
    if any(req.track_id != track_id for req in requests):
        return False, "Jobs are on different tracks."

    # Compute bounding box
    min_chain = min(min(req.chainage_start_km, req.chainage_end_km) for req in requests)
    max_chain = max(max(req.chainage_start_km, req.chainage_end_km) for req in requests)
    
    span = max_chain - min_chain
    if span > MAX_COMBINE_DISTANCE_KM:
        return False, f"Span {span:.2f}km exceeds MAX_COMBINE_DISTANCE_KM ({MAX_COMBINE_DISTANCE_KM}km)."

    return True, f"Spatially compatible on {track_id} (Span {span:.2f}km)."

def get_combined_spatial_bounds(requests: list) -> tuple[str, float, float]:
    """Returns track_id, min_chainage, max_chainage"""
    track_id = requests[0].track_id
    min_chain = min(min(req.chainage_start_km, req.chainage_end_km) for req in requests)
    max_chain = max(max(req.chainage_start_km, req.chainage_end_km) for req in requests)
    return track_id, min_chain, max_chain
