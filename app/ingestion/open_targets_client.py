"""
Open Targets Platform GraphQL client.

Pulls pre-computed association scores and L2G genetic evidence directly
from OTP rather than reimplementing their variant-to-gene mapping —
see project scoring reference doc, section 7 ("what to build vs. pull via API").

API endpoint: https://api.platform.opentargets.org/api/v4/graphql
"""

import requests

OTP_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"


def _run_query(query: str, variables: dict) -> dict:
    response = requests.post(OTP_GRAPHQL_URL, json={"query": query, "variables": variables}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"Open Targets GraphQL error: {payload['errors']}")
    return payload["data"]


def get_target_disease_association(ensembl_id: str, efo_id: str) -> dict:
    """
    Fetch the overall association score and per-datatype breakdown for one
    target-disease pair, plus a sample of underlying evidence for later
    normalization into EvidenceRecord rows.
    """
    query = """
    query TargetDiseaseAssociation($ensemblId: String!, $efoId: String!) {
      target(ensemblId: $ensemblId) {
        id
        approvedSymbol
        association: associatedDiseases(Bs: [$efoId]) {
          rows {
            disease { id name }
            score
            datatypeScores { id score }
          }
        }
      }
    }
    """
    data = _run_query(query, {"ensemblId": ensembl_id, "efoId": efo_id})
    return data


# Superset of scalar Evidence fields needed across all source types used by
# this pipeline (genetic / literature / clinical / experimental). OTP returns
# null for whichever fields don't apply to a given datasource rather than
# erroring — this IS the discovery documented in CLAUDE.md: no uniform field
# set exists across evidence source types, so we ask for the union and let
# per-source-type derivation logic (scripts/ingest_evidence.py) pick what's
# actually populated.
_EVIDENCE_FIELDS = """
    id
    score
    studyId
    variantRsId
    clinicalSignificances
    allelicRequirements
    directionOnTrait
    directionOnTarget
    diseaseFromSource
    resourceScore
    literature
    clinicalStage
    drugFromSource
    trialStopReasonCategories
    biosamplesFromSource
    biologicalModelAllelicComposition
    targetInModel
    diseaseModelAssociatedModelPhenotypes { label }
    diseaseModelAssociatedHumanPhenotypes { label }
    publicationYear
    studyStartDate
    log2FoldChangeValue
    log2FoldChangePercentileRank
    pValueMantissa
    pValueExponent
"""


def get_evidence_for_datasource(ensembl_id: str, efo_id: str, datasource_id: str, size: int = 200) -> list[dict]:
    """
    Fetch evidence rows for one (target, disease, datasource) triple.

    Replaces the earlier get_l2g_evidence()/get_literature_evidence()
    functions, which used field names from a retired schema version
    (`diseaseIds` -> now `efoIds`, `variantId` -> now `variantRsId`) and
    hardcoded `ot_genetics_portal`, a datasource that returns zero rows for
    ALS candidate genes on the current platform (superseded by
    `gwas_credible_sets`, and for rare-variant diseases like ALS, dominated
    by `eva`/`uniprot_variants` instead — see CLAUDE.md "Important discovery").
    """
    query = f"""
    query Evidence($ensemblId: String!, $efoId: String!, $datasourceId: String!, $size: Int!) {{
      target(ensemblId: $ensemblId) {{
        id
        evidences(efoIds: [$efoId], datasourceIds: [$datasourceId], size: $size) {{
          count
          rows {{
            {_EVIDENCE_FIELDS}
          }}
        }}
      }}
    }}
    """
    data = _run_query(query, {
        "ensemblId": ensembl_id, "efoId": efo_id, "datasourceId": datasource_id, "size": size,
    })
    return data.get("target", {}).get("evidences", {}).get("rows", [])


