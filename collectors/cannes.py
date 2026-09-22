"""Cannes Tourist Office event agenda collector.

en.cannes-france.com/events/all-agenda/ is plain server-rendered HTML. Its
listing only labels an event with a coarse type ("CULTURAL" also covers
exhibitions and heritage days), so a concert is recognised from the
criteria list on the event's own page. To keep the request count down only
listing types that can hold a concert get a detail request; the rest are
skipped.

robots.txt disallows `listpage=1` (page one is the bare agenda URL) and any
`?p=` / `?query=` form, so the crawl uses exactly `?listpage=N` for N >= 2.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

BASE_URL = "https://en.cannes-france.com/events/all-agenda/"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker; personal project)", "Accept-Language": "en"}
REQUEST_DELAY_SECONDS = 0.6

# Listing types that can contain a concert; the site's other types
# (COMMERCIAL EVENT, SPORTS AND LEISURE) never do.
DETAIL_TYPES = {"CULTURAL", "ENTERTAINMENT/RECREATION"}

EVENT_STATUS_LABELS = {
    "EventCancelled": "Cancelled",
    "EventPostponed": "Postponed",
    "EventRescheduled": "Rescheduled",
}
CANCELLATION_IN_TITLE = re.compile(r"\b(cancel(?:l)?ed|cancellation|postponed|annul[ée]e?)\b", re.IGNORECASE)
EURO_AMOUNT = re.compile(r"(?:€\s*(\d+(?:[.,]\d+)?))|(?:(\d+(?:[.,]\d+)?)\s*€)")


@dataclass(slots=True)
class ListingEntry:
    """One card on an agenda page."""

    sheet_id: str
    title: str
    type: str
    url: str


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}?listpage={page_number}"


def discover_last_page(soup: BeautifulSoup) -> int:
    page_numbers = [1]
    for link in soup.find_all("a", href=True):
        match = re.search(r"listpage=(\d+)", link["href"])
        if match:
            page_numbers.append(int(match.group(1)))
    return max(page_numbers)


def parse_listing_card(article: Any) -> ListingEntry | None:
    link = article.select_one("a[href]")
    title = article.select_one(".item-infos-title")
    if link is None or title is None:
        return None
    type_label = article.select_one(".item-infos-type")
    return ListingEntry(
        sheet_id=article.get("data-sheet-id", ""),
        title=title.get_text(strip=True),
        type=type_label.get_text(strip=True) if type_label else "",
        url=link["href"],
    )


def _json_ld_event(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in data.get("@graph", [data]) if isinstance(data, dict) else []:
            if isinstance(node, dict) and node.get("@type") == "Event":
                return node
    return None


def parse_criteria(soup: BeautifulSoup) -> list[str]:
    return [li.get_text(strip=True) for li in soup.select("ul.criterias-list li") if li.get_text(strip=True)]


def parse_locality(event: dict[str, Any]) -> str:
    """The event's commune from its JSON-LD address, defaulting to Cannes.

    The tourist office's agenda also lists events in nearby communes (its
    own examples include Mandelieu-la-Napoule and Frejus), so the listing
    site is not a reliable location on its own.
    """
    locality = ((event.get("location") or {}).get("address") or {}).get("addressLocality")
    return locality or "Cannes"


def parse_venue(soup: BeautifulSoup) -> str:
    """Venue name from the page's address line, or "" if it starts with a street number."""
    block = soup.select_one(".localisation-container")
    if block is None:
        return ""
    first_line = block.get_text("|", strip=True).split("|")[0]
    first_part = first_line.split(",")[0].strip()
    return "" if not first_part or first_part[0].isdigit() else first_part


