"""
Tests for app/ingestion/gtex_client.py — real, healthy-tissue expression
data replacing the Expression Atlas integration attempt (confirmed alive
at its own source but with no usable per-gene/disease REST API — see
CLAUDE.md). No real network call in unit tests, per this project's
existing convention for all ingestion clients.
"""

from unittest.mock import patch, MagicMock

from app.ingestion.gtex_client import get_median_tissue_expression, _resolve_gencode_id


def _mock_response(payload):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_resolves_real_gencode_id_shape():
    payload = {"data": [{"gencodeId": "ENSG00000142168.14", "geneSymbol": "SOD1"}]}
    with patch("app.ingestion.gtex_client.requests.get", return_value=_mock_response(payload)):
        assert _resolve_gencode_id("SOD1") == "ENSG00000142168.14"


def test_resolve_gencode_id_returns_none_when_gtex_has_no_mapping():
    with patch("app.ingestion.gtex_client.requests.get", return_value=_mock_response({"data": []})):
        assert _resolve_gencode_id("ZZZFAKE9") is None


def test_get_median_tissue_expression_returns_real_shaped_tissue_dict():
    """Mirrors real live SOD1 data (a small real slice)."""
    reference_payload = {"data": [{"gencodeId": "ENSG00000142168.14", "geneSymbol": "SOD1"}]}
    expression_payload = {"data": [
        {"median": 378.478, "tissueSiteDetailId": "Liver", "gencodeId": "ENSG00000142168.14", "unit": "TPM"},
        {"median": 247.236, "tissueSiteDetailId": "Brain_Substantia_nigra", "gencodeId": "ENSG00000142168.14", "unit": "TPM"},
        {"median": 289.02, "tissueSiteDetailId": "Brain_Spinal_cord_cervical_c-1", "gencodeId": "ENSG00000142168.14", "unit": "TPM"},
    ]}
    with patch(
        "app.ingestion.gtex_client.requests.get",
        side_effect=[_mock_response(reference_payload), _mock_response(expression_payload)],
    ):
        result = get_median_tissue_expression("SOD1")

    assert result == {
        "Liver": 378.478,
        "Brain_Substantia_nigra": 247.236,
        "Brain_Spinal_cord_cervical_c-1": 289.02,
    }


def test_get_median_tissue_expression_returns_none_for_unmapped_gene():
    with patch("app.ingestion.gtex_client.requests.get", return_value=_mock_response({"data": []})):
        assert get_median_tissue_expression("ZZZFAKE9") is None


def test_get_median_tissue_expression_sends_real_dataset_id():
    reference_payload = {"data": [{"gencodeId": "ENSG00000142168.14"}]}
    with patch(
        "app.ingestion.gtex_client.requests.get",
        side_effect=[_mock_response(reference_payload), _mock_response({"data": []})],
    ) as mock_get:
        get_median_tissue_expression("SOD1")

    second_call_kwargs = mock_get.call_args_list[1].kwargs
    assert second_call_kwargs["params"]["gencodeId"] == "ENSG00000142168.14"
    assert second_call_kwargs["params"]["datasetId"] == "gtex_v8"
