"""
gps.py — USB GPS(u-blox 계열) NMEA 수신 (pyserial + pynmea2)

백그라운드 스레드로 시리얼을 읽어 최신 위치/수신상태를 보관한다.
시리얼 포트/모듈이 없거나 실패해도 예외 없이 has_fix=False로 동작한다(비-Jetson 환경 안전).
"""
from __future__ import annotations

import threading
import time
from typing import Optional

try:
    import serial  # pyserial
except Exception:
    serial = None
try:
    import pynmea2
except Exception:
    pynmea2 = None


class GPS:
    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._fix = False
        self._sats = 0
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ser = None

    # ---- 공개 API -----------------------------------------------------------
    def start(self) -> "GPS":
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="gps", daemon=True)
        self._thread.start()
        return self

    def read(self) -> dict:
        """최신 GPS 상태. {lat, lon, has_fix, sats}"""
        with self._lock:
            return {"lat": self._lat, "lon": self._lon,
                    "has_fix": self._fix, "sats": self._sats}

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2.0)
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass

    # ---- 내부 ---------------------------------------------------------------
    def _run(self) -> None:
        while self._running.is_set():
            try:
                if serial is None:
                    raise RuntimeError("pyserial 미설치")
                self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
                print(f"[gps] open {self.port} @ {self.baud}")
                while self._running.is_set():
                    raw = self._ser.readline().decode("ascii", errors="ignore").strip()
                    if not raw.startswith("$") or pynmea2 is None:
                        continue
                    try:
                        msg = pynmea2.parse(raw)
                    except Exception:
                        continue
                    self._update(msg)
            except Exception as e:
                with self._lock:
                    self._fix = False
                if self._running.is_set():
                    print(f"[gps] 연결 실패, 2s 후 재시도: {e}")
                    time.sleep(2.0)
            finally:
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass

    def _update(self, msg) -> None:
        stype = getattr(msg, "sentence_type", "")
        lat = getattr(msg, "latitude", None)
        lon = getattr(msg, "longitude", None)
        fix = False
        sats = 0
        if stype == "GGA":
            try:
                fix = int(msg.gps_qual) > 0
            except Exception:
                fix = False
            try:
                sats = int(msg.num_sats)
            except Exception:
                sats = 0
        elif stype == "RMC":
            fix = getattr(msg, "status", "V") == "A"
        else:
            return
        valid = lat not in (None, 0.0) and lon not in (None, 0.0)
        with self._lock:
            if valid:
                self._lat, self._lon = lat, lon
            self._fix = fix and valid
            if sats:
                self._sats = sats


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="GPS 수신 확인")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args()

    g = GPS(port=args.port).start()
    t_end = time.time() + args.seconds
    while time.time() < t_end:
        print("[gps]", g.read())
        time.sleep(1.0)
    g.stop()
