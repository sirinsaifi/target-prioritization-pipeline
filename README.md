# ALS Target Prioritization & Research Gap Identification

## Overview
Prototype pipeline scoped to **Amyotrophic Lateral Sclerosis (ALS)**, Open Targets disease ID `MONDO_0004976`. The system collects multi-source biomedical evidence for candidate genes, scores it using a deterministic methodology informed by the Open Targets Platform (OTP), classifies contradictions between evidence sources, assesses evidence maturity, and identifies specific research gaps with linked investigation suggestions.

**Core design principle**: Deterministic modules compute every number. The agentic/LLM layer only retrieves, orchestrates, and explains — it never originates a score, weight, or threshold.

## Candidate Genes
Edit `app/config.py` to change. Defaults (Ensembl IDs resolved):

| Gene | Ensembl ID |
|---|---|
| SOD1 | ENSG00000142168 |
| C9orf72 | ENSG00000147894 |
| TARDBP | ENSG00000120948 |
| FUS | ENSG00000089280 |
| NEK1 | ENSG00000137601 |

## Evidence Dimensions (8)
Mapped from Open Targets data source types:

| Dimension | Description |
|---|---|
| Genetic | ClinVar pathogenicity, GWAS, eQTL (EVA, uniprot_variants, gwas_credible_sets) |
| Literature | PubMed / Europe PMC co-mentions of gene + disease (europepmc, pubmed) |
| Human/Clinical | ClinicalTrials.gov, drug approvals (clinical_precedence) |
| Experimental | IMPC phenotypic evidence |
| Pathway | Reactome pathway membership (Target.pathways) |
| Drug Target | DrugBank, ChEMBL binding data |
| Tissue Expression | GTEx tissue expression levels |
| PPI Network | STRING protein–protein interactions |

## Architecture
The application has two main parts:

### Backend (FastAPI, port 8000)
- **Routers** in `app/api/routes/`: targets, evidence, scoring, contradictions, gaps, narrative, narration
- **Core modules** in `app/core/`: scoring (harmonic sum, dimension scoring, evidence profile), verification (contradiction classifier), gaps (taxonomy)
- **Ingestion** in `app/ingestion/`: `open_targets_client.py` (OTP GraphQL + Reactome pathways), `literature_client.py` (PubMed E-utilities)
- **Database**: SQLite (`als_pipeline.db`) via SQLAlchemy
- **Endpoints** (all under `/api/v1` prefix in code, omitted in URLs for simplicity):
  - `GET /targets/` — list 5 candidate targets
  - `GET /targets/seed` — seed DB with 5 targets + real evidence
  - `GET /evidence/target/{id}` — evidence records for a target
  - `GET /evidence/target/{id}?dimension=genetic` — filter by dimension
  - `POST /scoring/target/{id}/compute` — compute Strength/Consistency/Maturity + priority score
  - `POST /scoring/target/{id}/run` — shortcut that computes + stores priority score
  - `POST /contradictions/target/{id}/run` — classify all evidence-record pairs
  - `POST /contradictions/target/{id}/run-literature` — literature-only contradiction check
  - `POST /gaps/target/{id}/run` — identify research gaps
  - `GET /narrative/target/{id}` — key-free template narrative (no LLM)
  - `GET /narration/target/{id}` — real LLM narrative (Groq, requires `GROQ_API_KEY`)
  - `GET /context/` — disease + target summary context

### Frontend (React 19 + Vite + Tailwind CSS v4, port 8443)
- **12 pages**: Landing, AnalysisSetup, Processing, Results, TargetDetail, WhyTarget, Contradictions, ResearchGaps, WhyTarget, Report, Comparison, EvidenceNetwork
- All pages fetch data from the backend API instead of using hardcoded demo data
- `src/api/transform.ts` — data transformation layer (score mapping 0-1→labels, dimension name mapping, target transformation)
- `src/api/hooks.ts` — React hooks (useApiData, useTargets, useTargetData, usePriorityScore, useEvidence, useContradictions, useGapAnalysis, usePipelineStatus, useRootData, useEvidenceDimensions)
- `src/api/client.ts` — typed API fetch wrapper using `import.meta.env.VITE_API_BASE_URL`

