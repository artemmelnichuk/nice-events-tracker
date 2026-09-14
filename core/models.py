"""Shared event data model used by every source adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class EventRecord:
    """Canonical event record produced by a collector.

    Values are kept as strings because source pages expose incomplete and
    inconsistent formatting (partial dates, missing venues, free-text
    locations). Normalization belongs to later pipeline stages, not here.
    """

    event_id: str = ""
    source: str = ""
    date_collected: str = ""
    title: str = ""
    category: str = ""
    theme: str = ""
    start_date: str = ""
    end_date: str = ""
    venue: str = ""
    location: str = ""
    region: str = ""
    country: str = "France"
    price: str = ""
    url: str = ""
    status: str = "scheduled"
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return the record in the canonical export schema."""
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "EventRecord":
        """Build a record from a mapping while ignoring unknown source fields."""
        known_fields = {field for field in cls.__dataclass_fields__}

        def as_text(value: Any) -> str:
            if value is None:
                return ""
            try:
                if value != value:  # NaN values loaded from spreadsheet cells.
                    return ""
            except (TypeError, ValueError):
                pass
            return str(value)

        normalized = {
            field: as_text(value)
            for field, value in values.items()
            if field in known_fields
        }
        return cls(**normalized)


EVENT_RECORD_COLUMNS: tuple[str, ...] = tuple(EventRecord.__dataclass_fields__)
