"""Taste-driven ordering, distinct from identity/dedup logic in core.ids."""

from __future__ import annotations

from core.models import EventRecord


def sort_by_theme_priority(
    records: list[EventRecord], deprioritized_themes: list[str]
) -> list[EventRecord]:
    """Sink records whose theme has a poor like rate to the end of the list.

    A stable sort: within each priority band, the original (chronological)
    order is preserved. Deprioritized records aren't dropped -- they still
    get collected and rated, just reviewed last.
    """
    deprioritized = set(deprioritized_themes)
    return sorted(records, key=lambda record: record.theme in deprioritized)