## Project Structure
```
als_target_prioritization/
├── app/
│   ├── main.py                          FastAPI entrypoint, wires all routers
│   ├── config.py                        Disease ID, target list, scoring constants
│   ├── db/
│   │   ├── database.py                  SQLAlchemy engine/session
│   │   └── models.py                    Target, EvidenceRecord, ContradictionLog, GapRecord, PriorityScore
│   ├── ingestion/
│   │   ├── open_targets_client.py       OTP GraphQL client
│   │   └── literature_client.py         PubMed E-utilities client
│   ├── core/
│   │   ├── scoring/
│   │   │   ├── harmonic_sum.py          Harmonic sum aggregation (OTP-referenced)
│   │   │   ├── dimension_scoring.py     Per-dimension scoring rules
│   │   │   └── evidence_profile.py      Consistency + Maturity modules
│   │   ├── verification/
│   │   │   └── contradiction_classifier.py  Source-type-aware contradiction classification
│   │   └── gaps/
│   │       └── gap_taxonomy.py          5 gap types: mechanistic, population, modality, validation, evidence_consistency
│   └── api/
│       ├── routes/                      FastAPI route handlers
│       └── client.ts / types.ts / hooks.ts / transform.ts  Frontend API clients
├── figma_frontend/
│   └── Build it/                        React + Vite + Tailwind frontend
│       ├── src/
│       │   ├── api/                     API client, hooks, transform layer
│       │   ├── pages/                   12 page components
│       │   ├── App.tsx                  React Router v7 setup
│       │   └── main.tsx                 React entrypoint
│       ├── vite.config.ts              Vite + Tailwind + Figma Make config
│       └── package.json
├── scripts/
│   └── ingest_evidence.py               Real ingestion: 5 genes × 6 OTP datasources + PubMed + Reactome = 1,858 records
├── tests/
│   ├── test_core_logic.py               21 passing unit tests across deterministic modules
│   └── test_agent_narrator.py           6 mocked tests for real-LLM narrator
├── streamlit_app.py                     Streamlit UI (thin API client only)
├── requirements.txt                     Python dependencies
├── Dockerfile                           Docker image definition
├── docker-compose.yml                   api + ui services (not yet run end-to-end in this env)
└── README.md                            You are here
```

## Setup

### Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Ensure .env file exists with GROQ_API_KEY if you want LLM narration
# If no key is present, the /narration endpoint returns a clean 503 RuntimeError
cp .env.example .env  # if available, otherwise create manually
uvicorn app.main:app --reload
# API runs at http://127.0.0.1:8000
```

### Frontend
```bash
cd figma_frontend/Build it
# This project already has deps installed from the parent session
# Set Vite env var for API base URL:
export VITE_API_BASE_URL=http://127.0.0.1:8000
# Or create a .env file with: VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
# Frontend runs at http://127.0.0.1:8443
```

### Run Both Together
Start the backend first, then the frontend in a separate terminal:
```bash
# Terminal 1
cd /Users/sohel/target-prioritization-pipeline
source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2
cd figma_frontend/Build it
export VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

### Ingestion (one-time, populates DB)
```bash
source /Users/sohel/target-prioritization-pipeline/venv/bin/activate
python -m scripts.ingest_evidence
# This clears and re-ingests all evidence for all 5 genes
# ~1,858 evidence records ingested across 6 OTP datasources + PubMed + Reactome pathways
```

## Intuitive Data Flow Diagram

