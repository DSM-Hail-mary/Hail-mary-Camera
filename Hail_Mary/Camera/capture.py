"""Hail-Mary edge camera capture.

Today (Windows laptop, no GStreamer-enabled OpenCV build): run with the default
`opencv` backend against the laptop webcam to validate the capture/FPS loop.

Tomorrow (Jetson, GStreamer available): switch to `--backend gstreamer` with one
of the pipeline templates below. Adjust sensor-id/device/resolution to match the
actual camera once it's connected.
"""
import argparse
import time
from collections.abc import Iterator
from typing import cast

import cv2
import numpy as np

PIPELINE_JETSON_CSI = (
    "nvarguscamerasrc sensor-id=0 ! "
    # placeholder resolution -- adjust to match the actual camera once connected
    "video/x-raw(memory:NVMM), width=640, height=384, framerate=30/1, format=NV12 ! "
    "nvvidconv flip-method=0 ! "
    "video/x-raw, format=BGRx ! "
    "videoconvert ! "
    "video/x-raw, format=BGR ! appsink drop=1"
)

PIPELINE_JETSON_USB = (
    "v4l2src device=/dev/video0 ! "
    # placeholder resolution -- adjust to match the actual camera once connected
    "video/x-raw, width=640, height=384, framerate=30/1 ! "
    "videoconvert ! "
    "video/x-raw, format=BGR ! appsink drop=1"
)

PIPELINES = {
    "jetson_csi": PIPELINE_JETSON_CSI,
    "jetson_usb": PIPELINE_JETSON_USB,
}

WINDOW_NAME = "Hail-Mary capture preview"


def open_source(
    backend: str,
    source: int | str = 0,
    pipeline_str: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
) -> cv2.VideoCapture:
    """Activate a camera/video source. `source` may be a camera index (int) or a
    file/device path (str) — both are valid cv2.VideoCapture sources, which lets
    tests exercise this against a real video file instead of physical hardware."""
    if backend == "gstreamer":
        # gstreamer callers always supply pipeline_str (see open_capture/PIPELINES);
        # cast avoids a runtime check that would change behavior for the None case.
        return cv2.VideoCapture(cast(str, pipeline_str), cv2.CAP_GSTREAMER)

    cap = cv2.VideoCapture(source)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps:
        cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def stream_frames(cap: cv2.VideoCapture) -> Iterator[np.ndarray]:
    """Yield frames from an opened cv2.VideoCapture until the source is exhausted
    or a read fails. This is the reusable streaming interface other edge modules
    (e.g. zone aggregation) import instead of re-implementing the read loop."""
    while True:
        ok, frame = cap.read()
        if not ok:
            return
        yield frame


def open_capture(args: argparse.Namespace) -> cv2.VideoCapture:
    if args.backend == "gstreamer":
        pipeline = args.pipeline_str or PIPELINES[args.pipeline]
        return open_source("gstreamer", pipeline_str=pipeline)
    return open_source("opencv", source=args.source, width=args.width, height=args.height, fps=args.fps)


def main() -> None:  # pragma: no cover -- interactive CLI loop, needs real camera/display; verified manually via skill-capture-check
    parser = argparse.ArgumentParser(description="Hail-Mary edge camera capture preview")
    parser.add_argument("--backend", choices=["opencv", "gstreamer"], default="opencv")
    parser.add_argument("--source", type=int, default=0, help="camera index for opencv backend")
    parser.add_argument("--pipeline", choices=list(PIPELINES), default="jetson_csi")
    parser.add_argument("--pipeline-str", default=None, help="override with a raw GStreamer pipeline")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=384)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--no-preview", action="store_true", help="skip cv2.imshow, just print FPS")
    parser.add_argument("--duration", type=float, default=0, help="auto-exit after N seconds (0 = run until 'q')")
    args = parser.parse_args()

    cap = open_capture(args)
    if not cap.isOpened():
        raise SystemExit(f"Failed to open capture (backend={args.backend})")

    start_time = time.time()
    frame_count = 0
    fps_window_start = start_time
    measured_fps = 0.0

    try:
        for frame in stream_frames(cap):
            frame_count += 1
            elapsed = time.time() - fps_window_start
            if elapsed >= 1.0:
                measured_fps = frame_count / elapsed
                frame_count = 0
                fps_window_start = time.time()
                print(f"fps={measured_fps:.1f} frame_size={frame.shape[1]}x{frame.shape[0]}")

            if not args.no_preview:
                cv2.putText(frame, f"FPS: {measured_fps:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.imshow(WINDOW_NAME, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break

            if args.duration and (time.time() - start_time) > args.duration:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":  # pragma: no cover
    main()
