"""Common interface for source-specific event collectors.

Unlike the job-collector reference, no adapter here needs a rendered
browser page yet -- every confirmed source (explorenicecotedazur.com,
Songkick, Nikaia, Opera de Nice, Cannes, Antibes) is plain server-rendered
HTML. So collectors take a plain ``requests.Session`` instead of a
Playwright browser context. If a future source needs real JS rendering,
that adapter can bring its own Playwright setup without forcing the
dependency on every other collector.
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
