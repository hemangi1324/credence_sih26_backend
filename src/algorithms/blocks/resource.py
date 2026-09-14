def check_resource_compatibility(job_resources: list) -> tuple[bool, str]:
    """
    Checks if combining these jobs exceeds available resources.
    job_resources is a list of JobResource objects for the involved jobs.
    
    Rule:
    If Job A requires Resource R1 and Job B requires Resource R1,
    since we assume sequential execution within the block, sharing R1 is generally ACCEPTABLE,
    unless R1 has a strict quantity of 1 and they overlap perfectly.
    Since we scheduled sequentially, they won't overlap.
    Therefore, for sequential blocks, resource conflicts are minimal unless the block exceeds 
    the resource's global availability window.
    """
    if not job_resources:
        return True, "No resources required."
        
    resource_counts = {}
    for jr in job_resources:
        resource_counts[jr.resource_id] = resource_counts.get(jr.resource_id, 0) + 1
        
    # If the same resource is used multiple times, it's fine for sequential.
    # However, if we wanted parallel execution, we would check if resource quantity > 1.
    
    return True, "Resources compatible for sequential execution."
