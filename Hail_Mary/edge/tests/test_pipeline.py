from Hail_Mary.edge.pipeline import WindowAccumulator

SQUARE_ZONE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_not_ready_before_window_elapses():
    window = WindowAccumulator("hall_main", SQUARE_ZONE, window_seconds=60)

    window.add_frame(frame_ts=1000.0, detections=[], now=1000.0)

    assert window.ready(now=1030.0) is False


def test_ready_once_window_seconds_elapsed():
    window = WindowAccumulator("hall_main", SQUARE_ZONE, window_seconds=60)

    window.add_frame(frame_ts=1000.0, detections=[], now=1000.0)

    assert window.ready(now=1060.0) is True


def test_close_aggregates_the_last_frame_and_resets():
    window = WindowAccumulator("hall_main", SQUARE_ZONE, window_seconds=60)

    window.add_frame(
        frame_ts=1000.0,
        detections=[{"track_id": 1, "bbox": [10, 10, 30, 30]}],
        now=1000.0,
    )
    window.add_frame(
        frame_ts=1059.0,
        detections=[
            {"track_id": 1, "bbox": [10, 10, 30, 30]},
            {"track_id": 2, "bbox": [40, 40, 60, 60]},
        ],
        now=1059.0,
    )

    record = window.close(now=1060.0)

    assert record["zone_id"] == "hall_main"
    assert record["count"] == 2
    assert record["window_start"] == "1970-01-01T00:16:40Z"
    assert record["window_end"] == "1970-01-01T00:17:40Z"

    # closing resets the accumulator for the next window
    assert window.ready(now=1060.1) is False


def test_close_with_no_frames_returns_zero_count():
    window = WindowAccumulator("hall_main", SQUARE_ZONE, window_seconds=60)

    record = window.close(now=1060.0)

    assert record["count"] == 0
