"""
Pharos druggability client — independent of the Open Targets Platform.

Pharos (pharos.nih.gov) is the NIH/NCATS knowledgebase that categorizes every
druggable target in the human genome. This client pulls FIVE distinct real
signals from Pharos's GraphQL API per gene, all in one round-trip:

1. TDL (Target Development Level: Tclin > Tchem > Tbio > Tdark) — the core
   druggability tier, scored via dimension_scoring.score_druggability_tdl().
2. Novelty (real Float field) — how under-studied a target is relative to
   its apparent importance (lower = more established). DISTINCT from TDL: a
   target can be well-studied (low novelty) yet still Tdark (no druggability
   characterization), or novel (high novelty) yet Tchem. Stored as its own
   field, never merged into the TDL-derived score.
3. Protein family (fam) — stored as context, with a prototype family-
   druggability heuristic label (see config.family_druggability_heuristic).
4. Ligand/drug activity detail — per-compound isdrug (approved vs. research)
   + activity type/value (EC50/IC50/Ki pChEMBL values), not just a count.
   Bounded to the top-N ligands by activity count (see LIGAND_SAMPLE_TOP).
5. Disease-association + PPI raw data — fetched here for the cross-check
   module (app/core/verification/pharos_cross_checks.py), which compares
   Pharos's own ALS evidence against this project's OTP-derived scores
   (item D) and Pharos's PPI partners against STRING (item E). These cross-
   checks are NOT a new EvidenceRecord dimension — they're comparisons.

No login required. Confirmed live (2026-09-09): the working GraphQL endpoint
is https://pharos-api.ncats.io/graphql — NOT pharos.nih.gov/api or
pharos.nih.gov/api/graphql, which both return 403 Forbidden (nginx block).

REAL, LIVE-CONFIRMED SCHEMA (via GraphQL introspection, dbVersion pharos319):
- The PPI fields are `ppis` (->[TargetNeighbor]) and `ppiCounts` (->[IntProp]),
  NOT `interactingProteins`/`interactions` (those names do NOT exist on the
  Target type — confirmed via introspection; the task's assumed field name was
  wrong, corrected here). TargetNeighbor.target is the neighbor's full Target.
- `diseaseAssociationDetails` (top-level) returns null for real genes — the
  per-gene disease signal lives in `diseases { associations { type score
  evidence conf source } }` (the Disease.associations list), NOT the
  top-level diseaseAssociationDetails field. CRITICAL: `diseaseCounts` /
  `associationCount` values are DISEASE-GLOBAL (e.g. 501 = total targets
  associated with ALS in Pharos, identical across all genes), NOT a per-gene
  evidence count — the per-gene signal is the DisGeNET `score` inside
  associations[] (SOD1/C9orf72/TARDBP=0.7, FUS=0.5, NEK1=0.61).
- `ligandAssociationDetails` (top-level) returns null for SOD1 — per-ligand
  activity detail lives in `ligands { activities { type value moa } }`.
- `ligands { count }` does NOT work (no count field on Ligand); the aggregate
  is `ligandCounts { value name }`, the per-ligand activity-count is `actcnt`.

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

# Bounds on the per-gene sample sizes fetched, so one gene's payload stays
# proportionate (NEK1 has 165 ligands and 88 PPI partners — fetching every
# one would bloat the stored notes without changing the druggability signal).
# The cross-check module reads partner LISTS, so PPI needs enough partners to
# compute meaningful overlap with STRING's high-confidence set — 50 is ample
# (STRING's own high-confidence sets for these genes are 10-485 partners).
LIGAND_SAMPLE_TOP = 10
PPI_PARTNER_SAMPLE_TOP = 50
# How many diseases to pull to reliably find the ALS entry (Pharos returns
# diseases unordered; ALS is one of hundreds for SOD1). 500 is generous —
# confirmed live: SOD1's ALS entry is within the first 500.
DISEASE_SAMPLE_TOP = 500

# One query per gene — fetches every real field all 5 signals need in a
# single round-trip. fam/ligandCounts can be null/empty for real genes
# (confirmed: C9orf72 has fam=null, ligandCounts=[{0,ligand},{0,drug}]); the
# client handles both honestly rather than substituting defaults.
_TARGET_QUERY = """
query targetBySym($sym: String) {
  target(q: {sym: $sym}) {
    name tdl fam sym description novelty publicationCount
    ligandCounts { value name }
    ligands(top: %d) { name isdrug actcnt activities { type value moa } }
    diseases(top: %d) { name associationCount associations { type evidence score conf source } }
    ppiCounts { value name }
    ppis(top: %d) { type target { sym name } }
  }
}
""" % (LIGAND_SAMPLE_TOP, DISEASE_SAMPLE_TOP, PPI_PARTNER_SAMPLE_TOP)

# Disease-name substrings (case-insensitive) that count as ALS-related for the
# disease-association cross-check. The EXACT "amyotrophic lateral sclerosis"
# match is the primary signal (its DisGeNET score is the cross-check value);
# the gene-specific subtypes (ALS1/6/10/24, FTDALS1) are recorded as context.
_ALS_DISEASE_SUBSTRINGS = ("amyotrophic lateral sclerosis",)


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


def _summarize_ligands(ligands: list | None) -> list[dict]:
    """
    Bounded per-ligand activity detail (Signal C) — NOT just a count. For
    each sampled ligand: name, isdrug (approved vs. research compound),
    actcnt, and a compact list of its activities [{type, value, moa}]. The
    full ligand list is bounded by LIGAND_SAMPLE_TOP in the query; a target
    with more ligands (NEK1=165) is sampled, not exhaustively stored — the
    aggregate ligand_count/drug_count (from ligandCounts) is stored
    separately and IS exhaustive.
    """
    if not ligands:
        return []
    summary = []
    for lig in ligands:
        if not isinstance(lig, dict):
            continue
        activities = [
            {"type": a.get("type"), "value": a.get("value"), "moa": a.get("moa")}
            for a in (lig.get("activities") or []) if isinstance(a, dict)
        ]
        summary.append({
            "name": lig.get("name"),
            "isdrug": bool(lig.get("isdrug")),
            "actcnt": lig.get("actcnt", 0),
            "activities": activities,
        })
    return summary


def _extract_als_association(diseases: list | None) -> dict | None:
    """
    Signal D's raw input: the per-gene ALS disease association from Pharos.
    CRITICAL (live-confirmed): `associationCount`/`diseaseCounts` are
    DISEASE-GLOBAL (501 = total ALS-associated targets in Pharos, identical
    across genes) — the per-gene signal is the DisGeNET `score` inside the
    EXACT "amyotrophic lateral sclerosis" disease's associations[] list.

    Returns the DisGeNET score + PubMed/SNP evidence for the exact ALS match,
    plus the gene-specific ALS subtype name (ALS1/6/10/24, FTDALS1) as
    context, or None if no ALS disease entry exists for this gene.
    """
    if not diseases:
        return None
    exact_als = None
    subtype = None
    for disease in diseases:
        if not isinstance(disease, dict):
            continue
        name = (disease.get("name") or "").strip()
        name_lower = name.lower()
        if name_lower == "amyotrophic lateral sclerosis":
            exact_als = disease
        elif "amyotrophic lateral sclerosis" in name_lower and name_lower != "amyotrophic lateral sclerosis":
            # A subtype (ALS1/6/10/24, FTDALS1, sporadic, Guam form, ...).
            # Record the first gene-specific subtype as context.
            if subtype is None:
                subtype = name
    if exact_als is None:
        return None
    disgenet_score = None
    evidence = None
    for assoc in (exact_als.get("associations") or []):
        if isinstance(assoc, dict) and assoc.get("type") == "DisGeNET":
            disgenet_score = assoc.get("score")
            evidence = assoc.get("evidence")
            break
    return {
        "disgenet_score": disgenet_score,
        "evidence": evidence,
        "subtype": subtype,
    }


def _summarize_ppis(ppis: list | None, ppi_counts: list | None) -> dict:
    """
    Signal E's raw input: Pharos PPI partners + counts. Returns the STRINGDB
    partner count (the directly-comparable figure, since this project's
    STRING ingestion also uses STRINGDB) and a bounded list of partner
    symbols for the overlap cross-check against the stored STRING
    ppi_network row. Also returns the Total count and BioPlex/Reactome
    counts as context.
    """
    counts = {}
    for entry in (ppi_counts or []):
        if isinstance(entry, dict):
            counts[entry.get("name")] = entry.get("value", 0)
    partners = []
    for ppi in (ppis or []):
        if not isinstance(ppi, dict):
            continue
        target = ppi.get("target") or {}
        sym = target.get("sym")
        if sym:
            partners.append(sym)
    return {
        "stringdb_count": int(counts.get("STRINGDB", 0)),
        "bioplex_count": int(counts.get("BioPlex", 0)),
        "reactome_count": int(counts.get("Reactome", 0)),
        "total_count": int(counts.get("Total", 0)),
        "partner_symbols": partners,
    }


def get_druggability_evidence(gene_symbol: str) -> dict | None:
    """
    Query Pharos for one gene's full druggability characterization (all 5
    signals) and return a normalized row ready for ingestion, or None if
    Pharos has no target for this symbol (a real absence — confirmed live:
    an unknown symbol returns {"data": {"target": null}}, surfaced as None
    rather than fabricating a Tdark-default row).

    Every field in the returned dict is real, straight from the live API
    response — nothing is defaulted or guessed. `fam` may legitimately be
    None (3 of the 5 real ALS genes return null), ligand_count/drug_count
    may be 0, and the ALS disease association may be None (no ALS entry).
    """
    response = requests.post(
        PHAROS_GRAPHQL_URL,
        json={"query": _TARGET_QUERY, "variables": {"sym": gene_symbol}},
        timeout=60,
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
        "ligands": _summarize_ligands(target.get("ligands")),
        "als_association": _extract_als_association(target.get("diseases")),
        "ppi": _summarize_ppis(target.get("ppis"), target.get("ppiCounts")),
    }


if __name__ == "__main__":
    # Manual smoke test — requires network access to pharos-api.ncats.io
    from app.config import CANDIDATE_TARGETS

    for gene in CANDIDATE_TARGETS:
        row = get_druggability_evidence(gene)
        if row is None:
            print(f"{gene}: NOT FOUND in Pharos")
            continue
        als = row["als_association"] or {}
        ppi = row["ppi"]
        print(f"{gene}: tdl={row['tdl']}, fam={row['fam']}, novelty={row['novelty']}, "
              f"ligands={row['ligand_count']}(drugs={row['drug_count']}), "
              f"als_disgenet={als.get('disgenet_score')}, als_evidence={als.get('evidence')}, "
              f"als_subtype={als.get('subtype')}, "
              f"ppi_stringdb={ppi['stringdb_count']}(sampled {len(ppi['partner_symbols'])})")
