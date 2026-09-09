"""Zone window aggregation (M2).

Reduces a window's worth of per-frame detections (from M1) down to a single
occupancy snapshot for a zone. Count = people in the zone in the last frame of
the window ("how many are here right now", not a cumulative visitor count).
"""

from collections.abc import Sequence
from typing import Any

from Hail_Mary.edge.zones import Point, count_people_in_zone


def aggregate_window(
    frames: Sequence[dict[str, Any]],
    zone_id: str,
    zone_polygon: Sequence[Point],
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    if not frames:
        count = 0
    else:
        last_frame = max(frames, key=lambda frame: frame["frame_ts"])
        count = count_people_in_zone(last_frame["detections"], zone_polygon)

    return {
        "zone_id": zone_id,
        "window_start": window_start,
        "window_end": window_end,
        "count": count,
    }
