from runtime.streamcore.config import EventsConfig
from runtime.streamcore.events.event_db import COCO_CLASSES, EventDatabase


def test_object_counts_store_all_coco_classes_per_camera(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMCORE_DB", str(tmp_path / "counts.db"))
    database = EventDatabase(EventsConfig())
    try:
        database.register_count_camera("CAM001")
        database.record_object_seen("CAM001", "person", timestamp=1_800_000_000)
        database.record_object_seen("CAM001", "car", timestamp=1_800_000_000)
        database.flush_object_counts()

        result = database.query_object_counts(database._count_date(1_800_000_000))
        assert result["classes"] == list(COCO_CLASSES)
        assert result["totals"]["person"] == 1
        assert result["totals"]["car"] == 1
        assert result["cameras"][0]["camera_id"] == "CAM001"
        assert result["cameras"][0]["total"] == 2
        assert len(result["cameras"][0]["counts"]) == 80
    finally:
        database.close_all_connections()
