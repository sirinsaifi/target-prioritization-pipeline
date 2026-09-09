"""
Real, clickable external source links for evidence records — one URL per
EvidenceRecord (or None), built ONLY from real, already-stored identifiers.
Never fabricates a URL from a guessed ID shape.

Every mapping below was decided by live-checking real SOD1/ALS data first
(see this task's write-up in CLAUDE.md for the full investigation), not
assumed from a data_source's name:

- eva: `source_record_id` IS a real ClinVar RCV accession (populated via
  OTP's own `studyId` field for this datasource specifically — confirmed
  live; other genetic datasources leave `studyId` null). Live-tested:
  https://www.ncbi.nlm.nih.gov/clinvar/RCV001095396/ -> 200.
- uniprot_variants: `source_record_id` is OTP's own internal evidence hash
  (studyId is null, and OTP's own `urls` field — a real, curated
  external-link list this schema exposes — is empty for every real row
  checked), so no real UniProt-specific accession is available. The only
  real external id this datasource DOES carry is the dbSNP rsID, already
  stored in `variant_id` — used for a dbSNP link instead. Live-tested:
  https://www.ncbi.nlm.nih.gov/snp/rs121912443 -> 200. (Deviates from a
  plain uniprot.org/uniprotkb/{accession} link for exactly this reason.)
- europepmc / pubmed: `source_record_id` is a real PMID for both (OTP's
  `literature` list for europepmc; our own direct NCBI E-utilities client
  for pubmed — see scripts/ingest_evidence.py). Confirmed real via NCBI's
  esummary API (PubMed's own HTML pages return a Cloudflare-style 403 to
  scripted fetches regardless of which real PMID is requested — bot
  mitigation, not a dead link).
- reactome: `source_record_id` IS the real Reactome pathway id. Live-tested:
  https://reactome.org/content/detail/R-HSA-114608 -> 200.
- chembl_drug_target: `source_record_id` IS the real ChEMBL compound id.
  Live-tested: https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL3833346/
  -> 200 (redirects to ChEMBL's current UI, still a real working page).
- clinical_precedence: real `clinicalReportId` (captured via `external_id`
  — not previously queried at all) is SOMETIMES a real ClinicalTrials.gov
  NCT id (e.g. "nct07223723") and sometimes a different internal report
  tag with no public page (e.g. "d0i1cq/amyotrophic lateral sclerosis") —
  confirmed live, both shapes seen in real SOD1 data. Only build a link
  when it actually matches the NCT pattern; live-tested:
  https://clinicaltrials.gov/study/NCT07223723 -> 200.
- gwas_credible_sets: real `credibleSet.studyLocusId` (captured via
  `external_id` — not previously queried) resolves to a real page on the
  unified Open Targets Platform's own site. Live-tested:
  https://platform.opentargets.org/credible-set/7bda1a15194fa9e277e2f76574d6f4b5
  -> 200.
- string: the real STRING-internal protein id (e.g. "9606.ENSP00000270142")
  is resolved during ingestion (string_client.get_string_id()) but was
  previously discarded — now captured via `external_id`. STRING's network
  page returns a Cloudflare JS-challenge to scripted fetches (confirmed via
  response headers: `Cf-Mitigated: challenge`, `Server: cloudflare`) — not
  a dead link, a real page a real browser would pass through to.
- hpa: derived purely from the record's own target's real `ensembl_id`
  (Human Protein Atlas's canonical per-gene page) — no new stored field
  needed. Live-tested: https://www.proteinatlas.org/ENSG00000142168 -> 200
  (redirects to .../ENSG00000142168-SOD1, still the real page).
- orphanet, impc: no real per-record external id is exposed by this
  pipeline's real data for either (id is OTP's internal hash, studyId/
  variantRsId/clinicalReportId all null) — a real, documented absence,
  not an oversight. Returns None.
- clinicaltrials_gov: real `external_id` is ALWAYS a well-formed NCT id
  straight from the API itself (not a mixed-format free-text field like
  clinical_precedence's clinicalReportId) — no pattern validation needed,
  always links. Live-tested: https://clinicaltrials.gov/study/NCT03626012
  -> 200 (the real BIIB078 trial this source was built to recover).
- ot_safety: `external_id` already IS a real, complete URL (OTP's own
  safetyLiabilities.url field) — passed through as-is, no template.
  Confirmed live real for 4 of 5 real KCNH2/hERG safety events (null only
  for a plain literature citation with no real web page).
- ot_genetic_constraint: no single dedicated page for this one factor —
  links to the gene's own real Open Targets Platform target page
  (https://platform.opentargets.org/target/{ensembl_id}), where the
  Genetic Constraint prioritisation factor this row is built from is
  actually displayed.
- ot_essentiality: same reasoning as ot_genetic_constraint above — no
  single dedicated page for this one factor alone, links to the gene's own
  real Open Targets Platform target page, where Gene Essentiality is
  displayed alongside every other prioritisation factor.
- ot_paralogy: `external_id` is the real paralogue's own Ensembl gene ID
  (Target.homologues.targetGeneId, e.g. ENSG00000173992 for SOD1's real
  paralogue CCS) — links to that PARALOGUE's own real Ensembl gene page,
  not the current gene's own page, since the whole point of this record is
  the OTHER gene. Live-tested:
  https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=ENSG00000173992 ->
  200 (redirects to Ensembl's current feature-explorer UI for that real
  gene, still a real working page).
"""

