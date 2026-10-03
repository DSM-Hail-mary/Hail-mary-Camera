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
from datetime import datetime, timedelta, timezone

import model_config   # 모델 교체 블럭(기본 엔진 경로)

KST = timezone(timedelta(hours=9))


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
    # 기록 시각: GPS 시각(UTC) 있으면 KST로 변환해 사용(정확), 없으면 보드 시계
    utc = fix.get("utc")
    if utc:
        try:
            recorded_at = datetime.fromisoformat(utc).astimezone(KST).isoformat(timespec="seconds")
        except Exception:
            recorded_at = datetime.now(KST).isoformat(timespec="seconds")
    else:
        recorded_at = datetime.now(KST).isoformat(timespec="seconds")
    tc.detection(grade=grade, hazard_type=hazard_type, conf=conf,
                 lat=fix.get("lat"), lon=fix.get("lon"), image_bytes=img,
                 pole_no=pole_no, recorded_at=recorded_at)


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
        gps_port: str = "/dev/ttyACM0", no_camera: bool = False, no_gps: bool = False,
        gst_host: str = "127.0.0.1", gst_port: int = 5000, gst_bridge: bool = False,
        engine: str = model_config.ENGINE,
        conf: float = 0.25, no_detect: bool = False,
        gps_source: str = "serial", phone_host: str = "192.168.42.129",
        phone_port: int = 11123, phone_proto: str = "tcp"):
    # 하드웨어 모듈은 필요할 때만 import (cv2/serial 없는 환경에서 --no-* 실행 가능)
    from metrics import MetricsCollector
    from telemetry_client import TelemetryClient

    cam = None
    if not no_camera:
        from camera import Camera
        cam = Camera().start()
    # 온디바이스 탐지+판정 (풀-파이썬). best.pt→export한 best.engine 필요.
    detector = judge = crop_bbox = None
    if cam is not None and not no_detect:
        from detector import Detector, crop_bbox as _crop
        from judge import Judge
        detector, judge, crop_bbox = Detector(engine, conf=conf), Judge(), _crop
    # (옵션) 세현 GStreamer로 프레임을 흘려보낼 TCP 브리지 — 이제 탐지는 우리가 하므로 기본 off
    bridge = None
    if cam is not None and gst_bridge:
        from gst_bridge import GstBridge
        bridge = GstBridge(gst_host, gst_port, width=cam.cfg.width, height=cam.cfg.height)
    gps = None
    if not no_gps:
        if gps_source == "phone":
            from phone_gps import PhoneGPS
            gps = PhoneGPS(phone_host, phone_port, phone_proto).start()
        else:
            from gps import GPS
            gps = GPS(port=gps_port).start()
    jt = _open_jtop()

    collector = MetricsCollector(cam, gps, jt)
    tc = TelemetryClient(url).start()

    start_dt = datetime.now()
    tc.session_start(device, start_dt.strftime("%Y-%m-%d"), start_dt.strftime("%H:%M"))
    print(f"[pipeline] 세션 시작 {start_dt:%Y-%m-%d %H:%M} · interval={interval}s · "
          f"camera={'on' if cam else 'off'} detect={'on' if detector else 'off'} "
          f"gps={'on' if gps else 'off'} jtop={'on' if jt else 'off'}")

    agg = _Agg()
    last_tele = 0.0
    try:
        while True:
            # 카메라 프레임 소비 (fps/drop 통계 갱신 + 온디바이스 추론 입력)
            if cam is not None:
                frame = cam.read(timeout=1.0)
                if frame is not None:
                    # (옵션) 세현 GStreamer로 프레임 전송 — 브리지 끊김이 주행을 막지 않게
                    if bridge is not None:
                        try:
                            bridge.send(frame.image)
                        except Exception as e:
                            print(f"[pipeline] 브리지 전송 오류(무시): {e}")
                    # 온디바이스 탐지 → 판정 → 전송 — 프레임 단위 예외 격리
                    if detector is not None:
                        try:
                            result = judge.update(detector.infer(frame.image))
                            if result is not None and result.emit:
                                crop = crop_bbox(frame.image, result.bbox)
                                emit_detection(tc, gps, grade=result.grade,
                                               hazard_type=result.hazard_type,
                                               conf=result.conf, crops=[crop])
                                print(f"[pipeline] 판정 전송: {result.grade} "
                                      f"{result.hazard_type} conf={result.conf}")
                        except Exception as e:
                            print(f"[pipeline] 탐지/판정 오류(프레임 건너뜀): {e}")
            else:
                time.sleep(0.05)

            now = time.time()
            if now - last_tele >= interval:
                try:
                    snap = collector.snapshot()
                    agg.update(snap)
                    t = datetime.now().strftime("%H:%M")
                    tc.telemetry(t, snap["temp"], snap["power"], snap["drops"], snap["gps"])
                    print(f"[pipeline] telemetry {t} · temp={snap['temp']} power={snap['power']} "
                          f"fps={snap['fps']} drops={snap['drops']} gps={snap['gps']} · 대기={tc.pending()}")
                except Exception as e:
                    print(f"[pipeline] telemetry 수집/전송 오류(계속): {e}")
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
        if bridge is not None:
            bridge.close()
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
    ap.add_argument("--engine", default=model_config.ENGINE,
                    help="탐지 TensorRT 엔진 (기본값은 model_config.ENGINE)")
    ap.add_argument("--conf", type=float, default=0.25, help="탐지 신뢰도 임계값")
    ap.add_argument("--no-detect", action="store_true", help="온디바이스 탐지/판정 끔")
    ap.add_argument("--gst-bridge", action="store_true",
                    help="(옵션) 세현 GStreamer로 프레임 TCP 전송 켬")
    ap.add_argument("--gst-host", default="127.0.0.1", help="세현 GStreamer TCP 호스트")
    ap.add_argument("--gst-port", type=int, default=5000, help="세현 GStreamer TCP 포트")
    ap.add_argument("--gps-source", default="serial", choices=["serial", "phone"],
                    help="GPS 소스: serial(모듈) | phone(폰 NMEA, USB 테더)")
    ap.add_argument("--phone-host", default="192.168.42.129", help="폰 테더 IP")
    ap.add_argument("--phone-port", type=int, default=11123)
    ap.add_argument("--phone-proto", default="tcp", choices=["tcp", "udp"])
    a = ap.parse_args()
    run(a.url, a.interval, a.duration, gps_port=a.gps_port,
        no_camera=a.no_camera, no_gps=a.no_gps,
        engine=a.engine, conf=a.conf, no_detect=a.no_detect,
        gst_bridge=a.gst_bridge, gst_host=a.gst_host, gst_port=a.gst_port,
        gps_source=a.gps_source, phone_host=a.phone_host,
        phone_port=a.phone_port, phone_proto=a.phone_proto)