def _discover_datasource_ids_for_datatype(ensembl_id: str, efo_id: str, datatype_id: str, page_size: int = 500) -> set[str]:
    """
    Paginate through EVERY real evidence row for one (target, disease) pair,
    collecting the real, complete set of `datasourceId`s whose `datatypeId`
    matches `datatype_id`.

    WHY THIS EXISTS: live schema introspection against Target's `evidences`
    field shows it accepts only `efoIds`/`datasourceIds`/`size`/`cursor` —
    there is NO server-side datatype filter, even though every real Evidence
    row carries its own `datatypeId`. So the only way to query "all genetic
    evidence" without hardcoding which specific OTP datasourceIds count as
    genetic is to discover them here, per (target, disease) pair. Confirmed
    live for SOD1 vs ALS: `datatypeId == "genetic_association"` covers
    `eva`, `uniprot_variants`, `gwas_credible_sets`, AND `orphanet` — the
    last of which a hardcoded 3-item list previously missed entirely (see
    docs/07 "Genetic evidence: datatype-driven fetch"). A GWAS-driven
    disease would surface whatever ITS real dominant datasourceIds are
    through this same discovery, with no code change.

    Cheap per page despite needing many pages for evidence-rich targets
    (SOD1 vs ALS has 9,564 total real rows across all datatypes): each page
    requests only the two scalar fields needed to classify a row, not the
    full Evidence payload.
    """
    query = """
    query DiscoverGeneticDatasources($ensemblId: String!, $efoId: String!, $size: Int!, $cursor: String) {
      target(ensemblId: $ensemblId) {
        evidences(efoIds: [$efoId], size: $size, cursor: $cursor) {
          count
          cursor
          rows { datasourceId datatypeId }
        }
      }
    }
    """
    found: set[str] = set()
    cursor = None
    fetched = 0
    while True:
        data = _run_query(query, {"ensemblId": ensembl_id, "efoId": efo_id, "size": page_size, "cursor": cursor})
        evidences = data.get("target", {}).get("evidences", {})
        rows = evidences.get("rows", [])
        for row in rows:
            if row["datatypeId"] == datatype_id:
                found.add(row["datasourceId"])
        fetched += len(rows)
        cursor = evidences.get("cursor")
        if not rows or cursor is None or fetched >= evidences.get("count", 0):
            break
    return found


def get_evidence_by_datatype(ensembl_id: str, efo_id: str, datatype_id: str, page_size: int = 500) -> list[dict]:
    """
    Fetch ALL real evidence rows for one (target, disease) pair whose
    OTP-assigned `datatypeId` matches `datatype_id` — e.g. "genetic_association"
    — without hardcoding which specific datasourceIds belong to that
    datatype. Replaces the earlier pattern of looping over a fixed
    datasourceId list (e.g. `["eva", "uniprot_variants", "gwas_credible_sets"]`),
    which silently under-collected real evidence in two confirmed ways for
    SOD1 vs ALS: it never included `orphanet` (a real datasourceId under
    "genetic_association" nobody had anticipated), and each per-datasource
    call was separately capped by `size` (the old default 200), silently
    truncating `eva`'s real 275 rows down to 200. Both are fixed here: the
    real datasourceId set is discovered dynamically (see
    _discover_datasource_ids_for_datatype()), and the fetch itself is fully
    paginated rather than capped at one page.

    This makes the fetch disease-agnostic in the way that actually matters:
    it never assumes in advance whether a disease's genetics are
    rare-variant-dominated (eva/uniprot_variants-heavy, like ALS) or
    GWAS-dominated (gwas_credible_sets-heavy) — whichever real
    datasourceIds actually carry `datatype_id` evidence for THIS
    target-disease pair are the ones fetched.
    """
    datasource_ids = _discover_datasource_ids_for_datatype(ensembl_id, efo_id, datatype_id, page_size=page_size)
    if not datasource_ids:
        return []

    query = f"""
    query EvidenceByDatatype($ensemblId: String!, $efoId: String!, $datasourceIds: [String!], $size: Int!, $cursor: String) {{
      target(ensemblId: $ensemblId) {{
        evidences(efoIds: [$efoId], datasourceIds: $datasourceIds, size: $size, cursor: $cursor) {{
          count
          cursor
          rows {{
            {_EVIDENCE_FIELDS}
            datasourceId
            datatypeId
          }}
        }}
      }}
    }}
    """
    all_rows: list[dict] = []
    cursor = None
    fetched = 0
    while True:
        data = _run_query(query, {
            "ensemblId": ensembl_id, "efoId": efo_id,
            "datasourceIds": sorted(datasource_ids), "size": page_size, "cursor": cursor,
        })
        evidences = data.get("target", {}).get("evidences", {})
        rows = evidences.get("rows", [])
        all_rows.extend(rows)
        fetched += len(rows)
        cursor = evidences.get("cursor")
        if not rows or cursor is None or fetched >= evidences.get("count", 0):
            break
    return all_rows


