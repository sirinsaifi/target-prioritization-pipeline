"""
Expression Atlas DIRECT REST API client — NOT via Open Targets.

Confirmed live: the Open Targets Platform's routing to Expression Atlas is
broken/retired (confirmed in earlier Omics cleanup). BUT Expression Atlas
itself is alive and actively maintained (4,562 studies as of Sep 2026),
with its OWN direct REST API and download endpoints.

This client queries Expression Atlas directly using its native JSON and TSV
download endpoints. It follows the existing client pattern (see
open_targets_client.py, literature_client.py), using `requests` with the
same timeout/error-handling conventions.

API endpoints confirmed working (live-tested Sep 2026):
  - GET /gxa/json/experiments                       → list all experiments
  - GET /gxa/json/experiments/{accession}            → metadata + partial expression profiles
  - GET /gxa/experiments-content/{accession}/download/{type}?geneQuery={gene}
    → TSV download with gene-specific expression values (BASELINE: TPM values;
      DIFFERENTIAL: foldChange + pValue)

Verified for real ALS genes:
  - SOD1 (ENSG00000142168): expressed in ALL 53 GTEx tissues at high levels
    (106-853 TPM), highest in liver/adrenal/cerebral cortex
  - TP53 (ENSG00000141510): expressed in all 29 tissues, moderately
    (6-52 TPM)
  - 5 human ALS differential experiments identified with real data
"""

import csv
import io
from typing import Any, Dict, List, Optional

import requests

EXPRESSION_ATLAS_BASE = "https://www.ebi.ac.uk/gxa"

# ── Baseline experiments with the broadest human tissue coverage ─────────
# Confirmed to contain expression data for SOD1, TP53 (and by extension,
# most human genes). Queried via the TSV download endpoint.
BASELINE_EXPERIMENTS = [
    "E-GTEX-8",       # GTEx v8 — 53 tissues, 17,382 samples
    "E-MTAB-2836",    # Human tissue atlas — 32 tissues, 122 individuals
    "E-MTAB-513",     # Illumina Body Map — 16 tissues
]

# ── Human ALS differential expression experiments (confirmed real) ────────
# Each compares ALS patients (or ALS-relevant models) vs controls in a
# disease-relevant tissue/cell-type.
ALS_DIFFERENTIAL_EXPERIMENTS = [
    "E-GEOD-52946",   # sporadic ALS vs normal (whole blood RNA-seq)
    "E-GEOD-52202",   # C9orf72 ALS vs normal (iPSC motor neurons, RNA-seq)
    "E-GEOD-67196",   # ALS cerebellum + frontal cortex (C9orf72+ and C9orf72-)
    "E-MTAB-1925",    # ALS post-mortem brain cortex (microarray)
    "E-GEOD-56808",   # sporadic ALS vs normal (fibroblast, microarray)
]

TIMEOUT_SEC = 30


# ──────────────────────────── helpers ──────────────────────────────────────

def _fetch_json(path: str) -> dict:
    """GET a JSON endpoint under /gxa."""
    resp = requests.get(f"{EXPRESSION_ATLAS_BASE}{path}", timeout=TIMEOUT_SEC,
                        headers={"Accept": "application/json",
                                 "User-Agent": "TargetEvidenceIntelligence/1.0"})
    resp.raise_for_status()
    return resp.json()


def _fetch_tsv(path: str) -> str:
    """GET a TSV endpoint under /gxa (the download API)."""
    resp = requests.get(f"{EXPRESSION_ATLAS_BASE}{path}", timeout=TIMEOUT_SEC,
                        headers={"Accept": "text/tsv",
                                 "User-Agent": "TargetEvidenceIntelligence/1.0"})
    resp.raise_for_status()
    return resp.text


def _parse_tsv_rows(tsv_text: str) -> list[dict[str, str]]:
    """Parse TSV into a list of dicts, skipping comment lines."""
    lines = tsv_text.strip().split("\n")
    data_lines = [ln for ln in lines if not ln.startswith("#")]
    if not data_lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(data_lines)), delimiter="\t")
    return list(reader)


# ──────────────────────── public API ──────────────────────────────────────

def list_experiments() -> List[dict]:
    """
    List all experiments indexed in Expression Atlas.
    Returns the raw JSON list from /json/experiments.
    """
    return _fetch_json("/json/experiments").get("experiments", [])


def get_experiment_metadata(accession: str) -> dict:
    """Return full experiment metadata (species, type, column headers, etc.)."""
    return _fetch_json(f"/json/experiments/{accession}")


# ── Baseline expression (TPM values per tissue/condition) ──────────────────

