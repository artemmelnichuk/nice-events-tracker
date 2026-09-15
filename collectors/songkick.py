"""Songkick Nice metro-area concert listings collector.

Uses the schema.org MusicEvent JSON-LD block embedded in each event card --
more reliable than the display markup, and confirmed plain server-rendered
HTML (no JS needed to see the data). Real listings run out after 2-3 pages;
a page with no MusicEvent entries means we've reached the end.

Songkick blocks plain requests.Session traffic outright (406 on every
header combination tried, including a full browser-like set) but loads
fine in a real browser -- TLS/HTTP fingerprinting, not a header check
(curl with the exact same headers passes; requests doesn't). Confirmed via
the browser tool before reaching for Playwright, same as HelloAsso and the
reference job collector's LinkedIn/WTTJ adapters.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from collectors.base import BaseCollector, CollectorResult
from core.models import EventRecord

BASE_URL = "https://www.songkick.com/metro-areas/28903-france-nice"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PAGE_TIMEOUT_MS = 20_000
REQUEST_DELAY_SECONDS = 0.5
MAX_PAGES = 20  # safety cap -- real listings end well before this


def page_url(page_number: int) -> str:
    return f"{BASE_URL}?page={page_number}"


def parse_json_ld_events(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    events: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "MusicEvent":
                events.append(item)
    return events


def record_from_event(event: dict[str, Any]) -> EventRecord:
    location = event.get("location") or {}
    address = location.get("address") or {}
    start_date = str(event.get("startDate") or "")[:10]
    end_date = str(event.get("endDate") or "")[:10] or start_date

    return EventRecord(
        source="songkick",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=event.get("name", ""),
        category="Concert",
        start_date=start_date,
        end_date=end_date,
        venue=location.get("name", ""),
        location=address.get("addressLocality", ""),
        url=str(event.get("url", "")),
    )


class SongkickCollector(BaseCollector):
    """Collect concerts from Songkick's Nice metro-area listing."""

    source_name = "songkick"

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_USER_AGENT)

            try:
                for page_number in range(1, MAX_PAGES + 1):
                    if limit is not None and len(result.records) >= limit:
                        break
                    try:
                        page.goto(page_url(page_number), timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                        html = page.content()
                    except PlaywrightError as error:
                        result.errors += 1
                        result.error_messages.append(f"page {page_number}: {error}")
                        break

                    events = parse_json_ld_events(html)
                    if not events:
                        break

                    for event in events:
                        result.records.append(record_from_event(event))
                        if limit is not None and len(result.records) >= limit:
                            break

                    if page_number < MAX_PAGES:
                        time.sleep(REQUEST_DELAY_SECONDS)
            finally:
                browser.close()

        result.found = len(result.records)
        return result
