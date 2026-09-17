import unittest

from core.models import EventRecord
from core.priority import sort_by_theme_priority


class SortByThemePriorityTests(unittest.TestCase):
    def test_sinks_deprioritized_themes_to_the_end(self) -> None:
        jazz = EventRecord(title="Jazz Night", theme="Jazz and blues")
        pop = EventRecord(title="Pop Show", theme="Pop music")
        rock = EventRecord(title="Rock Show", theme="Rock")

        result = sort_by_theme_priority([pop, jazz, rock], ["Pop music", "Light music"])

        self.assertEqual([r.title for r in result], ["Jazz Night", "Rock Show", "Pop Show"])

    def test_preserves_relative_order_within_each_band(self) -> None:
        a = EventRecord(title="A", theme="Rock")
        b = EventRecord(title="B", theme="Pop music")
        c = EventRecord(title="C", theme="Jazz and blues")
        d = EventRecord(title="D", theme="Pop music")

        result = sort_by_theme_priority([a, b, c, d], ["Pop music"])

        self.assertEqual([r.title for r in result], ["A", "C", "B", "D"])

    def test_empty_deprioritized_list_keeps_original_order(self) -> None:
        records = [EventRecord(title="A", theme="Rock"), EventRecord(title="B", theme="Pop music")]
        result = sort_by_theme_priority(records, [])
        self.assertEqual([r.title for r in result], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
