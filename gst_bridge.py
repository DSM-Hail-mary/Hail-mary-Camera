"""
gst_bridge.py — OpenCV 프레임을 C++ GStreamer 파이프라인(HailMary)으로 전송

C++ 쪽 CameraElement(tcpserversrc → rawvideoparse)가 127.0.0.1:5000에서 대기하고,
이 모듈이 BGR 프레임을 raw 바이트 그대로 TCP로 흘려보낸다.
  - 포맷 계약: BGR, 1280x720, 30fps (C++ OPENCV_WIDTH/HEIGHT/FPS와 반드시 일치)
  - 크기가 다르면 resize해서 맞춤 (프레임 경계가 어긋나면 C++ 쪽 영상이 깨짐)
  - 연결 실패/끊김 시 retry_sec 간격으로 재연결, 그동안 send()는 False 반환
"""
from __future__ import annotations

import socket
import time
from typing import Optional

import cv2
import numpy as np


class GstBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 5000,
                 width: int = 1280, height: int = 720,
                 retry_sec: float = 1.0, send_timeout: float = 1.0):
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.retry_sec = retry_sec
        self.send_timeout = send_timeout
        self.sent = 0
        self._sock: Optional[socket.socket] = None
        self._last_try = 0.0

    def _connect(self) -> bool:
        now = time.time()
        if now - self._last_try < self.retry_sec:
            return False
        self._last_try = now
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.retry_sec)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(self.send_timeout)
            self._sock = sock
            print(f"[gst_bridge] connected {self.host}:{self.port}")
            return True
        except OSError:
            return False

    def send(self, image: np.ndarray) -> bool:
        """BGR 프레임 1장 전송. 연결이 없거나 실패하면 False."""
        if self._sock is None and not self._connect():
            return False

        if image.shape[1] != self.width or image.shape[0] != self.height:
            image = cv2.resize(image, (self.width, self.height))
        if not image.flags["C_CONTIGUOUS"]:
            image = np.ascontiguousarray(image)

        try:
            self._sock.sendall(memoryview(image))
            self.sent += 1
            return True
        except OSError as e:
            # 프레임 중간에서 끊기면 스트림 경계가 깨지므로 연결을 버리고 재연결
            print(f"[gst_bridge] send 실패, 재연결 대기: {e}")
            self.close()
            return False

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# --- 단독 실행: 카메라 → C++ 파이프라인 전송 검증 ------------------------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="OpenCV → GStreamer 전송 검증")
    ap.add_argument("--device", default="/dev/video0", help="카메라 장치 (Windows는 0)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()

    device = int(args.device) if args.device.isdigit() else args.device
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        raise SystemExit(f"카메라 열기 실패: {args.device}")

    bridge = GstBridge(args.host, args.port)
    t_end = time.time() + args.seconds
    while time.time() < t_end:
        ok, img = cap.read()
        if not ok:
            continue
        bridge.send(img)

    print(f"[gst_bridge] 종료. sent={bridge.sent}")
    bridge.close()
    cap.release()
