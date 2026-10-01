"""
phone_gps.py — 폰 GPS를 네트워크(NMEA)로 수신 (방법 B: USB 테더링)

폰의 GPS 공유 앱(GPS2IP, Share GPS 등)이 NMEA 문장을 내보내면, 이 모듈이 받아
파싱해 최신 위치/시각(UTC)/방향을 보관한다. gps.py(시리얼 GPS)와 **같은 인터페이스**
(.start / .read / .stop)라 pipeline에서 그대로 교체 가능.

연결 경로(USB 테더링):
  폰(USB 테더 + GPS앱) ── USB ── Jetson(usb0).  폰의 테더 IP로 접속/수신한다.
  (Android USB 테더 기본 게이트웨이 예: 폰 = 192.168.42.129)

프로토콜:
  - proto="tcp": 폰 앱(=TCP 서버)에 접속해 NMEA 스트림을 읽음. 끊기면 재연결.
  - proto="udp": 로컬 포트를 열고 폰이 쏘는 NMEA 패킷을 받음.

의존성: pynmea2
단독 검증:  python phone_gps.py --host 192.168.42.129 --port 11123 --proto tcp
"""
from __future__ import annotations

import datetime
import socket
import threading
import time
from typing import Optional

try:
    import pynmea2
except Exception:
    pynmea2 = None


class PhoneGPS:
    def __init__(self, host: str = "192.168.42.129", port: int = 11123,
                 proto: str = "tcp", retry_sec: float = 2.0):
        self.host = host
        self.port = port
        self.proto = proto.lower()
        self.retry_sec = retry_sec
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._fix = False
        self._sats = 0
        self._utc: Optional[str] = None       # ISO8601 (+00:00)
        self._heading: Optional[float] = None
        self._speed: Optional[float] = None
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    # ---- 공개 API (gps.py와 동일) ------------------------------------------
    def start(self) -> "PhoneGPS":
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="phone-gps", daemon=True)
        self._thread.start()
        return self

    def read(self) -> dict:
        with self._lock:
            return {"lat": self._lat, "lon": self._lon, "has_fix": self._fix,
                    "sats": self._sats, "utc": self._utc,
                    "heading": self._heading, "speed": self._speed}

    def stop(self) -> None:
        self._running.clear()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    # ---- 수신 루프 ----------------------------------------------------------
    def _run(self) -> None:
        if self.proto == "udp":
            self._run_udp()
        else:
            self._run_tcp()

    def _run_tcp(self) -> None:
        while self._running.is_set():
            try:
                self._sock = socket.create_connection((self.host, self.port), timeout=5)
                self._sock.settimeout(5)
                print(f"[phone_gps] TCP 연결 {self.host}:{self.port}")
                buf = b""
                while self._running.is_set():
                    data = self._sock.recv(4096)
                    if not data:
                        raise OSError("연결 종료됨")
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self._parse(line.decode("ascii", "ignore").strip())
            except OSError as e:
                with self._lock:
                    self._fix = False
                if self._running.is_set():
                    print(f"[phone_gps] 재연결 {self.retry_sec}s 후: {e}")
                    time.sleep(self.retry_sec)
            finally:
                try:
                    if self._sock:
                        self._sock.close()
                except OSError:
                    pass

    def _run_udp(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", self.port))
            s.settimeout(1.0)
            self._sock = s
            print(f"[phone_gps] UDP 수신 :{self.port}")
            while self._running.is_set():
                try:
                    data, _ = s.recvfrom(4096)
                except socket.timeout:
                    continue
                for line in data.decode("ascii", "ignore").splitlines():
                    self._parse(line.strip())
        except OSError as e:
            print(f"[phone_gps] UDP 오류: {e}")

    # ---- NMEA 파싱 (gps.py 로직 재사용) ------------------------------------
    def _parse(self, line: str) -> None:
        if not line.startswith("$") or pynmea2 is None:
            return
        try:
            msg = pynmea2.parse(line)
        except Exception:
            return
        stype = getattr(msg, "sentence_type", "")
        lat = getattr(msg, "latitude", None)
        lon = getattr(msg, "longitude", None)
        valid = lat not in (None, 0.0) and lon not in (None, 0.0)
        with self._lock:
            if stype == "GGA":
                try:
                    self._fix = int(msg.gps_qual) > 0
                except Exception:
                    pass
                try:
                    self._sats = int(msg.num_sats)
                except Exception:
                    pass
                if valid:
                    self._lat, self._lon = lat, lon
            elif stype == "RMC":
                self._fix = (getattr(msg, "status", "V") == "A") and valid
                if valid:
                    self._lat, self._lon = lat, lon
                try:
                    if msg.datestamp and msg.timestamp:
                        self._utc = datetime.datetime.combine(
                            msg.datestamp, msg.timestamp,
                            tzinfo=datetime.timezone.utc).isoformat()
                except Exception:
                    pass
                try:
                    if msg.true_course:
                        self._heading = float(msg.true_course)
                except Exception:
                    pass
                try:
                    if msg.spd_over_grnd:
                        self._speed = float(msg.spd_over_grnd)
                except Exception:
                    pass
            elif stype == "VTG":
                try:
                    if msg.true_track:
                        self._heading = float(msg.true_track)
                except Exception:
                    pass


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="폰 GPS(NMEA) 수신 확인")
    ap.add_argument("--host", default="192.168.42.129", help="폰 테더 IP")
    ap.add_argument("--port", type=int, default=11123)
    ap.add_argument("--proto", default="tcp", choices=["tcp", "udp"])
    ap.add_argument("--seconds", type=float, default=15)
    a = ap.parse_args()

    g = PhoneGPS(a.host, a.port, a.proto).start()
    t_end = time.time() + a.seconds
    while time.time() < t_end:
        print("[phone_gps]", g.read())
        time.sleep(1)
    g.stop()
