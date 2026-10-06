"""
snapshot_forwarder.py — 세현 C++ 판정결과(snapshot) → 서버 전송 (연동 방법 A)

세현 C++(HailMary)이 위험 판정 시 저장하는 snapshot_*.jpg를 폴링 감시해,
새 파일이 생기면 GPS 좌표 + 등급과 함께 **기존 서버 엔드포인트**로 전송한다.
서버/송신부(telemetry_client)는 그대로 재사용 — **세현 C++ 수정 불필요.**

흐름:  session_start → (새 snapshot마다) detection → session_end
실행(Jetson, HailMary와 함께):
  python snapshot_forwarder.py --url ws://<서버IP>:8000/ws/device \
      --watch-dir ~/Hail-mary-main/HailMary --gps-source phone --phone-host 192.168.1.21

참고: 세현 judge는 현재 이진(정상/위험)이라, snapshot=위험으로 보고 --grade(기본 danger)로
      전송한다. 3단계(위험/주의/양호)가 필요하면 세현 judge 확장 후 매핑하면 됨.
"""
from __future__ import annotations

import argparse
import glob
import os
import time
from datetime import datetime, timedelta, timezone

from telemetry_client import TelemetryClient

KST = timezone(timedelta(hours=9))


def _recorded_at_and_fix(gps):
    fix = gps.read() if gps is not None else {}
    utc = fix.get("utc")
    if utc:
        try:
            return datetime.fromisoformat(utc).astimezone(KST).isoformat(timespec="seconds"), fix
        except Exception:
            pass
    return datetime.now(KST).isoformat(timespec="seconds"), fix


def main():
    ap = argparse.ArgumentParser(description="세현 snapshot → 서버 전송 (방법 A)")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/device")
    ap.add_argument("--watch-dir", default=os.path.expanduser("~/Hail-mary-main/HailMary"))
    ap.add_argument("--pattern", default="snapshot_*.jpg")
    ap.add_argument("--grade", default="danger", choices=["danger", "caution", "safe"],
                    help="snapshot(위험)→전송 등급 (세현 판정이 이진이라 기본 danger)")
    ap.add_argument("--hazard", default="nest")
    ap.add_argument("--conf", type=float, default=None)
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--device", default="Jetson Orin Nano")
    ap.add_argument("--no-gps", action="store_true")
    ap.add_argument("--gps-source", default="phone", choices=["phone", "serial"])
    ap.add_argument("--phone-host", default="192.168.1.21")
    ap.add_argument("--phone-port", type=int, default=11123)
    ap.add_argument("--phone-proto", default="tcp")
    ap.add_argument("--gps-port", default="/dev/ttyACM0")
    ap.add_argument("--duration", type=float, default=None, help="최대 실행(초). 미지정 시 Ctrl+C까지")
    ap.add_argument("--send-existing", action="store_true",
                    help="시작 시점에 이미 있던 snapshot도 전송(기본은 무시)")
    a = ap.parse_args()

    gps = None
    if not a.no_gps:
        if a.gps_source == "phone":
            from phone_gps import PhoneGPS
            gps = PhoneGPS(a.phone_host, a.phone_port, a.phone_proto).start()
        else:
            from gps import GPS
            gps = GPS(port=a.gps_port).start()

    tc = TelemetryClient(a.url).start()
    start_dt = datetime.now()
    tc.session_start(a.device, start_dt.strftime("%Y-%m-%d"), start_dt.strftime("%H:%M"))
    print(f"[forwarder] 시작 · watch={a.watch_dir}/{a.pattern} · url={a.url} "
          f"· grade={a.grade} · gps={'off' if a.no_gps else a.gps_source}")

    def current():
        return set(glob.glob(os.path.join(a.watch_dir, a.pattern)))

    seen = set() if a.send_existing else current()
    sent = 0
    try:
        while True:
            for path in sorted(current() - seen):
                seen.add(path)
                time.sleep(0.05)                      # 파일 쓰기 완료 대기
                try:
                    with open(path, "rb") as f:
                        img = f.read()
                except OSError:
                    continue
                if not img:
                    continue
                recorded_at, fix = _recorded_at_and_fix(gps)
                tc.detection(grade=a.grade, hazard_type=a.hazard, conf=a.conf,
                             lat=fix.get("lat"), lon=fix.get("lon"),
                             image_bytes=img, recorded_at=recorded_at)
                sent += 1
                print(f"[forwarder] 전송 #{sent}: {os.path.basename(path)} "
                      f"grade={a.grade} gps=({fix.get('lat')},{fix.get('lon')}) 대기={tc.pending()}")
            if a.duration is not None and (time.time() - start_dt.timestamp()) >= a.duration:
                break
            time.sleep(a.poll)
    except KeyboardInterrupt:
        print("\n[forwarder] 중단(Ctrl+C)")
    finally:
        end_dt = datetime.now()
        tc.session_end(end_time=end_dt.strftime("%H:%M"),
                       duration_sec=int((end_dt - start_dt).total_seconds()),
                       max_temp=None, avg_temp=None, throttle_temp=87.0,
                       max_power=None, avg_power=None, frame_drops=None,
                       total_frames=None, gps_reception=None)
        tc.stop()
        if gps is not None:
            gps.stop()
        print(f"[forwarder] 종료 · 전송 {sent}건")


if __name__ == "__main__":
    main()
