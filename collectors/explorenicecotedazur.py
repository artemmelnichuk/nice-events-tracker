"""Nice Cote d'Azur Tourist Office event calendar collector.

explorenicecotedazur.com/en/events/all-events/ is plain server-rendered
HTML (confirmed via scrape_mvp.py) -- no API, no JS rendering needed.
Category filtering only works client-side in the browser (the
`wpet_search[...]` query param is silently ignored server-side), so this
collector downloads every page and filters by category in Python.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

BASE_URL = "https://www.explorenicecotedazur.com/en/events/all-events/"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker; personal project)"}
REQUEST_DELAY_SECONDS = 0.5


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}page/{page_number}/"


def discover_last_page(soup: BeautifulSoup) -> int:
    page_numbers = [1]
    for link in soup.find_all("a", href=True):
        match = re.search(r"/all-events/page/(\d+)/", link["href"])
        if match:
            page_numbers.append(int(match.group(1)))
    return max(page_numbers)


def parse_period(card: Any) -> tuple[str, str]:
    period = card.select_one(".iris-card__period")
    if period is None:
        return "", ""
    days = [d.get_text(strip=True) for d in period.select(".iris-card__period__day")]
    months = [m.get_text(strip=True) for m in period.select(".iris-card__period__monthName")]
    years = [y.get_text(strip=True) for y in period.select(".iris-card__period__year")]
    year = years[0] if years else ""

    def build(idx: int) -> str:
        if idx >= len(days) or idx >= len(months):
            return ""
        month = MONTHS.get(months[idx].strip().lower())
        if not year or not month:
            return ""
        return f"{year}-{month}-{days[idx].strip().zfill(2)}"

    start_date = build(0)
    end_date = build(1) if len(days) > 1 else start_date
    return start_date, end_date


def parse_offer(offer_li: Any) -> EventRecord | None:
    card = offer_li.select_one(".iris-card")
    if card is None:
        return None

    title_link = card.select_one("h2.iris-card__content__title a")
    if title_link is None:
        return None

    meta_values = [span.get_text(strip=True) for span in card.select(".entry-meta .content")]
    category = meta_values[0] if len(meta_values) > 0 else ""
    theme = meta_values[1] if len(meta_values) > 1 else ""
    start_date, end_date = parse_period(card)

    record = EventRecord(
        source="explorenicecotedazur",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=title_link.get_text(strip=True),
        category=category,
        theme=theme,
        start_date=start_date,
        end_date=end_date,
        location=card.get("data-layer-wpet-offer-location", ""),
        url=title_link.get("href", ""),
    )
    return record


class ExploreNiceCoteDAzurCollector(BaseCollector):
    """Collect events from the official Nice Cote d'Azur tourist office agenda."""

    source_name = "explorenicecotedazur"

    def __init__(self, category_filter: str | None = "Concert") -> None:
        self.category_filter = category_filter

    def _fetch_soup(self, session: requests.Session, page_number: int) -> BeautifulSoup:
        response = session.get(page_url(page_number), headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)

        try:
            first_page = self._fetch_soup(session, 1)
        except requests.RequestException as error:
            result.errors += 1
            result.error_messages.append(str(error))
            return result

        last_page = discover_last_page(first_page)
        pages = [first_page] + [None] * (last_page - 1)

        for page_number in range(1, last_page + 1):
            if limit is not None and len(result.records) >= limit:
                break
            try:
                soup = pages[page_number - 1] if page_number == 1 else self._fetch_soup(session, page_number)
            except requests.RequestException as error:
                result.errors += 1
                result.error_messages.append(f"page {page_number}: {error}")
                continue

            for offer_li in soup.select("li.wpet-block-list__offer"):
                record = parse_offer(offer_li)
                if record is None:
                    continue
                if self.category_filter and record.category.strip().lower() != self.category_filter.lower():
                    continue
                result.records.append(record)
                if limit is not None and len(result.records) >= limit:
                    break

            if page_number < last_page:
                time.sleep(REQUEST_DELAY_SECONDS)

        result.found = len(result.records)
        return result
