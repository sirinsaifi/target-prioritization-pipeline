"""
Agent tools for the autonomous investigation loop (app/agent/investigation_loop.py).

NAMING NOTE: this is deliberately NOT called `app/agent/tools.py`, even
though that was the requested filename — `app/agent/tools.py` already
exists and is actively used by the narration orchestration layer
(app/agent/orchestrator.py, live at GET /narrative/target/{id}): it holds
read-only DB wrappers (get_target, get_latest_priority_score, etc.), a
completely different job from the ingestion-wrapping tools below. Reusing
that filename would have overwritten working, in-use code. Flagged before
writing rather than silently done.

Each function here is a thin wrapper around an ALREADY-BUILT ingestion
function (open_targets_client.py / literature_client.py) — no new
data-fetching logic lives here. The wrapping exists only to give each
function a tool-calling-compatible signature (JSON-serializable args, one
gene/disease per call) and a docstring the LLM reads as the tool
description, per docs/01_final_architecture.md's "Agentic layer role":
"selects sources/tools -> triggers retrieval ... invokes deterministic
[modules] as tools." The agent controls WHICH of these to call and WHEN to
stop; it never computes a score itself (see CLAUDE.md core principle) —
these tools return raw evidence rows, never a score.

search_pathway_evidence() now wraps the real
open_targets_client.get_pathway_evidence() (Target.pathways — a
disease-agnostic Reactome annotation, not an evidences()-based
datasource; see that function's docstring and
docs/07_final_architecture_and_phases.md for the live-confirmed reason).
This is the same client function scripts/ingest_evidence.py's
_build_pathway_fields() consumes for the fixed pipeline — imported
directly here, not reimplemented, per this module's own "no new
data-fetching logic" rule.
"""

from app.config import CANDIDATE_TARGETS, DISEASE_EFO_ID, GENETIC_DATATYPE_ID, EXPRESSION_ATLAS_DATASOURCE_ID
from app.ingestion.open_targets_client import (
    get_evidence_for_datasource, get_evidence_by_datatype, get_pathway_evidence,
    get_drug_target_evidence,
)
from app.ingestion.literature_client import get_literature_evidence_pubmed
from app.ingestion.hpa_client import get_tissue_expression
from app.ingestion.string_client import get_ppi_partners


def _ensembl_id_for(gene: str) -> str | None:
    return CANDIDATE_TARGETS.get(gene)


