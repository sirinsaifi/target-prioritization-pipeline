"""
PubMed literature client — independent of the Open Targets Platform.

This is a second, independent literature source (CLAUDE.md item 2):
scripts/ingest_evidence.py already pulls literature evidence via OTP's own
`europepmc` datasource, which does its own internal NLP-based co-occurrence
scoring. This client instead queries PubMed directly via NCBI's public
E-utilities API (no API key required) for gene-symbol + disease-name
co-occurrence in title/abstract — a much simpler, presence-based signal,
not a weighted NLP pipeline. Building a real text-mining scorer is out of
scope for this MVP (see dimension_scoring.py's score_literature_cooccurrence
docstring, which already documents accepting a pre-normalized confidence
from an external source rather than reimplementing OTP's own NLP).

Confidence convention: every paper returned by the co-occurrence search
gets confidence 1.0 — a paper either mentions both the gene and the disease
in its title/abstract, or it wasn't returned at all; there is no in-between
here. This mirrors what OTP's own europepmc evidence rows do in practice
for this dataset (confirmed via live introspection: `score` is 1 for every
included row; the real, granular confidence lives in the unbounded
`resourceScore` field instead, which this simpler client does not attempt
to reproduce). Documented as a real limitation, not hidden: this is a
presence/absence signal, not a strength-of-association score, and should
not be read as more precise than that.

API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import requests

NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def search_cooccurrence_pmids(gene_symbol: str, disease_name: str, retmax: int = 20) -> list[str]:
    """
    Return PMIDs of papers mentioning both `gene_symbol` and `disease_name`
    in title/abstract. No API key required; NCBI asks for <=3 requests/sec
    without one — this function makes exactly one request per call, callers
    are responsible for pacing across multiple genes.
    """
    term = f'("{gene_symbol}"[Title/Abstract]) AND ("{disease_name}"[Title/Abstract])'
    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": retmax,
    }
    response = requests.get(NCBI_ESEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload.get("esearchresult", {}).get("idlist", [])


def get_publication_years(pmids: list[str]) -> dict[str, int | None]:
    """
    Real publication year per PMID, via NCBI's esummary endpoint — one
    batched request for every PMID (not one call per PMID). Added for
    Evidence Momentum (app/core/scoring/evidence_momentum.py), which needs
    a real year for our own direct-PubMed rows the same way OTP's
    europepmc rows already carry `publicationYear`.

    Confirmed live: esummary's `sortpubdate` field is a real, reliably
    parseable "YYYY/MM/DD HH:MM" string (its sibling `pubdate` is
    real but inconsistently formatted — e.g. "2016 Oct" vs "2022 Mar 23" —
    so `sortpubdate` is used instead, not `pubdate`). Returns None for a
    PMID with no real parseable date, never a guessed year.
    """
    if not pmids:
        return {}
    response = requests.get(
        NCBI_ESUMMARY_URL,
        params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json().get("result", {})
    years: dict[str, int | None] = {}
    for pmid in pmids:
        doc = result.get(pmid, {})
        sortpubdate = doc.get("sortpubdate", "")
        year_str = sortpubdate.split("/")[0] if sortpubdate else None
        years[pmid] = int(year_str) if year_str and year_str.isdigit() else None
    return years


def get_literature_evidence_pubmed(gene_symbol: str, disease_name: str, retmax: int = 20) -> list[dict]:
    """
    Normalized rows ready for ingestion: one row per co-occurring PMID.
    Confidence is always 1.0 (presence-based) — see module docstring.
    `year` is real (via get_publication_years()) or None if NCBI had no
    real parseable date for that PMID — never fabricated.
    """
    pmids = search_cooccurrence_pmids(gene_symbol, disease_name, retmax=retmax)
    years = get_publication_years(pmids)
    return [{"pmid": pmid, "confidence": 1.0, "year": years.get(pmid)} for pmid in pmids]


if __name__ == "__main__":
    # Manual smoke test — requires network access to eutils.ncbi.nlm.nih.gov
    from app.config import DISEASE_NAME

    rows = get_literature_evidence_pubmed("SOD1", DISEASE_NAME)
    print(f"Found {len(rows)} co-occurring PMIDs for SOD1 x {DISEASE_NAME}:")
    for r in rows[:5]:
        print(" ", r)
