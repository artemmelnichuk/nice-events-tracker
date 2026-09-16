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
_FILLABLE_FIELDS = ("venue", "theme", "price", "url", "region", "location", "description")


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


def _is_word_prefix(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """True if one token list is a leading, whole-word prefix of the other."""
    if not tokens_a or not tokens_b:
        return False
    shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    return longer[: len(shorter)] == shorter


def _cluster_by_title_prefix(records: list[EventRecord]) -> list[list[EventRecord]]:
    """Group records whose normalized titles share a leading-word prefix.

    Catches a pattern exact-title matching misses: the same concert listed as
    just the artist name on one source ("Ninho") and as "Artist -- Tour Name"
    or "Artist Trio" on another. Only clusters records that (a) share a date,
    already guaranteed by the caller, and (b) come from more than one
    distinct source -- this pass exists for cross-source matches, not to
    second-guess a single source's own listings.
    """
    tokens = [normalize_title_for_matching(r.title).split() for r in records]
    clusters: list[list[int]] = []
    for i in range(len(records)):
        for cluster in clusters:
            if any(_is_word_prefix(tokens[i], tokens[j]) for j in cluster):
                cluster.append(i)
                break
        else:
            clusters.append([i])

    result = []
    for cluster in clusters:
        members = [records[i] for i in cluster]
        if len(members) > 1 and len({r.source for r in members}) > 1:
            result.append(members)
    return result


def merge_cross_source_duplicates(records: list[EventRecord]) -> CrossSourceMergeResult:
    """Merge the same real-world event when multiple sources independently list it.

    Matches on (normalized title, start_date) rather than URL -- each source
    links to its own page for the same concert, so URL-based dedup never
    catches this. Combines fields instead of picking a winner: a record
    missing a venue/theme/price/url gets it filled in from whichever
    duplicate has it. Records with no title or no date never match each
    other, to avoid grouping unrelated events on a shared blank key.

    A record left standalone by the exact-title pass gets a second chance:
    grouped by date with other leftover standalones and clustered by title
    prefix (see `_cluster_by_title_prefix`), to catch same-day cross-source
    listings whose titles matched exactly on nothing but the artist name.
    """
    groups: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    standalone: list[EventRecord] = []

    for record in records:
        normalized_title = normalize_title_for_matching(record.title)
        if not normalized_title or not record.start_date:
            standalone.append(record)
            continue
        groups[(normalized_title, record.start_date)].append(record)

    merged_records: list[EventRecord] = []
    merged_groups = 0
    leftover: list[EventRecord] = list(standalone)
    for group in groups.values():
        if len(group) == 1:
            leftover.append(group[0])
        else:
            merged_records.append(_merge_group(group))
            merged_groups += 1

    by_date: dict[str, list[EventRecord]] = defaultdict(list)
    for record in leftover:
        if record.start_date:
            by_date[record.start_date].append(record)
        else:
            merged_records.append(record)

    for same_day_records in by_date.values():
        clustered_indices: set[int] = set()
        for cluster in _cluster_by_title_prefix(same_day_records):
            merged_records.append(_merge_group(cluster))
            merged_groups += 1
            clustered_indices.update(id(r) for r in cluster)
        for record in same_day_records:
            if id(record) not in clustered_indices:
                merged_records.append(record)

    return CrossSourceMergeResult(records=merged_records, merged_groups=merged_groups)
