"""
Tests for app/ingestion/literature_text_client.py.

Includes a regression test for a real bug caught while testing this module
against real PubMed data: PMID 36711601's real abstract opens with
"Repeat expansions in the <i>C9orf72</i> gene are..." — inline markup
(<i>, common for gene/species names in PubMed abstracts) truncated
ElementTree `.text`-only extraction to just "Repeat expansions in the",
silently dropping the rest of a several-sentence abstract. Fixed via
`el.itertext()` instead of `el.text`. This test constructs a minimal XML
fixture reproducing the exact same structure rather than depending on a
live network call and NCBI's data staying unchanged.
"""

from unittest.mock import Mock, patch

from app.ingestion.literature_text_client import get_abstract_text


def _fake_response(xml_body: str) -> Mock:
    resp = Mock()
    resp.content = xml_body.encode("utf-8")
    resp.raise_for_status = Mock()
    return resp


def test_get_abstract_text_includes_text_after_an_inline_tag():
    # Reproduces PMID 36711601's real structure: text, then an inline <i>
    # tag, then more text after it (the tag's "tail").
    xml = (
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><Abstract>"
        "<AbstractText>Repeat expansions in the <i>C9orf72</i> gene are the most "
        "common genetic cause of ALS.</AbstractText>"
        "</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"
    )
    with patch("app.ingestion.literature_text_client.requests.get", return_value=_fake_response(xml)):
        text = get_abstract_text("36711601")

    assert text == "Repeat expansions in the C9orf72 gene are the most common genetic cause of ALS."
    # The old .text-only bug would have produced exactly this truncated string:
    assert text != "Repeat expansions in the"


def test_get_abstract_text_joins_multiple_labeled_sections():
    xml = (
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><Abstract>"
        '<AbstractText Label="BACKGROUND">Background text here.</AbstractText>'
        '<AbstractText Label="RESULTS">Results text here.</AbstractText>'
        "</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"
    )
    with patch("app.ingestion.literature_text_client.requests.get", return_value=_fake_response(xml)):
        text = get_abstract_text("12345")

    assert text == "Background text here. Results text here."


def test_get_abstract_text_returns_none_when_no_abstracttext_element_exists():
    xml = "<PubmedArticleSet></PubmedArticleSet>"
    with patch("app.ingestion.literature_text_client.requests.get", return_value=_fake_response(xml)):
        text = get_abstract_text("999999999999")

    assert text is None


def test_get_abstract_text_parses_pubmedbookarticle_structure():
    # GeneReviews-style book chapters (e.g. cited by Orphanet) nest
    # differently but still expose a real AbstractText.
    xml = (
        "<PubmedArticleSet><PubmedBookArticle><BookDocument><Abstract>"
        "<AbstractText>Overview of ALS genetics.</AbstractText>"
        "</Abstract></BookDocument></PubmedBookArticle></PubmedArticleSet>"
    )
    with patch("app.ingestion.literature_text_client.requests.get", return_value=_fake_response(xml)):
        text = get_abstract_text("20301623")

    assert text == "Overview of ALS genetics."
