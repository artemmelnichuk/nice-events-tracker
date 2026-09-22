import json
import unittest
from unittest import mock

import requests
from bs4 import BeautifulSoup

from collectors import menton
from collectors.menton import MentonCollector, ListingEntry, page_url, parse_detail, parse_listing_card, parse_price, parse_venue

CARD = """
<article class="rc_lego item_sheet" data-sheet-id="{sheet_id}">
  <a href="{url}" rel="opener" target="_blank">
    <section class="infos"><div class="infos-wrapper"><div class="item-infos">
      <div class="item-infos-title h3">{title}</div>
      <p class="item-infos-type">{type}</p>
    </div></div></section>
  </a>
</article>
"""


def listing_page(*cards: dict, last_page: int = 1) -> str:
    body = "".join(CARD.format(**card) for card in cards)
    links = "".join(f'<a href="?listpage={n}">{n}</a>' for n in range(2, last_page + 1))
    return f"<html><body>{body}{links}</body></html>"


def card(sheet_id="1", title="Concert de Jazz", type="CULTURAL", url=None) -> dict:
    return dict(sheet_id=sheet_id, title=title, type=type, url=url or f"https://www.menton-riviera-merveilles.co.uk/offers/e-{sheet_id}/")


def detail_page(
    criteria=("Cultural", "Concert", "Music"),
    start="2026-09-20",
    end="2026-09-20",
    status="http://schema.org/EventScheduled",
    location="Palais de l'Europe, 8 Avenue Boyer, 06500 Menton",
    rates="Full price €30 - Reduced price €22",
    locality="Menton",
) -> str:
    event = {
        "@type": "Event",
        "name": "x",
        "url": "https://www.menton-riviera-merveilles.co.uk/offers/jazz/",
        "startDate": start,
        "endDate": end,
        "eventStatus": status,
        "location": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": locality}} if locality else {},
    }
    ld = json.dumps({"@graph": [{"@type": "WebSite"}, event]})
    chips = "".join(f"<li>{c}</li>" for c in criteria)
    return f"""<html><head><script type="application/ld+json">{ld}</script></head><body>
      <ul class="criterias-list">{chips}</ul>
      <div class="localisation-container">{location}<span>Getting there</span></div>
      <h3>Description</h3><div>Some text</div>
      <h3>Rates</h3><div>{rates}</div>
    </body></html>"""


ENTRY = ListingEntry(sheet_id="1", title="Concert de Jazz", type="CULTURAL", url="https://www.menton-riviera-merveilles.co.uk/offers/jazz/")


class UrlTests(unittest.TestCase):
    def test_page_one_is_the_bare_agenda_url_and_never_listpage_one(self) -> None:
        self.assertEqual(page_url(1), menton.BASE_URL)
        self.assertNotIn("listpage=1", page_url(1))
        self.assertTrue(page_url(2).endswith("?listpage=2"))


class ListingTests(unittest.TestCase):
    def test_parses_a_listing_card(self) -> None:
        soup = BeautifulSoup(listing_page(card(sheet_id="6433617", title="Exposition")), "lxml")

        entry = parse_listing_card(soup.select_one("article.item_sheet"))

        self.assertEqual(entry.sheet_id, "6433617")
        self.assertEqual(entry.title, "Exposition")
        self.assertEqual(entry.type, "CULTURAL")

    def test_a_card_without_a_title_is_skipped(self) -> None:
        soup = BeautifulSoup('<article class="item_sheet"><a href="/x"></a></article>', "lxml")

        self.assertIsNone(parse_listing_card(soup.select_one("article")))


class DetailTests(unittest.TestCase):
    def test_builds_a_concert_record(self) -> None:
        record = parse_detail(detail_page(), ENTRY)

        self.assertEqual(record.source, "menton")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.theme, "Music")
        self.assertEqual(record.start_date, "2026-09-20")
        self.assertEqual(record.end_date, "2026-09-20")
        self.assertEqual(record.venue, "Palais de l'Europe")
        self.assertEqual(record.location, "Menton")
        self.assertEqual(record.price, "€22 - €30")
        self.assertEqual(record.availability, "")

    def test_a_non_concert_takes_its_first_extra_criterion_as_category(self) -> None:
        record = parse_detail(detail_page(criteria=("Cultural", "Exhibition")), ENTRY)

        self.assertEqual(record.category, "Exhibition")
        self.assertEqual(record.theme, "")

    def test_a_concert_without_a_genre_has_an_empty_theme(self) -> None:
        record = parse_detail(detail_page(criteria=("Cultural", "Concert")), ENTRY)

        self.assertEqual((record.category, record.theme), ("Concert", ""))

    def test_a_multi_day_event_keeps_both_dates(self) -> None:
        record = parse_detail(detail_page(start="2026-07-01", end="2026-09-30"), ENTRY)

        self.assertEqual((record.start_date, record.end_date), ("2026-07-01", "2026-09-30"))

    def test_cancelled_status_is_captured(self) -> None:
        record = parse_detail(detail_page(status="http://schema.org/EventCancelled"), ENTRY)

        self.assertEqual(record.availability, "Cancelled")

    def test_a_cancellation_in_the_title_is_captured(self) -> None:
        entry = ListingEntry("2", "Concert - Cancelled", "CULTURAL", "https://x/2")

        self.assertEqual(parse_detail(detail_page(), entry).availability, "Cancelled")

    def test_a_page_without_an_event_is_skipped(self) -> None:
        self.assertIsNone(parse_detail("<html><body>nothing</body></html>", ENTRY))

    def test_an_event_outside_menton_proper_keeps_its_own_commune(self) -> None:
        # The agenda also lists events in nearby communes, e.g. Sospel.
        record = parse_detail(detail_page(locality="Sospel"), ENTRY)

        self.assertEqual(record.location, "Sospel")

    def test_a_missing_locality_falls_back_to_menton(self) -> None:
        record = parse_detail(detail_page(locality=None), ENTRY)

        self.assertEqual(record.location, "Menton")


