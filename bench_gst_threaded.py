"""
bench_gst_threaded.py — HW 디코드(NVDEC) + 스레드 캡처 결합 벤치

조합:
  - 디코드: nvv4l2decoder(HW, GStreamer appsink)  ← bench_gst.py
  - 캡처:  별도 스레드에서 끊임없이 pop, 추론과 분리 ← bench_threaded.py
목적: HW 디코드로 처리량(FPS)을 올린 상태에서, 스레드 분리로 E2E 지연·프레임
      신선도(frame age)가 추가로 줄어드는지 측정. (순차 bench_gst.py와 직접 비교)

측정:
  ① FPS            (추론 루프가 실제 처리하는 초당 프레임)
  ② E2E latency    (프레임 캡처 시점 → 추론 결과까지, glass-to-result)
  ③ Capture        (캡처 스레드의 appsink pop 1회 시간, HW 디코드)
  ④ Frame age      (프레임이 큐에서 소비될 때의 나이 = 큐 지연)

실행:  python bench_gst_threaded.py --width 1280 --height 720 --frames 100
"""
import argparse
import collections
import glob
import re
import statistics
import subprocess
import threading
import time

import cv2
import psutil
from ultralytics import YOLO


def gst_pipeline(device, w, h, fps):
    return (
        f"v4l2src device={device} io-mode=2 ! "
        f"image/jpeg,width={w},height={h},framerate={fps}/1 ! "
        f"nvv4l2decoder mjpeg=1 ! nvvidconv ! video/x-raw,format=BGRx ! "
        f"videoconvert ! video/x-raw,format=BGR ! "
        f"appsink drop=1 max-buffers=1 sync=false"
    )


class TegraGPU:
    def __init__(self, interval_ms=200):
        self.samples, self._run = [], True
        try:
            self.p = subprocess.Popen(["sudo", "tegrastats", "--interval", str(interval_ms)],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            threading.Thread(target=self._loop, daemon=True).start()
        except Exception:
            self.p = None

    def _loop(self):
        for line in self.p.stdout:
            m = re.search(r"GR3D_FREQ\s+(\d+)%", line)
            if m:
                self.samples.append(int(m.group(1)))
            if not self._run:
                break

    def stop(self):
        self._run = False
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass

    def avg(self):
        return round(statistics.mean(self.samples), 1) if self.samples else None


def read_temp_c():
    t = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            t.append(int(open(p).read().strip()) / 1000.0)
        except Exception:
            pass
    return round(max(t), 1) if t else None


class GstCapturer(threading.Thread):
    """GStreamer(HW 디코드) 파이프라인을 스레드에서 끊임없이 읽어 최신 프레임 유지."""
    def __init__(self, pipeline, qsize):
        super().__init__(daemon=True)
        self.pipeline = pipeline
        self.q = collections.deque(maxlen=qsize)
        self.lock = threading.Lock()
        self.evt = threading.Event()
        self._run = True
        self.opened = False
        self.cap_ms, self.captured, self.dropped = [], 0, 0

    def run(self):
        cap = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        self.opened = cap.isOpened()
        if not self.opened:
            return
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
                    self.dropped += 1
                self.q.append((t1, img))
            self.evt.set()
        cap.release()

    def get(self, timeout=5.0):
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            with self.lock:
                if self.q:
                    return self.q.popleft()
            self.evt.wait(0.005)
            self.evt.clear()
        return None

    def stop(self):
        self._run = False


def avg(a):
    return round(statistics.mean(a), 2) if a else 0.0


def main():
    ap = argparse.ArgumentParser(description="HW 디코드 + 스레드 캡처 벤치")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/yolov8n_fp16.engine")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--qsize", type=int, default=4)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=15)
    a = ap.parse_args()

    # 자동노출(현실적 추론 부하)
    subprocess.run(["v4l2-ctl", "-d", a.device, "--set-ctrl=auto_exposure=3"],
                   stderr=subprocess.DEVNULL)

    pipe = gst_pipeline(a.device, a.width, a.height, a.fps)
    print("GST:", pipe)
    model = YOLO(a.engine, task="detect")
    cap = GstCapturer(pipe, a.qsize)
    cap.start()

    # 워밍업
    n = 0
    while n < a.warmup:
        f = cap.get()
        if f is None:
            if not cap.opened:
                raise SystemExit("GStreamer 파이프라인 열기 실패 (nvv4l2decoder 확인)")
            continue
        model.predict(f[1], verbose=False)
        n += 1

    # 측정
    gpu = TegraGPU()
    psutil.cpu_percent(None)
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
        age_ms.append((t_pull - cap_ts) * 1000)
        e2e_ms.append((t_done - cap_ts) * 1000)
        sp = r.speed
        proc_ms.append(sp.get("preprocess", 0) + sp.get("inference", 0) + sp.get("postprocess", 0))
    elapsed = time.perf_counter() - t_start
    fps = round(len(e2e_ms) / elapsed, 1) if elapsed else 0

    cpu = psutil.cpu_percent(None)
    ram = round(psutil.virtual_memory().used / 1024 / 1024)
    temp = read_temp_c()
    gpu_pct = gpu.avg()
    gpu.stop()
    cap.stop()
    time.sleep(0.2)
    drop_rate = round(cap.dropped / cap.captured * 100, 1) if cap.captured else 0

    f = lambda v, u="": f"{v}{u}" if v is not None else "N/A"
    print(f"""
[HW decode + Threaded] {a.width}x{a.height} @ {a.fps} · 큐 {a.qsize} · {len(e2e_ms)}프레임
Model: YOLOv8n / TensorRT FP16

① FPS           : {fps}
② E2E latency   : {avg(e2e_ms)} ms   (캡처→결과)
③ Capture       : {avg(cap.cap_ms)} ms   (appsink pop, HW 디코드)
④ Frame age     : {avg(age_ms)} ms   (큐 지연)

  처리(pre+inf+post): {avg(proc_ms)} ms
  캡처 스레드: {cap.captured}장 캡처 / {cap.dropped}장 드롭 ({drop_rate}%)
  CPU {f(cpu,' %')} · GPU {f(gpu_pct,' %')} · RAM {ram}MB · {f(temp,' °C')}
""")


if __name__ == "__main__":
    main()
