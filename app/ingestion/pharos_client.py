"""
Pharos druggability client — independent of the Open Targets Platform.

Pharos (pharos.nih.gov) is the NIH/NCATS knowledgebase that categorizes every
druggable target in the human genome by Target Development Level (TDL):
Tclin > Tchem > Tbio > Tdark. This is a genuinely independent signal from
anything OTP provides — OTP's own Target Prioritisation Factors deliberately
exclude every structural/druggability factor (hasLigand, hasPocket,
hasSmallMoleculeBinder, etc. — see app/config.py's "ot_essentiality" entry),
so Pharos is the project's first real druggability source.

No login required. Confirmed live (2026-09-09): the working GraphQL endpoint
is https://pharos-api.ncats.io/graphql — NOT pharos.nih.gov/api or
pharos.nih.gov/api/graphql, which both return 403 Forbidden (nginx block).
Discovered via live probing, not assumed — see CLAUDE.md's "introspect first,
pull real sample data, then build" discipline.

Real, live-confirmed field semantics (verified against all 5 ALS genes):
- tdl: "Tclin" | "Tchem" | "Tbio" | "Tdark" — the druggability tier
- fam: target family ("Enzyme", "Kinase", ...) — REAL NULL for some genes
  (C9orf72/TARDBP/FUS all return fam=null), never guessed
- novelty: 0-1 float — how novel/under-studied the target is (lower = more
  established; SOD1=0.00040, NEK1=0.01649)
- publicationCount: int — Pharos's own literature count (distinct from this
  project's PubMed/OTP literature ingestion, not used as evidence here)
- ligandCounts: list of {value, name} where name in {"ligand","drug"} — the
  aggregate count of known ligands vs. approved drugs. `ligands { count }`
  does NOT work (no `count` field on the Ligand type — confirmed live: the
  per-ligand field is `actcnt`, the aggregate is `ligandCounts`).

NO tissue/population/assay_type/direction_on_trait fields exist on the Pharos
Target type (confirmed via live introspection) — this dimension is therefore
structurally excluded from direction-of-effect contradiction checking, the
same treatment as pathway/drug_target/safety_signal (see
app.config.COMPARABILITY_FIELDS_BY_SOURCE_TYPE["druggability"]).

API: https://pharos-api.ncats.io/graphql
Docs: https://pharos.nih.gov (the web UI; the API itself is undocumented but live)
"""

import requests

PHAROS_GRAPHQL_URL = "https://pharos-api.ncats.io/graphql"

# One query per gene — fetches every real field this dimension needs in a
# single round-trip. fam/ligandCounts can be null/empty for real genes
# (confirmed: C9orf72 has fam=null, ligandCounts=[{0,ligand},{0,drug}]); the
# client handles both honestly rather than substituting defaults.
_TARGET_QUERY = """
query targetBySym($sym: String) {
  target(q: {sym: $sym}) {
    name
    tdl
    fam
    sym
    description
    novelty
    publicationCount
    ligandCounts { value name }
  }
}
"""


def _parse_ligand_counts(ligand_counts: list | None) -> tuple[int, int]:
    """
    Pharos returns ligandCounts as a list of {value, name} objects where
    name is "ligand" or "drug". Returns (ligand_count, drug_count) — (0, 0)
    when the field is null/empty (a real absence for an undrugged target,
    not a parsing failure).
    """
    if not ligand_counts:
        return 0, 0
    by_name = {entry.get("name"): entry.get("value", 0) for entry in ligand_counts if isinstance(entry, dict)}
    return int(by_name.get("ligand", 0)), int(by_name.get("drug", 0))


def get_druggability_evidence(gene_symbol: str) -> dict | None:
    """
    Query Pharos for one gene's druggability characterization and return a
    normalized row ready for ingestion, or None if Pharos has no target for
    this symbol (a real absence — confirmed live: an unknown symbol returns
    {"data": {"target": null}}, which this function surfaces as None rather
    than fabricating a Tdark-default row).

    Every field in the returned dict is real, straight from the live API
    response — nothing is defaulted or guessed. `fam` may legitimately be
    None (3 of the 5 real ALS genes return null), and ligand_count/drug_count
    may legitimately be 0.
    """
    response = requests.post(
        PHAROS_GRAPHQL_URL,
        json={"query": _TARGET_QUERY, "variables": {"sym": gene_symbol}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    target = payload.get("data", {}).get("target")
    if target is None:
        return None
    ligand_count, drug_count = _parse_ligand_counts(target.get("ligandCounts"))
    return {
        "sym": target.get("sym") or gene_symbol,
        "name": target.get("name"),
        "tdl": target.get("tdl"),
        "fam": target.get("fam"),
        "description": target.get("description"),
        "novelty": target.get("novelty"),
        "publication_count": target.get("publicationCount"),
        "ligand_count": ligand_count,
        "drug_count": drug_count,
    }


if __name__ == "__main__":
    # Manual smoke test — requires network access to pharos-api.ncats.io
    from app.config import CANDIDATE_TARGETS

    for gene in CANDIDATE_TARGETS:
        row = get_druggability_evidence(gene)
        if row is None:
            print(f"{gene}: NOT FOUND in Pharos")
        else:
            print(f"{gene}: tdl={row['tdl']}, fam={row['fam']}, "
                  f"novelty={row['novelty']}, ligands={row['ligand_count']}, "
                  f"drugs={row['drug_count']}, pubs={row['publication_count']}")
