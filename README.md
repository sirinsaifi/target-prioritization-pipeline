# ALS Target Prioritization & Research Gap Identification

Prototype pipeline scoped to Amyotrophic Lateral Sclerosis (Open Targets disease ID: MONDO_0004976).

MVP evidence dimensions: **Genetic, Literature, Pathway, Human/Clinical** (Omics, Biomarker, Experimental added in phase 2).

Candidate genes (edit in `app/config.py`): SOD1, C9orf72, TARDBP, FUS, NEK1.

## Design principle
Deterministic modules compute the numbers; the agentic/LLM layer retrieves, orchestrates, and explains them. The LLM never originates a score.

## Structure

```
app/
  main.py                          FastAPI app entrypoint
  config.py                        Disease ID, target list, thresholds
  db/
    database.py                    SQLAlchemy engine/session
    models.py                      EvidenceRecord, Target, ContradictionLog, GapRecord tables
  ingestion/
    open_targets_client.py         GraphQL client — pulls L2G scores, association scores, evidence
    literature_client.py           PubMed/PMC client stub — literature co-occurrence evidence
  core/
    scoring/
      harmonic_sum.py              OTP's harmonic-sum aggregation (implemented, cite OTP docs)
      dimension_scoring.py         Per-dimension scoring rules (ClinVar, trial phase, etc.)
    verification/
      contradiction_classifier.py  Direct / population-heterogeneity / methodological decision tree
    gaps/
      gap_taxonomy.py              Mechanistic / population / modality / validation / consistency gap rules
  api/
    routes/
      targets.py                   GET candidate targets for the configured disease
      evidence.py                  GET evidence records for a target
      scoring.py                   GET dimension scores + composite score for a target
      contradictions.py            GET classified contradiction pairs for a target
      gaps.py                      GET research gaps + investigation suggestions for a target
  models/
    schemas.py                     Pydantic request/response models
tests/                             Unit tests for scoring + classifier logic
```

## Build order (matches the finalized architecture)
1. ~~Project skeleton~~ (this step)
2. Data ingestion — pull real evidence for the 5 genes from Open Targets API + PubMed
3. Deterministic scoring modules — harmonic sum + per-dimension scoring, tested against real pulled data
4. Contradiction classifier — needs populated evidence fields (tissue/population/assay/endpoint) to test against
5. Gap taxonomy + investigation suggestions
6. Agent orchestration layer (calls the above as tools, narrates results)
7. Streamlit UI (built last)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Report language reminders (say these explicitly)
- "The prototype adopts the Open Targets evidence-scoring framework as a methodological reference and implements a disease-specific subset of evidence dimensions."
- "Target priority = relative research priority based on strength, consistency, maturity, and completeness of currently available evidence — not a prediction of clinical success."
- "This is case-based validation on selected known examples, not statistically validated model accuracy."
