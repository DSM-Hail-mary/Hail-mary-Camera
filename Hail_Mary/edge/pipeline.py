"""Edge orchestration (M1-detection -> M2 -> M3).

WindowAccumulator is the pure, testable piece: it decides when a 1-minute
window is done and turns the frames collected during it into one M2 record
via aggregator.aggregate_window(). run() wires this to the real camera, the
real YOLOv8n model, the real SQLite buffer and the real HTTP uplink -- that
part is exercised manually (real camera/model/network), same as
capture.py/preview.py's main().
"""

import time
from datetime import datetime, timezone

from Hail_Mary.edge.aggregator import aggregate_window
from Hail_Mary.edge.buffer import LocalBuffer
from Hail_Mary.edge.capture import open_source, stream_frames
from Hail_Mary.edge.uplink import Uplink
from Hail_Mary.vision.detect import boxes_from_result, extract_person_detections, load_model

DEFAULT_ZONE_ID = "hall_main"
DEFAULT_ZONE_POLYGON = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:8000/api/v1/occupancy"
DEFAULT_DB_PATH = "occupancy.db"


def _iso(epoch_seconds):
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WindowAccumulator:
    def __init__(self, zone_id, zone_polygon, window_seconds=60):
        self.zone_id = zone_id
        self.zone_polygon = zone_polygon
        self.window_seconds = window_seconds
        self._frames = []
        self._window_start = None

    def add_frame(self, frame_ts, detections, now):
        if self._window_start is None:
            self._window_start = now
        self._frames.append({"frame_ts": frame_ts, "detections": detections})

    def ready(self, now):
        return self._window_start is not None and (now - self._window_start) >= self.window_seconds

    def close(self, now):
        window_start = self._window_start if self._window_start is not None else now
        record = aggregate_window(
            self._frames,
            zone_id=self.zone_id,
            zone_polygon=self.zone_polygon,
            window_start=_iso(window_start),
            window_end=_iso(now),
        )
        self._frames = []
        self._window_start = None
        return record


def run(  # pragma: no cover -- live loop needs real camera/model/network
    camera_source=0,
    zone_id=DEFAULT_ZONE_ID,
    zone_polygon=DEFAULT_ZONE_POLYGON,
    endpoint_url=DEFAULT_ENDPOINT_URL,
    db_path=DEFAULT_DB_PATH,
    window_seconds=60,
    upload_interval_seconds=60,
):
    model = load_model("yolov8n.pt")
    cap = open_source(backend="opencv", source=camera_source, width=1280, height=720)
    if not cap.isOpened():
        raise SystemExit("Failed to open camera")

    buf = LocalBuffer(db_path)
    uplink = Uplink(endpoint_url)
    window = WindowAccumulator(zone_id, zone_polygon, window_seconds)
    last_upload = time.time()

    try:
        for frame in stream_frames(cap):
            now = time.time()
            result = model.track(frame, persist=True, verbose=False, classes=[0])[0]
            boxes = boxes_from_result(result)
            detections = extract_person_detections(now, boxes)["detections"]
            window.add_frame(now, detections, now)

            if window.ready(now):
                record = window.close(now)
                buf.insert(record)
                print(f"window closed: zone={record['zone_id']} count={record['count']}", flush=True)

            if now - last_upload >= upload_interval_seconds:
                pending = buf.fetch_pending(limit=100)
                if pending:
                    result = uplink.upload_batch(pending)
                    if result.success:
                        buf.mark_uploaded(result.uploaded_ids)
                        print(f"uploaded {len(result.uploaded_ids)} records", flush=True)
                    else:
                        print("upload failed, will retry next cycle", flush=True)
                last_upload = now
    finally:
        cap.release()


if __name__ == "__main__":  # pragma: no cover
    run()
