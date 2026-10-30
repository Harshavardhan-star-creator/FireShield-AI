"""SQLite event store tests use isolated temporary database files."""

from datetime import datetime, timezone
from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
import unittest

from fireshield.database import (
    EVENT_CATEGORIES,
    initialize_database,
    load_recent_session_data,
    recent_events,
    record_event,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "fireshield.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_creation_and_indexes(self):
        created = initialize_database(self.path)
        self.assertEqual(created, self.path)
        self.assertTrue(self.path.exists())
        with closing(sqlite3.connect(self.path)) as connection:
            indexes = {row[1] for row in connection.execute("PRAGMA index_list(events)")}
        self.assertIn("idx_events_category_time", indexes)
        self.assertIn("idx_events_zone_time", indexes)

    def test_insert_and_retrieve_all_six_categories(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for category in EVENT_CATEGORIES:
            self.assertTrue(record_event(
                category,
                timestamp=timestamp,
                zone_id="Zone ' OR 1=1 --",
                details={"value": 7, "category_detail": category},
                event_key=f"test:{category}",
                path=self.path,
            ))
        events = recent_events(path=self.path, limit=20)
        self.assertEqual({event["category"] for event in events}, set(EVENT_CATEGORIES))
        self.assertEqual(len(events), 6)
        self.assertTrue(all(event["zone"] == "Zone ' OR 1=1 --" for event in events))

    def test_duplicate_event_key_is_ignored(self):
        first = record_event("sensor_reading", zone_id="A", details={"v": 1}, event_key="stable", path=self.path)
        second = record_event("sensor_reading", zone_id="A", details={"v": 1}, event_key="stable", path=self.path)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(recent_events("sensor_reading", path=self.path)), 1)

    def test_records_persist_across_new_connections(self):
        record_event(
            "camera_detection", timestamp="2026-01-01T00:00:00+00:00",
            zone_id="Electrical Room", details={"detection_class": "Smoke", "confidence": 0.88},
            event_key="camera:one", path=self.path,
        )
        # A second call opens a fresh SQLite connection, as after an app restart.
        loaded = recent_events("camera_detection", path=self.path)
        self.assertEqual(loaded[0]["detection_class"], "Smoke")
        self.assertEqual(loaded[0]["confidence"], 0.88)

    def test_session_history_mapping_loads_sensor_and_camera_contracts(self):
        record_event(
            "sensor_reading", zone_id="A", timestamp="2026-01-01T00:00:00+00:00",
            details={"sensor": "temperature", "value": 25.5}, event_key="sensor:one", path=self.path,
        )
        record_event(
            "camera_detection", zone_id="A", timestamp="2026-01-01T00:00:01+00:00",
            details={"detection_class": "Fire", "confidence": 0.91}, event_key="camera:two", path=self.path,
        )
        restored = load_recent_session_data(path=self.path)
        self.assertEqual(restored["sensor_history"][0]["sensor"], "temperature")
        self.assertEqual(restored["camera_detection_history"][0]["detection_class"], "Fire")


if __name__ == "__main__":
    unittest.main()
