"""Antibes Juan-les-Pins Tourist Office event agenda collector.

antibesjuanlespins.com runs the same "Tourism System" platform as Cannes
(same `item_sheet` listing cards, same `?listpage=N` pagination), and its
listing pages are plain server-rendered HTML like Cannes' -- confirmed on
both language paths. Its detail pages are not, though: category
(`.sheet-header-criterias`) and venue (`.sidebar-contact-address`) are
filled in by an Angular app after the page loads, and are simply absent
from the initial HTML -- there is no listing-level type badge to filter on
either, unlike Cannes. So detail pages go through Playwright (same
approach as Songkick) instead of a plain request. The listing is small
enough (~20 events across 2 pages) that fetching every detail page this
way is still fast.

No price/rates block was found on any sample detail page, rendered or
not -- price is left empty for this source.
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
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

BASE_URL = "https://www.antibesjuanlespins.com/en/must-see-must-do/going-out/diary-all-the-events"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker; personal project)", "Accept-Language": "en"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PAGE_TIMEOUT_MS = 20_000
REQUEST_DELAY_SECONDS = 0.6

EVENT_STATUS_LABELS = {
    "EventCancelled": "Cancelled",
    "EventPostponed": "Postponed",
    "EventRescheduled": "Rescheduled",
}
CANCELLATION_IN_TITLE = re.compile(r"\b(cancel(?:l)?ed|cancellation|postponed|annul[ée]e?)\b", re.IGNORECASE)


@dataclass(slots=True)
class ListingEntry:
    """One card on an agenda page."""

    sheet_id: str
    title: str
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
    return ListingEntry(
        sheet_id=article.get("data-sheet-id", ""),
        title=title.get_text(strip=True),
        url=link["href"],
    )


def _json_ld_event(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Event":
            return data
    return None


def parse_criteria(soup: BeautifulSoup) -> list[str]:
    """Human-readable category chips, Angular-rendered as one comma-joined span."""
    el = soup.select_one(".sheet-header-criterias")
    if el is None:
        return []
    return [part.strip() for part in el.get_text().split(",") if part.strip()]


def parse_venue(soup: BeautifulSoup) -> str:
    """The venue/street name line, or "" when the address is just a postal code and city."""
    el = soup.select_one(".sidebar-contact-address .address1")
    return el.get_text(strip=True) if el else ""


def parse_locality(event: dict[str, Any]) -> str:
    locality = ((event.get("location") or {}).get("address") or {}).get("addressLocality")
    if not locality:
        return "Antibes"
    return locality.title() if locality.isupper() else locality


def parse_detail(html: str, entry: ListingEntry) -> EventRecord | None:
    soup = BeautifulSoup(html, "lxml")
    event = _json_ld_event(soup)
    if event is None or not event.get("startDate"):
        return None

    criteria = parse_criteria(soup)
    category = "Concert" if "Concert" in criteria else (criteria[0] if criteria else "")
    theme = next((c for c in criteria if c not in ("Concert", category)), "")

    status = EVENT_STATUS_LABELS.get(str(event.get("eventStatus", "")).rsplit("/", 1)[-1], "")
    if not status and CANCELLATION_IN_TITLE.search(entry.title):
        status = "Cancelled"

    return EventRecord(
        source="antibes",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=entry.title,
        category=category,
        theme=theme,
        start_date=event["startDate"],
        end_date=event.get("endDate") or event["startDate"],
        venue=parse_venue(soup),
        location=parse_locality(event),
        url=event.get("url") or entry.url,
        availability=status,
    )


class AntibesCollector(BaseCollector):
    """Collect concerts from the Antibes Juan-les-Pins Tourist Office agenda."""

    source_name = "antibes"

    def __init__(self, category_filter: str | None = "Concert") -> None:
        self.category_filter = category_filter

    def _get(self, session: requests.Session, url: str) -> str:
        response = session.get(url, headers=HEADERS, timeout=20)
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
        entries = self._listing(session, result)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_USER_AGENT)
            try:
                for entry in entries:
                    if limit is not None and len(result.records) >= limit:
                        break
                    time.sleep(REQUEST_DELAY_SECONDS)
                    try:
                        page.goto(entry.url, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
                        html = page.content()
                    except PlaywrightError as error:
                        result.errors += 1
                        result.error_messages.append(f"{entry.title}: {error}")
                        continue
                    record = parse_detail(html, entry)
                    if record is None:
                        continue
                    if self.category_filter and record.category.lower() != self.category_filter.lower():
                        continue
                    result.records.append(record)
            finally:
                browser.close()

        result.found = len(result.records)
        return result
