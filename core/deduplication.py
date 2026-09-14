"""Event deduplication helpers."""

from __future__ import annotations

from dataclasses import dataclass

from core.ids import build_deduplication_key, build_event_id
from core.models import EventRecord


@dataclass(slots=True)
class DeduplicationResult:
    """Unique records and summary information for one collection run."""

    records: list[EventRecord]
    duplicates: int


def deduplicate_records(records: list[EventRecord]) -> DeduplicationResult:
    """Keep the first record for every source-specific identity key."""
    unique_records: list[EventRecord] = []
    seen_keys: set[str] = set()
    duplicates = 0

    for record in records:
        key = build_deduplication_key(record)
        if key in seen_keys:
            duplicates += 1
            continue

        seen_keys.add(key)
        if not record.event_id:
            record.event_id = build_event_id(record)
        unique_records.append(record)

    return DeduplicationResult(records=unique_records, duplicates=duplicates)
