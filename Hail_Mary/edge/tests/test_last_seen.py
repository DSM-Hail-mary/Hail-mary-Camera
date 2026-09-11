from Hail_Mary.edge.last_seen import LastSeenTracker, is_valid_zone_id, save_last_seen_locally


def test_first_update_with_zero_count_is_not_a_transition():
    tracker = LastSeenTracker()

    assert tracker.update("hall_main", 0, now=1000.0) is False


def test_first_update_with_positive_count_is_not_a_transition():
    tracker = LastSeenTracker()

    assert tracker.update("hall_main", 3, now=1000.0) is False


def test_transition_from_positive_to_zero_returns_true():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)

    assert tracker.update("hall_main", 0, now=1001.0) is True


def test_staying_at_zero_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    tracker.update("hall_main", 0, now=1001.0)

    assert tracker.update("hall_main", 0, now=1002.0) is False


def test_staying_positive_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)

    assert tracker.update("hall_main", 5, now=1001.0) is False


def test_zero_to_positive_is_not_a_transition():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 0, now=1000.0)

    assert tracker.update("hall_main", 4, now=1001.0) is False


def test_zones_are_tracked_independently():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    tracker.update("entrance", 1, now=1000.0)

    assert tracker.update("hall_main", 0, now=1001.0) is True
    assert tracker.update("entrance", 3, now=1001.0) is False
    assert tracker.update("entrance", 0, now=1002.0) is True


def test_re_transition_after_refill_returns_true_again():
    tracker = LastSeenTracker()
    tracker.update("hall_main", 2, now=1000.0)
    assert tracker.update("hall_main", 0, now=1001.0) is True

    tracker.update("hall_main", 1, now=1002.0)

    assert tracker.update("hall_main", 0, now=1003.0) is True


# ---- is_valid_zone_id / save_last_seen_locally ----
# Code review 2026-09-11: pipeline.py wrote `last_seen_dir / f"{zone_id}.jpg"`
# with zone_id taken straight from --zone-id/zone.json, unsanitized -- a
# zone_id containing "..", "/", or "\\" could escape last_seen_dir, and the
# write itself had no error handling (an OSError would kill the whole
# capture loop). Mirrors the server's last_seen.py is_valid_zone_id().

def test_is_valid_zone_id_rejects_path_traversal_tokens():
    assert is_valid_zone_id("hall_main") is True
    assert is_valid_zone_id("../secret") is False
    assert is_valid_zone_id("a/b") is False
    assert is_valid_zone_id("a\\b") is False
    assert is_valid_zone_id("") is False


def test_save_last_seen_locally_writes_the_jpeg(tmp_path):
    path = save_last_seen_locally(tmp_path, "hall_main", b"fake-jpeg-bytes")

    assert path == tmp_path / "hall_main.jpg"
    assert path.read_bytes() == b"fake-jpeg-bytes"


def test_save_last_seen_locally_rejects_invalid_zone_id_without_writing(tmp_path):
    path = save_last_seen_locally(tmp_path, "../escape", b"x")

    assert path is None
    assert list(tmp_path.iterdir()) == []


def test_save_last_seen_locally_returns_none_on_write_failure_instead_of_raising(tmp_path):
    # last_seen_dir itself doesn't exist and isn't creatable (its parent is a
    # file, not a directory) -- write_bytes() raises OSError/NotADirectoryError.
    blocked_parent = tmp_path / "not_a_dir"
    blocked_parent.write_text("i am a file")
    unwritable_dir = blocked_parent / "last_seen"

    path = save_last_seen_locally(unwritable_dir, "hall_main", b"x")

    assert path is None
