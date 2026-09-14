import unittest

from collectors.songkick import parse_json_ld_events, record_from_event

PAGE_HTML = """
<html><body>
<script type="application/ld+json">[{"@context":"http://schema.org","@type":"MusicEvent","name":"KT @ Le 109","url":"https://www.songkick.com/concerts/43280569-kt-at-le-109?utm_medium=organic&utm_source=microformat","location":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Nice","addressCountry":"France"},"name":"Le 109"},"startDate":"2026-09-18T18:00:00","endDate":"2026-09-18"}]</script>
</body></html>
"""

NON_EVENT_PAGE_HTML = """
<html><body>
<script type="application/ld+json">{"@context":"http://schema.org","@type":"WebPage","name":"Nice metro area"}</script>
</body></html>
"""


class ParseJsonLdEventsTests(unittest.TestCase):
    def test_extracts_music_events(self) -> None:
        events = parse_json_ld_events(PAGE_HTML)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "KT @ Le 109")

    def test_ignores_non_music_event_schema(self) -> None:
        events = parse_json_ld_events(NON_EVENT_PAGE_HTML)
        self.assertEqual(events, [])


class RecordFromEventTests(unittest.TestCase):
    def test_builds_a_record_with_venue_and_town_split_out(self) -> None:
        events = parse_json_ld_events(PAGE_HTML)
        record = record_from_event(events[0])

        self.assertEqual(record.source, "songkick")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.title, "KT @ Le 109")
        self.assertEqual(record.venue, "Le 109")
        self.assertEqual(record.location, "Nice")
        self.assertEqual(record.start_date, "2026-09-18")
        self.assertEqual(record.end_date, "2026-09-18")
        self.assertEqual(
            record.url,
            "https://www.songkick.com/concerts/43280569-kt-at-le-109?utm_medium=organic&utm_source=microformat",
        )


if __name__ == "__main__":
    unittest.main()
