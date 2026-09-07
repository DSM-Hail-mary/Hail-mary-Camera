from Hail_Mary.edge.buffer import LocalBuffer


def _sample_record(count=3):
    return {
        "zone_id": "hall_main",
        "window_start": "2026-09-08T09:00:00Z",
        "window_end": "2026-09-08T09:01:00Z",
        "count": count,
    }


def test_insert_then_fetch_pending_returns_the_record(tmp_path):
    buf = LocalBuffer(tmp_path / "occupancy.db")

    buf.insert(_sample_record(count=3))
    pending = buf.fetch_pending(limit=10)

    assert len(pending) == 1
    assert pending[0]["zone_id"] == "hall_main"
    assert pending[0]["count"] == 3
    assert "id" in pending[0]


def test_fetch_pending_respects_limit(tmp_path):
    buf = LocalBuffer(tmp_path / "occupancy.db")

    for i in range(5):
        buf.insert(_sample_record(count=i))

    pending = buf.fetch_pending(limit=2)

    assert len(pending) == 2


def test_mark_uploaded_removes_records_from_pending(tmp_path):
    buf = LocalBuffer(tmp_path / "occupancy.db")

    buf.insert(_sample_record(count=1))
    buf.insert(_sample_record(count=2))
    pending = buf.fetch_pending(limit=10)
    first_id = pending[0]["id"]

    buf.mark_uploaded([first_id])
    remaining = buf.fetch_pending(limit=10)

    assert len(remaining) == 1
    assert remaining[0]["count"] == 2


def test_purge_older_than_removes_only_old_uploaded_rows(tmp_path):
    buf = LocalBuffer(tmp_path / "occupancy.db")

    buf.insert(_sample_record(count=1))
    pending = buf.fetch_pending(limit=10)
    buf.mark_uploaded([pending[0]["id"]])

    # created "now" -> purge_older_than(days=7) must not touch it
    buf.purge_older_than(days=7)
    remaining_after_recent_purge = buf.fetch_all()
    assert len(remaining_after_recent_purge) == 1

    # purge_older_than(days=0) treats "now" as the cutoff -> row is removed
    buf.purge_older_than(days=0)
    remaining_after_full_purge = buf.fetch_all()
    assert len(remaining_after_full_purge) == 0


def test_mark_uploaded_with_empty_ids_is_a_no_op(tmp_path):
    buf = LocalBuffer(tmp_path / "occupancy.db")
    buf.insert(_sample_record(count=1))

    buf.mark_uploaded([])

    assert len(buf.fetch_pending(limit=10)) == 1


def test_insert_survives_across_separate_buffer_instances(tmp_path):
    db_path = tmp_path / "occupancy.db"
    LocalBuffer(db_path).insert(_sample_record(count=7))

    reopened = LocalBuffer(db_path)
    pending = reopened.fetch_pending(limit=10)

    assert len(pending) == 1
    assert pending[0]["count"] == 7
