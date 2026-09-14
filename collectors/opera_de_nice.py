"""Opera Nice Cote d'Azur agenda collector.

Plain server-rendered HTML (WordPress "event" custom post type) with
schema.org/Event microdata per card, including an explicit category label
(Concert, Rencontre, ...) via the visible category link -- unlike Nikaia's
programmation page, which tags everything as MusicEvent with no per-card
category text, so it isn't a usable signal for filtering to concerts.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

BASE_URL = "https://www.opera-nice.org/agenda/"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker; personal project)"}
REQUEST_DELAY_SECONDS = 0.5


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}page/{page_number}/"


def parse_event(article: Any) -> EventRecord | None:
    title_el = article.select_one("[itemprop='name']")
    if title_el is None:
        return None

    category_link = article.select_one("a.cat-event")
    category = category_link.get_text(strip=True) if category_link else ""

    venue_el = article.select_one("[itemprop='location'] [itemprop='name']")
    venue = venue_el.get_text(strip=True) if venue_el else ""

    start_meta = article.select_one("meta[itemprop='startDate']")
    start_date = start_meta.get("content", "") if start_meta else ""

    price_el = article.select_one(".event--price")
    price = price_el.get_text(strip=True) if price_el else ""

    return EventRecord(
        source="opera_de_nice",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=title_el.get_text(strip=True),
        category=category,
        start_date=start_date,
        end_date=start_date,
        venue=venue,
        location="Nice",
        price=price,
    )


class OperaDeNiceCollector(BaseCollector):
    """Collect events from the Opera Nice Cote d'Azur public agenda."""

    source_name = "opera_de_nice"

    def __init__(self, category_filter: str | None = "Concert") -> None:
        self.category_filter = category_filter

    def _fetch_soup(self, session: requests.Session, page_number: int) -> BeautifulSoup:
        response = session.get(page_url(page_number), headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)
        page_number = 1

        while True:
            if limit is not None and len(result.records) >= limit:
                break
            try:
                soup = self._fetch_soup(session, page_number)
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    break  # ran past the last page -- not an error
                result.errors += 1
                result.error_messages.append(f"page {page_number}: {error}")
                break
            except requests.RequestException as error:
                result.errors += 1
                result.error_messages.append(f"page {page_number}: {error}")
                break

            articles = soup.select("article[id^='event-']")
            if not articles:
                break

            for article in articles:
                record = parse_event(article)
                if record is None:
                    continue
                if self.category_filter and record.category.strip().lower() != self.category_filter.lower():
                    continue
                result.records.append(record)
                if limit is not None and len(result.records) >= limit:
                    break

            page_number += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        result.found = len(result.records)
        return result
