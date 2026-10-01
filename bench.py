"""
bench.py — Jetson 성능 벤치마크 (FPS / 단계별 지연 / 자원 사용)

측정:
  1) FPS                2) End-to-End Latency
  3) Capture           4) Preprocess
  5) TensorRT Inference 6) Postprocess
  7) CPU%  8) GPU%  9) RAM  10) Temperature

파이프라인: 카메라 캡처 → YOLOv8n(TensorRT FP16) 추론(전/후처리 포함).
추론·전/후처리 시간은 ultralytics가 제공(results.speed), 캡처/E2E는 직접 측정,
GPU%는 tegrastats(GR3D_FREQ), CPU/RAM은 psutil, 온도는 thermal zone.

실행(Jetson):
  source ~/polewatch-env/bin/activate
  python bench.py --engine ~/polewatch/models/yolov8n_fp16.engine --width 640 --height 480
"""
import argparse
import glob
import re
import statistics
import subprocess
import threading
import time

import cv2
import psutil
from ultralytics import YOLO


class TegraGPU:
    """tegrastats로 GPU 사용률(GR3D_FREQ) 백그라운드 샘플링."""
    def __init__(self, interval_ms: int = 200):
        self.samples = []
        self._run = True
        try:
            self.p = subprocess.Popen(
                ["sudo", "tegrastats", "--interval", str(interval_ms)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except Exception:
            self.p = None
        if self.p:
            threading.Thread(target=self._loop, daemon=True).start()

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
    temps = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            temps.append(int(open(p).read().strip()) / 1000.0)
        except Exception:
            pass
    return round(max(temps), 1) if temps else None


def avg(a):
    return round(statistics.mean(a), 2) if a else 0.0


def main():
    ap = argparse.ArgumentParser(description="Jetson YOLOv8n TensorRT 벤치마크")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/yolov8n_fp16.engine")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--format", default="MJPG", choices=["MJPG", "YUYV"])
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=15)
    a = ap.parse_args()

    # 카메라
    cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*a.format))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)
    cap.set(cv2.CAP_PROP_FPS, a.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise SystemExit(f"카메라 열기 실패: {a.device}")
    # 자동노출(실내에서도 장면이 보이게 → 현실적인 추론 부하)
    subprocess.run(["v4l2-ctl", "-d", a.device, "--set-ctrl=auto_exposure=3"],
                   stderr=subprocess.DEVNULL)

    model = YOLO(a.engine, task="detect")

    # 워밍업 (TensorRT 초기 커널 로딩/최적화)
    for _ in range(a.warmup):
        ok, img = cap.read()
        if ok:
            model.predict(img, verbose=False)

    # 측정
    gpu = TegraGPU()
    psutil.cpu_percent(None)        # CPU% 기준점 초기화
    cap_ms, pre_ms, inf_ms, post_ms, e2e_ms = [], [], [], [], []
    for _ in range(a.frames):
        t0 = time.perf_counter()
        ok, img = cap.read()
        t1 = time.perf_counter()
        if not ok:
            continue
        r = model.predict(img, verbose=False)[0]
        t2 = time.perf_counter()
        sp = r.speed                # {'preprocess','inference','postprocess'} ms
        cap_ms.append((t1 - t0) * 1000)
        pre_ms.append(sp.get("preprocess", 0.0))
        inf_ms.append(sp.get("inference", 0.0))
        post_ms.append(sp.get("postprocess", 0.0))
        e2e_ms.append((t2 - t0) * 1000)

    cpu = psutil.cpu_percent(None)
    ram = round(psutil.virtual_memory().used / 1024 / 1024)
    temp = read_temp_c()
    gpu_pct = gpu.avg()
    gpu.stop()
    cap.release()

    e2e = avg(e2e_ms)
    fps = round(1000.0 / e2e, 1) if e2e else 0.0

    def fmt(v, unit=""):
        return f"{v}{unit}" if v is not None else "N/A"

    print(f"""
[Baseline]

Camera       : {a.width}x{a.height} @ {a.fps} FPS ({a.format})
Model        : YOLOv8n
TensorRT     : FP16

FPS          : {fps}
E2E Latency  : {e2e} ms

Capture      : {avg(cap_ms)} ms
Preprocess   : {avg(pre_ms)} ms
Inference    : {avg(inf_ms)} ms
Postprocess  : {avg(post_ms)} ms

CPU          : {fmt(cpu, ' %')}
GPU          : {fmt(gpu_pct, ' %')}
RAM          : {ram} MB
Temperature  : {fmt(temp, ' °C')}

(측정 {len(e2e_ms)}프레임 평균, 순차 파이프라인 기준)
""")


if __name__ == "__main__":
    main()
