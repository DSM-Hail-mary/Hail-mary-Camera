# PoleWatch 엣지 (edge) — Jetson

Jetson Orin Nano에서 도는 코드. 카메라 캡처와 서버 텔레메트리 전송을 담당한다.

## 설치
```bash
pip install -r requirements.txt
```

## 구성
| 파일 | 역할 |
|---|---|
| `pipeline.py` | **통합 오케스트레이터**: 카메라+지표+GPS+서버전송 (session_start→telemetry→session_end) |
| `camera.py` | USB 카메라 캡처 (스레드 · 바운드 큐 · 드롭 카운터) |
| `gps.py` | USB GPS(u-blox) NMEA 수신 (pyserial+pynmea2, 백그라운드 스레드) |
| `metrics.py` | 실제 기기 지표 수집 (온도=thermal zone / 전력=jtop·sysfs / fps·drop=카메라 실측 / gps) |
| `telemetry_client.py` | 서버로 실시간 전송 (WebSocket, 재연결·오프라인 버퍼) — 기기 telemetry + 전주 `detection` |
| `best_frame.py` | 전주당 여러 크롭 중 가장 선명한(흔들림 적은) 한 장 선택 (Laplacian variance) |

## 통합 실행 (pipeline.py)
```bash
# 실제 주행 (Jetson): 60초마다 telemetry 전송, Ctrl+C까지
python pipeline.py --url ws://<서버IP>:8000/ws/device --interval 60

# 하드웨어 없이 오케스트레이션 점검 (카메라/GPS 없이)
python pipeline.py --no-camera --no-gps --interval 1 --duration 5
```
- 실제 전력값(W)은 `jetson-stats` 설치 시 `jtop`으로 정확히 측정. 미설치 시 sysfs INA3221 근사 → 그래도 없으면 `null`.
- 온도는 thermal zone에서 실측, fps/frame_drop은 카메라 캡처 통계에서 실측.

### 개별 점검
```bash
python metrics.py                       # 온도·전력·스냅샷 확인
python gps.py --port /dev/ttyACM0 --seconds 5   # GPS 수신 확인
```

## 전주 판정 결과 전송 (사진)

온디바이스 판정(위험/주의/양호)이 나오면, 전주당 여러 크롭 중 **가장 선명한 한 장**을
골라 서버로 실시간 전송한다. (영상 미전송 원칙 유지 · best-frame으로 흔들림 최소화)

```python
from telemetry_client import TelemetryClient
from best_frame import select_best, encode_jpeg

best, _ = select_best(pole_crops)       # 여러 크롭 중 최선명
tc.detection(grade="danger", hazard_type="nest", conf=0.9,
             lat=lat, lon=lon, image_bytes=encode_jpeg(best))
```
파이프라인에서는 `emit_detection(tc, gps, grade, hazard_type, conf, crops)` 헬퍼로 한 번에 처리.

## 텔레메트리 클라이언트

서버(`server/main.py`)의 `WS /ws/device`로 연결해 주행 세션을 스트리밍한다.
프로토콜: `session_start` → `telemetry` × N → `session_end` (상세는 `문서/API_명세서.md` §2).

- **자동 재연결 + 오프라인 버퍼**: Wi-Fi가 끊겨도 메시지를 버퍼에 쌓고, 재연결 시
  순서대로 flush한다. 전송 성공 전까지 버퍼에서 제거하지 않아 **유실이 없다**.
- 백그라운드 스레드로 동작해 주 파이프라인(캡처·추론)을 막지 않는다.

### 데모 (가상 주행을 서버로 전송)
```bash
# 서버를 먼저 띄운 상태에서
python telemetry_client.py --url ws://<서버IP>:8000/ws/device --points 5
```

### 파이프라인에서 사용 예
```python
from telemetry_client import TelemetryClient
from metrics import read_temp_c, read_power_w

tc = TelemetryClient("ws://<서버IP>:8000/ws/device").start()
tc.session_start("Jetson Nano", "2026-09-28", "10:00")

# 주행 루프에서 주기적으로 (예: 1분마다)
tc.telemetry(t="10:01",
             temp=read_temp_c(),        # 온도(°C)
             power=read_power_w(jt),    # 전력(W) — jtop 인스턴스
             drops=cam.stats.dropped,   # camera.py 드롭 카운터
             gps=1)                     # GPS 수신 1/0

tc.session_end(end_time="10:32", duration_sec=1260, max_temp=74.0, ...)
tc.stop()   # 남은 버퍼 flush 후 종료
```

## 다음 연결 지점
- `camera.py`의 `stats.dropped` → telemetry `drops`
- GPS 모듈(pyserial/pynmea2) 수신 → telemetry `gps`
- 추론 파이프라인(`vision/`)의 크롭·판정 → (전주 데이터, 별도 채널)
