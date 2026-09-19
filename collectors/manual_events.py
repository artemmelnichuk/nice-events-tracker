"""Hand-entered events, for sources the tracker can't or shouldn't read.

Resident Advisor (CAPTCHA + terms forbidding bots), Shotgun and Instagram
all show events worth having but can't be collected automatically. When one
turns up, it goes into config/manual_events.yaml and this collector feeds it
through the same pipeline as every other source -- dedup, cross-source merge
and export all apply. No network access.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import requests
import yaml

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "manual_events.yaml"

ALLOWED_FIELDS = {
    "title", "date", "end_date", "venue", "location", "price", "theme",
    "category", "url", "description", "availability", "found_via",
}


def _iso_date(value: Any, field: str) -> str:
    # YAML turns an unquoted 2026-09-18 into a date object, a quoted one stays text.
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        return value.isoformat()
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from None


def parse_entry(entry: Any) -> EventRecord:
    """Turn one YAML entry into a record; raise ValueError naming what's wrong."""
    if not isinstance(entry, dict):
        raise ValueError("entry must be a mapping of fields")

    # Strict on purpose: a typo like `venu:` would otherwise silently drop data.
    unknown = sorted(set(entry) - ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")

    def text(key: str) -> str:
        return str(entry.get(key) or "").strip()

    title = text("title")
    if not title:
        raise ValueError("title is required")
    if entry.get("date") in (None, ""):
        raise ValueError("date is required")

    start_date = _iso_date(entry["date"], "date")
    end_date = _iso_date(entry["end_date"], "end_date") if entry.get("end_date") else start_date
    found_via = text("found_via")

    return EventRecord(
        source="manual_events",
        date_collected=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        title=title,
        category=text("category") or "Concert",
        theme=text("theme"),
        start_date=start_date,
        end_date=end_date,
        venue=text("venue"),
        location=text("location"),
        price=text("price"),
        url=text("url"),
        description=text("description"),
        availability=text("availability"),
        note=f"found via {found_via}" if found_via else "",
    )


class ManualEventsCollector(BaseCollector):
    """Read events entered by hand in config/manual_events.yaml."""

    source_name = "manual_events"

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH

    def collect(self, session: requests.Session | None = None, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)
        if not self.path.exists():
            return result

        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8-sig")) or {}
        except yaml.YAMLError as error:
            result.errors += 1
            result.error_messages.append(f"{self.path.name}: invalid YAML: {error}")
            return result

        entries = data.get("events") if isinstance(data, dict) else None
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            result.errors += 1
            result.error_messages.append(f"{self.path.name}: `events` must be a list")
            return result

        for number, entry in enumerate(entries, start=1):
            if limit is not None and len(result.records) >= limit:
                break
            try:
                result.records.append(parse_entry(entry))
            except ValueError as error:
                label = entry.get("title", "") if isinstance(entry, dict) else ""
                result.errors += 1
                result.error_messages.append(f"entry {number} {label!r}: {error}")

        result.found = len(result.records)
        return result
