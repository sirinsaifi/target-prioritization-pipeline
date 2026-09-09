import json
from collections import defaultdict, Counter
from math import comb
from app.db.database import SessionLocal
from app.db.models import Target, EvidenceRecord, PriorityScore, ContradictionLog
from app.core.scoring.harmonic_sum import harmonic_sum_score_scaled_for_type
from app.core.scoring.evidence_profile import (
    comparable_pair_count, compute_evidence_consistency, compute_evidence_maturity,
    compute_literature_consistency, combine_consistency_scores,
)
from app.core.verification.contradiction_classifier import classify_contradiction
from app.core.verification.pharos_cross_checks import disease_association_cross_check, ppi_cross_check

def run_contradictions(target_id, db):
    records = db.query(EvidenceRecord).filter(EvidenceRecord.target_id == target_id).all()
    direction_labeled = [r for r in records if r.direction_on_trait is not None]
    
    # Clear old logs
    db.query(ContradictionLog).filter(ContradictionLog.target_id == target_id).delete()
    
    count = 0
    for i in range(len(direction_labeled)):
        for j in range(i + 1, len(direction_labeled)):
            r1, r2 = direction_labeled[i], direction_labeled[j]
            res = classify_contradiction(r1, r2)
            if res.classification != "unclassified":
                log = ContradictionLog(
                    target_id=target_id,
                    evidence_record_a_id=r1.id,
                    evidence_record_b_id=r2.id,
                    classification=res.classification,
                    matched_fields=", ".join(res.matched_fields) if res.matched_fields else None,
                    mismatched_fields=", ".join(res.mismatched_fields) if res.mismatched_fields else None,
                )
                db.add(log)
                count += 1
    db.commit()
    return count

def compute_score(target_id, db):
    records = db.query(EvidenceRecord).filter(EvidenceRecord.target_id == target_id).all()
    scores_by_dimension = defaultdict(list)
    for r in records:
        if r.evidence_score is not None:
            scores_by_dimension[r.dimension].append(r.evidence_score)
    
    dimension_breakdown = {
        dim: harmonic_sum_score_scaled_for_type(scores)
        for dim, scores in scores_by_dimension.items()
    }
    
    all_scores = [s for scores in scores_by_dimension.values() for s in scores]
    evidence_strength = harmonic_sum_score_scaled_for_type(all_scores) if all_scores else 0.0
    
    direction_labeled = [r for r in records if r.direction_on_trait is not None]
    total_pairs = comparable_pair_count([r.source_type for r in direction_labeled])
    classification_counts = dict(Counter(
        c.classification for c in
        db.query(ContradictionLog).filter(ContradictionLog.target_id == target_id).all()
    ))
    structured_consistency = compute_evidence_consistency(classification_counts, total_pairs)
    
    literature_records_considered = (
        db.query(EvidenceRecord.id)
        .filter(EvidenceRecord.target_id == target_id, EvidenceRecord.dimension == "literature", EvidenceRecord.abstract_text.isnot(None))
        .order_by(EvidenceRecord.id)
        .limit(20) # LITERATURE_CONTRADICTION_MAX_RECORDS
        .count()
    )
    literature_pairs_evaluated = comb(literature_records_considered, 2)
    literature_contradiction_count = classification_counts.get("literature_contradiction", 0)
    literature_consistency = compute_literature_consistency(literature_contradiction_count, literature_pairs_evaluated)
    
    evidence_consistency = combine_consistency_scores(
        structured_consistency, total_pairs, literature_consistency, literature_pairs_evaluated,
    )
    
    dimensions_with_evidence = {r.dimension for r in records}
    evidence_maturity = compute_evidence_maturity(dimensions_with_evidence)
    priority_score = round((evidence_strength + evidence_consistency + evidence_maturity) / 3, 4)
    
    # Wipe and re-insert
    db.query(PriorityScore).filter(PriorityScore.target_id == target_id).delete()
    priority = PriorityScore(
        target_id=target_id,
        evidence_strength=evidence_strength,
        evidence_consistency=evidence_consistency,
        evidence_maturity=evidence_maturity,
        dimension_breakdown=json.dumps(dimension_breakdown),
        priority_score=priority_score,
    )
    db.add(priority)
    db.commit()
    return priority

def run_report():
    db = SessionLocal()
    targets = db.query(Target).all()
    
    print("--- FINAL CONSOLIDATION REPORT ---")
    print(f"{'Gene':<10} | {'Assoc':<12} | {'PPI':<12} | {'Strength':<10}")
    print("-" * 50)
    
    for t in targets:
        # 1. Run contradiction check
        run_contradictions(t.id, db)
        # 2. Compute priority score
        priority = compute_score(t.id, db)
        # 3. Get Pharos row
        pharos_row = db.query(EvidenceRecord).filter_by(target_id=t.id, dimension="druggability").first()
        string_row = db.query(EvidenceRecord).filter_by(target_id=t.id, dimension="ppi_network").first()
        
        if not pharos_row:
            print(f"{t.gene_symbol:<10} | N/A          | N/A         | {priority.evidence_strength:.4f}")
            continue
            
        d_res = disease_association_cross_check(t.gene_symbol, pharos_row.notes, priority.dimension_breakdown)
        p_res = ppi_cross_check(t.gene_symbol, pharos_row.notes, string_row.notes if string_row else None)
        
        print(f"{t.gene_symbol:<10} | {d_res.verdict:<12} | {p_res.verdict:<12} | {priority.evidence_strength:.4f}")
        print(f"  - Assoc: {d_res.pharos_value} vs {d_res.pipeline_value}")
        print(f"  - PPI:   {p_res.pharos_value} vs {p_res.pipeline_value}")
        print("-" * 50)

    db.close()

if __name__ == "__main__":
    run_report()
