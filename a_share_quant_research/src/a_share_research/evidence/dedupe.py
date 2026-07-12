from __future__ import annotations

from collections.abc import Iterable

from a_share_research.evidence.models import EvidenceItem


def independent_c_representatives(items: Iterable[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    representatives: list[EvidenceItem] = []
    owners: set[str] = set()
    clusters: set[str] = set()
    hashes: set[str] = set()
    for item in sorted(items, key=lambda value: (value.published_at, value.evidence_id)):
        if (
            item.source_owner in owners
            or item.syndication_cluster in clusters
            or item.content_sha256 in hashes
        ):
            continue
        representatives.append(item)
        owners.add(item.source_owner)
        clusters.add(item.syndication_cluster)
        hashes.add(item.content_sha256)
    return tuple(representatives)
