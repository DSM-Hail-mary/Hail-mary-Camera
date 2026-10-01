"""
bench_gst.py — GStreamer 하드웨어 디코드(NVDEC) 캡처 벤치

OpenCV의 GStreamer 백엔드로 카메라 MJPG를 nvv4l2decoder(HW)로 디코드한다.
디코드가 GStreamer(C, GIL 밖) + NVDEC HW에서 일어나 CPU/파이썬 병목을 우회.
bench.py(순차, OpenCV CPU 디코드)와 같은 측정이라 직접 비교 가능.

실행:  python bench_gst.py --width 640 --height 480 --frames 100
"""
import argparse
import glob
import statistics
import subprocess
import threading
import re
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


def avg(a):
    return round(statistics.mean(a), 2) if a else 0.0


def main():
    ap = argparse.ArgumentParser(description="GStreamer HW 디코드 벤치")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/yolov8n_fp16.engine")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=15)
    a = ap.parse_args()

    pipe = gst_pipeline(a.device, a.width, a.height, a.fps)
    print("GST:", pipe)
    cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise SystemExit("GStreamer 파이프라인 열기 실패 (nvv4l2decoder 확인)")

    model = YOLO(a.engine, task="detect")
    for _ in range(a.warmup):
        ok, img = cap.read()
        if ok:
            model.predict(img, verbose=False)

    gpu = TegraGPU()
    psutil.cpu_percent(None)
    cap_ms, pre_ms, inf_ms, post_ms, e2e_ms = [], [], [], [], []
    for _ in range(a.frames):
        t0 = time.perf_counter()
        ok, img = cap.read()
        t1 = time.perf_counter()
        if not ok:
            continue
        r = model.predict(img, verbose=False)[0]
        t2 = time.perf_counter()
        sp = r.speed
        cap_ms.append((t1 - t0) * 1000)
        pre_ms.append(sp.get("preprocess", 0))
        inf_ms.append(sp.get("inference", 0))
        post_ms.append(sp.get("postprocess", 0))
        e2e_ms.append((t2 - t0) * 1000)

    cpu = psutil.cpu_percent(None)
    ram = round(psutil.virtual_memory().used / 1024 / 1024)
    temp = read_temp_c()
    gpu_pct = gpu.avg()
    gpu.stop()
    cap.release()

    e2e = avg(e2e_ms)
    fps = round(1000.0 / e2e, 1) if e2e else 0.0
    f = lambda v, u="": f"{v}{u}" if v is not None else "N/A"
    print(f"""
[GStreamer HW decode] {a.width}x{a.height} @ {a.fps} (MJPG→nvv4l2decoder)
Model: YOLOv8n / TensorRT FP16 / {len(e2e_ms)}프레임

FPS          : {fps}
E2E Latency  : {e2e} ms

Capture      : {avg(cap_ms)} ms   (appsink pop, HW 디코드)
Preprocess   : {avg(pre_ms)} ms
Inference    : {avg(inf_ms)} ms
Postprocess  : {avg(post_ms)} ms

CPU          : {f(cpu, ' %')}
GPU          : {f(gpu_pct, ' %')}
RAM          : {ram} MB
Temperature  : {f(temp, ' °C')}
""")


if __name__ == "__main__":
    main()
