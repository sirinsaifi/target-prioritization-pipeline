"""
Human Protein Atlas (HPA) client — tissue expression / specificity.

Used in place of Open Targets' Expression Atlas datasource, which live
introspection confirmed returns zero real rows for every gene tested (see
config.EXPRESSION_ATLAS_DATASOURCE_ID's docstring) — HPA is a genuinely
different, independent external source, not a substitute query against OTP.

API confirmed live, real, and public: GET https://www.proteinatlas.org/<ensembl_id>.json
(no API key required). Real sample pulled for SOD1 (ENSG00000142168) before
writing this client, plus INS/ACTB as high-specificity/ubiquitous reference
points — see docs for the real field values found.

REAL FIELDS USED (confirmed via live introspection, not guessed):
- "RNA tissue specificity": categorical — "Tissue enriched" > "Group
  enriched" > "Tissue enhanced" > "Low tissue specificity" > "Not
  detected" (HPA's own ordered taxonomy, most to least specific).
- "RNA tissue distribution": categorical breadth — "Detected in all" /
  "Detected in many" / "Detected in some" / "Detected in single" / "Not
  detected".
- "RNA tissue specific nTPM": dict of {tissue: nTPM value}, but ONLY for
  the tissue(s) driving the "enriched"/"enhanced" classification, not a
  complete per-tissue profile — confirmed via a real SOD1 sample
  ({"liver": "1537.1"}, one entry despite SOD1 being broadly detected).

NOT USED, and why: "RNA tissue specificity score" was checked as a
candidate for a ready-made numeric specificity score, but confirmed via
real samples to be unreliable — null for 2 of 3 test genes (SOD1, ACTB),
and even when populated (INS: "135") it is a different kind of statistic
(a fold-enrichment value, unbounded) rather than a comparable 0-1 score —
not usable as a drop-in replacement for the categorical mapping this
client builds instead (see dimension_scoring.score_tissue_specificity()).
"""

import requests

HPA_BASE_URL = "https://www.proteinatlas.org"


def get_tissue_expression(ensembl_id: str) -> dict | None:
    """
    Fetch real HPA tissue-expression data for one gene. Returns None if HPA
    has no record for this Ensembl ID (real 404, not an error) — the
    caller decides what "no data" means, this function doesn't fabricate a
    default.
    """
    url = f"{HPA_BASE_URL}/{ensembl_id}.json"
    response = requests.get(url, timeout=20)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    return {
        "gene": data.get("Gene"),
        "rna_tissue_specificity": data.get("RNA tissue specificity"),
        "rna_tissue_distribution": data.get("RNA tissue distribution"),
        "rna_tissue_specific_nTPM": data.get("RNA tissue specific nTPM"),
    }


if __name__ == "__main__":
    # Manual smoke test — requires network access to proteinatlas.org
    result = get_tissue_expression("ENSG00000142168")
    print(result)
