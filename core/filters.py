"""Filters applied to a collection run before it reaches the workbook."""

from __future__ import annotations

from core.models import EventRecord


def drop_finished_events(records: list[EventRecord], today: str) -> tuple[list[EventRecord], int]:
    """Drop records whose last day is before `today` (ISO date); return (kept, dropped).

    A source's agenda can still show yesterday's event, and it would land in
    the review tool as something to rate that already happened. Multi-day
    events are judged by their end date; a record with no usable date is kept
    rather than guessed at. Rows already stored are unaffected: this only
    stops finished events from being added.
    """
    kept: list[EventRecord] = []
    for record in records:
        last_day = record.end_date or record.start_date
        if last_day and last_day < today:
            continue
        kept.append(record)
    return kept, len(records) - len(kept)
