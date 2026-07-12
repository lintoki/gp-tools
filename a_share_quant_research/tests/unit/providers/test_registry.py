from datetime import UTC, date, datetime

import pytest

from a_share_research.core.models import DataBatch, FieldProvenance
from a_share_research.core.retry import BoundedRetryPolicy
from a_share_research.providers.base import FetchRequest, ProviderRegistry

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def complete_batch(source: str) -> DataBatch:
    provenance = FieldProvenance(
        source_name=source,
        source_uri=f"https://example.invalid/{source}",
        source_record_id="1",
        fetched_at=NOW,
        effective_at=NOW,
        available_at=NOW,
        run_id="TEST_ONLY_run",
        payload_sha256="d" * 64,
    )
    row = {"instrument_id": "SH600000", "close": 10.0}
    return DataBatch(
        dataset="daily_bars",
        rows=(row,),
        field_provenance={field: provenance for field in row},
        provider_version="TEST_ONLY_1",
    )


class FakeProvider:
    capabilities = frozenset({"daily_bars"})

    def __init__(self, name: str, failures: int) -> None:
        self.name = name
        self.failures = failures
        self.calls = 0

    def fetch(self, request: FetchRequest) -> DataBatch:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError(self.name)
        return complete_batch(self.name)


def request() -> FetchRequest:
    return FetchRequest(
        dataset="daily_bars",
        symbols=("600000",),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 11),
        as_of=NOW,
        run_id="TEST_ONLY_run",
    )


def test_registry_switches_to_one_backup_only() -> None:
    primary = FakeProvider("primary", failures=10)
    backup = FakeProvider("backup", failures=0)
    policy = BoundedRetryPolicy(max_attempts=3, delays=(0, 0), sleep=lambda _: None)

    result = ProviderRegistry(primary, [backup], policy=policy).fetch_with_fallback(request())

    assert result.field_provenance["close"].source_name == "backup"
    assert primary.calls == 3
    assert backup.calls == 1


def test_registry_never_tries_second_backup() -> None:
    primary = FakeProvider("primary", failures=10)
    backup_one = FakeProvider("backup-one", failures=10)
    backup_two = FakeProvider("backup-two", failures=0)
    policy = BoundedRetryPolicy(max_attempts=1, delays=(), sleep=lambda _: None)

    with pytest.raises(RuntimeError, match="all allowed providers failed"):
        ProviderRegistry(
            primary, [backup_one, backup_two], policy=policy, maximum_backups=1
        ).fetch_with_fallback(request())

    assert backup_one.calls == 1
    assert backup_two.calls == 0
