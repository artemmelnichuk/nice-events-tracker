import unittest

from bs4 import BeautifulSoup

from collectors.panda_events import parse_card, parse_french_date

CARD_TEMPLATE = """
<div class="jet-listing-grid__item" data-post-id="4358">
  <div class="jet-engine-listing-overlay-wrap" data-url="{url}">
    <div class="elementor-widget-container"><h1 class="elementor-heading-title">{title}</h1></div>
    <div class="jet-listing-dynamic-field__inline-wrap"><h2 class="jet-listing-dynamic-field__content">{date}</h2></div>
    <div class="jet-listing-dynamic-field__inline-wrap"><h2 class="jet-listing-dynamic-field__content">{venue}</h2></div>
    <div class="jet-listing-dynamic-field__inline-wrap"><div class="jet-listing-dynamic-field__content">{price}</div></div>
  </div>
</div>
"""


def make_card(**overrides) -> BeautifulSoup:
    fields = dict(
        url="https://www.panda-events.com/evenement/liv-del-estal/",
        title="LIV DEL ESTAL",
        date="10 octobre, 2026",
        venue="Frigo 16",
        price="à partir de 5 € + FL*",
    )
    fields.update(overrides)
    return BeautifulSoup(CARD_TEMPLATE.format(**fields), "lxml").select_one(".jet-listing-grid__item")


class ParseCardTests(unittest.TestCase):
    def test_extracts_all_fields_from_a_real_card(self) -> None:
        record = parse_card(make_card())

        self.assertIsNotNone(record)
        self.assertEqual(record.source, "panda_events")
        self.assertEqual(record.title, "LIV DEL ESTAL")
        self.assertEqual(record.start_date, "2026-10-10")
        self.assertEqual(record.end_date, "2026-10-10")
        self.assertEqual(record.venue, "Frigo 16")
        self.assertEqual(record.location, "Nice")
        self.assertEqual(record.price, "à partir de 5 € + FL*")
        self.assertEqual(record.url, "https://www.panda-events.com/evenement/liv-del-estal/")
        self.assertEqual(record.availability, "")

    def test_normalizes_the_sites_short_name_for_le_109(self) -> None:
        record = parse_card(make_card(venue="109"))
        self.assertEqual(record.venue, "Le 109")

    def test_hors_les_murs_has_no_known_location(self) -> None:
        record = parse_card(make_card(venue="Hors les murs"))
        self.assertEqual(record.venue, "Hors les murs")
        self.assertEqual(record.location, "")

    def test_cancellation_in_the_title_sets_availability(self) -> None:
        record = parse_card(make_card(title="CAMILLE YEMBE : ANNULATION"))
        self.assertEqual(record.availability, "Annulation")

    def test_returns_none_without_a_url_or_title(self) -> None:
        self.assertIsNone(parse_card(make_card(url="")))
        self.assertIsNone(parse_card(make_card(title="")))


class ParseFrenchDateTests(unittest.TestCase):
    def test_parses_accented_and_unaccented_months(self) -> None:
        self.assertEqual(parse_french_date("27 février, 2027"), "2027-02-27")
        self.assertEqual(parse_french_date("5 août, 2026"), "2026-08-05")
        self.assertEqual(parse_french_date("4 décembre, 2026"), "2026-12-04")

    def test_returns_empty_string_for_unparseable_text(self) -> None:
        self.assertEqual(parse_french_date("bientôt"), "")
        self.assertEqual(parse_french_date("3 smarch, 2026"), "")


if __name__ == "__main__":
    unittest.main()