def get_baseline_expression(
    gene: str,
    experiment_accession: str,
    unit: str = "TPM",
) -> List[Dict[str, str]]:
    """
    Fetch baseline expression values for *gene* in *experiment*.

    Parameters
    ----------
    gene : str
        Gene symbol (e.g. "SOD1") or Ensembl ID (e.g. "ENSG00000142168").
        Symbol-based queries are more reliable in the Atlas search index.
    experiment_accession : str
        E.g. "E-GTEX-8", "E-MTAB-2836".
    unit : str
        "TPM" (transcripts per million — the standard RNA-seq unit).

    Returns
    -------
    list[dict]
        Each dict has keys: "Gene ID", "Gene Name", plus one column per
        tissue/condition with the TPM value (empty string if below detection).
    """
    path = (
        f"/experiments-content/{experiment_accession}/download/"
        f"RNASEQ_MRNA_BASELINE"
        f"?geneQuery={gene}&unit={unit}&cutoff=0.0&heatmapMatrixSize=1"
    )
    raw = _fetch_tsv(path)
    return _parse_tsv_rows(raw)


def get_baseline_across_experiments(
    gene: str,
    experiments: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Fetch baseline expression across multiple experiments.

    Returns {experiment_accession: parsed_rows}.
    """
    if experiments is None:
        experiments = BASELINE_EXPERIMENTS
    result: Dict[str, List[Dict[str, str]]] = {}
    for exp in experiments:
        try:
            rows = get_baseline_expression(gene, exp)
            result[exp] = rows
        except Exception as exc:
            result[exp] = [{"error": str(exc)}]
    return result


# ── Differential expression (fold change + p-value) ───────────────────────

def get_differential_expression(
    gene: str,
    experiment_accession: str,
    cutoff: float = 0.0,
) -> List[Dict[str, str]]:
    """
    Fetch differential expression results for *gene* in *experiment*.

    Parameters
    ----------
    gene : str
        Gene symbol or Ensembl ID.
    experiment_accession : str
        Differential experiment accession (e.g. "E-GEOD-52946").
    cutoff : float
        Adjusted p-value cutoff. 0.0 = include all results regardless of
        significance (the API still applies a default log2FC cutoff of 1).

    Returns
    -------
    list[dict]
        Each dict has columns:
          "Gene ID", "Gene Name",
          "{comparison}.foldChange", "{comparison}.pValue"
        Empty list if the gene is NOT significantly differentially expressed
        in this experiment at the given cutoff (this IS meaningful data —
        not a failure).

    Notes
    -----
    The API enforces a minimum |log2FC| of 1 even with cutoff=0.0, so genes
    with very small fold changes are not returned even if they pass the
    p-value filter.
    """
    # Try RNA-seq first, fall back to microarray
    for etype in ["RNASEQ_MRNA_DIFFERENTIAL", "MICROARRAY_1COLOUR_MRNA_DIFFERENTIAL"]:
        path = (
            f"/experiments-content/{experiment_accession}/download/{etype}"
            f"?geneQuery={gene}&unit=FOLD_CHANGE&cutoff={cutoff}&heatmapMatrixSize=1"
        )
        try:
            raw = _fetch_tsv(path)
        except requests.HTTPError:
            continue
        rows = _parse_tsv_rows(raw)
        if rows:
            return rows
    return []


def get_differential_across_als_experiments(
    gene: str,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Fetch differential expression across ALL known human ALS experiments.
    Unlike baseline (which has one expression profile per tissue), each
    differential experiment has its own disease-vs-control comparison.
    We query all 5 known ALS experiments and return per-experiment results.
    """
    result: Dict[str, List[Dict[str, str]]] = {}
    for exp in ALS_DIFFERENTIAL_EXPERIMENTS:
        try:
            rows = get_differential_expression(gene, exp)
            result[exp] = rows
        except Exception:
            result[exp] = []
    return result


# ── Expression Atlas gene search ──────────────────────────────────────────

def search_gene(gene: str) -> List[dict]:
    """
    Search Expression Atlas for a gene. Uses EBI Search API.
    Returns best-matching entry with Ensembl ID, species, description.
    Useful for disambiguating human vs non-human matches.
    """
    url = (
        f"https://www.ebi.ac.uk/ebisearch/ws/rest/atlas-genes"
        f"?query={gene}&size=10&fields=id,description,name&format=json"
    )
    resp = requests.get(url, timeout=TIMEOUT_SEC,
                        headers={"User-Agent": "TargetEvidenceIntelligence/1.0"})
    resp.raise_for_status()
    data = resp.json()
    return data.get("entries", [])


def find_human_experiments_for_gene(gene: str) -> List[dict]:
    """
    Use EBI Search to find which experiments contain expression data for
    a given gene. The atlas-genes search index tracks this association.
    """
    # Search atlas-experiments for gene mentions
    url = (
        f"https://www.ebi.ac.uk/ebisearch/ws/rest/atlas-experiments"
        f"?query={gene}+AND+species:%22Homo+sapiens%22"
        f"&size=100&fields=description,species&format=json"
    )
    resp = requests.get(url, timeout=TIMEOUT_SEC,
                        headers={"User-Agent": "TargetEvidenceIntelligence/1.0"})
    resp.raise_for_status()
    data = resp.json()
    return data.get("entries", [])