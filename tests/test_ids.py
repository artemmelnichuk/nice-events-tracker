import unittest

from core.ids import build_deduplication_key, build_event_id, normalize_url
from core.models import EventRecord


class NormalizeUrlTests(unittest.TestCase):
    def test_strips_tracking_params_and_trailing_slash(self) -> None:
        url = "https://Example.com/en/event/foo/?utm_source=fb&ref=1"
        self.assertEqual(normalize_url(url), "https://example.com/en/event/foo?ref=1")

    def test_empty_url_returns_empty_string(self) -> None:
        self.assertEqual(normalize_url(""), "")


class DeduplicationKeyTests(unittest.TestCase):
    def test_uses_url_when_present(self) -> None:
        record = EventRecord(source="explorenicecotedazur", url="https://example.com/event/foo/")
        key = build_deduplication_key(record)
        self.assertIn("url", key)

    def test_falls_back_to_title_date_location_without_url(self) -> None:
        record = EventRecord(source="x", title="Jazz Night", start_date="12 September 2026", location="Nice")
        key = build_deduplication_key(record)
        self.assertIn("fallback", key)
        self.assertIn("jazz night", key)

    def test_same_url_different_casing_produces_same_key(self) -> None:
        a = EventRecord(source="X", url="https://Example.com/Event/Foo/")
        b = EventRecord(source="x", url="https://example.com/Event/Foo")
        self.assertEqual(build_deduplication_key(a), build_deduplication_key(b))

    def test_same_url_different_source_produces_same_key(self) -> None:
        # A record's `source` changes when cross-source merging picks it up
        # (e.g. "explorenicecotedazur" -> "explorenicecotedazur+songkick").
        # The identity key must not move when that happens, or merge_records()
        # treats the merged record as new instead of updating the old one.
        a = EventRecord(source="explorenicecotedazur", url="https://example.com/event/foo/")
        b = EventRecord(source="explorenicecotedazur+songkick", url="https://example.com/event/foo/")
        self.assertEqual(build_deduplication_key(a), build_deduplication_key(b))


class BuildEventIdTests(unittest.TestCase):
    def test_is_stable_for_the_same_record_content(self) -> None:
        record_a = EventRecord(source="explorenicecotedazur", url="https://example.com/event/foo/")
        record_b = EventRecord(source="explorenicecotedazur", url="https://example.com/event/foo/")
        self.assertEqual(build_event_id(record_a), build_event_id(record_b))

    def test_differs_for_different_urls(self) -> None:
        record_a = EventRecord(source="explorenicecotedazur", url="https://example.com/event/foo/")
        record_b = EventRecord(source="explorenicecotedazur", url="https://example.com/event/bar/")
        self.assertNotEqual(build_event_id(record_a), build_event_id(record_b))


if __name__ == "__main__":
    unittest.main()
