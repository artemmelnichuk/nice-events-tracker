"""
Nice events tracker -- MVP scrape (stage 1 of the plan).

Pulls "Concert" events from the official Nice Cote d'Azur tourist office
event calendar (explorenicecotedazur.com) and dumps them into an Excel file.

No architecture yet on purpose -- this only exists to prove the source
works end to end on real data before designing EventRecord/collectors/etc.
"""

import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.explorenicecotedazur.com/en/events/all-events/"
HEADERS = {"User-Agent": "Mozilla/5.0 (nice-events-tracker MVP; personal project)"}
CATEGORY_FILTER = "Concert"
OUTPUT_PATH = "data/nice_concerts_raw.xlsx"
REQUEST_DELAY_SECONDS = 0.5


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}page/{page_number}/"


def fetch_page(session: requests.Session, page_number: int) -> BeautifulSoup:
    response = session.get(page_url(page_number), headers=HEADERS, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def discover_last_page(soup: BeautifulSoup) -> int:
    page_numbers = [1]
    for link in soup.find_all("a", href=True):
        match = re.search(r"/all-events/page/(\d+)/", link["href"])
        if match:
            page_numbers.append(int(match.group(1)))
    return max(page_numbers)


def parse_period(card) -> tuple[str, str]:
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
        return f"{days[idx]} {months[idx]} {year}".strip()

    start_date = build(0)
    end_date = build(1) if len(days) > 1 else start_date
    return start_date, end_date


def parse_offer(offer_li) -> dict | None:
    card = offer_li.select_one(".iris-card")
    if card is None:
        return None

    title_link = card.select_one("h2.iris-card__content__title a")
    if title_link is None:
        return None

    meta_values = [
        span.get_text(strip=True)
        for span in card.select(".entry-meta .content")
    ]
    category = meta_values[0] if len(meta_values) > 0 else ""
    theme = meta_values[1] if len(meta_values) > 1 else ""
    start_date, end_date = parse_period(card)

    return {
        "event_id": offer_li.get("data-wpet-offer", ""),
        "title": title_link.get_text(strip=True),
        "url": title_link.get("href", ""),
        "location": card.get("data-layer-wpet-offer-location", ""),
        "category": category,
        "theme": theme,
        "start_date": start_date,
        "end_date": end_date,
    }


def scrape_all_events() -> list[dict]:
    session = requests.Session()
    first_page = fetch_page(session, 1)
    last_page = discover_last_page(first_page)
    print(f"Found {last_page} pages, scanning all of them...")

    all_events: list[dict] = []
    pages = [first_page] + [None] * (last_page - 1)  # placeholder, first already fetched

    for page_number in range(1, last_page + 1):
        soup = pages[page_number - 1] if page_number == 1 else fetch_page(session, page_number)
        offers = soup.select("li.wpet-block-list__offer")
        for offer_li in offers:
            record = parse_offer(offer_li)
            if record:
                all_events.append(record)
        print(f"  page {page_number}/{last_page}: {len(offers)} events (running total {len(all_events)})")
        if page_number < last_page:
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_events


def main() -> None:
    all_events = scrape_all_events()
    df = pd.DataFrame(all_events)
    print(f"\nTotal events scraped: {len(df)}")
    print("Category breakdown:")
    print(df["category"].value_counts())

    concerts = df[df["category"].str.strip().str.lower() == CATEGORY_FILTER.lower()]
    print(f"\n'{CATEGORY_FILTER}' events kept: {len(concerts)}")

    concerts.to_excel(OUTPUT_PATH, index=False)
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