def search_genetic_evidence(gene: str) -> dict:
    """
    Fetch real genetic evidence for a gene against the configured disease
    from Open Targets — via OTP's real "genetic_association" datatype
    (config.GENETIC_DATATYPE_ID), NOT a hardcoded datasourceId list. Same
    real client the fixed pipeline uses
    (open_targets_client.get_evidence_by_datatype()), just reused here —
    see that function's docstring for why a hardcoded list (previously
    eva/uniprot_variants/gwas_credible_sets, tuned for ALS's rare-variant
    genetics) silently under-collected real evidence, and docs/07 for the
    live schema check that motivated this fix. Returns row counts and the
    real evidence rows — NOT a score; dimension_scoring.py scores these
    later in the deterministic pipeline, not this tool.
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_evidence_by_datatype(ensembl_id, DISEASE_EFO_ID, GENETIC_DATATYPE_ID)
    except Exception as exc:
        return {"gene": gene, "error": str(exc), "rows": []}

    counts: dict = {}
    for row in rows:
        ds = row.get("datasourceId", "unknown")
        counts[ds] = counts.get(ds, 0) + 1

    return {
        "gene": gene,
        "ensembl_id": ensembl_id,
        "row_counts_by_datasource": counts,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_literature_evidence(gene: str, disease: str) -> dict:
    """
    Fetch real literature co-occurrence evidence for a gene and disease
    directly from PubMed (see app/ingestion/literature_client.py) — a
    presence-based signal (confidence 1.0 per co-occurring paper), not a
    weighted NLP score.
    """
    try:
        rows = get_literature_evidence_pubmed(gene, disease)
    except Exception as exc:
        return {"gene": gene, "disease": disease, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "disease": disease,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_pathway_evidence(gene: str) -> dict:
    """
    Fetch real Reactome pathway membership for a gene (Target.pathways —
    disease-agnostic: this reflects whether the gene is annotated to any
    curated pathway at all, not whether that pathway is disease-specific
    evidence). Same real client as the fixed pipeline
    (open_targets_client.get_pathway_evidence()), just reused here.
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_pathway_evidence(ensembl_id)
    except Exception as exc:
        return {"gene": gene, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "ensembl_id": ensembl_id,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_clinical_evidence(gene: str, disease: str) -> dict:
    """
    Fetch real clinical-trial/precedence evidence for a gene against the
    configured disease from Open Targets (clinical_precedence datasource).
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_evidence_for_datasource(ensembl_id, DISEASE_EFO_ID, "clinical_precedence")
    except Exception as exc:
        return {"gene": gene, "disease": disease, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "disease": disease,
        "ensembl_id": ensembl_id,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_experimental_evidence(gene: str, disease: str) -> dict:
    """
    Fetch real experimental (IMPC animal-model) evidence for a gene against
    the configured disease from Open Targets — same real client
    (get_evidence_for_datasource) and datasource ("impc") the fixed
    pipeline uses (see scripts/ingest_evidence.py's DATASOURCE_TO_DIMENSION).
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_evidence_for_datasource(ensembl_id, DISEASE_EFO_ID, "impc")
    except Exception as exc:
        return {"gene": gene, "disease": disease, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "disease": disease,
        "ensembl_id": ensembl_id,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_omics_evidence(gene: str, disease: str) -> dict:
    """
    Fetch real differential-expression (Expression Atlas) evidence for a
    gene against the configured disease. Same real client and datasource
    ID (config.EXPRESSION_ATLAS_DATASOURCE_ID) the fixed pipeline uses —
    confirmed via live introspection to return zero real rows for every
    one of the 5 real ALS candidate genes (and 2 additional well-studied
    cancer gene/disease pairs tested outside this codebase), so this tool
    is real and correctly wired but will honestly report zero rows for
    this project's actual disease/genes, not a bug.
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_evidence_for_datasource(ensembl_id, DISEASE_EFO_ID, EXPRESSION_ATLAS_DATASOURCE_ID)
    except Exception as exc:
        return {"gene": gene, "disease": disease, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "disease": disease,
        "ensembl_id": ensembl_id,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_drug_target_evidence(gene: str) -> dict:
    """
    Fetch real ChEMBL-backed drug-target mechanism-of-action data for a
    gene, already disease-filtered to the configured disease (see
    open_targets_client.get_drug_target_evidence() docstring — this field
    is gene-level/disease-agnostic at the API level, same as pathways, so
    the disease-relevance filter happens client-side in that function).
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        rows = get_drug_target_evidence(ensembl_id, DISEASE_EFO_ID)
    except Exception as exc:
        return {"gene": gene, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "ensembl_id": ensembl_id,
        "total_rows": len(rows),
        "rows": rows,
    }


def search_tissue_expression(gene: str) -> dict:
    """
    Fetch real Human Protein Atlas tissue-expression data for a gene — a
    genuinely independent external source (not Open Targets, see
    app/ingestion/hpa_client.py docstring). Disease-agnostic (HPA has no
    disease concept at all), so this tool takes only a gene, not a disease.
    """
    ensembl_id = _ensembl_id_for(gene)
    if ensembl_id is None:
        return {"error": f"Unknown gene symbol {gene!r} — not in configured CANDIDATE_TARGETS."}

    try:
        hpa_data = get_tissue_expression(ensembl_id)
    except Exception as exc:
        return {"gene": gene, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "ensembl_id": ensembl_id,
        "total_rows": 1 if hpa_data is not None else 0,
        "rows": [hpa_data] if hpa_data is not None else [],
    }


def search_ppi_network(gene: str) -> dict:
    """
    Fetch real STRING high-confidence (combined_score > 700) interaction
    partners for a gene — a genuinely independent external source, no
    Open Targets involvement at all.
    """
    try:
        partners = get_ppi_partners(gene)
    except Exception as exc:
        return {"gene": gene, "error": str(exc), "rows": []}

    return {
        "gene": gene,
        "total_rows": len(partners),
        "rows": partners,
    }


# Tool schemas for Groq's (OpenAI-compatible) tool-calling API — see
# investigation_loop.py. Kept alongside the functions they describe so the
# schema can never silently drift from the actual signature.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_genetic_evidence",
            "description": (
                "Fetch real genetic evidence for a gene against the configured disease from "
                "Open Targets, covering whichever real datasources (ClinVar, GWAS credible "
                "sets, Orphanet, etc.) carry genetic evidence for this specific target-disease "
                "pair."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                },
                "required": ["gene"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_literature_evidence",
            "description": "Fetch real PubMed co-occurrence evidence for a gene and disease.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                    "disease": {"type": "string", "description": "Disease name, e.g. Amyotrophic Lateral Sclerosis"},
                },
                "required": ["gene", "disease"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_pathway_evidence",
            "description": (
                "Fetch real curated Reactome pathway membership for a gene (e.g. "
                "'Detoxification of Reactive Oxygen Species'). Disease-agnostic: reflects "
                "whether the gene participates in any curated pathway at all, not "
                "disease-specific evidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                },
                "required": ["gene"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clinical_evidence",
            "description": "Fetch real clinical trial/precedence evidence for a gene and disease from Open Targets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                    "disease": {"type": "string", "description": "Disease name, e.g. Amyotrophic Lateral Sclerosis"},
                },
                "required": ["gene", "disease"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_experimental_evidence",
            "description": "Fetch real IMPC animal-model phenotype evidence for a gene and disease from Open Targets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                    "disease": {"type": "string", "description": "Disease name, e.g. Amyotrophic Lateral Sclerosis"},
                },
                "required": ["gene", "disease"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_omics_evidence",
            "description": (
                "Fetch real differential-expression (Expression Atlas) evidence for a gene and "
                "disease from Open Targets. NOTE: confirmed to return zero rows for every real "
                "ALS candidate gene in this project — the datasource appears to have been "
                "retired from the live Open Targets Platform."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                    "disease": {"type": "string", "description": "Disease name, e.g. Amyotrophic Lateral Sclerosis"},
                },
                "required": ["gene", "disease"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_drug_target_evidence",
            "description": (
                "Fetch real ChEMBL-backed drug-target mechanism-of-action data for a gene "
                "(e.g. drug name, drug type, mechanism of action), already filtered to the "
                "configured disease."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                },
                "required": ["gene"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tissue_expression",
            "description": (
                "Fetch real Human Protein Atlas tissue-expression specificity data for a gene "
                "(which tissues it's expressed in and how specific that expression is). "
                "Disease-agnostic — supportive biological context, not a disease- or "
                "safety-relevance signal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                },
                "required": ["gene"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ppi_network",
            "description": (
                "Fetch real STRING high-confidence (combined_score > 700) protein-protein "
                "interaction partners for a gene. Disease-agnostic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gene": {"type": "string", "description": "Gene symbol, e.g. SOD1"},
                },
                "required": ["gene"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "search_genetic_evidence": search_genetic_evidence,
    "search_literature_evidence": search_literature_evidence,
    "search_pathway_evidence": search_pathway_evidence,
    "search_clinical_evidence": search_clinical_evidence,
    "search_experimental_evidence": search_experimental_evidence,
    "search_omics_evidence": search_omics_evidence,
    "search_drug_target_evidence": search_drug_target_evidence,
    "search_tissue_expression": search_tissue_expression,
    "search_ppi_network": search_ppi_network,
}
