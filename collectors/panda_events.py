"""Panda Events agenda collector.

Panda Events programs most of Nice's club and mid-size concert circuit --
Le 109, Frigo 16, Theatre Lino Ventura, the Ref Session series, Paranormal
Festival. The agenda at /agenda/ is plain server-rendered WordPress
(JetEngine listing grid): no JS rendering, no bot protection, and unlike
every other source so far a price on almost every card.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

AGENDA_URL = "https://www.panda-events.com/agenda/"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker; personal project)"}

MONTHS = {
    "janvier": "01", "fevrier": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "aout": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "decembre": "12",
}

# The site's own short name for the venue at 89 route de Turin; Songkick and
# the tourist office call it "Le 109", so match that for venue statistics.
VENUE_ALIASES = {"109": "Le 109"}

HORS_LES_MURS = "hors les murs"
CANCELLATION = re.compile(r"annulation|annul[ée]", re.IGNORECASE)


def parse_french_date(text: str) -> str:
    """Turn "10 octobre, 2026" into "2026-10-10"; empty string if unparseable."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    match = re.search(r"(\d{1,2})\s+([a-z]+),?\s+(\d{4})", folded)
    if not match:
        return ""
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name)
    if not month:
        return ""
    return f"{year}-{month}-{day.zfill(2)}"


def parse_card(item: Any) -> EventRecord | None:
    overlay = item.select_one(".jet-engine-listing-overlay-wrap")
    title_tag = item.select_one("h1.elementor-heading-title")
    if overlay is None or title_tag is None:
        return None

    url = overlay.get("data-url", "")
    title = title_tag.get_text(strip=True)
    if not url or not title:
        return None

    # Card fields come as two <h2> (date, venue) and one <div> (price) sharing
    # the same JetEngine class -- position is the only distinguishing marker.
    headings = [h.get_text(strip=True) for h in item.select("h2.jet-listing-dynamic-field__content")]
    price_tag = item.select_one("div.jet-listing-dynamic-field__content")
    date_text = headings[0] if len(headings) > 0 else ""
    venue = headings[1] if len(headings) > 1 else ""
    venue = VENUE_ALIASES.get(venue, venue)
    start_date = parse_french_date(date_text)

    cancellation = CANCELLATION.search(title)

    return EventRecord(
        source="panda_events",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=title,
        # The agenda has no category (battles and workshops sit next to
        # concerts); treat everything as Concert, like Songkick does.
        category="Concert",
        start_date=start_date,
        end_date=start_date,
        venue=venue,
        location="" if venue.casefold() == HORS_LES_MURS else "Nice",
        price=price_tag.get_text(strip=True) if price_tag else "",
        url=url,
        availability=cancellation.group(0).capitalize() if cancellation else "",
    )


class PandaEventsCollector(BaseCollector):
    """Collect upcoming events from the Panda Events agenda."""

    source_name = "panda_events"

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)

        try:
            response = session.get(AGENDA_URL, headers=HEADERS, timeout=20)
            response.raise_for_status()
        except requests.RequestException as error:
            result.errors += 1
            result.error_messages.append(str(error))
            return result

        soup = BeautifulSoup(response.text, "lxml")
        for item in soup.select(".jet-listing-grid__item"):
            record = parse_card(item)
            if record is None:
                continue
            result.records.append(record)
            if limit is not None and len(result.records) >= limit:
                break

        result.found = len(result.records)
        return result