import re

_NCT_PATTERN = re.compile(r"^nct\d+$", re.IGNORECASE)


def get_source_url(
    data_source: str,
    source_record_id: str | None,
    variant_id: str | None,
    external_id: str | None,
    ensembl_id: str | None,
) -> str | None:
    if data_source == "eva":
        return f"https://www.ncbi.nlm.nih.gov/clinvar/{source_record_id}/" if source_record_id else None

    if data_source == "uniprot_variants":
        return f"https://www.ncbi.nlm.nih.gov/snp/{variant_id}" if variant_id else None

    if data_source in ("europepmc", "pubmed"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{source_record_id}/" if source_record_id else None

    if data_source == "reactome":
        return f"https://reactome.org/content/detail/{source_record_id}" if source_record_id else None

    if data_source == "chembl_drug_target":
        return f"https://www.ebi.ac.uk/chembl/compound_report_card/{source_record_id}/" if source_record_id else None

    if data_source == "clinical_precedence":
        if external_id and _NCT_PATTERN.match(external_id):
            return f"https://clinicaltrials.gov/study/{external_id.upper()}"
        return None

    if data_source == "clinicaltrials_gov":
        return f"https://clinicaltrials.gov/study/{external_id}" if external_id else None

    if data_source == "gwas_credible_sets":
        return f"https://platform.opentargets.org/credible-set/{external_id}" if external_id else None

    if data_source == "string":
        return f"https://string-db.org/network/{external_id}" if external_id else None

    if data_source == "ot_safety":
        # `external_id` already IS a real, complete URL here (OTP's own
        # safetyLiabilities.url field) — no template needed, just pass it
        # through. Confirmed live: real for 4 of 5 real KCNH2/hERG events
        # (null only for a plain literature citation with no real web
        # page — "Bowes et al. (2012)" — a genuine absence, not a bug).
        return external_id if external_id else None

    if data_source == "hpa":
        return f"https://www.proteinatlas.org/{ensembl_id}" if ensembl_id else None

    if data_source == "ot_genetic_constraint":
        # No dedicated real page for this one factor alone — links to the
        # gene's own real Open Targets Platform target page, where the
        # Genetic Constraint prioritisation factor this row is built from
        # is actually displayed.
        return f"https://platform.opentargets.org/target/{ensembl_id}" if ensembl_id else None

    if data_source == "ot_essentiality":
        # No dedicated real page for this one factor alone — same
        # reasoning as ot_genetic_constraint above.
        return f"https://platform.opentargets.org/target/{ensembl_id}" if ensembl_id else None

    if data_source == "ot_paralogy":
        # `external_id` is the real PARALOGUE's own Ensembl gene id (not
        # this record's own gene) — links to that other gene's page, since
        # that's the actual subject of this record.
        return f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={external_id}" if external_id else None

    # orphanet, impc, and anything else not listed above: no real per-record
    # external id exists in this pipeline's data — see module docstring.
    return None
