import itertools
import uuid
from collections import defaultdict
from .models import CandidateBlock
from .spatial import check_spatial_compatibility, get_combined_spatial_bounds
from .temporal import check_temporal_compatibility
from .resource import check_resource_compatibility
from .safety import check_safety_compatibility
from .operational import check_operational_compatibility

MAX_JOBS_PER_CANDIDATE = 3

def generate_candidate_blocks(
    jobs_with_scores: list, 
    requests: list, 
    assets: list, 
    rules: list, 
    availabilities: list,
    job_resources: list,
    dependencies: list
) -> list[CandidateBlock]:
    """
    Staged generation strategy:
    1. Group jobs by track_id.
    2. Generate single-job candidates.
    3. Generate combinations (up to MAX_JOBS_PER_CANDIDATE) within the same track.
    4. Apply compatibility checks (Spatial, Temporal, Resource, Safety, Operational).
    """
    candidates = []
    
    # Dictionaries for O(1) lookup
    req_dict = {r.job_id: r for r in requests if r.job_id}
    asset_dict = {a.asset_id: a for a in assets}
    job_res_dict = defaultdict(list)
    for jr in job_resources:
        job_res_dict[jr.job_id].append(jr)
        
    deps_predecessors = defaultdict(set) # job_id -> set of predecessors
    for d in dependencies:
        deps_predecessors[d.job_id_successor].add(d.job_id_predecessor)

    # Filter schedulable jobs (ignore completed/cancelled)
    schedulable_jobs = [item for item in jobs_with_scores if item['priority_category'] != 'COMPLETED']
    
    # Map job to its track_id based on request
    track_groups = defaultdict(list)
    
    for item in schedulable_jobs:
        job_id = item['job_id']
        if job_id not in req_dict:
            continue
        track_id = req_dict[job_id].track_id
        track_groups[track_id].append(item)

    # Generate Candidates per track
    for track_id, items in track_groups.items():
        # Sort items by priority score descending
        items.sort(key=lambda x: x['priority_score'], reverse=True)
        
        # We will iterate through subsets of size 1 to MAX_JOBS_PER_CANDIDATE
        for r in range(1, min(len(items), MAX_JOBS_PER_CANDIDATE) + 1):
            for subset in itertools.combinations(items, r):
                job_ids = [s['job_id'] for s in subset]
                
                # Verify inherent dependencies: if job B is in subset and depends on job A, 
                # job A MUST be in subset OR already completed (for now we assume if it's not in subset, it's invalid unless it's completed, but to be simple: we don't mix them unless both are here or predecessor is ignored)
                # For safety, if A and B are in the subset, we allow it. If B is in subset but A is not, it's fine (A will be scheduled earlier by CP-SAT).
                # But we shouldn't create a block that violates B -> A order. Sequential duration assumes arbitrary order, CP-SAT will order them.
                
                reqs = [req_dict[j] for j in job_ids]
                subset_assets = {j: asset_dict[s['asset_id']] for j, s in zip(job_ids, subset)}
                subset_job_res = []
                for j in job_ids:
                    subset_job_res.extend(job_res_dict[j])
                    
                # 1. Spatial
                spatial_ok, spat_reason = check_spatial_compatibility(reqs)
                if not spatial_ok:
                    if r > 1: 
                        print(f"Rejected {job_ids} Space: {spat_reason}")
                        continue
                
                # 2. Temporal
                temp_ok, temp_reason, p_start, p_end, duration = check_temporal_compatibility(reqs)
                if not temp_ok:
                    if r > 1: 
                        print(f"Rejected {job_ids} Temp: {temp_reason}")
                        continue
                
                # 3. Resource
                res_ok, res_reason = check_resource_compatibility(subset_job_res)
                if not res_ok:
                    if r > 1: 
                        print(f"Rejected {job_ids} Res: {res_reason}")
                        continue
                    
                # 4. Safety
                subset_mock_jobs = [type('obj', (object,), {'asset_id': s['asset_id']}) for s in subset]
                safe_ok, safe_reason, isolation = check_safety_compatibility(subset_mock_jobs, asset_dict, rules)
                if not safe_ok:
                    if r > 1: 
                        print(f"Rejected {job_ids} Safe: {safe_reason}")
                        continue
                    
                # 5. Operational
                requested_date = reqs[0].requested_date
                op_ok, op_reason = check_operational_compatibility(track_id, p_start, p_end, requested_date, availabilities)
                if not op_ok:
                    if r > 1: 
                        print(f"Rejected {job_ids} Op: {op_reason}")
                        continue
                    
                # Create Candidate Block
                _, min_c, max_c = get_combined_spatial_bounds(reqs)
                depts = list(set(s['department'] for s in subset))
                avg_priority = sum(s['priority_score'] for s in subset) / len(subset)
                
                candidate = CandidateBlock(
                    candidate_id=f"CB-{uuid.uuid4().hex[:6].upper()}",
                    track_id=track_id,
                    chainage_start_km=min_c,
                    chainage_end_km=max_c,
                    proposed_start=p_start,
                    proposed_end=p_end,
                    duration_min=duration,
                    job_ids=job_ids,
                    departments=depts,
                    request_ids=[req.request_id for req in reqs],
                    priority_score=round(avg_priority, 4),
                    isolation_required=isolation,
                    spatial_compatible=spatial_ok,
                    temporal_compatible=temp_ok,
                    resource_compatible=res_ok,
                    safety_compatible=safe_ok,
                    operational_compatible=op_ok,
                    compatibility_reasons=[spat_reason, temp_reason, res_reason, safe_reason, op_reason]
                )
                
                candidates.append(candidate)

    return candidates
