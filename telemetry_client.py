"""
telemetry_client.py — Jetson → 서버 WebSocket 텔레메트리 클라이언트 (임베디드)

주행 중 기기 지표(온도/전력/프레임드롭/GPS)를 서버로 실시간 전송한다.
프로토콜: session_start → telemetry × N → session_end  (서버가 각 메시지에 ack)

특징:
  - 백그라운드 송신 스레드 (주 파이프라인을 막지 않음)
  - 자동 재연결 + 오프라인 버퍼: Wi-Fi가 끊겨도 메시지를 버퍼에 쌓아두고
    재연결 시 순서대로 flush (전송 성공 전까지 버퍼에서 제거하지 않음 → 유실 없음)

의존성: websocket-client  (pip install websocket-client)
서버:   main.py 의 WS /ws/device
"""
from __future__ import annotations

import base64
import json
import threading
import time
from collections import deque
from typing import Optional

import websocket  # websocket-client


class TelemetryClient:
    def __init__(self, url: str = "ws://127.0.0.1:8000/ws/device",
                 reconnect_sec: float = 2.0, timeout: float = 3.0,
                 max_buffer: int = 5000):
        self.url = url
        self.reconnect_sec = reconnect_sec
        self.timeout = timeout
        self.max_buffer = max_buffer           # 오프라인 버퍼 상한(메모리 폭주 방지)
        self._dropped_tele = 0                 # 상한 초과로 버린 telemetry 수
        self._buf: deque = deque()             # 미전송 메시지 버퍼(오프라인 대비)
        self._lock = threading.Lock()
        self._wake = threading.Event()         # 새 메시지 신호
        self._running = threading.Event()
        self._connected = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 공개 API -----------------------------------------------------------
    def start(self) -> "TelemetryClient":
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="telemetry", daemon=True)
        self._thread.start()
        return self

    def stop(self, drain_timeout: float = 5.0) -> None:
        """남은 버퍼를 최대 drain_timeout초 동안 전송 시도한 뒤 종료."""
        deadline = time.time() + drain_timeout
        while time.time() < deadline and self.pending() > 0:
            time.sleep(0.1)
        self._running.clear()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._connected.clear()

    def session_start(self, device: str, date: str, start_time: str) -> None:
        self._enqueue({"type": "session_start", "device": device,
                       "date": date, "start_time": start_time})

    def telemetry(self, t: str, temp, power, drops, gps) -> None:
        self._enqueue({"type": "telemetry", "t": t, "temp": temp,
                       "power": power, "drops": drops, "gps": gps})

    def session_end(self, **summary) -> None:
        self._enqueue({"type": "session_end", **summary})

    def detection(self, grade: str, hazard_type: Optional[str] = None,
                  conf: Optional[float] = None, lat=None, lon=None,
                  image_bytes: Optional[bytes] = None, pole_no: Optional[str] = None,
                  recorded_at: Optional[str] = None) -> None:
        """온디바이스 판정 결과 1건을 실시간 전송.
        grade: danger|caution|safe (위험/주의/양호).
        image_bytes: best-frame 크롭(JPEG 바이트) — base64로 실려 감."""
        msg = {"type": "detection", "grade": grade, "hazard_type": hazard_type,
               "conf": conf, "lat": lat, "lon": lon, "pole_no": pole_no,
               "recorded_at": recorded_at}
        if image_bytes is not None:
            msg["image_b64"] = base64.b64encode(image_bytes).decode("ascii")
        self._enqueue(msg)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def pending(self) -> int:
        with self._lock:
            return len(self._buf)

    # ---- 내부 ---------------------------------------------------------------
    def _enqueue(self, msg: dict) -> None:
        with self._lock:
            self._buf.append(msg)
            # 상한 초과 시: 오래된 telemetry만 버리고 session/detection은 보존(유실 방지)
            if len(self._buf) > self.max_buffer:
                for i, m in enumerate(self._buf):
                    if m.get("type") == "telemetry":
                        del self._buf[i]
                        self._dropped_tele += 1
                        break
                else:
                    self._buf.popleft()   # telemetry가 없으면 가장 오래된 것 제거
        self._wake.set()

    def _run(self) -> None:
        while self._running.is_set():
            try:
                ws = websocket.create_connection(self.url, timeout=self.timeout)
                self._connected.set()
                print(f"[telemetry] 연결됨: {self.url}")
                self._pump(ws)
                try:
                    ws.close()
                except Exception:
                    pass
            except Exception as e:
                self._connected.clear()
                if self._running.is_set():
                    print(f"[telemetry] 연결 끊김, {self.reconnect_sec}s 후 재시도: {e}")
                    time.sleep(self.reconnect_sec)
        self._connected.clear()

    def _pump(self, ws) -> None:
        """연결된 동안 버퍼를 순서대로 전송. 실패하면 예외를 올려 재연결시킨다."""
        while self._running.is_set():
            with self._lock:
                msg = self._buf[0] if self._buf else None
            if msg is None:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                continue
            ws.send(json.dumps(msg))     # 실패 시 예외 → _run에서 재연결(버퍼 유지)
            ws.recv()                    # ack 수신(내용은 무시)
            with self._lock:             # 전송 성공 → 버퍼에서 제거
                if self._buf and self._buf[0] is msg:
                    self._buf.popleft()


# --- 단독 실행: 서버로 가상 주행 세션 스트리밍 (전송 경로 검증) ---------------
if __name__ == "__main__":
    import argparse
    import math

    ap = argparse.ArgumentParser(description="텔레메트리 클라이언트 데모(가상 주행)")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/device")
    ap.add_argument("--points", type=int, default=5, help="telemetry 포인트 수")
    ap.add_argument("--interval", type=float, default=0.5, help="포인트 간 간격(초)")
    args = ap.parse_args()

    c = TelemetryClient(args.url).start()
    c.session_start("Jetson Nano", "2026-09-28", "10:00")

    temps, powers, drops_total, gps_ok = [], [], 0, 0
    for i in range(args.points):
        temp = round(45 + 29 * (1 - math.exp(-i / 6.0)), 1)
        power = round(8.4 + 0.9 * math.sin(i / 2.0), 2)
        drop = 0 if i % 4 else 3
        gps = 1
        temps.append(temp); powers.append(power)
        drops_total += drop; gps_ok += gps
        c.telemetry(f"10:{i:02d}", temp, power, drop, gps)
        print(f"[main] 전송 {i + 1}/{args.points}  연결={c.connected}  대기={c.pending()}")
        time.sleep(args.interval)

    c.session_end(
        end_time="10:05", duration_sec=args.points * 60,
        max_temp=max(temps), avg_temp=round(sum(temps) / len(temps), 1),
        throttle_temp=87.0, avg_power=round(sum(powers) / len(powers), 2),
        max_power=max(powers), frame_drops=drops_total,
        total_frames=args.points * 1800, gps_reception=round(gps_ok / args.points, 2),
    )
    c.stop()
    print(f"[main] 종료. 미전송 잔여={c.pending()}")
