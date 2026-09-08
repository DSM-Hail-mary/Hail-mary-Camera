"""Edge orchestration (M1-detection -> M2 -> M3).

WindowAccumulator is the pure, testable piece: it decides when a 1-minute
window is done and turns the frames collected during it into one M2 record
via aggregator.aggregate_window(). run() wires this to the real camera, the
real YOLOv8n model, the real SQLite buffer and the real HTTP uplink -- that
part is exercised manually (real camera/model/network), same as
capture.py/preview.py's main().
"""

import argparse
import time
from datetime import datetime, timezone

from Hail_Mary.edge import capture as capture_module
from Hail_Mary.edge.aggregator import aggregate_window
from Hail_Mary.edge.buffer import LocalBuffer
from Hail_Mary.edge.calibrate import load_polygon
from Hail_Mary.edge.capture import stream_frames
from Hail_Mary.edge.uplink import Uplink
from Hail_Mary.vision.detect import DEFAULT_MIN_CONF, boxes_from_result, extract_person_detections, load_model

DEFAULT_ZONE_ID = "hall_main"
DEFAULT_ZONE_POLYGON = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:8000/api/v1/occupancy"
DEFAULT_DB_PATH = "occupancy.db"


def _iso(epoch_seconds):
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_capture_args(backend="opencv", camera_source=0, pipeline="jetson_csi",
                        pipeline_str=None, width=1280, height=720, fps=30):
    """Same shape capture.open_capture() expects -- reused here instead of
    re-implementing the opencv/gstreamer backend switch."""
    return argparse.Namespace(
        backend=backend, source=camera_source, pipeline=pipeline,
        pipeline_str=pipeline_str, width=width, height=height, fps=fps,
    )


def resolve_zone(zone_id, zone_polygon, zone_file):
    if zone_file is None:
        return zone_id, zone_polygon
    return load_polygon(zone_file)


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
    backend="opencv",
    camera_source=0,
    pipeline="jetson_csi",
    pipeline_str=None,
    width=1280,
    height=720,
    fps=30,
    zone_id=DEFAULT_ZONE_ID,
    zone_polygon=DEFAULT_ZONE_POLYGON,
    zone_file=None,
    endpoint_url=DEFAULT_ENDPOINT_URL,
    db_path=DEFAULT_DB_PATH,
    window_seconds=60,
    upload_interval_seconds=60,
    min_conf=DEFAULT_MIN_CONF,
):
    zone_id, zone_polygon = resolve_zone(zone_id, zone_polygon, zone_file)
    model = load_model("yolov8n.pt")
    cap = capture_module.open_capture(build_capture_args(
        backend=backend, camera_source=camera_source, pipeline=pipeline,
        pipeline_str=pipeline_str, width=width, height=height, fps=fps,
    ))
    if not cap.isOpened():
        raise SystemExit(f"Failed to open capture (backend={backend})")

    buf = LocalBuffer(db_path)
    uplink = Uplink(endpoint_url)
    window = WindowAccumulator(zone_id, zone_polygon, window_seconds)
    last_upload = time.time()

    try:
        for frame in stream_frames(cap):
            now = time.time()
            result = model.track(frame, persist=True, verbose=False, classes=[0])[0]
            boxes = boxes_from_result(result)
            detections = extract_person_detections(now, boxes, min_conf=min_conf)["detections"]
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


def _parse_args():  # pragma: no cover -- thin argparse wiring, exercised manually
    parser = argparse.ArgumentParser(description="Hail-Mary edge pipeline (capture -> detect -> M2 -> M3)")
    parser.add_argument("--backend", choices=["opencv", "gstreamer"], default="opencv")
    parser.add_argument("--source", type=int, default=0, help="camera index for opencv backend")
    parser.add_argument("--pipeline", choices=list(capture_module.PIPELINES), default="jetson_csi")
    parser.add_argument("--pipeline-str", default=None, help="override with a raw GStreamer pipeline")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--zone-id", default=DEFAULT_ZONE_ID)
    parser.add_argument("--zone-file", default=None, help="JSON polygon from calibrate.py, overrides --zone-id/defaults")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--upload-interval-seconds", type=int, default=60)
    parser.add_argument("--min-conf", type=float, default=DEFAULT_MIN_CONF)
    return parser.parse_args()


if __name__ == "__main__":  # pragma: no cover
    _args = _parse_args()
    run(
        backend=_args.backend, camera_source=_args.source, pipeline=_args.pipeline,
        pipeline_str=_args.pipeline_str, width=_args.width, height=_args.height, fps=_args.fps,
        zone_id=_args.zone_id, zone_file=_args.zone_file, endpoint_url=_args.endpoint, db_path=_args.db_path,
        window_seconds=_args.window_seconds, upload_interval_seconds=_args.upload_interval_seconds,
        min_conf=_args.min_conf,
    )