```
┌─────────────────────┐          ┌─────────────────────────┐
│   Frontend (port)   │          │   Backend (port 8000)   │
│   React + Vite      │          │   FastAPI + SQLAlchemy  │
└─────────────┬───────┤          └───────┬─────────────────┘
              │                   │
              │  GET /targets/    │
              ▼                   ▼
┌─────────────────────┐   GET /evidence/target/{id}
│   Landing page      │──►│  OTP GraphQL API        │
│   (disease + 5     │   │  PubMed E-utilities   │
│    targets overview)│   │  Reactome pathways    │
└─────────────┬───────┘   └───────┬─────────────────┘
              │                   │
              │  POST /targets/seed│
              ▼                   ▼
┌─────────────────────┐   EvidenceRecord rows
│  AnalysisSetup page │   stored in SQLite      │
│   (5 targets +     │   + dimension fields  │
│    8 evidence dims) │   + source metadata │
└─────────────┬───────┘   └───────┬─────────────────┘
              │                   │
              │  POST /scoring/.../compute
              ▼                   ▼
┌─────────────────────┐   PriorityScore row
│   Processing page   │──►│  Deterministic modules │
│   (trigger pipeline)│   │  harmonic_sum.py     │
│                    │   │  dimension_scoring.py│
│                    │   │  contradiction_classifier.py│
│                    │   │  gap_taxonomy.py     │
└─────────────┬───────┘   └───────┬─────────────────┘
              │                   │
              │  GET /scoring/target/{id}
              ▼                   ▼
┌─────────────────────┐   Evidence profile + scores
│   Results page      │──►│  API routes return JSON│
│   (evidence matrix) │   └──────────────────────┘
└─────────────┬───────┘               │
              │                   │
           GET /target/{id} GET /contradictions/target/{id}
              │                   │
   ┌────────────▼───────┐  ┌──────▼───────┐
   │  TargetDetail page │  │ Contradictions │
   │ (7 tabs: Overview,  │  │ page           │
   │  Evidence, ...     │  │ (source A vs B)│
   └────────────┬───────┘  └──────┬───────┘
                │                 │
           GET /gaps/target/{id}
                ▼                 ▼
         ResearchGaps page    WhyTarget page
         (5 gap types +      (score summary,
          investigation       score decomposition,
          suggestions)         limitations/uncertainty)

                │                 │
                ▼                 ▼
         ┌─────────────────┐ ┌─────────────────┐
         │   Report page   │ │  Comparison page│
         │ (print-ready)   │ │ (portfolio       │
         │                 │ │  comparison for  │
         │                 │ │  first 3 targets)│
         └─────────────────┘ └─────────────────┘

                │
                ▼
         ┌─────────────────────┐
         │ EvidenceNetwork page│
         │ (SVG biological    │
         │  network with PPI, │
         │  pathways, evidence │
         │  nodes; filterable)│
         └─────────────────────┘
```

## API Endpoints Summary

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Root response with project info |
| GET | `/context/` | Disease + target_count + last_analysis + target_summary |
| GET | `/targets/` | List 5 candidate targets with gene_symbol, ensembl_id |
| POST | `/targets/seed` | Seed DB with 5 targets + ingest evidence |
| GET | `/evidence/target/{id}` | Evidence records for a target |
| GET | `/evidence/target/{id}?dimension=genetic` | Filter evidence by dimension |
| POST | `/scoring/target/{id}/compute` | Compute Strength/Consistency/Maturity + priority_score |
| POST | `/scoring/target/{id}/run` | Shortcut: compute + store priority_score |
| POST | `/contradictions/target/{id}/run` | Classify all evidence-record pairs |
| POST | `/contradictions/target/{id}/run-literature` | Literature-only contradiction check |
| GET | `/contradictions/target/{id}` | List contradiction records |
| POST | `/gaps/target/{id}/run` | Identify research gaps + translational opportunity |
| GET | `/gaps/target/{id}` | List gap records for a target |
| GET | `/narrative/target/{id}` | Key-free template narrative (no LLM needed) |
| GET | `/narration/target/{id}` | Real LLM narrative (Groq `openai/gpt-oss-20b`, needs `GROQ_API_KEY`) |

## Design Principle (Quoted from CLAUDE.md)
> **Deterministic modules compute every number. The agentic/LLM layer only retrieves, orchestrates, and explains.** The LLM must never originate a score, weight, or threshold. Where an LLM is used (e.g. proposing candidate contradictions from free-text literature), a deterministic rule layer always verifies before anything is presented as a confirmed finding.

## Report Language Reminders
- "The prototype adopts the Open Targets evidence-scoring framework as a methodological reference and implements a disease-specific subset of evidence dimensions."
- "Target priority = relative research priority based on strength, consistency, maturity, and completeness of currently available evidence — not a prediction of clinical success."
- "This is case-based validation on selected known examples, not statistically validated model accuracy."

## Testing
```bash
cd /Users/sohel/target-prioritization-pipeline
source venv/bin/activate
pytest tests/ -v
# 21/21 test_core_logic.py tests pass
# 6/6 test_agent_narrator.py tests pass (mocked _call_llm)
```

## Optional: Docker
```bash
docker compose up --build
# API: http://localhost:8000/docs   UI: http://localhost:8501
```
*Note: Docker not installed in this dev environment; compose YAML validated but not run end-to-end.*