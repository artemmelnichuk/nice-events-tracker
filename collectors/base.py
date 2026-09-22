"""Common interface for source-specific event collectors.

Collectors take a plain ``requests.Session`` -- most sources
(explorenicecotedazur.com, Nikaia, Opera de Nice, Cannes) are plain
server-rendered HTML and never touch it beyond that. A source whose
category/venue only shows up after client-side JS runs (Songkick, blocked
outright without a real browser; Antibes, Angular-rendered detail pages)
brings its own Playwright setup instead, without forcing the dependency
on every other collector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

from core.models import EventRecord


@dataclass(slots=True)
class CollectorResult:
    """Raw result and counters returned by one source adapter."""

    source: str
    records: list[EventRecord] = field(default_factory=list)
    found: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


class BaseCollector(ABC):
    """Contract shared by every event source adapter."""

    source_name: str

    @abstractmethod
    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        """Collect events from this source, optionally capped at ``limit``."""
        raise NotImplementedError
