"""Event deduplication helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from core.ids import build_deduplication_key, build_event_id, normalize_title_for_matching
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


# Fields worth filling in from a duplicate found on another source -- not
# identity fields, just the ones sources tend to report unevenly (Songkick
# has real venue names, explorenicecotedazur has genre themes, Opera de
# Nice has prices; none of them have all three).
_FILLABLE_FIELDS = ("venue", "theme", "price", "url", "region", "location")


@dataclass(slots=True)
class CrossSourceMergeResult:
    """Records after merging same-event duplicates found across sources."""

    records: list[EventRecord]
    merged_groups: int


def _richness(record: EventRecord) -> int:
    return sum(1 for field in ("venue", "theme", "price", "url") if getattr(record, field))


def _merge_group(group: list[EventRecord]) -> EventRecord:
    # Deterministic order so the same real event always merges the same way,
    # regardless of which order collectors happened to run in.
    ordered = sorted(group, key=lambda r: (-_richness(r), r.source))
    merged = replace(ordered[0])
    for record in ordered[1:]:
        for field in _FILLABLE_FIELDS:
            if not getattr(merged, field) and getattr(record, field):
                setattr(merged, field, getattr(record, field))
    merged.source = "+".join(sorted({record.source for record in group}))
    return merged


def merge_cross_source_duplicates(records: list[EventRecord]) -> CrossSourceMergeResult:
    """Merge the same real-world event when multiple sources independently list it.

    Matches on (normalized title, start_date) rather than URL -- each source
    links to its own page for the same concert, so URL-based dedup never
    catches this. Combines fields instead of picking a winner: a record
    missing a venue/theme/price/url gets it filled in from whichever
    duplicate has it. Records with no title or no date never match each
    other, to avoid grouping unrelated events on a shared blank key.
    """
    groups: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    standalone: list[EventRecord] = []

    for record in records:
        normalized_title = normalize_title_for_matching(record.title)
        if not normalized_title or not record.start_date:
            standalone.append(record)
            continue
        groups[(normalized_title, record.start_date)].append(record)

    merged_records: list[EventRecord] = list(standalone)
    merged_groups = 0
    for group in groups.values():
        if len(group) == 1:
            merged_records.append(group[0])
        else:
            merged_records.append(_merge_group(group))
            merged_groups += 1

    return CrossSourceMergeResult(records=merged_records, merged_groups=merged_groups)
