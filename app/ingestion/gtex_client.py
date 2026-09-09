"""
GTEx Portal API v2 client — real, direct healthy-tissue gene expression
data. Replaces the Expression Atlas integration attempt: Expression Atlas
is alive at its own source (confirmed real data for SOD1/TP53), but has no
usable per-gene/disease REST API — only a bulk per-experiment flat-file
archive with no gene+disease search mechanism (see this task's
predecessor write-up in CLAUDE.md). GTEx's own v2 API is exactly the shape
every other client in this project already has: one real gene in, one
real JSON response out.

CONCEPTUAL SCOPE, decided explicitly (this task, see
scripts/ingest_evidence.py's _build_gtex_fields() docstring for the full
reasoning): GTEx measures REAL median expression levels across healthy
donors — NOT disease-vs-healthy differential expression the way
Expression Atlas would have been. This is the same underlying concept the
existing Tissue Expression dimension (HPA) already covers, just from a
second, independent, richer real source — so this is stored as
dimension="tissue_expression", data_source="gtex", NOT a new "omics"
dimension.

API: https://gtexportal.org/api/v2/
Docs: https://gtexportal.org/api/v2/docs (real, live OpenAPI spec, confirmed)

REAL FIELDS CONFIRMED LIVE (this task) for SOD1 (ENSG00000142168.14) and
TP53 (ENSG00000141510.16), both via GET /api/v2/expression/medianGeneExpression
?gencodeId=...&datasetId=gtex_v8 — 54 real tissues each, e.g.:
    {"median": 247.236, "tissueSiteDetailId": "Brain_Substantia_nigra",
     "ontologyId": "UBERON:0002038", "datasetId": "gtex_v8",
     "gencodeId": "ENSG00000142168.14", "geneSymbol": "SOD1", "unit": "TPM"}
"""

import requests

GTEX_BASE_URL = "https://gtexportal.org/api/v2"

# Matches gencodeVersion "v26", the /reference/gene endpoint's own default
# annotation release — confirmed live this is the version SOD1's/TP53's
# real gencodeId comes back as, and gtex_v8 is the dataset that actually
# has real expression rows under that annotation (gtex_v10, the API's own
# newer default dataset, returned 0 real rows for the same gencodeId —
# confirmed live, a real annotation-version mismatch, not a bug here).
GTEX_DATASET_ID = "gtex_v8"


def _resolve_gencode_id(gene_symbol: str) -> str | None:
    """
    Real versioned gencodeId (e.g. "ENSG00000142168.14") for a gene
    symbol — confirmed live for SOD1/TP53. Returns None if GTEx has no
    real mapping for this symbol (a real absence, not an error).
    """
    response = requests.get(f"{GTEX_BASE_URL}/reference/gene", params={"geneId": gene_symbol}, timeout=20)
    response.raise_for_status()
    rows = response.json().get("data", [])
    return rows[0]["gencodeId"] if rows else None


def get_median_tissue_expression(gene_symbol: str) -> dict[str, float] | None:
    """
    Real median TPM expression per tissue (up to 54 real GTEx tissues,
    healthy donors) for one gene. Returns None if GTEx has no real gene
    mapping at all (distinct from a real, empty {} result for a gene that
    resolves but has zero expression rows — both are honestly possible,
    never conflated).
    """
    gencode_id = _resolve_gencode_id(gene_symbol)
    if gencode_id is None:
        return None

    response = requests.get(
        f"{GTEX_BASE_URL}/expression/medianGeneExpression",
        params={"gencodeId": gencode_id, "datasetId": GTEX_DATASET_ID},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json().get("data", [])
    return {row["tissueSiteDetailId"]: row["median"] for row in rows}


if __name__ == "__main__":
    # Manual smoke test — requires network access to gtexportal.org.
    # Real, expected output: 54 real tissues for both SOD1 and TP53.
    for gene in ("SOD1", "TP53"):
        result = get_median_tissue_expression(gene)
        if result is None:
            print(f"{gene}: no real GTEx gene mapping")
        else:
            print(f"{gene}: {len(result)} real tissues")
            top = sorted(result.items(), key=lambda kv: -kv[1])[:3]
            for tissue, median in top:
                print(f"    {tissue}: {median} TPM")