class VenueTests(unittest.TestCase):
    def _soup(self, location: str) -> BeautifulSoup:
        return BeautifulSoup(f'<div class="localisation-container">{location}</div>', "lxml")

    def test_takes_the_place_name_before_the_street(self) -> None:
        self.assertEqual(parse_venue(self._soup("Médiathèque de Sospel, place Trincat, 06380 Sospel")), "Médiathèque de Sospel")

    def test_a_bare_street_address_gives_no_venue(self) -> None:
        self.assertEqual(parse_venue(self._soup("12 Rue Longue, 06500 Menton")), "")

    def test_no_location_block_gives_no_venue(self) -> None:
        self.assertEqual(parse_venue(BeautifulSoup("<div></div>", "lxml")), "")


class PriceTests(unittest.TestCase):
    def _soup(self, rates: str) -> BeautifulSoup:
        return BeautifulSoup(f"<h3>Rates</h3><div>{rates}</div>", "lxml")

    def test_a_single_price(self) -> None:
        self.assertEqual(parse_price(self._soup("Full price €45")), "€45")

    def test_a_range_uses_the_lowest_and_highest_amount(self) -> None:
        self.assertEqual(parse_price(self._soup("Adult 12,50 € - Child €8")), "€8 - €12.5")

    def test_free_admission(self) -> None:
        self.assertEqual(parse_price(self._soup("Free admission")), "Free")

    def test_no_rates_block_gives_no_price(self) -> None:
        self.assertEqual(parse_price(BeautifulSoup("<h3>Description</h3><div>x</div>", "lxml")), "")


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


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(menton.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _pages(self) -> dict[str, str]:
        concert, expo, sport = card("1"), card("2", "Expo", url="https://x/e2"), card("3", "Swim", "SPORTS AND LEISURE", "https://x/e3")
        return {
            page_url(1): listing_page(concert, expo, last_page=2),
            page_url(2): listing_page(concert, sport, last_page=2),
            concert["url"]: detail_page(),
            "https://x/e2": detail_page(criteria=("Cultural", "Exhibition")),
            "https://x/e3": detail_page(criteria=("Sports",)),
        }

    def test_collects_concerts_and_only_opens_detail_pages_for_plausible_types(self) -> None:
        session = FakeSession(self._pages())

        result = MentonCollector().collect(session)

        self.assertEqual((result.found, result.errors), (1, 0))
        self.assertEqual(result.records[0].category, "Concert")
        self.assertNotIn("https://x/e3", session.requested)

    def test_an_event_repeated_across_listing_pages_is_fetched_once(self) -> None:
        session = FakeSession(self._pages())

        MentonCollector().collect(session)

        self.assertEqual(session.requested.count("https://www.menton-riviera-merveilles.co.uk/offers/e-1/"), 1)

    def test_a_failing_detail_page_is_counted_and_the_rest_still_load(self) -> None:
        pages = self._pages()
        pages["https://x/e4"] = detail_page()
        pages[page_url(1)] = listing_page(card("1"), card("4", "Other Concert", url="https://x/e4"), last_page=1)
        session = FakeSession(pages, failing={"https://www.menton-riviera-merveilles.co.uk/offers/e-1/"})

        result = MentonCollector().collect(session)

        self.assertEqual((result.found, result.errors), (1, 1))
        self.assertIn("Concert de Jazz", result.error_messages[0])

    def test_a_failing_first_listing_page_is_an_error_not_a_crash(self) -> None:
        session = FakeSession({}, failing={page_url(1)})

        result = MentonCollector().collect(session)

        self.assertEqual((result.found, result.errors), (0, 1))

    def test_respects_limit(self) -> None:
        pages = self._pages()
        pages[page_url(1)] = listing_page(card("1"), card("4", "Second", url="https://x/e4"), last_page=1)
        pages["https://x/e4"] = detail_page()

        result = MentonCollector().collect(FakeSession(pages), limit=1)

        self.assertEqual(result.found, 1)


if __name__ == "__main__":
    unittest.main()
