from datetime import UTC, datetime

import httpx

from a_share_research.providers.base import FetchRequest
from a_share_research.providers.official import CftcCotProvider, FredCsvProvider, SecEdgarProvider

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fred_csv_provider_parses_observations_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id"] == "SP500"
        return httpx.Response(200, text="observation_date,SP500\n2026-07-10,6250.5\n")

    provider = FredCsvProvider(client=client(handler), clock=lambda: NOW)
    batch = provider.fetch(
        FetchRequest(dataset="us_market", series_ids=("SP500",), as_of=NOW, run_id="TEST_ONLY_run")
    )
    assert batch.rows[0]["series_id"] == "SP500"
    assert batch.rows[0]["value"] == 6250.5


def test_cftc_and_sec_providers_use_structured_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "publicreporting.cftc.gov" in request.url.host:
            return httpx.Response(
                200,
                json=[
                    {
                        "report_date_as_yyyy_mm_dd": "2026-07-07",
                        "contract_market_name": "S&P 500",
                        "noncomm_positions_long_all": "120",
                        "noncomm_positions_short_all": "90",
                    }
                ],
            )
        return httpx.Response(
            200, json={"cik": "0000320193", "name": "Apple Inc.", "filings": {"recent": {}}}
        )

    http_client = client(handler)
    cot = CftcCotProvider(client=http_client, clock=lambda: NOW).fetch(
        FetchRequest(dataset="cftc_cot", as_of=NOW, run_id="TEST_ONLY_run")
    )
    sec = SecEdgarProvider(client=http_client, clock=lambda: NOW).fetch(
        FetchRequest(dataset="sec_submissions", symbols=("0000320193",), as_of=NOW, run_id="TEST_ONLY_run")
    )
    assert cot.rows[0]["contract_market_name"] == "S&P 500"
    assert sec.rows[0]["name"] == "Apple Inc."
