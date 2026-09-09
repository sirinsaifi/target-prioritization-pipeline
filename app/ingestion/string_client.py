"""
STRING (string-db.org) client — protein-protein interaction (PPI) network
context.

API confirmed live, real, and public (no API key required). Real sample
pulled for SOD1 before writing this client: 10 real high-confidence
partners at required_score=700 (CCS, BCL2, PARK7, ...).

REAL, TWO-STEP PROCESS (confirmed via live introspection, not guessed):
STRING's `interaction_partners` endpoint needs a STRING-internal protein
ID (e.g. "9606.ENSP00000270142"), not a plain gene symbol — so
`get_ppi_partners()` first resolves the gene symbol via
`get_string_ids`, then queries partners for that resolved ID.

IMPORTANT SCALE MISMATCH, confirmed live, not assumed: STRING's
`required_score` query PARAMETER uses the 0-1000 integer convention
documented for STRING's combined_score (the task's "combined_score > 700"
threshold applies here, and does filter correctly — confirmed live), but
the `score` field in each RETURNED row is a 0-1 float (e.g. 0.999), not
the 0-1000 integer. Both conventions are real and simultaneously in use
by this one real API — not a bug in this client, a real quirk of
STRING's own REST API vs. its bulk-download file format.
"""

import requests

STRING_BASE_URL = "https://string-db.org/api"
STRING_SPECIES_HUMAN = 9606


def get_string_id(gene_symbol: str) -> str | None:
    """
    Resolve a gene symbol to its real STRING-internal protein identifier
    (e.g. "9606.ENSP00000270142") — the ID-resolution step
    get_ppi_partners() already does internally, factored out here so a
    caller that needs the real id ITSELF (not just the partner list) —
    e.g. scripts/ingest_evidence.py, capturing it for a real, clickable
    STRING source link — doesn't have to reimplement this lookup. Returns
    None if STRING has no real mapping for this gene symbol (a real
    absence, not an error), same convention as get_ppi_partners().
    """
    id_response = requests.get(
        f"{STRING_BASE_URL}/json/get_string_ids",
        params={"identifiers": gene_symbol, "species": STRING_SPECIES_HUMAN},
        timeout=20,
    )
    id_response.raise_for_status()
    id_matches = id_response.json()
    return id_matches[0]["stringId"] if id_matches else None


def get_ppi_partners(gene_symbol: str, required_score: int = 700) -> list[dict]:
    """
    Fetch real high-confidence STRING interaction partners for a gene.
    Returns an empty list if STRING has no real mapping for this gene
    symbol (real absence, not an error) — the ID-resolution step returning
    zero hits is itself a valid, real outcome.
    """
    string_id = get_string_id(gene_symbol)
    if string_id is None:
        return []

    partners_response = requests.get(
        f"{STRING_BASE_URL}/json/interaction_partners",
        params={"identifiers": string_id, "species": STRING_SPECIES_HUMAN, "required_score": required_score},
        timeout=20,
    )
    partners_response.raise_for_status()
    return partners_response.json()


if __name__ == "__main__":
    # Manual smoke test — requires network access to string-db.org
    result = get_ppi_partners("SOD1")
    print(f"{len(result)} real high-confidence partners")
    for p in result[:5]:
        print(f"  {p['preferredName_B']}: score={p['score']}")
