import datetime as dt
from unittest.mock import Mock

from src.validator.core_api import CoreApiClient


def test_fetch_weight_matrix_parses_endpoint_contract():
    client = CoreApiClient("https://core.example/api/v1", Mock())
    client._request = request = Mock(
        return_value={
            "refreshed_at": "2026-10-05T22:45:11.003Z",
            "entries": [{"uid": 0, "score": 0}, {"uid": 7, "score": 0.75}],
        }
    )

    matrix = client.fetch_weight_matrix()

    assert matrix.refreshed_at == dt.datetime(
        2026, 10, 5, 22, 45, 11, 3000, tzinfo=dt.timezone.utc
    )
    assert matrix.entries == {0: 0.0, 7: 0.75}
    request.assert_called_once_with("GET", "integration/validator/weight-matrix")
