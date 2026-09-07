"""Zone window aggregation (M2).

Reduces a window's worth of per-frame detections (from M1) down to a single
occupancy snapshot for a zone. Count = people in the zone in the last frame of
the window ("how many are here right now", not a cumulative visitor count).
"""

from Hail_Mary.edge.zones import count_people_in_zone


def aggregate_window(frames, zone_id, zone_polygon, window_start, window_end):
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
