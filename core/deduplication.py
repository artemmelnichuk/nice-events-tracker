"""Event deduplication helpers."""

from __future__ import annotations

from collections import defaultdict
import re
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


def _atomic_sources(record: EventRecord) -> set[str]:
    """Sources behind a record; a merged record's `source` is "a+b"."""
    return set(record.source.split("+"))


def _is_shouting(title: str) -> bool:
    """True for an ALL-CAPS title, tolerating a lowercase "x" between names."""
    letters = [char for char in title if char.isalpha()]
    return len(letters) >= 4 and sum(char.isupper() for char in letters) / len(letters) >= 0.85


def _display_title(ordered: list[EventRecord]) -> str:
    """Title for a merged record: the base's, unless it is an ALL-CAPS shout.

    Panda Events writes every title in capitals and is usually the richest
    member, so without this a merge would turn "Danyl @ Theatre Lino Ventura"
    into "DANYL" in the review tool. Fall back to the first mixed-case title
    among the members (minus Songkick's " @ Venue" suffix).
    """
    title = ordered[0].title
    if not _is_shouting(title):
        return title
    for record in ordered[1:]:
        if record.title and not _is_shouting(record.title):
            return re.split(r"\s+@\s+", record.title, maxsplit=1)[0]
    return title


def _merge_group(group: list[EventRecord]) -> EventRecord:
    # Deterministic order so the same real event always merges the same way,
    # regardless of which order collectors happened to run in.
    ordered = sorted(group, key=lambda r: (-_richness(r), r.source))
    merged = replace(ordered[0])
    for record in ordered[1:]:
        for field in _FILLABLE_FIELDS:
            if not getattr(merged, field) and getattr(record, field):
                setattr(merged, field, getattr(record, field))
    merged.title = _display_title(ordered)
    merged.source = "+".join(sorted(set().union(*(_atomic_sources(record) for record in group))))
    return merged


def _is_word_prefix(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """True if one token list is a leading, whole-word prefix of the other."""
    if not tokens_a or not tokens_b:
        return False
    shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    return longer[: len(shorter)] == shorter


def titles_overlap(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """Same artist(s) named differently: a whole-word prefix, or the same words reordered.

    "Ninho" / "Ninho Quatro Tour" is a prefix; "Isha & Limsa" / "LIMSA + ISHA"
    is the same two names in the other order.
    """
    if _is_word_prefix(tokens_a, tokens_b):
        return True
    return bool(tokens_a) and sorted(tokens_a) == sorted(tokens_b)


# Words that start many unrelated titles; never enough on their own to say two
# listings are the same act.
_LEAD_STOPWORDS = frozenset(
    {"le", "la", "les", "l", "the", "un", "une", "de", "du", "des", "au", "aux", "live", "soiree", "festival", "concert", "night", "nuit"}
)


def _lead_token(tokens: list[str]) -> str:
    for token in tokens:
        if len(token) >= 4 and token not in _LEAD_STOPWORDS:
            return token
    return ""


def share_venue_and_lead(a: EventRecord, b: EventRecord) -> bool:
    """Same venue and the same first significant title word.

    Catches what prefix matching cannot: Songkick lists a co-headliner as its
    own event ("Limsa d'Aulnay @ Theatre Lino Ventura") while another source
    lists the double bill ("LIMSA + ISHA"). Only trusted when both sides name a
    venue, and the caller decides whether the two records must come from
    different sources.
    """
    venue_a = normalize_title_for_matching(a.venue)
    if not venue_a or venue_a != normalize_title_for_matching(b.venue):
        return False
    lead = _lead_token(normalize_title_for_matching(a.title).split())
    return bool(lead) and lead == _lead_token(normalize_title_for_matching(b.title).split())


def covers_same_event(stored: EventRecord, incoming: EventRecord) -> bool:
    """True if a stored row is the older form of an incoming (freshly merged) record.

    Same day, at least one source in common, and the titles or the
    venue-plus-lead-word agree. Used by `merge_records` to keep a row's
    identity (and the ratings hung on it) when a new source joins its event
    and changes its title or url.
    """
    if not stored.start_date or stored.start_date != incoming.start_date:
        return False
    if _atomic_sources(stored).isdisjoint(_atomic_sources(incoming)):
        return False
    tokens_stored = normalize_title_for_matching(stored.title).split()
    tokens_incoming = normalize_title_for_matching(incoming.title).split()
    return titles_overlap(tokens_stored, tokens_incoming) or share_venue_and_lead(stored, incoming)


def _cluster_same_day(records: list[EventRecord]) -> list[list[EventRecord]]:
    """Group same-day records that are plausibly one event listed several ways.

    Two records are linked when their titles overlap (prefix or reordered
    words), or when they name the same venue and lead word and come from
    disjoint sources. Links chain, so a co-headliner listed on its own still
    joins the double bill. A cluster is only kept if it spans more than one
    distinct source -- this pass exists for cross-source matches, not to
    second-guess a single source's own listings.
    """
    tokens = [normalize_title_for_matching(r.title).split() for r in records]
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            linked = titles_overlap(tokens[i], tokens[j]) or (
                _atomic_sources(records[i]).isdisjoint(_atomic_sources(records[j]))
                and share_venue_and_lead(records[i], records[j])
            )
            if linked:
                parent[find(j)] = find(i)

    clusters: dict[int, list[EventRecord]] = defaultdict(list)
    for i, record in enumerate(records):
        clusters[find(i)].append(record)

    return [
        members
        for members in clusters.values()
        if len(members) > 1 and len(set().union(*(_atomic_sources(r) for r in members))) > 1
    ]


def merge_cross_source_duplicates(records: list[EventRecord]) -> CrossSourceMergeResult:
    """Merge the same real-world event when multiple sources independently list it.

    Matches on (normalized title, start_date) rather than URL -- each source
    links to its own page for the same concert, so URL-based dedup never
    catches this. Combines fields instead of picking a winner: a record
    missing a venue/theme/price/url gets it filled in from whichever
    duplicate has it. Records with no title or no date never match each
    other, to avoid grouping unrelated events on a shared blank key.

    Every record then gets a second chance, grouped by date and clustered by
    looser title/venue similarity (see `_cluster_same_day`), to catch
    same-day cross-source listings whose titles matched exactly on nothing
    but the artist name. Records already merged by the exact pass take part
    too: a third source can still join them ("Henrik Schwarz" on Songkick
    beside an explorenice+panda pair).
    """
    groups: dict[tuple[str, str], list[EventRecord]] = defaultdict(list)
    undated: list[EventRecord] = []

    for record in records:
        normalized_title = normalize_title_for_matching(record.title)
        if not normalized_title or not record.start_date:
            undated.append(record)
            continue
        groups[(normalized_title, record.start_date)].append(record)

    merged_groups = 0
    candidates: list[EventRecord] = []
    for group in groups.values():
        if len(group) == 1:
            candidates.append(group[0])
        else:
            candidates.append(_merge_group(group))
            merged_groups += 1

    by_date: dict[str, list[EventRecord]] = defaultdict(list)
    for record in candidates:
        by_date[record.start_date].append(record)

    result: list[EventRecord] = list(undated)
    for same_day_records in by_date.values():
        clustered: set[int] = set()
        for cluster in _cluster_same_day(same_day_records):
            result.append(_merge_group(cluster))
            merged_groups += 1
            clustered.update(id(r) for r in cluster)
        result.extend(record for record in same_day_records if id(record) not in clustered)

    return CrossSourceMergeResult(records=result, merged_groups=merged_groups)
