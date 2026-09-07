"""
Tests for the datatype-driven genetic evidence fetch (Option A fix, see
docs/07 "Genetic evidence: datatype-driven fetch"). Replaces a hardcoded
`GENETIC_DATASOURCES = ["eva", "uniprot_variants", "gwas_credible_sets"]`
list (tuned for ALS's rare-variant genetics, would silently under-collect
for a GWAS-driven disease) with a discovery step against OTP's real,
disease-agnostic "genetic_association" datatype.

All tests mock `_run_query` (the one function that talks to the network),
same pattern as tests/test_agent_narrator.py mocking `_call_llm` — no real
API call or network access needed to verify the pagination/discovery logic.
"""

from unittest.mock import patch

from app.ingestion.open_targets_client import (
    _discover_datasource_ids_for_datatype, get_evidence_by_datatype,
)
from app.agent.investigation_tools import search_genetic_evidence


def _evidences_page(rows, cursor, count):
    return {"target": {"evidences": {"count": count, "cursor": cursor, "rows": rows}}}


def test_discover_datasource_ids_paginates_until_cursor_exhausted():
    # 2 real pages: page 1 has a genetic_association row (eva) and a
    # literature row (should be ignored); page 2 has a second genetic_
    # association row (orphanet) under a DIFFERENT datasourceId — proving
    # discovery isn't hardcoded to any specific list.
    page1 = _evidences_page(
        rows=[
            {"datasourceId": "eva", "datatypeId": "genetic_association"},
            {"datasourceId": "europepmc", "datatypeId": "literature"},
        ],
        cursor="CURSOR_1", count=3,
    )
    page2 = _evidences_page(
        rows=[{"datasourceId": "orphanet", "datatypeId": "genetic_association"}],
        cursor=None, count=3,
    )
    with patch("app.ingestion.open_targets_client._run_query") as mock_query:
        mock_query.side_effect = [page1, page2]
        found = _discover_datasource_ids_for_datatype("ENSG_TEST", "EFO_TEST", "genetic_association", page_size=2)

    assert found == {"eva", "orphanet"}
    assert mock_query.call_count == 2


def test_discover_datasource_ids_stops_when_fetched_reaches_real_count():
    # 1 page covers the entire real count (3 == 3) -> must stop even though
    # a cursor value is still present, to avoid one extra wasted request.
    page1 = _evidences_page(
        rows=[
            {"datasourceId": "eva", "datatypeId": "genetic_association"},
            {"datasourceId": "gwas_credible_sets", "datatypeId": "genetic_association"},
            {"datasourceId": "europepmc", "datatypeId": "literature"},
        ],
        cursor="CURSOR_UNUSED", count=3,
    )
    with patch("app.ingestion.open_targets_client._run_query") as mock_query:
        mock_query.return_value = page1
        found = _discover_datasource_ids_for_datatype("ENSG_TEST", "EFO_TEST", "genetic_association", page_size=10)

    assert found == {"eva", "gwas_credible_sets"}
    mock_query.assert_called_once()


def test_get_evidence_by_datatype_returns_empty_when_no_real_datasource_found():
    page1 = _evidences_page(rows=[{"datasourceId": "europepmc", "datatypeId": "literature"}], cursor=None, count=1)
    with patch("app.ingestion.open_targets_client._run_query") as mock_query:
        mock_query.return_value = page1
        rows = get_evidence_by_datatype("ENSG_TEST", "EFO_TEST", "genetic_association")

    assert rows == []
    # Only the discovery call should have run — no point issuing a fetch
    # query for an empty datasourceIds list.
    mock_query.assert_called_once()


def test_get_evidence_by_datatype_discovers_then_fetches_paginated_rows():
    discovery_page = _evidences_page(
        rows=[{"datasourceId": "eva", "datatypeId": "genetic_association"}], cursor=None, count=1,
    )
    fetch_page1 = {"target": {"evidences": {
        "count": 3, "cursor": "CURSOR_1",
        "rows": [{"id": "e1", "score": 0.9, "datasourceId": "eva", "datatypeId": "genetic_association"}],
    }}}
    fetch_page2 = {"target": {"evidences": {
        "count": 3, "cursor": None,
        "rows": [
            {"id": "e2", "score": 0.5, "datasourceId": "eva", "datatypeId": "genetic_association"},
            {"id": "e3", "score": 0.3, "datasourceId": "eva", "datatypeId": "genetic_association"},
        ],
    }}}
    with patch("app.ingestion.open_targets_client._run_query") as mock_query:
        mock_query.side_effect = [discovery_page, fetch_page1, fetch_page2]
        rows = get_evidence_by_datatype("ENSG_TEST", "EFO_TEST", "genetic_association", page_size=1)

    assert [r["id"] for r in rows] == ["e1", "e2", "e3"]
    assert mock_query.call_count == 3  # 1 discovery + 2 fetch pages


def test_search_genetic_evidence_uses_real_per_row_datasource_not_a_hardcoded_list():
    # Two different real datasourceIds in one result set — could never
    # happen under the old per-fixed-datasource-loop implementation, where
    # every row in one call shared the SAME hardcoded datasource_id.
    rows = [
        {"id": "e1", "datasourceId": "eva", "datatypeId": "genetic_association"},
        {"id": "e2", "datasourceId": "orphanet", "datatypeId": "genetic_association"},
    ]
    with patch("app.agent.investigation_tools.get_evidence_by_datatype") as mock_fetch:
        mock_fetch.return_value = rows
        result = search_genetic_evidence("SOD1")

    assert result["total_rows"] == 2
    assert result["row_counts_by_datasource"] == {"eva": 1, "orphanet": 1}
    mock_fetch.assert_called_once_with("ENSG00000142168", "MONDO_0004976", "genetic_association")


def test_search_genetic_evidence_reports_unknown_gene_without_calling_the_client():
    with patch("app.agent.investigation_tools.get_evidence_by_datatype") as mock_fetch:
        result = search_genetic_evidence("NOT_A_REAL_GENE")

    assert "error" in result
    mock_fetch.assert_not_called()
