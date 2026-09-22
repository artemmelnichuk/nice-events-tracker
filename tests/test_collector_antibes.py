import json
import unittest
from unittest import mock

import requests
from bs4 import BeautifulSoup

from collectors import antibes
from collectors.antibes import (
    AntibesCollector,
    ListingEntry,
    page_url,
    parse_detail,
    parse_listing_card,
    parse_locality,
    parse_venue,
)

CARD = """
<article class="rc_lego item_sheet" data-sheet-id="{sheet_id}">
  <a href="{url}" rel="opener" target="_blank">
    <div class="item-infos"><div class="item-infos-left">
      <h3 class="item-infos-title h3">{title}</h3>
    </div></div>
  </a>
</article>
"""


def listing_page(*cards: dict, last_page: int = 1) -> str:
    body = "".join(CARD.format(**card) for card in cards)
    links = "".join(f'<a href="?listpage={n}">{n}</a>' for n in range(2, last_page + 1))
    return f"<html><body>{body}{links}</body></html>"


def card(sheet_id="1", title="Jammin'Juan", url=None) -> dict:
    return dict(sheet_id=sheet_id, title=title, url=url or f"https://www.antibesjuanlespins.com/e-{sheet_id}")


def detail_page(
    criteria="Music, Concert, Jazz and blues",
    start="2026-10-29",
    end="2026-10-30",
    status="http://schema.org/EventScheduled",
    address1="Palais des Congrès",
    locality="Antibes",
) -> str:
    event = {
        "@context": "http://schema.org/",
        "@type": "Event",
        "name": "x",
        "url": "https://www.antibesjuanlespins.com/e/jammin-juan",
        "startDate": start,
        "endDate": end,
        "eventStatus": status,
        "location": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": locality}} if locality else {},
    }
    ld = json.dumps(event)
    criteria_html = f'<span class="sheet-header-criterias">{criteria}</span>' if criteria is not None else ""
    address1_html = f'<div class="address1">{address1}</div>' if address1 else ""
    return f"""<html><head><script type="application/ld+json">{ld}</script></head><body>
      <div class="h2 sheet-header_subtitle">{criteria_html}<span class="sheet-header-city">in {locality}</span></div>
      <li class="sidebar-contact-address"><address>{address1_html}<div class="_plu-caps"><span>06600</span><span>{locality}</span></div></address></li>
    </body></html>"""


ENTRY = ListingEntry(sheet_id="1", title="Jammin'Juan", url="https://www.antibesjuanlespins.com/e/jammin-juan")


class UrlTests(unittest.TestCase):
    def test_page_one_is_the_bare_agenda_url(self) -> None:
        self.assertEqual(page_url(1), antibes.BASE_URL)
        self.assertTrue(page_url(2).endswith("?listpage=2"))


class ListingTests(unittest.TestCase):
    def test_parses_a_listing_card(self) -> None:
        soup = BeautifulSoup(listing_page(card(sheet_id="2221957", title="Jammin'Juan")), "lxml")

        entry = parse_listing_card(soup.select_one("article.item_sheet"))

        self.assertEqual(entry.sheet_id, "2221957")
        self.assertEqual(entry.title, "Jammin'Juan")

    def test_a_card_without_a_title_is_skipped(self) -> None:
        soup = BeautifulSoup('<article class="item_sheet"><a href="/x"></a></article>', "lxml")

        self.assertIsNone(parse_listing_card(soup.select_one("article")))


