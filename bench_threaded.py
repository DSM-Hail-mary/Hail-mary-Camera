"""
bench_threaded.py — 스레드 캡처 벤치 (vs 순차 bench.py 비교용)

캡처를 별도 스레드에서 돌려(바운드 큐, drop-oldest) 추론과 분리한다.
측정:
  ① FPS            (추론 루프가 실제 처리하는 초당 프레임)
  ② E2E latency    (프레임 캡처 시점 → 추론 결과까지, glass-to-result)
  ③ Capture latency(캡처 스레드의 cap.read() 1회 시간)
  ④ Frame age      (프레임이 큐에서 소비될 때의 나이 = 큐 지연)

실행:  python bench_threaded.py --format YUYV --width 640 --height 480 --frames 100
"""
import argparse
import collections
import statistics
import subprocess
import threading
import time

import cv2
from ultralytics import YOLO


class Capturer(threading.Thread):
    def __init__(self, device, fmt, w, h, fps, qsize):
        super().__init__(daemon=True)
        self.device, self.fmt, self.w, self.h, self.fps = device, fmt, w, h, fps
        self.q = collections.deque(maxlen=qsize)
        self.lock = threading.Lock()
        self.evt = threading.Event()
        self._run = True
        self.cap_ms, self.captured, self.dropped = [], 0, 0

    def run(self):
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fmt))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.h)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        subprocess.run(["v4l2-ctl", "-d", self.device, "--set-ctrl=auto_exposure=3"],
                       stderr=subprocess.DEVNULL)
        while self._run:
            t0 = time.perf_counter()
            ok, img = cap.read()
            t1 = time.perf_counter()
            if not ok:
                continue
            self.cap_ms.append((t1 - t0) * 1000)
            self.captured += 1
            with self.lock:
                if len(self.q) == self.q.maxlen:
                    self.dropped += 1          # 꽉 차서 가장 오래된 프레임 버려짐
                self.q.append((t1, img))        # (캡처시각, 프레임)
            self.evt.set()
        cap.release()

    def get(self, timeout=3.0):
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            with self.lock:
                if self.q:
                    return self.q.popleft()     # FIFO(가장 오래된 것부터)
            self.evt.wait(0.005)
            self.evt.clear()
        return None

    def stop(self):
        self._run = False


def avg(a):
    return round(statistics.mean(a), 2) if a else 0.0


def main():
    ap = argparse.ArgumentParser(description="스레드 캡처 벤치")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/yolov8n_fp16.engine")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--format", default="YUYV", choices=["MJPG", "YUYV"])
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--qsize", type=int, default=4)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=15)
    a = ap.parse_args()

    model = YOLO(a.engine, task="detect")
    cap = Capturer(a.device, a.format, a.width, a.height, a.fps, a.qsize)
    cap.start()

    # 워밍업
    n = 0
    while n < a.warmup:
        f = cap.get()
        if f:
            model.predict(f[1], verbose=False)
            n += 1

    # 측정
    e2e_ms, age_ms, proc_ms = [], [], []
    t_start = time.perf_counter()
    for _ in range(a.frames):
        f = cap.get()
        if f is None:
            break
        cap_ts, img = f
        t_pull = time.perf_counter()
        r = model.predict(img, verbose=False)[0]
        t_done = time.perf_counter()
        age_ms.append((t_pull - cap_ts) * 1000)       # ④ frame age(큐 지연)
        e2e_ms.append((t_done - cap_ts) * 1000)        # ② E2E (캡처→결과)
        sp = r.speed
        proc_ms.append(sp.get("preprocess", 0) + sp.get("inference", 0) + sp.get("postprocess", 0))
    elapsed = time.perf_counter() - t_start
    fps = round(len(e2e_ms) / elapsed, 1) if elapsed else 0

    cap.stop()
    time.sleep(0.2)
    drop_rate = round(cap.dropped / cap.captured * 100, 1) if cap.captured else 0

    print(f"""
[Threaded capture] {a.width}x{a.height} {a.format} · 큐 {a.qsize} · {len(e2e_ms)}프레임

① FPS           : {fps}
② E2E latency   : {avg(e2e_ms)} ms   (캡처→결과)
③ Capture       : {avg(cap.cap_ms)} ms   (스레드 cap.read)
④ Frame age     : {avg(age_ms)} ms   (큐 지연)

  처리(pre+inf+post): {avg(proc_ms)} ms
  캡처 스레드: {cap.captured}장 캡처 / {cap.dropped}장 드롭 ({drop_rate}%)
""")


if __name__ == "__main__":
    main()