def parse_price(soup: BeautifulSoup) -> str:
    """A compact price from the "Rates" block: "€38 - €70", "€45", "Free" or ""."""
    heading = next((h for h in soup.find_all(["h2", "h3", "h4"]) if h.get_text(strip=True) == "Rates"), None)
    if heading is None:
        return ""
    block = heading.find_next(["div", "p", "ul"])
    if block is None:
        return ""
    text = block.get_text(" ", strip=True)
    amounts = [float((m.group(1) or m.group(2)).replace(",", ".")) for m in EURO_AMOUNT.finditer(text)]
    if not amounts:
        return "Free" if re.search(r"\b(free|gratuit)\b", text, re.IGNORECASE) else ""

    def fmt(value: float) -> str:
        return f"€{value:g}"

    low, high = min(amounts), max(amounts)
    return fmt(low) if low == high else f"{fmt(low)} - {fmt(high)}"


def parse_detail(html: str, entry: ListingEntry) -> EventRecord | None:
    soup = BeautifulSoup(html, "lxml")
    event = _json_ld_event(soup)
    if event is None or not event.get("startDate"):
        return None

    criteria = parse_criteria(soup)
    type_label = entry.type.strip().lower()
    extras = [c for c in criteria if c.lower() != type_label]
    category = "Concert" if "Concert" in criteria else (extras[0] if extras else "")
    theme = next((c for c in extras if c not in ("Concert", category)), "")

    status = EVENT_STATUS_LABELS.get(str(event.get("eventStatus", "")).rsplit("/", 1)[-1], "")
    if not status and CANCELLATION_IN_TITLE.search(entry.title):
        status = "Cancelled"

    return EventRecord(
        source="cannes",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=entry.title,
        category=category,
        theme=theme,
        start_date=event["startDate"],
        end_date=event.get("endDate") or event["startDate"],
        venue=parse_venue(soup),
        location=parse_locality(event),
        price=parse_price(soup),
        url=event.get("url") or entry.url,
        availability=status,
    )


class CannesCollector(BaseCollector):
    """Collect concerts from the Cannes Tourist Office agenda."""

    source_name = "cannes"

    def __init__(self, category_filter: str | None = "Concert") -> None:
        self.category_filter = category_filter

    def _get(self, session: requests.Session, url: str) -> str:
        # A handful of event slugs with an accented punctuation mark (e.g. "E=mc²")
        # 301-redirect to themselves once `requests` re-encodes the URL for the
        # hop -- a genuine site bug, not a transient one. A normal page never
        # redirects more than once or twice, so failing fast at 5 avoids
        # burning the default 30 requests on those before giving up.
        original_limit = getattr(session, "max_redirects", 30)
        session.max_redirects = 5
        try:
            response = session.get(url, headers=HEADERS, timeout=20)
        finally:
            session.max_redirects = original_limit
        response.raise_for_status()
        return response.text

    def _listing(self, session: requests.Session, result: CollectorResult) -> list[ListingEntry]:
        try:
            first = BeautifulSoup(self._get(session, page_url(1)), "lxml")
        except requests.RequestException as error:
            result.errors += 1
            result.error_messages.append(str(error))
            return []

        entries: dict[str, ListingEntry] = {}
        last_page = discover_last_page(first)
        for page_number in range(1, last_page + 1):
            if page_number == 1:
                soup = first
            else:
                time.sleep(REQUEST_DELAY_SECONDS)
                try:
                    soup = BeautifulSoup(self._get(session, page_url(page_number)), "lxml")
                except requests.RequestException as error:
                    result.errors += 1
                    result.error_messages.append(f"listing page {page_number}: {error}")
                    continue
            for article in soup.select("article.item_sheet"):
                entry = parse_listing_card(article)
                # An event that spans several pages of the sorted listing repeats.
                if entry is not None and entry.sheet_id not in entries:
                    entries[entry.sheet_id] = entry
        return list(entries.values())

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)

        for entry in self._listing(session, result):
            if entry.type.strip().upper() not in DETAIL_TYPES:
                continue
            if limit is not None and len(result.records) >= limit:
                break
            time.sleep(REQUEST_DELAY_SECONDS)
            try:
                record = parse_detail(self._get(session, entry.url), entry)
            except requests.RequestException as error:
                result.errors += 1
                result.error_messages.append(f"{entry.title}: {error}")
                continue
            if record is None:
                continue
            if self.category_filter and record.category.lower() != self.category_filter.lower():
                continue
            result.records.append(record)

        result.found = len(result.records)
        return result
