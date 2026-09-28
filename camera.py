"""
camera.py — USB 카메라 프레임 캡처 (Jetson 엣지)

역할:
  - /dev/video0 (OV2311 계열 글로벌셔터 UVC 캠)에서 MJPG 1280x720 30fps 캡처
  - 캡처를 별도 스레드(생산자)로 돌려, 추론 스레드(소비자)와 분리
  - 바운드 큐 + 드롭 카운터로 "프레임 드롭 0%" KPI를 측정 가능하게 함
  - 수동 노출(≈1/1000s)을 장치 오픈 시마다 재설정 (재오픈 리셋 방지)

이 모듈은 순수 캡처만 담당한다. 추론(TensorRT)은 trt_infer.py, 조립은 pipeline.py.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Full, Empty
from typing import Optional

import cv2
import numpy as np


@dataclass
class CameraConfig:
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = "MJPG"            # OV2311 UVC에서 30fps 나오는 포맷
    queue_size: int = 8            # 소비자가 밀릴 때 버퍼링할 최대 프레임 수
    # v4l2 수동 노출 설정값 (STEP2에서 확인한 값). None이면 건드리지 않음
    manual_exposure: Optional[int] = 10        # ≈1/1000s
    auto_exposure_manual_val: int = 1          # 1 = Manual mode (드라이버 관례)


@dataclass
class CaptureStats:
    captured: int = 0              # 카메라에서 읽어낸 총 프레임
    delivered: int = 0             # 큐에 성공적으로 넣은 프레임
    dropped: int = 0               # 큐가 꽉 차서 버린 프레임 (소비자가 밀림)
    read_fail: int = 0             # cap.read() 실패 횟수
    started_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def fps(self) -> float:
        elapsed = time.time() - self.started_at
        return self.captured / elapsed if elapsed > 0 else 0.0

    def drop_rate(self) -> float:
        return self.dropped / self.captured if self.captured else 0.0


@dataclass
class Frame:
    seq: int                       # 캡처 순번 (드롭 추적용)
    ts: float                      # 캡처 시각 (time.time())
    image: np.ndarray              # BGR 프레임


class Camera:
    """스레드 기반 카메라 캡처. with 문 또는 start()/stop()으로 사용."""

    def __init__(self, cfg: CameraConfig = CameraConfig()):
        self.cfg = cfg
        self.stats = CaptureStats()
        self._cap: Optional[cv2.VideoCapture] = None
        self._queue: "Queue[Frame]" = Queue(maxsize=cfg.queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()

    # ---- 장치 오픈 / 설정 -------------------------------------------------
    def _apply_manual_exposure(self) -> None:
        """v4l2-ctl로 수동 노출 재설정 (OpenCV 노출 제어는 드라이버마다 불안정)."""
        if self.cfg.manual_exposure is None:
            return
        cmds = [
            ["v4l2-ctl", "-d", self.cfg.device,
             f"--set-ctrl=auto_exposure={self.cfg.auto_exposure_manual_val}"],
            ["v4l2-ctl", "-d", self.cfg.device,
             f"--set-ctrl=exposure_time_absolute={self.cfg.manual_exposure}"],
        ]
        for c in cmds:
            try:
                subprocess.run(c, check=True, capture_output=True, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    FileNotFoundError) as e:
                # 컨트롤명이 다를 수 있음 → 경고만, 캡처는 계속
                print(f"[camera] 노출 설정 경고: {' '.join(c)} -> {e}")

    def _open(self) -> None:
        cap = cv2.VideoCapture(self.cfg.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"카메라 열기 실패: {self.cfg.device}")

        fourcc = cv2.VideoWriter_fourcc(*self.cfg.fourcc)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # 지연 최소화: 드라이버 버퍼 최소

        # 실제 적용값 확인 (요청과 다를 수 있음)
        aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        af = cap.get(cv2.CAP_PROP_FPS)
        print(f"[camera] open {self.cfg.device}: {aw}x{ah} @ {af:.0f}fps "
              f"(요청 {self.cfg.width}x{self.cfg.height}@{self.cfg.fps})")

        self._cap = cap
        self._apply_manual_exposure()

    # ---- 캡처 루프 (생산자 스레드) ----------------------------------------
    def _loop(self) -> None:
        seq = 0
        while self._running.is_set():
            ok, img = self._cap.read()
            if not ok:
                self.stats.read_fail += 1
                continue

            seq += 1
            with self.stats._lock:
                self.stats.captured += 1

            frame = Frame(seq=seq, ts=time.time(), image=img)
            try:
                self._queue.put_nowait(frame)
                with self.stats._lock:
                    self.stats.delivered += 1
            except Full:
                # 소비자(추론)가 밀림 → 가장 오래된 프레임을 버리고 최신을 넣음
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
                try:
                    self._queue.put_nowait(frame)
                except Full:
                    pass
                with self.stats._lock:
                    self.stats.dropped += 1

    # ---- 공개 API ---------------------------------------------------------
    def start(self) -> "Camera":
        self._open()
        self.stats.started_at = time.time()
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="camera-capture",
                                        daemon=True)
        self._thread.start()
        return self

    def read(self, timeout: float = 1.0) -> Optional[Frame]:
        """다음 프레임 반환. timeout 내 없으면 None."""
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        print(f"[camera] stopped. captured={self.stats.captured} "
              f"delivered={self.stats.delivered} dropped={self.stats.dropped} "
              f"({self.stats.drop_rate()*100:.2f}%) avg_fps={self.stats.fps():.1f}")

    def __enter__(self) -> "Camera":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


# --- 단독 실행: 캡처 검증 (프레임 수신 + fps + 드롭률 + 샘플 저장) ----------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="카메라 캡처 검증")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--seconds", type=float, default=10.0, help="검증 시간(초)")
    ap.add_argument("--save", default="capture_sample.jpg", help="마지막 프레임 저장 경로")
    args = ap.parse_args()

    cfg = CameraConfig(device=args.device)
    last: Optional[Frame] = None
    processed = 0

    with Camera(cfg) as cam:
        t_end = time.time() + args.seconds
        while time.time() < t_end:
            frame = cam.read(timeout=1.0)
            if frame is None:
                print("[main] 프레임 타임아웃")
                continue
            last = frame
            processed += 1
            # 여기가 나중에 추론(trt_infer)이 들어갈 자리
            if processed % 30 == 0:
                print(f"[main] processed={processed} "
                      f"seq={frame.seq} qsize~={cam._queue.qsize()} "
                      f"fps={cam.stats.fps():.1f} drop={cam.stats.drop_rate()*100:.2f}%")

    if last is not None:
        cv2.imwrite(args.save, last.image)
        print(f"[main] 마지막 프레임 저장: {args.save} "
              f"shape={last.image.shape}, 소비 프레임={processed}")
    else:
        print("[main] 수신된 프레임 없음 — 카메라/권한 확인 필요")
