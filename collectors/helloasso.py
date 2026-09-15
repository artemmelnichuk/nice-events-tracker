"""HelloAsso association event collector.

Unlike the other sources (broad regional calendars filtered down by
category), this one is deliberately narrow: it follows specific
organizers the user already likes, configured by association slug. So
there is no category filter -- everything a configured association lists
is kept.

HelloAsso's org and event pages are server-rendered (Nuxt SSR), and each
event detail page embeds a full schema.org Event JSON-LD block
(description, venue with address, price tiers) -- richer than any other
source found so far.
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

BASE_URL = "https://www.helloasso.com/associations"
# HelloAsso blocks plain requests.Session traffic outright (403 on every
# header combination tried, including a browser User-Agent) but loads fine
# in a real browser -- this is TLS/HTTP fingerprinting, not a header check,
# so this adapter uses Playwright instead of the shared requests.Session
# every other collector uses (see the note in collectors/base.py).
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PAGE_TIMEOUT_MS = 20_000
REQUEST_DELAY_SECONDS = 0.5

# Domain-specific: this adapter exists to follow dark/alternative-music
# organizers, so a small keyword scan over the event description is enough
# to tag a genre -- not meant to generalize beyond that use case.
GENRE_KEYWORDS = [
    ("cold wave", "Cold wave"),
    ("coldwave", "Cold wave"),
    ("dark wave", "Darkwave"),
    ("darkwave", "Darkwave"),
    ("post-punk", "Post-punk"),
    ("post punk", "Post-punk"),
    ("synth-pop", "Synth-pop"),
    ("synthpop", "Synth-pop"),
    ("synth pop", "Synth-pop"),
    ("gothic", "Gothic"),
    ("goth", "Gothic"),
    ("industrial", "Industrial"),
    ("ebm", "EBM"),
    ("dark ambient", "Dark ambient"),
    ("new wave", "New wave"),
]


def guess_theme(description: str) -> str:
    text = description.lower()
    found: list[str] = []
    for keyword, label in GENRE_KEYWORDS:
        if keyword in text and label not in found:
            found.append(label)
    return ", ".join(found)


def discover_event_urls(soup: BeautifulSoup) -> list[str]:
    event_section = soup.select_one("#event")
    if event_section is None:
        return []
    urls = []
    for link in event_section.select("a[href]"):
        href = link.get("href", "")
        if "/evenements/" in href and href not in urls:
            urls.append(href)
    return urls


def find_event_object(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if payload.get("@type") == "Event":
            return payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                found = find_event_object(item)
                if found:
                    return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_event_object(item)
            if found:
                return found
    return None


def format_price(offers: Any) -> str:
    if not isinstance(offers, dict):
        return ""
    currency = offers.get("priceCurrency", "") or ""
    low = offers.get("lowPrice")
    high = offers.get("highPrice")
    if low and high and low != high:
        return f"{low}-{high} {currency}".strip()
    price = offers.get("price") or low or high
    return f"{price} {currency}".strip() if price else ""


def parse_event_detail(html: str, event_url: str) -> EventRecord | None:
    soup = BeautifulSoup(html, "lxml")
    event_obj: dict[str, Any] | None = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        event_obj = find_event_object(payload)
        if event_obj:
            break

    if not event_obj:
        return None

    location = event_obj.get("location") or {}
    address = location.get("address") or {}
    start_date = str(event_obj.get("startDate") or "")[:10]
    end_date = str(event_obj.get("endDate") or "")[:10] or start_date
    description = str(event_obj.get("description") or "").strip()

    return EventRecord(
        source="helloasso",
        date_collected=datetime.now().astimezone().isoformat(timespec="seconds"),
        title=str(event_obj.get("name") or "").strip(),
        description=description,
        category="Concert",
        theme=guess_theme(description),
        start_date=start_date,
        end_date=end_date,
        venue=str(location.get("name") or "").strip(),
        location=str(address.get("addressLocality") or "").strip(),
        price=format_price(event_obj.get("offers")),
        url=str(event_obj.get("url") or event_url),
    )


class HelloAssoCollector(BaseCollector):
    """Collect events from a hand-picked list of HelloAsso association pages."""

    source_name = "helloasso"

    def __init__(self, association_slugs: list[str]) -> None:
        self.association_slugs = association_slugs

    def collect(self, session: requests.Session, limit: int | None = None) -> CollectorResult:
        result = CollectorResult(source=self.source_name)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_USER_AGENT)

            try:
                for slug in self.association_slugs:
                    if limit is not None and len(result.records) >= limit:
                        break
                    try:
                        page.goto(f"{BASE_URL}/{slug}", timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                        org_html = page.content()
                    except PlaywrightError as error:
                        result.errors += 1
                        result.error_messages.append(f"{slug}: {error}")
                        continue

                    soup = BeautifulSoup(org_html, "lxml")
                    event_urls = discover_event_urls(soup)

                    for event_url in event_urls:
                        if limit is not None and len(result.records) >= limit:
                            break
                        try:
                            page.goto(event_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                            event_html = page.content()
                        except PlaywrightError as error:
                            result.errors += 1
                            result.error_messages.append(f"{event_url}: {error}")
                            continue

                        record = parse_event_detail(event_html, event_url)
                        if record:
                            result.records.append(record)
                        time.sleep(REQUEST_DELAY_SECONDS)
            finally:
                browser.close()

        result.found = len(result.records)
        return result
