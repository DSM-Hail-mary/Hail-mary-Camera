"""Last-seen-image transition detection + safe local storage.

Pure logic: watches each zone's people count over time and flags the exact
frame where a zone goes from occupied to empty (count > 0 -> count == 0).
That flagged frame is the one pipeline.py saves/uploads as the zone's
"last seen" image (Server API contract: POST /api/v1/last-seen/{zone_id}).
save_last_seen_locally() is the local-disk half of that; last_seen_uplink.py
has the upload side and reuses is_valid_zone_id() from here.
"""

from pathlib import Path


class LastSeenTracker:
    def __init__(self) -> None:
        self._last_counts: dict[str, int] = {}

    def update(self, zone_id: str, count: int, now: float) -> bool:
        previous_count = self._last_counts.get(zone_id)
        self._last_counts[zone_id] = count
        return previous_count is not None and previous_count > 0 and count == 0


def is_valid_zone_id(zone_id: str) -> bool:
    """Reject zone_ids that could escape last_seen_dir when used as a
    filename, or break a URL path segment when used in an upload URL
    (path traversal via "..", "/", or "\\"). zone_id comes from --zone-id
    or a zone.json produced by calibrate.py, neither of which validates it
    today -- mirrors the server's api/last_seen.py is_valid_zone_id()."""
    if not zone_id:
        return False
    return not any(token in zone_id for token in ("..", "/", "\\"))


def save_last_seen_locally(last_seen_dir: str | Path, zone_id: str, image_bytes: bytes) -> Path | None:
    """Write the last-seen JPEG for zone_id under last_seen_dir. Returns the
    written path, or None (logged, never raised) if zone_id is invalid or
    the write fails -- one zone's bad zone_id or a transient disk error must
    not crash the capture loop for every other zone."""
    if not is_valid_zone_id(zone_id):
        print(f"last-seen local write skipped: invalid zone_id={zone_id!r}", flush=True)
        return None

    path = Path(last_seen_dir) / f"{zone_id}.jpg"
    try:
        path.write_bytes(image_bytes)
    except OSError as exc:
        print(f"last-seen local write failed: zone={zone_id} error={exc}", flush=True)
        return None
    return path
