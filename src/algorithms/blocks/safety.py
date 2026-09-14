def check_safety_compatibility(jobs: list, assets: dict, rules: list) -> tuple[bool, str, bool]:
    """
    Checks if a group of jobs can be safely combined based on compatibility_rules.
    assets: dict mapping asset_id -> Asset object
    rules: list of CompatibilityRule objects
    
    Returns: (is_compatible, reason, isolation_required)
    """
    if len(jobs) <= 1:
        return True, "Single job, inherently safe.", False
        
    isolation_required = False
    
    # Check pairwise compatibility
    for i in range(len(jobs)):
        for j in range(i + 1, len(jobs)):
            asset_a = assets.get(jobs[i].asset_id)
            asset_b = assets.get(jobs[j].asset_id)
            
            if not asset_a or not asset_b:
                continue
                
            type_a = asset_a.asset_type
            type_b = asset_b.asset_type
            
            # Find rule
            rule = next((r for r in rules if 
                         (r.asset_type_a == type_a and r.asset_type_b == type_b) or 
                         (r.asset_type_a == type_b and r.asset_type_b == type_a)), None)
            
            if rule:
                if not rule.compatible:
                    return False, f"Incompatible asset types: {type_a} and {type_b}.", False
                if rule.isolation_required:
                    isolation_required = True
            else:
                # Conservative fallback: if no explicit rule allows it, reject it.
                if type_a != type_b:
                    return False, f"No compatibility rule found for {type_a} and {type_b}. Rejecting conservatively.", False
                    
    reason = "Safety rules passed."
    if isolation_required:
        reason += " Isolation required."
        
    return True, reason, isolation_required