class DetailTests(unittest.TestCase):
    def test_builds_a_concert_record(self) -> None:
        record = parse_detail(detail_page(), ENTRY)

        self.assertEqual(record.source, "antibes")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.theme, "Music")
        self.assertEqual(record.start_date, "2026-10-29")
        self.assertEqual(record.end_date, "2026-10-30")
        self.assertEqual(record.venue, "Palais des Congrès")
        self.assertEqual(record.location, "Antibes")
        self.assertEqual(record.price, "")
        self.assertEqual(record.availability, "")

    def test_a_non_concert_takes_its_first_criterion_as_category(self) -> None:
        record = parse_detail(detail_page(criteria="Sports and recreation, Running"), ENTRY)

        self.assertEqual(record.category, "Sports and recreation")
        self.assertEqual(record.theme, "Running")

    def test_no_criteria_span_gives_an_empty_category_and_theme(self) -> None:
        record = parse_detail(detail_page(criteria=None), ENTRY)

        self.assertEqual((record.category, record.theme), ("", ""))

    def test_no_address1_div_gives_an_empty_venue(self) -> None:
        record = parse_detail(detail_page(address1=""), ENTRY)

        self.assertEqual(record.venue, "")

    def test_a_multi_day_event_keeps_both_dates(self) -> None:
        record = parse_detail(detail_page(start="2026-09-29", end="2026-10-04"), ENTRY)

        self.assertEqual((record.start_date, record.end_date), ("2026-09-29", "2026-10-04"))

    def test_cancelled_status_is_captured(self) -> None:
        record = parse_detail(detail_page(status="http://schema.org/EventCancelled"), ENTRY)

        self.assertEqual(record.availability, "Cancelled")

    def test_a_cancellation_in_the_title_is_captured(self) -> None:
        entry = ListingEntry("2", "Concert - Cancelled", "https://x/2")

        self.assertEqual(parse_detail(detail_page(), entry).availability, "Cancelled")

    def test_a_page_without_an_event_is_skipped(self) -> None:
        self.assertIsNone(parse_detail("<html><body>nothing</body></html>", ENTRY))


class LocalityTests(unittest.TestCase):
    def test_uses_the_locality_as_is_when_not_all_caps(self) -> None:
        self.assertEqual(parse_locality({"location": {"address": {"addressLocality": "Antibes"}}}), "Antibes")

    def test_titlecases_an_all_caps_locality(self) -> None:
        self.assertEqual(parse_locality({"location": {"address": {"addressLocality": "ANTIBES"}}}), "Antibes")

    def test_missing_locality_falls_back_to_antibes(self) -> None:
        self.assertEqual(parse_locality({}), "Antibes")


class VenueTests(unittest.TestCase):
    def test_takes_the_address1_line(self) -> None:
        soup = BeautifulSoup('<div class="sidebar-contact-address"><address><div class="address1">Salle du 8 Mai</div></address></div>', "lxml")

        self.assertEqual(parse_venue(soup), "Salle du 8 Mai")

    def test_no_address1_gives_no_venue(self) -> None:
        soup = BeautifulSoup('<div class="sidebar-contact-address"><address></address></div>', "lxml")

        self.assertEqual(parse_venue(soup), "")


class FakeSession:
    """Serves canned pages by url and records every request."""

    def __init__(self, pages: dict[str, str], failing: set[str] | None = None) -> None:
        self.pages = pages
        self.failing = failing or set()
        self.requested: list[str] = []

    def get(self, url, headers=None, timeout=None):
        self.requested.append(url)
        if url in self.failing:
            raise requests.ConnectionError("boom")
        response = mock.Mock()
        response.text = self.pages[url]
        response.raise_for_status = lambda: None
        return response


class ListingFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(antibes.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dedupes_an_entry_repeated_across_listing_pages(self) -> None:
        pages = {
            page_url(1): listing_page(card("1"), card("2"), last_page=2),
            page_url(2): listing_page(card("1"), card("3"), last_page=2),
        }
        session = FakeSession(pages)
        result = antibes.CollectorResult(source="antibes")

        entries = AntibesCollector()._listing(session, result)

        self.assertEqual(sorted(e.sheet_id for e in entries), ["1", "2", "3"])

    def test_a_failing_first_listing_page_is_an_error_not_a_crash(self) -> None:
        session = FakeSession({}, failing={page_url(1)})
        result = antibes.CollectorResult(source="antibes")

        entries = AntibesCollector()._listing(session, result)

        self.assertEqual((entries, result.errors), ([], 1))

    def test_a_failing_later_page_is_counted_and_the_rest_still_load(self) -> None:
        pages = {
            page_url(1): listing_page(card("1"), last_page=2),
        }
        session = FakeSession(pages, failing={page_url(2)})
        result = antibes.CollectorResult(source="antibes")

        entries = AntibesCollector()._listing(session, result)

        self.assertEqual(([e.sheet_id for e in entries], result.errors), (["1"], 1))


if __name__ == "__main__":
    unittest.main()
