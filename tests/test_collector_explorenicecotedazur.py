import unittest

from bs4 import BeautifulSoup

from collectors.explorenicecotedazur import discover_last_page, parse_offer, parse_period

CONCERT_CARD_HTML = """
<li class="wpet-block-list__offer" data-wpet-wrapper="offer" data-wpet-offer="64029">
  <div class="iris-card" data-layer-wpet-offer-location="Villefranche-sur-Mer">
    <div class="iris-card__content">
      <div class="wp-block-wpet-card-template-period period">
        <p class="iris-card__period reset-margin">
          <span class="iris-card__period__day">21</span>
          <span class="iris-card__period__monthName">February</span>
          <span class="iris-card__period__sep"></span>
          <span class="iris-card__period__day">29</span>
          <span class="iris-card__period__monthName">November</span>
          <span class="iris-card__period__year">2026</span>
        </p>
      </div>
      <h2 class="iris-card__content__title">
        <a href="https://www.explorenicecotedazur.com/en/event/concerts-at-the-trinquette-jazz-club/">
          Concerts at the Trinquette Jazz Club
        </a>
      </h2>
      <div class="entry-meta"><span class="content">Concert</span></div>
      <div class="entry-meta"><span class="content">Jazz and blues</span></div>
    </div>
  </div>
</li>
"""

CARD_WITHOUT_TITLE_HTML = """
<li class="wpet-block-list__offer" data-wpet-offer="1">
  <div class="iris-card"></div>
</li>
"""

PAGINATION_HTML = """
<html><body>
<a href="/en/events/all-events/page/2/">2</a>
<a href="/en/events/all-events/page/57/">57</a>
</body></html>
"""


class ParseOfferTests(unittest.TestCase):
    def test_extracts_all_fields_from_a_real_card(self) -> None:
        soup = BeautifulSoup(CONCERT_CARD_HTML, "lxml")
        offer_li = soup.select_one("li.wpet-block-list__offer")
        record = parse_offer(offer_li)

        self.assertIsNotNone(record)
        self.assertEqual(record.title, "Concerts at the Trinquette Jazz Club")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.theme, "Jazz and blues")
        self.assertEqual(record.location, "Villefranche-sur-Mer")
        self.assertEqual(record.start_date, "2026-02-21")
        self.assertEqual(record.end_date, "2026-11-29")
        self.assertEqual(
            record.url,
            "https://www.explorenicecotedazur.com/en/event/concerts-at-the-trinquette-jazz-club/",
        )
        self.assertEqual(record.source, "explorenicecotedazur")

    def test_returns_none_when_card_has_no_title_link(self) -> None:
        soup = BeautifulSoup(CARD_WITHOUT_TITLE_HTML, "lxml")
        offer_li = soup.select_one("li.wpet-block-list__offer")
        self.assertIsNone(parse_offer(offer_li))


class ParsePeriodTests(unittest.TestCase):
    def test_single_day_event_uses_the_same_start_and_end(self) -> None:
        html = """
        <div class="iris-card__period">
          <span class="iris-card__period__day">11</span>
          <span class="iris-card__period__monthName">September</span>
          <span class="iris-card__period__year">2026</span>
        </div>
        """
        card = BeautifulSoup(html, "lxml")
        start, end = parse_period(card)
        self.assertEqual(start, "2026-09-11")
        self.assertEqual(end, start)


class DiscoverLastPageTests(unittest.TestCase):
    def test_finds_the_highest_page_number(self) -> None:
        soup = BeautifulSoup(PAGINATION_HTML, "lxml")
        self.assertEqual(discover_last_page(soup), 57)

    def test_defaults_to_one_without_pagination_links(self) -> None:
        soup = BeautifulSoup("<html><body>no links here</body></html>", "lxml")
        self.assertEqual(discover_last_page(soup), 1)


if __name__ == "__main__":
    unittest.main()
