"""
PubMed abstract TEXT client — fetches the actual abstract text for a real
PMID via NCBI's E-utilities `efetch` endpoint (free, no API key required for
low request volume, same terms as `literature_client.py`'s `esearch` use).

Distinct from `literature_client.py`, which only discovers WHICH PMIDs
co-occur with a gene/disease (no abstract text). This module fetches the
actual TEXT for a PMID already known — the PMID stored as
`EvidenceRecord.source_record_id` for `dimension="literature"` rows,
regardless of whether that row came from OTP's `europepmc` datasource or
this project's own direct-PubMed client (`literature_client.py`) — both
populate a real PMID there.

This is the real, previously-unbuilt `literature_text_client.py` referenced
in docs/07 Phase 7 ("planned, not yet built as of this module").

API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import xml.etree.ElementTree as ET

import requests

NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def get_abstract_text(pmid: str) -> str | None:
    """
    Fetch the real abstract text for one PMID. Returns None (not an empty
    string, not a fabricated placeholder) if the PMID doesn't resolve to a
    record with abstract text — confirmed live: an invalid/nonexistent PMID
    returns zero real <AbstractText> elements, some PubMed entry types
    (e.g. GeneReviews book chapters, some early records) have none. Callers
    must treat None as "no real text available", never substitute guessed
    text.

    Uses a plain `.//AbstractText` XPath rather than assuming a single
    PubmedArticle structure — confirmed live this also correctly parses
    PubmedBookArticle entries (e.g. GeneReviews overviews cited by
    Orphanet), which nest differently but still expose AbstractText the
    same way. A structured abstract (multiple labeled sections — Background/
    Methods/Results/Conclusion) is joined with spaces into one string; the
    section labels themselves are not preserved, since the contradiction
    proposer only needs the prose, not the structure.

    Uses `el.itertext()` (all text within an element, including inline
    child tags' text/tail), NOT `el.text` alone — a real bug caught while
    testing this module against real PubMed data: PubMed abstracts
    routinely wrap gene/species names in inline markup (e.g.
    `Repeat expansions in the <i>C9orf72</i> gene are...`), and
    ElementTree's `.text` only returns the text BEFORE the first child
    element, silently truncating everything after the first `<i>`/`<b>`/
    `<sup>` tag. Confirmed live: PMID 36711601's real abstract is several
    full sentences, but `.text`-only extraction returned just
    "Repeat expansions in the" (cut off at the `<i>C9orf72</i>` tag) before
    this fix.
    """
    params = {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "xml"}
    response = requests.get(NCBI_EFETCH_URL, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    abstract_elements = root.findall(".//AbstractText")
    if not abstract_elements:
        return None

    joined = " ".join("".join(el.itertext()).strip() for el in abstract_elements).strip()
    return joined or None


if __name__ == "__main__":
    # Manual smoke test — requires network access to eutils.ncbi.nlm.nih.gov
    text = get_abstract_text("27481264")
    print(f"Fetched {len(text) if text else 0} chars for PMID 27481264:")
    print(text[:300] if text else "(no abstract text found)")
