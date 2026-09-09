"""Last-seen-image transition detection.

Pure logic: watches each zone's people count over time and flags the exact
frame where a zone goes from occupied to empty (count > 0 -> count == 0).
That flagged frame is the one pipeline.py saves/uploads as the zone's
"last seen" image (Server API contract: POST /api/v1/last-seen/{zone_id}).
No image data or I/O here -- see last_seen_uplink.py for the upload side.
"""


class LastSeenTracker:
    def __init__(self) -> None:
        self._last_counts: dict[str, int] = {}

    def update(self, zone_id: str, count: int, now: float) -> bool:
        previous_count = self._last_counts.get(zone_id)
        self._last_counts[zone_id] = count
        return previous_count is not None and previous_count > 0 and count == 0
