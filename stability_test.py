"""
stability_test.py — 장기 안정성 + 장애주입(Fault Injection) 통합 테스트 (더미 없음)

실제 구성요소를 전부 연동해서 돌린다:
  Camera(HW디코드 + 자동 재오픈) → Detector(best.engine, 실추론) → Judge(판정)
  → (판정 emit 시) 실서버로 전송(TelemetryClient).  합성/더미 입력 없음.

프레임단위 예외 격리 검증:
  --fault-every N  → N프레임마다 탐지 경로에서 예외를 강제 발생시켜(주입),
  루프가 죽지 않고 그 프레임만 건너뛰며 계속 도는지 + exception 카운트가 맞는지 확인.

기록 지표(종료 시 JSON + 콘솔):
  FPS avg/min · E2E avg/p95/max · RAM 시작/종료 · Temp avg/max
  · Drop rate · Camera reopen 수 · Exception 수 · 처리/전송 프레임 수

실행(Jetson):
  python -u stability_test.py --duration 1800 --url ws://<server>:8000/ws/device \
         --fault-every 600 --out /tmp/stability_summary.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime

import psutil

from camera import Camera, CameraConfig
from detector import Detector, crop_bbox
from judge import Judge
from metrics import read_temp_c
from pipeline import emit_detection
from telemetry_client import TelemetryClient


def pctl(a, p):
    """정렬 기반 백분위수(p=0~100). 비면 None."""
    if not a:
        return None
    s = sorted(a)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def main():
    ap = argparse.ArgumentParser(description="장기 안정성 + 장애주입 통합 테스트")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/best.engine")
    ap.add_argument("--url", default="ws://192.168.1.10:8000/ws/device")
    ap.add_argument("--no-server", action="store_true", help="서버 전송 끔")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--duration", type=float, default=1800.0, help="실행 시간(초)")
    ap.add_argument("--fault-every", type=int, default=0,
                    help="N프레임마다 탐지 경로에 예외 주입(0=끔)")
    ap.add_argument("--report-interval", type=float, default=30.0)
    ap.add_argument("--out", default="/tmp/stability_summary.json")
    a = ap.parse_args()

    cam = Camera(CameraConfig()).start()
    det = Detector(a.engine, conf=a.conf)
    judge = Judge()
    tc = None
    if not a.no_server:
        tc = TelemetryClient(a.url).start()
        sd = datetime.now()
        tc.session_start("Jetson Orin Nano (stability)", sd.strftime("%Y-%m-%d"),
                         sd.strftime("%H:%M"))

    # 워밍업: 엔진/CUDA 커널 로드 + 큐 드레인 (측정 오염 방지). 이후부터 계측 시작.
    print("[stability] 워밍업...", flush=True)
    wu, wu_end = 0, time.time() + 5.0
    while time.time() < wu_end and wu < 90:
        f = cam.read(timeout=1.0)
        if f is None:
            continue
        try:
            det.infer(f.image)
        except Exception:
            pass
        wu += 1
    print(f"[stability] 워밍업 완료 ({wu}프레임) — 측정 시작", flush=True)

    ram0 = round(psutil.virtual_memory().used / 1024 / 1024)   # MB (워밍업 후 = 정상상태 기준)
    e2e = []                 # 프레임별 glass-to-decision 지연(ms)
    temps = []               # 주기 온도 샘플
    proc = 0                 # 정상 처리 프레임
    exc = 0                  # 격리된 예외 수(주입 포함)
    emits = 0                # 서버로 보낸 판정 수
    ram_peak = ram0

    t0 = time.time()
    end = t0 + a.duration
    next_report = t0 + a.report_interval
    next_temp = t0
    # FPS min 측정용 10초 버킷
    bucket_start, bucket_proc, fps_min = t0, 0, None

    print(f"[stability] 시작 duration={a.duration:.0f}s fault_every={a.fault_every} "
          f"server={'off' if a.no_server else a.url} RAM0={ram0}MB", flush=True)

    try:
        while time.time() < end:
            frame = cam.read(timeout=1.0)
            if frame is None:
                continue
            # ── 프레임단위 예외 격리 (주입 포함) ──
            try:
                if a.fault_every and frame.seq % a.fault_every == 0:
                    raise RuntimeError("injected fault (test)")
                dets = det.infer(frame.image)
                res = judge.update(dets)
                now = time.time()
                e2e.append((now - frame.ts) * 1000.0)
                proc += 1
                bucket_proc += 1
                if res is not None and res.emit and tc is not None:
                    emit_detection(tc, None, grade=res.grade, hazard_type=res.hazard_type,
                                   conf=res.conf, crops=[crop_bbox(frame.image, res.bbox)])
                    emits += 1
            except Exception as e:
                exc += 1
                if exc <= 3 or exc % 50 == 0:
                    print(f"[stability] 예외 격리 #{exc}: {e}", flush=True)

            now = time.time()
            # 온도 샘플(5s)
            if now >= next_temp:
                t = read_temp_c()
                if t is not None:
                    temps.append(t)
                ram_now = round(psutil.virtual_memory().used / 1024 / 1024)
                ram_peak = max(ram_peak, ram_now)
                next_temp = now + 5.0
            # FPS min 버킷(10s)
            if now - bucket_start >= 10.0:
                fps_b = bucket_proc / (now - bucket_start)
                fps_min = fps_b if fps_min is None else min(fps_min, fps_b)
                bucket_start, bucket_proc = now, 0
            # 진행 보고
            if now >= next_report:
                el = now - t0
                recent = e2e[-300:]
                print(f"[stability] {el:6.0f}s proc={proc} fps~{proc/el:4.1f} "
                      f"e2e~{statistics.mean(recent):5.1f}ms temp={temps[-1] if temps else '-'} "
                      f"exc={exc} reopen={cam.stats.reopens} "
                      f"drop={cam.stats.drop_rate()*100:4.1f}% emit={emits} pend={tc.pending() if tc else 0}",
                      flush=True)
                next_report = now + a.report_interval
    finally:
        elapsed = time.time() - t0
        ram1 = round(psutil.virtual_memory().used / 1024 / 1024)
        if tc is not None:
            tc.session_end(end_time=datetime.now().strftime("%H:%M"),
                           duration_sec=int(elapsed),
                           max_temp=max(temps) if temps else None,
                           avg_temp=round(statistics.mean(temps), 1) if temps else None,
                           throttle_temp=87.0, avg_power=None, max_power=None,
                           frame_drops=cam.stats.dropped, total_frames=cam.stats.captured,
                           gps_reception=None)
            tc.stop()
        cam.stop()

        summary = {
            "duration_s": round(elapsed, 1),
            "frames_processed": proc,
            "frames_captured": cam.stats.captured,
            "fps_avg": round(proc / elapsed, 2) if elapsed else None,
            "fps_min_10s_bucket": round(fps_min, 2) if fps_min is not None else None,
            "e2e_avg_ms": round(statistics.mean(e2e), 2) if e2e else None,
            "e2e_p95_ms": round(pctl(e2e, 95), 2) if e2e else None,
            "e2e_max_ms": round(max(e2e), 2) if e2e else None,
            "ram_start_mb": ram0,
            "ram_end_mb": ram1,
            "ram_peak_mb": ram_peak,
            "temp_avg_c": round(statistics.mean(temps), 1) if temps else None,
            "temp_max_c": round(max(temps), 1) if temps else None,
            "drop_rate_pct": round(cam.stats.drop_rate() * 100, 2),
            "camera_reopens": cam.stats.reopens,
            "exceptions_isolated": exc,
            "fault_every": a.fault_every,
            "detections_emitted": emits,
        }
        with open(a.out, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print("[stability] === SUMMARY ===", flush=True)
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
        print(f"[stability] DONE (saved {a.out})", flush=True)


if __name__ == "__main__":
    main()
