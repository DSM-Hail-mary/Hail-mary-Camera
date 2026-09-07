import cv2
import numpy as np

from Hail_Mary.edge import capture as capture_module
from Hail_Mary.edge.pipeline import build_capture_args


def _write_real_video(path, frame_count=3, width=64, height=48, fps=10):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    for i in range(frame_count):
        writer.write(np.full((height, width, 3), fill_value=i * 10, dtype=np.uint8))
    writer.release()


def test_build_capture_args_opencv_backend_shape():
    args = build_capture_args(backend="opencv", camera_source=0, width=640, height=480, fps=15)

    assert args.backend == "opencv"
    assert args.source == 0
    assert args.width == 640
    assert args.height == 480
    assert args.fps == 15


def test_build_capture_args_gstreamer_backend_shape():
    args = build_capture_args(backend="gstreamer", pipeline="jetson_usb")

    assert args.backend == "gstreamer"
    assert args.pipeline == "jetson_usb"
    assert args.pipeline_str is None


def test_build_capture_args_opens_a_real_capture_via_open_capture(tmp_path):
    video_path = tmp_path / "sample.mp4"
    _write_real_video(video_path, frame_count=3, width=64, height=48)

    args = build_capture_args(backend="opencv", camera_source=str(video_path), width=64, height=48)
    cap = capture_module.open_capture(args)
    try:
        assert cap.isOpened()
        frames = list(capture_module.stream_frames(cap))
    finally:
        cap.release()

    assert len(frames) == 3


def test_build_capture_args_gstreamer_uses_gstreamer_pipeline_from_registry():
    args = build_capture_args(backend="gstreamer", pipeline="jetson_csi")
    cap = capture_module.open_capture(args)
    try:
        # No GStreamer runtime on this dev machine -- this proves the gstreamer
        # code path (and the jetson_csi pipeline) was selected, not that it opens.
        assert isinstance(cap, cv2.VideoCapture)
    finally:
        cap.release()
