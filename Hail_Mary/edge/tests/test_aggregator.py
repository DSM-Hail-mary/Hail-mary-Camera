from Hail_Mary.edge import aggregator

SQUARE_ZONE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def _frame(ts, detections):
    return {"frame_ts": ts, "detections": detections}


def test_aggregate_window_counts_people_in_last_frame_snapshot():
    frames = [
        _frame("2026-09-08T09:00:00Z", [{"track_id": 1, "bbox": [10, 10, 30, 30]}]),
        _frame("2026-09-08T09:00:30Z", [
            {"track_id": 1, "bbox": [10, 10, 30, 30]},
            {"track_id": 2, "bbox": [40, 40, 60, 60]},
        ]),
    ]

    record = aggregator.aggregate_window(
        frames, zone_id="hall_main", zone_polygon=SQUARE_ZONE,
        window_start="2026-09-08T09:00:00Z", window_end="2026-09-08T09:01:00Z",
    )

    assert record == {
        "zone_id": "hall_main",
        "window_start": "2026-09-08T09:00:00Z",
        "window_end": "2026-09-08T09:01:00Z",
        "count": 2,
    }


def test_aggregate_window_ignores_detections_outside_zone():
    frames = [
        _frame("2026-09-08T09:00:00Z", [
            {"track_id": 1, "bbox": [10, 10, 30, 30]},    # inside
            {"track_id": 2, "bbox": [140, 10, 160, 30]},  # outside
        ]),
    ]

    record = aggregator.aggregate_window(
        frames, zone_id="hall_main", zone_polygon=SQUARE_ZONE,
        window_start="2026-09-08T09:00:00Z", window_end="2026-09-08T09:01:00Z",
    )

    assert record["count"] == 1


def test_aggregate_window_uses_only_the_last_frame_not_a_cumulative_total():
    frames = [
        _frame("2026-09-08T09:00:00Z", [
            {"track_id": 1, "bbox": [10, 10, 30, 30]},
            {"track_id": 2, "bbox": [40, 40, 60, 60]},
        ]),
        _frame("2026-09-08T09:00:59Z", [
            {"track_id": 1, "bbox": [10, 10, 30, 30]},
        ]),
    ]

    record = aggregator.aggregate_window(
        frames, zone_id="hall_main", zone_polygon=SQUARE_ZONE,
        window_start="2026-09-08T09:00:00Z", window_end="2026-09-08T09:01:00Z",
    )

    assert record["count"] == 1


def test_aggregate_window_returns_zero_count_for_empty_frames():
    record = aggregator.aggregate_window(
        [], zone_id="hall_main", zone_polygon=SQUARE_ZONE,
        window_start="2026-09-08T09:00:00Z", window_end="2026-09-08T09:01:00Z",
    )

    assert record["count"] == 0
