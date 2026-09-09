import json
from app.db.database import SessionLocal
from app.db.models import Target, EvidenceRecord, PriorityScore
from app.core.verification.pharos_cross_checks import disease_association_cross_check, ppi_cross_check

def run_report():
    db = SessionLocal()
    targets = db.query(Target).all()
    
    print(f"{'Gene':<10} | {'Disease Assoc':<15} | {'PPI Overlap':<15}")
    print("-" * 45)
    
    for t in targets:
        pharos_row = db.query(EvidenceRecord).filter_by(target_id=t.id, dimension="druggability").first()
        string_row = db.query(EvidenceRecord).filter_by(target_id=t.id, dimension="ppi_network").first()
        priority = db.query(PriorityScore).filter(PriorityScore.target_id == t.id).order_by(PriorityScore.computed_at.desc()).first()
        
        if not pharos_row:
            print(f"{t.gene_symbol:<10} | No Pharos data  | No Pharos data")
            continue
            
        d_res = disease_association_cross_check(t.gene_symbol, pharos_row.notes, priority.dimension_breakdown if priority else None)
        p_res = ppi_cross_check(t.gene_symbol, pharos_row.notes, string_row.notes if string_row else None)
        
        print(f"{t.gene_symbol:<10} | {d_res.verdict:<15} | {p_res.verdict:<15}")
        print(f"  - Assoc: {d_res.pharos_value} vs {d_res.pipeline_value}")
        print(f"  - PPI:   {p_res.pharos_value} vs {p_res.pipeline_value}")
        print(f"  - Rationale (Assoc): {d_res.rationale}")
        print(f"  - Rationale (PPI): {p_res.rationale}")
        print("-" * 45)

    db.close()

if __name__ == "__main__":
    run_report()
