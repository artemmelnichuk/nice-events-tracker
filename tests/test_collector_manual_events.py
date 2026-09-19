import tempfile
import unittest
from pathlib import Path

from collectors.manual_events import ManualEventsCollector, parse_entry

VALID_YAML = """
events:
  - title: "Cielo presents: Boris Brejcha"
    date: 2026-09-18
    venue: Arènes de Fréjus
    location: Fréjus
    price: "à partir de 52,50 €"
    theme: Techno
    url: https://ra.co/events/2492424
    found_via: Resident Advisor
  - title: Quoted Date Night
    date: "2026-11-02"
    end_date: 2026-11-03
"""


def collect_from(text: str, **kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manual_events.yaml"
        path.write_text(text, encoding="utf-8")
        return ManualEventsCollector(path).collect(**kwargs)


class ParseEntryTests(unittest.TestCase):
    def test_builds_a_full_record(self) -> None:
        record = parse_entry(
            {
                "title": "Boris Brejcha",
                "date": "2026-09-18",
                "venue": "Arènes de Fréjus",
                "location": "Fréjus",
                "price": "52,50 €",
                "theme": "Techno",
                "url": "https://ra.co/events/2492424",
                "found_via": "Resident Advisor",
            }
        )

        self.assertEqual(record.source, "manual_events")
        self.assertEqual(record.title, "Boris Brejcha")
        self.assertEqual(record.start_date, "2026-09-18")
        self.assertEqual(record.end_date, "2026-09-18")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.venue, "Arènes de Fréjus")
        self.assertEqual(record.price, "52,50 €")
        self.assertEqual(record.note, "found via Resident Advisor")

    def test_requires_title_and_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "title is required"):
            parse_entry({"date": "2026-09-18"})
        with self.assertRaisesRegex(ValueError, "date is required"):
            parse_entry({"title": "No date"})

    def test_rejects_a_malformed_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            parse_entry({"title": "Bad", "date": "18/09/2026"})

    def test_reports_unknown_fields_instead_of_dropping_them(self) -> None:
        with self.assertRaisesRegex(ValueError, "venu"):
            parse_entry({"title": "Typo", "date": "2026-09-18", "venu": "Le 109"})


class ManualEventsCollectorTests(unittest.TestCase):
    def test_reads_unquoted_and_quoted_dates(self) -> None:
        result = collect_from(VALID_YAML)

        self.assertEqual(result.errors, 0)
        self.assertEqual(result.found, 2)
        self.assertEqual(result.records[0].start_date, "2026-09-18")
        self.assertEqual(result.records[1].start_date, "2026-11-02")
        self.assertEqual(result.records[1].end_date, "2026-11-03")

    def test_a_bad_entry_is_reported_and_the_rest_still_load(self) -> None:
        result = collect_from(
            "events:\n  - title: Good\n    date: 2026-10-01\n  - title: Broken\n    date: soon\n"
        )

        self.assertEqual(result.found, 1)
        self.assertEqual(result.errors, 1)
        self.assertIn("Broken", result.error_messages[0])

    def test_missing_file_and_empty_list_are_not_errors(self) -> None:
        missing = ManualEventsCollector(Path("does-not-exist.yaml")).collect()
        self.assertEqual((missing.found, missing.errors), (0, 0))

        empty = collect_from("events: []\n")
        self.assertEqual((empty.found, empty.errors), (0, 0))

    def test_invalid_yaml_is_an_error(self) -> None:
        result = collect_from("events: [unclosed\n")
        self.assertEqual(result.errors, 1)
        self.assertEqual(result.found, 0)

    def test_respects_limit(self) -> None:
        result = collect_from(VALID_YAML, limit=1)
        self.assertEqual(result.found, 1)


if __name__ == "__main__":
    unittest.main()
