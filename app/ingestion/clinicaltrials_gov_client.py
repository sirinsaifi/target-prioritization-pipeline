"""
ClinicalTrials.gov API v2 client — a second, independent human_clinical
source alongside OTP's own `clinical_precedence` datasource (see
scripts/ingest_evidence.py's _build_clinical_fields()).

REAL, LIVE-CONFIRMED GAP THIS CLOSES (this task): OTP's `clinical_precedence`
datasource returns ZERO real rows for C9orf72 vs ALS, despite two real,
well-documented, discontinued antisense-oligonucleotide trials existing
for C9orf72-associated ALS — BIIB078 (Biogen) and WVE-004 (Wave Life
Sciences). Confirmed live against this exact API
(query.cond="Amyotrophic Lateral Sclerosis", query.term="C9orf72"): both
appear, across 4 real trial records total —
  BIIB078: NCT03626012 (COMPLETED), NCT04288856 (TERMINATED)
  WVE-004: NCT04931862 (TERMINATED), NCT05683860 (TERMINATED, open-label extension)
— each carrying a real, detailed `whyStopped` explanation (e.g. WVE-004:
"no clinical benefit was seen at 24 weeks... Wave decided to stop
development"). OTP's clinical_precedence rows never populate this field at
all for any of the 5 candidate genes (confirmed: trialStopReasonCategories/
trialWhyStopped empty on every real row, every gene — see
_build_clinical_fields()'s docstring) — this is the richest real
"why a trial stopped" text this project has ever had access to.

API: https://clinicaltrials.gov/api/v2/studies
Docs: https://clinicaltrials.gov/data-api/api

Search strategy: query.cond=<disease name> + query.term=<gene symbol> —
confirmed live to surface real, relevant trials by gene-symbol mention in
title/conditions/interventions/keywords, without needing to already know a
drug name in advance (a gene-symbol-only search generalizes to any of the
5 candidate genes; searching by a specific drug name like query.intr=
"BIIB078" would not, since we don't know a gene's candidate drug names
ahead of ingestion).

NOISE, confirmed live and filtered out below: a plain gene-symbol term
search also returns real but irrelevant matches — observational/natural-
history studies (`studyType="OBSERVATIONAL"`, no real intervention at all),
and interventional studies whose "intervention" is a diagnostic procedure,
device, or survey (e.g. real C9orf72/ALS studies literally named
"Skin biopsy", "Transcranial Pulse Stimulation", "Survey for ALS
patients"). Filtered to only DRUG_LIKE_INTERVENTION_TYPES — the real
`interventions[].type` values CT.gov itself assigns to an actual candidate
therapeutic — and placebo arms (CT.gov types "Placebo" as type=DRUG too,
which would otherwise fabricate a false candidate-compound row).
"""

import requests

CTGOV_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# Real CT.gov intervention types that represent an actual candidate
# therapeutic (confirmed live) — excludes DEVICE, DIAGNOSTIC_TEST,
# BEHAVIORAL, OTHER, RADIATION, PROCEDURE (see module docstring's real
# noise examples).
DRUG_LIKE_INTERVENTION_TYPES = {"DRUG", "BIOLOGICAL", "GENETIC"}


def get_clinical_trials(gene_symbol: str, disease_name: str, page_size: int = 100) -> list[dict]:
    """
    Real ClinicalTrials.gov trial-intervention pairs mentioning
    `gene_symbol` for `disease_name`. Returns one dict per (trial,
    intervention) pair — a trial with 2 real drug arms yields 2 rows, same
    "one row per real comparable claim" convention already used by
    open_targets_client.get_drug_target_evidence(). Placebo arms are
    dropped (see module docstring).

    Not paginated beyond one page (`page_size`, default 100) — real trial
    counts for a single gene/disease pair are realistically in the tens,
    not hundreds (confirmed live for C9orf72/ALS: 20 real studies
    returned, 9 real drug-arm rows survive the filter) — a documented
    limitation, not an oversight, should a future gene/disease pair ever
    exceed this in real data.
    """
    params = {
        "query.cond": disease_name,
        "query.term": gene_symbol,
        "pageSize": page_size,
        "format": "json",
    }
    response = requests.get(CTGOV_BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    studies = response.json().get("studies", [])

    rows = []
    for study in studies:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status_module = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        arms = proto.get("armsInterventionsModule", {})

        nct_id = ident.get("nctId")
        brief_title = ident.get("briefTitle")
        overall_status = status_module.get("overallStatus")
        why_stopped = status_module.get("whyStopped")
        phases = design.get("phases") or []
        # Real, reliably-populated start date (confirmed live: "2022-12-14"
        # style, ACTUAL or ESTIMATED) — used for Evidence Momentum the same
        # way clinical_precedence's studyStartDate already is (see
        # scripts/ingest_evidence.py's _build_ctgov_clinical_fields()).
        start_date = (status_module.get("startDateStruct") or {}).get("date")

        for intervention in arms.get("interventions", []):
            intervention_name = intervention.get("name") or ""
            if intervention.get("type") not in DRUG_LIKE_INTERVENTION_TYPES:
                continue
            if "placebo" in intervention_name.lower():
                continue
            rows.append({
                "nct_id": nct_id,
                "brief_title": brief_title,
                "overall_status": overall_status,
                "why_stopped": why_stopped,
                "phases": phases,
                "start_date": start_date,
                "intervention_name": intervention_name,
                "intervention_type": intervention.get("type"),
            })
    return rows


if __name__ == "__main__":
    # Manual smoke test — requires network access to clinicaltrials.gov.
    # Real, expected output: BIIB078 and WVE-004 both present.
    rows = get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")
    print(f"{len(rows)} real drug-arm trial rows for C9orf72 x ALS:")
    for r in rows:
        print(f"  {r['nct_id']} [{r['overall_status']}] {r['intervention_name']} (phases={r['phases']})")
        if r["why_stopped"]:
            print(f"      why_stopped: {r['why_stopped'][:120]}...")
