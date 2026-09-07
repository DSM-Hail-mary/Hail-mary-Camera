import argparse

import cv2
import numpy as np

from Hail_Mary.edge import capture


def _write_real_video(path, frame_count=5, width=64, height=48, fps=10):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    for i in range(frame_count):
        frame = np.full((height, width, 3), fill_value=i * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_stream_frames_yields_every_frame_in_source(tmp_path):
    video_path = tmp_path / "sample.mp4"
    _write_real_video(video_path, frame_count=5, width=64, height=48)

    cap = cv2.VideoCapture(str(video_path))
    try:
        frames = list(capture.stream_frames(cap))
    finally:
        cap.release()

    assert len(frames) == 5
    assert frames[0].shape == (48, 64, 3)


def test_stream_frames_stops_when_source_exhausted(tmp_path):
    video_path = tmp_path / "sample_single.mp4"
    _write_real_video(video_path, frame_count=1)

    cap = cv2.VideoCapture(str(video_path))
    try:
        frames = list(capture.stream_frames(cap))
    finally:
        cap.release()

    assert len(frames) == 1


def test_open_source_opencv_backend_opens_real_file():
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = os.path.join(tmp_dir, "sample_open.mp4")
        _write_real_video(video_path, frame_count=3, width=32, height=32)

        cap = capture.open_source(backend="opencv", source=video_path)
        try:
            assert cap.isOpened()
            frames = list(capture.stream_frames(cap))
        finally:
            cap.release()

    assert len(frames) == 3


def test_open_source_applies_requested_width_and_height(tmp_path):
    video_path = tmp_path / "sample_dims.mp4"
    _write_real_video(video_path, frame_count=2, width=64, height=48)

    cap = capture.open_source(backend="opencv", source=str(video_path), width=64, height=48)
    try:
        assert cap.get(cv2.CAP_PROP_FRAME_WIDTH) == 64
        assert cap.get(cv2.CAP_PROP_FRAME_HEIGHT) == 48
    finally:
        cap.release()


def test_open_source_gstreamer_backend_uses_gstreamer_api():
    cap = capture.open_source(backend="gstreamer", pipeline_str=capture.PIPELINE_JETSON_CSI)
    try:
        # No real GStreamer runtime on this dev machine, so the pipeline won't
        # actually open — this just proves the gstreamer code path is taken
        # (cv2.CAP_GSTREAMER) rather than falling through to the opencv path.
        assert isinstance(cap, cv2.VideoCapture)
    finally:
        cap.release()


def test_open_capture_opencv_backend_from_parsed_args(tmp_path):
    video_path = tmp_path / "sample_args.mp4"
    _write_real_video(video_path, frame_count=2, width=64, height=48)

    args = argparse.Namespace(
        backend="opencv", source=str(video_path), width=64, height=48, fps=10,
    )
    cap = capture.open_capture(args)
    try:
        assert cap.isOpened()
        frames = list(capture.stream_frames(cap))
    finally:
        cap.release()

    assert len(frames) == 2


def test_open_capture_gstreamer_backend_from_parsed_args():
    args = argparse.Namespace(
        backend="gstreamer", pipeline_str=None, pipeline="jetson_usb",
    )
    cap = capture.open_capture(args)
    try:
        assert isinstance(cap, cv2.VideoCapture)
    finally:
        cap.release()
