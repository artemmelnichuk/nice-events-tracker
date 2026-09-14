import unittest

from bs4 import BeautifulSoup

from collectors.opera_de_nice import parse_event

CONCERT_ARTICLE_HTML = """
<article id="event-1527" class="event--block post-1527 event_type-concert" itemscope itemtype="https://schema.org/Event">
  <div class="wrapper-info">
    <h2 itemprop="name">Chopin</h2>
    <p itemprop="location" itemscope itemtype="https://schema.org/Place">
      <span itemprop="name">Foyer Montserrat Caballe de l'Opera</span>
    </p>
  </div>
  <div class="wrapper-meta">
    <p class="meta--item event--event-type">
      <a class="link cat-event" href="https://www.opera-nice.org/agenda/type-evenement/concert/">Concert</a>
    </p>
    <p class="event--date">
      <meta itemprop="startDate" content="2026-09-18">
    </p>
    <p class="text-end mb-2"><span class="event--price">gratuit</span></p>
  </div>
</article>
"""

RENCONTRE_ARTICLE_HTML = """
<article id="event-1532" class="event--block post-1532 event_type-rencontre" itemscope itemtype="https://schema.org/Event">
  <div class="wrapper-info">
    <h2 itemprop="name">De l'operette a la comedie musicale</h2>
  </div>
  <div class="wrapper-meta">
    <p class="meta--item event--event-type">
      <a class="link cat-event" href="https://www.opera-nice.org/agenda/type-evenement/rencontre/">Rencontre</a>
    </p>
    <p class="event--date">
      <meta itemprop="startDate" content="2026-09-20">
    </p>
  </div>
</article>
"""

ARTICLE_WITHOUT_TITLE_HTML = """<article id="event-1"><div class="wrapper-meta"></div></article>"""


class ParseEventTests(unittest.TestCase):
    def test_extracts_a_concert_with_category_and_venue(self) -> None:
        soup = BeautifulSoup(CONCERT_ARTICLE_HTML, "lxml")
        record = parse_event(soup.select_one("article"))

        self.assertEqual(record.title, "Chopin")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.venue, "Foyer Montserrat Caballe de l'Opera")
        self.assertEqual(record.start_date, "2026-09-18")
        self.assertEqual(record.end_date, "2026-09-18")
        self.assertEqual(record.price, "gratuit")
        self.assertEqual(record.source, "opera_de_nice")

    def test_extracts_the_real_category_for_a_non_concert_event(self) -> None:
        soup = BeautifulSoup(RENCONTRE_ARTICLE_HTML, "lxml")
        record = parse_event(soup.select_one("article"))
        self.assertEqual(record.category, "Rencontre")

    def test_returns_none_without_a_title(self) -> None:
        soup = BeautifulSoup(ARTICLE_WITHOUT_TITLE_HTML, "lxml")
        self.assertIsNone(parse_event(soup.select_one("article")))


if __name__ == "__main__":
    unittest.main()