def get_pathway_evidence(ensembl_id: str) -> list[dict]:
    """
    Fetch real Reactome pathway membership for a target.

    NOT a per-(target,disease) evidence row via evidences() — confirmed
    live via GraphQL introspection that pathway/Reactome evidence does not
    exist through that field at all: grouping ALL 9,564 real evidence rows
    for SOD1 vs MONDO_0004976 (and the full row sets for the other 4
    candidate genes) by datasourceId/datatypeId shows zero pathway-like
    entries anywhere. Pathway membership in OTP is instead a
    disease-agnostic TARGET annotation, exposed via `Target.pathways`
    (type `ReactomePathway`: `pathway`, `pathwayId`, `topLevelTerm`) —
    confirmed by introspecting the Target type's own fields. This means
    pathway "evidence" in this pipeline is gene-level (is this gene known
    to participate in any curated pathway at all), not
    disease-specific — consistent with dimension_scoring.py's
    score_pathway_curated(), which already scores curated pathway
    membership as a fixed 1.0 regardless of disease context.
    """
    query = """
    query TargetPathways($ensemblId: String!) {
      target(ensemblId: $ensemblId) {
        approvedSymbol
        pathways { pathway pathwayId topLevelTerm }
      }
    }
    """
    data = _run_query(query, {"ensemblId": ensembl_id})
    return data.get("target", {}).get("pathways", [])


def get_drug_target_evidence(ensembl_id: str, efo_id: str) -> list[dict]:
    """
    Fetch real ChEMBL-backed drug-target mechanism-of-action data for a
    target, filtered to rows genuinely indicated for the given disease.

    NOT from evidences() — confirmed via live GraphQL introspection
    (same discovery pattern as get_pathway_evidence()) that OTP exposes no
    ChEMBL binding/mechanism datasource through evidences() at all for the
    5 ALS candidate genes. The real data instead lives on
    `Target.drugAndClinicalCandidates` (type ClinicalTargetFromTarget) —
    gene-level and disease-agnostic at the API level (the field takes no
    arguments at all, confirmed via introspection, same as `pathways`), so
    disease-relevance is filtered HERE, client-side, keeping only rows
    where at least one of the row's real `diseases[].disease.id` values
    exactly matches `efo_id` — the "direct association" concept from
    docs/03_open_targets_scoring_reference.md, applied because this field
    (unlike clinical_precedence) mixes every disease a drug has ever been
    tried for into one gene-level list.

    Real, richer-than-clinical_precedence data confirmed live for SOD1:
    tofersen (CHEMBL3833346) appears here with `drugType="Oligonucleotide"`
    and a real mechanism of action ("SOD1 mRNA antisense inhibitor") —
    fields clinical_precedence does not carry at all. This is genuinely
    useful evidence for exactly the kind of RNA-targeted-therapy blind spot
    docs/07's C9orf72 case study found in clinical_precedence (BIIB078/
    WVE-004 not indexed there) — though live-checked here too: C9orf72,
    TARDBP, FUS, and NEK1 all real-return zero rows from this field as
    well, so it does not recover those two specific discontinued programs
    either. Reported as a real (negative) finding, not silently omitted.
    """
    query = """
    query DrugTargetCandidates($ensemblId: String!) {
      target(ensemblId: $ensemblId) {
        drugAndClinicalCandidates {
          count
          rows {
            maxClinicalStage
            drug {
              id
              name
              drugType
              mechanismsOfAction { rows { mechanismOfAction actionType } }
            }
            diseases { diseaseFromSource disease { id name } }
          }
        }
      }
    }
    """
    data = _run_query(query, {"ensemblId": ensembl_id})
    all_rows = data.get("target", {}).get("drugAndClinicalCandidates", {}).get("rows", [])
    return [
        row for row in all_rows
        if any(d["disease"] and d["disease"]["id"] == efo_id for d in row["diseases"])
    ]


if __name__ == "__main__":
    # Manual smoke test — requires network access to api.platform.opentargets.org
    from app.config import DISEASE_EFO_ID, CANDIDATE_TARGETS

    gene, ensembl_id = "SOD1", CANDIDATE_TARGETS["SOD1"]
    print(f"Querying association score for {gene} ({ensembl_id}) vs {DISEASE_EFO_ID} ...")
    try:
        result = get_target_disease_association(ensembl_id, DISEASE_EFO_ID)
        print(result)
    except Exception as e:
        print(f"Request failed (expected if run outside network access): {e}")
