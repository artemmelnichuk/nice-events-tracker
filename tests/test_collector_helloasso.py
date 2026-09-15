import unittest

from bs4 import BeautifulSoup

from collectors.helloasso import (
    discover_event_urls,
    find_event_object,
    format_price,
    guess_theme,
    parse_event_detail,
)

ORG_PAGE_HTML = """
<html><body>
<section id="event" data-test-id="EventSection" class="ActionGroup">
  <ul class="ActionList">
    <li class="Action"><div class="ActionWrapper">
      <a href="https://www.helloasso.com/associations/dark-paca/evenements/concerts-de-neva-bitch-et-contre-jour" class="ActionLink ActionLink-Event">
        <h3>Concerts de NEVA BITCH et CONTRE JOUR</h3>
      </a>
    </div></li>
  </ul>
</section>
<section id="donation"><a href="https://www.helloasso.com/associations/dark-paca/dons">Faire un don</a></section>
</body></html>
"""

EVENT_PAGE_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@graph": [
    {"@type": "Organization", "name": "HelloAsso"},
    {
      "@type": "Event",
      "url": "https://www.helloasso.com/associations/dark-paca/evenements/concerts-de-neva-bitch-et-contre-jour",
      "name": "Concerts de NEVA BITCH et CONTRE JOUR",
      "description": "Forme au debut des annees 80, NEVA s'impose comme un projet de la scene cold wave francaise. Contre Jour, groupe de cold-wave / synth-pop.",
      "startDate": "2026-10-24T20:00:00+02:00",
      "endDate": "2026-10-25T02:00:00+02:00",
      "location": {
        "@type": "Place",
        "name": "l'Altherax",
        "address": {"@type": "PostalAddress", "addressLocality": "Nice", "postalCode": "06200"}
      },
      "offers": {
        "@type": "AggregateOffer",
        "lowPrice": "12",
        "highPrice": "15",
        "priceCurrency": "Eur"
      }
    }
  ]
}
</script>
</head><body></body></html>
"""


class DiscoverEventUrlsTests(unittest.TestCase):
    def test_finds_links_inside_the_event_section_only(self) -> None:
        soup = BeautifulSoup(ORG_PAGE_HTML, "lxml")
        urls = discover_event_urls(soup)
        self.assertEqual(
            urls,
            ["https://www.helloasso.com/associations/dark-paca/evenements/concerts-de-neva-bitch-et-contre-jour"],
        )

    def test_returns_empty_list_without_an_event_section(self) -> None:
        soup = BeautifulSoup("<html><body>no events here</body></html>", "lxml")
        self.assertEqual(discover_event_urls(soup), [])


class GuessThemeTests(unittest.TestCase):
    def test_detects_known_genre_keywords(self) -> None:
        theme = guess_theme("A cold wave and synth-pop night.")
        self.assertIn("Cold wave", theme)
        self.assertIn("Synth-pop", theme)

    def test_empty_for_no_match(self) -> None:
        self.assertEqual(guess_theme("A lovely evening of chamber music."), "")


class FormatPriceTests(unittest.TestCase):
    def test_formats_a_price_range(self) -> None:
        self.assertEqual(
            format_price({"lowPrice": "12", "highPrice": "15", "priceCurrency": "Eur"}),
            "12-15 Eur",
        )

    def test_formats_a_single_price(self) -> None:
        self.assertEqual(format_price({"price": "10", "priceCurrency": "Eur"}), "10 Eur")

    def test_empty_for_missing_offers(self) -> None:
        self.assertEqual(format_price(None), "")


class ParseEventDetailTests(unittest.TestCase):
    def test_extracts_a_full_record_from_json_ld(self) -> None:
        record = parse_event_detail(EVENT_PAGE_HTML, "https://fallback.example/event")

        self.assertIsNotNone(record)
        self.assertEqual(record.title, "Concerts de NEVA BITCH et CONTRE JOUR")
        self.assertEqual(record.venue, "l'Altherax")
        self.assertEqual(record.location, "Nice")
        self.assertEqual(record.start_date, "2026-10-24")
        self.assertEqual(record.end_date, "2026-10-25")
        self.assertEqual(record.price, "12-15 Eur")
        self.assertEqual(record.category, "Concert")
        self.assertIn("Cold wave", record.theme)
        self.assertIn("Synth-pop", record.theme)
        self.assertIn("cold wave", record.description.lower())
        self.assertEqual(record.source, "helloasso")

    def test_returns_none_without_a_json_ld_event(self) -> None:
        record = parse_event_detail("<html><body>no data here</body></html>", "https://fallback.example/event")
        self.assertIsNone(record)


class FindEventObjectTests(unittest.TestCase):
    def test_finds_event_inside_a_graph(self) -> None:
        payload = {"@graph": [{"@type": "Organization"}, {"@type": "Event", "name": "X"}]}
        found = find_event_object(payload)
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "X")

    def test_returns_none_without_an_event(self) -> None:
        self.assertIsNone(find_event_object({"@graph": [{"@type": "Organization"}]}))


if __name__ == "__main__":
    unittest.main()
