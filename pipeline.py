"""
pipeline.py — 엣지 통합 파이프라인 (기기 상태 축)

카메라 캡처 + 실제 기기 지표 수집(metrics) + GPS + 서버 WebSocket 전송(telemetry_client)을
오케스트레이션한다. 현재는 기기 상태(telemetry)까지. 전주 탐지(vision) 추론은 아래 TODO에 연결.

흐름:  session_start → (주기적) telemetry × N → session_end
실행:  python pipeline.py --url ws://<서버IP>:8000/ws/device --interval 60
       python pipeline.py --no-camera --no-gps --interval 1 --duration 5   # 하드웨어 없이 점검
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime


class _Agg:
    """세션 요약 집계 (session_end용)."""
    def __init__(self, throttle_temp: float = 87.0):
        self.temps, self.powers = [], []
        self.gps_ok, self.gps_n = 0, 0
        self.throttle_temp = throttle_temp

    def update(self, snap: dict) -> None:
        if snap["temp"] is not None:
            self.temps.append(snap["temp"])
        if snap["power"] is not None:
            self.powers.append(snap["power"])
        self.gps_n += 1
        self.gps_ok += int(bool(snap["gps"]))

    def summary(self, camera) -> dict:
        mx = lambda a: max(a) if a else None
        s = {
            "max_temp": mx(self.temps),
            "avg_temp": round(sum(self.temps) / len(self.temps), 1) if self.temps else None,
            "throttle_temp": self.throttle_temp,
            "max_power": mx(self.powers),
            "avg_power": round(sum(self.powers) / len(self.powers), 2) if self.powers else None,
            "gps_reception": round(self.gps_ok / self.gps_n, 2) if self.gps_n else None,
        }
        if camera is not None:
            s["frame_drops"] = camera.stats.dropped
            s["total_frames"] = camera.stats.captured
        return s


def emit_detection(tc, gps, grade, hazard_type, conf, crops, pole_no=None):
    """비전 판정 결과를 best-frame 사진과 함께 서버로 실시간 전송.
    crops: 전주당 확보된 크롭 이미지 리스트 → 가장 선명한 한 장을 골라 보냄.
    grade: danger|caution|safe (위험/주의/양호)."""
    from best_frame import select_best, encode_jpeg
    best, _ = select_best(crops or [])
    img = encode_jpeg(best) if best is not None else None
    fix = gps.read() if gps is not None else {}
    tc.detection(grade=grade, hazard_type=hazard_type, conf=conf,
                 lat=fix.get("lat"), lon=fix.get("lon"), image_bytes=img,
                 pole_no=pole_no,
                 recorded_at=datetime.now().isoformat(timespec="seconds"))


def _open_jtop():
    """jetson-stats(jtop) 세션 — 정확한 전력 측정용. 없으면 None."""
    try:
        from jtop import jtop
        jt = jtop()
        jt.start()
        return jt
    except Exception:
        return None


def run(url: str, interval: float = 60.0, duration=None, device: str = "Jetson Nano",
        gps_port: str = "/dev/ttyACM0", no_camera: bool = False, no_gps: bool = False):
    # 하드웨어 모듈은 필요할 때만 import (cv2/serial 없는 환경에서 --no-* 실행 가능)
    from metrics import MetricsCollector
    from telemetry_client import TelemetryClient

    cam = None
    if not no_camera:
        from camera import Camera
        cam = Camera().start()
    gps = None
    if not no_gps:
        from gps import GPS
        gps = GPS(port=gps_port).start()
    jt = _open_jtop()

    collector = MetricsCollector(cam, gps, jt)
    tc = TelemetryClient(url).start()

    start_dt = datetime.now()
    tc.session_start(device, start_dt.strftime("%Y-%m-%d"), start_dt.strftime("%H:%M"))
    print(f"[pipeline] 세션 시작 {start_dt:%Y-%m-%d %H:%M} · interval={interval}s · "
          f"camera={'on' if cam else 'off'} gps={'on' if gps else 'off'} jtop={'on' if jt else 'off'}")

    agg = _Agg()
    last_tele = 0.0
    try:
        while True:
            # 카메라 프레임 소비 (fps/drop 통계 갱신 + 추후 추론 입력)
            if cam is not None:
                frame = cam.read(timeout=1.0)
                # TODO(vision): stage1(전주)→stage2(까치집/수목) 추론 → 등급 판정.
                # 전주 판정이 확정되면 best-frame 사진과 함께 실시간 전송:
                #   emit_detection(tc, gps, grade="danger", hazard_type="nest",
                #                  conf=0.9, crops=pole_crops, pole_no=pole_no)
                _ = frame
            else:
                time.sleep(0.05)

            now = time.time()
            if now - last_tele >= interval:
                snap = collector.snapshot()
                agg.update(snap)
                t = datetime.now().strftime("%H:%M")
                tc.telemetry(t, snap["temp"], snap["power"], snap["drops"], snap["gps"])
                print(f"[pipeline] telemetry {t} · temp={snap['temp']} power={snap['power']} "
                      f"fps={snap['fps']} drops={snap['drops']} gps={snap['gps']} · 대기={tc.pending()}")
                last_tele = now

            if duration is not None and (time.time() - start_dt.timestamp()) >= duration:
                break
    except KeyboardInterrupt:
        print("\n[pipeline] 중단 요청(Ctrl+C)")
    finally:
        end_dt = datetime.now()
        summary = agg.summary(cam)
        tc.session_end(end_time=end_dt.strftime("%H:%M"),
                       duration_sec=int((end_dt - start_dt).total_seconds()), **summary)
        print(f"[pipeline] 세션 종료 · 요약={summary}")
        tc.stop()
        if cam is not None:
            cam.stop()
        if gps is not None:
            gps.stop()
        if jt is not None:
            try:
                jt.close()
            except Exception:
                pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="엣지 통합 파이프라인 (기기 상태)")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/device")
    ap.add_argument("--interval", type=float, default=60.0, help="telemetry 전송 간격(초)")
    ap.add_argument("--duration", type=float, default=None, help="최대 실행(초). 미지정 시 Ctrl+C까지")
    ap.add_argument("--gps-port", default="/dev/ttyACM0")
    ap.add_argument("--no-camera", action="store_true", help="카메라 없이 실행")
    ap.add_argument("--no-gps", action="store_true", help="GPS 없이 실행")
    a = ap.parse_args()
    run(a.url, a.interval, a.duration, gps_port=a.gps_port,
        no_camera=a.no_camera, no_gps=a.no_gps)
