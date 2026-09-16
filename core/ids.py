"""Stable event identifier and deduplication-key helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.models import EventRecord


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
}


def normalize_text(value: str) -> str:
    """Normalize text for comparison without changing the stored value."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_url(value: str) -> str:
    """Return a stable URL representation suitable for identity checks."""
    raw_url = str(value or "").strip()
    if not raw_url:
        return ""

    parts = urlsplit(raw_url)
    if not parts.scheme or not parts.netloc:
        return normalize_text(raw_url)

    query_items = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold().startswith("utm_"):
            continue
        if key.casefold() in TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, query_value))

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path,
            urlencode(sorted(query_items)),
            "",
        )
    )


def normalize_title_for_matching(title: str) -> str:
    """Normalize a title for cross-source duplicate matching.

    Different sources format the same real-world event differently --
    Songkick appends " @ Venue Name" to every title, others don't. Strip
    that, fold accents, drop punctuation, so "Djadja & Dinaz" (source A)
    and "Djadja & Dinaz @ Palais Nikaia" (source B) compare equal.
    """
    title = re.split(r"\s+@\s+", str(title or ""), maxsplit=1)[0]
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE).lower()
    return re.sub(r"\s+", " ", folded).strip()


def build_deduplication_key(record: EventRecord) -> str:
    """Build the primary identity key for an event.

    URL is the strongest signal (a source rarely reuses one event page for two
    different events). Without a URL, fall back to a normalized
    title+date+location composite -- good enough to catch a source re-listing
    the same event without a stable link.

    Deliberately excludes `source`: cross-source merging can rewrite a
    record's `source` field (e.g. "explorenicecotedazur" ->
    "explorenicecotedazur+songkick") once a second site starts listing the
    same event. If the key included source, that record would look brand new
    to merge_records() on the next run instead of updating the one already in
    storage, permanently orphaning the old row as a duplicate.
    """
    normalized_url = normalize_url(record.url)
    if normalized_url:
        return f"url|{normalized_url}"

    fallback = "|".join(
        (
            normalize_text(record.title),
            normalize_text(record.start_date),
            normalize_text(record.location),
        )
    )
    return f"fallback|{fallback}"


def _source_slug(source: str) -> str:
    slug = re.sub(r"[^\w]+", "_", normalize_text(source), flags=re.UNICODE)
    return slug.strip("_") or "event"


def build_event_id(record: EventRecord) -> str:
    """Build a stable, readable identifier from the deduplication key."""
    key = build_deduplication_key(record)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"{_source_slug(record.source)}_{digest}"
