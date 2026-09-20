import unittest

from core.filters import drop_finished_events
from core.models import EventRecord

TODAY = "2026-09-20"


class DropFinishedEventsTests(unittest.TestCase):
    def test_drops_an_event_that_ended_yesterday(self) -> None:
        records = [EventRecord(source="x", title="Yesterday", start_date="2026-09-19", end_date="2026-09-19")]

        kept, dropped = drop_finished_events(records, TODAY)

        self.assertEqual((kept, dropped), ([], 1))

    def test_keeps_todays_event(self) -> None:
        records = [EventRecord(source="x", title="Tonight", start_date=TODAY, end_date=TODAY)]

        kept, dropped = drop_finished_events(records, TODAY)

        self.assertEqual((len(kept), dropped), (1, 0))

    def test_keeps_a_multi_day_event_still_running(self) -> None:
        records = [EventRecord(source="x", title="Festival", start_date="2026-09-18", end_date="2026-09-22")]

        kept, dropped = drop_finished_events(records, TODAY)

        self.assertEqual((len(kept), dropped), (1, 0))

    def test_uses_the_start_date_when_there_is_no_end_date(self) -> None:
        records = [EventRecord(source="x", title="Old", start_date="2026-09-01")]

        self.assertEqual(drop_finished_events(records, TODAY)[1], 1)

    def test_keeps_a_record_with_no_dates(self) -> None:
        records = [EventRecord(source="x", title="Undated")]

        self.assertEqual(len(drop_finished_events(records, TODAY)[0]), 1)


if __name__ == "__main__":
    unittest.main()
