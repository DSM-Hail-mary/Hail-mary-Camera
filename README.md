# PoleWatch 엣지 (edge) — Jetson Orin Nano

차량 장착 카메라로 배전 전주 상단의 위험물(까치집)을 **온디바이스로 탐지·판정**하고,
판정 결과(등급 + best-frame 사진)와 기기 상태를 서버로 실시간 전송하는 엣지 코드.

**풀-파이썬 파이프라인**(탐지·판정을 우리 쪽에서 수행):
```
카메라(USB, MJPG) ──HW디코드(NVDEC)──▶ Detector(YOLOv8 TensorRT)
   └ 스레드 캡처 + 자동 재오픈                 │
                                        Judge(위험/주의/양호)
                                               │ 위험 시
                              best-frame 크롭 + 등급 ──WS──▶ 서버
   기기지표(온도/전력/fps/GPS) ────────────────WS──▶ 서버(telemetry)
```

## 환경
- Jetson Orin Nano · JetPack 7.2.1 (L4T R39.2) · Ubuntu 24.04 · Python 3.12
- CUDA 13.2 · TensorRT 10.16 · (DeepStream 9.1 설치됨 — 세현 C++용, 풀-파이썬 경로엔 불필요)
- OpenCV(GStreamer 백엔드 포함) · ultralytics

## 구성
| 파일 | 역할 |
|---|---|
| `pipeline.py` | **통합 오케스트레이터**: 카메라→탐지→판정→전송 + 기기 telemetry. 프레임단위 예외 격리 |
| `camera.py` | USB 카메라 캡처 (스레드·바운드 큐·드롭 카운터). **NVDEC HW디코드**(실패 시 V4L2 CPU 폴백) + **USB 단절 자동 재오픈** |
| `detector.py` | YOLOv8 TensorRT(ultralytics) 래퍼. 프레임→탐지결과(cls/conf/bbox/면적비) + bbox 크롭 |
| `judge.py` | 위험 등급 판정 (까치집, danger/caution/safe). ⚠ 현재 임계값은 **임시 placeholder** — 담당자가 작성 |
| `model_config.py` | **모델 교체 블럭**(단일 수정 지점): 엔진 경로 + 클래스 역할/hazard enum |
| `telemetry_client.py` | 서버 WebSocket 전송. 재연결 + 오프라인 버퍼(유실 없음, 상한 초과 시 telemetry만 드롭) |
| `metrics.py` | 실기기 지표: 온도(thermal zone)/전력(jtop·sysfs)/fps·drop(카메라 실측)/gps |
| `best_frame.py` | 크롭 중 가장 선명한 한 장 선택(Laplacian variance) + JPEG 인코딩 |
| `gps.py` / `phone_gps.py` | NMEA 수신 — 시리얼(u-blox) / 네트워크(폰, TCP·UDP). 동일 인터페이스, 재연결 내장 |
| `gst_bridge.py` | (옵션) 캡처 BGR을 TCP로 세현 C++ GStreamer에 전송 — 이제 `--gst-bridge`로 opt-in |
| `bench*.py` | 성능 벤치(순차/MJPG·YUYV/스레드/HW디코드/HW+스레드) |
| `stability_test.py` | 장기 안정성 + 장애주입 하니스 (FPS/E2E/RAM/온도/drop/reopen/exception) |
| `eval_model.py` | **라벨 val셋** conf-threshold 스윕 평가 (P/R/F1/TP/FP/FN + PR curve). 운용점 미선택 |
| `eval_unlabeled.py` | 라벨 없을 때 검출 분포/거동만 (⚠ 정확도 아님) |

## 설치
```bash
python -m venv ~/polewatch-env && source ~/polewatch-env/bin/activate
pip install -r requirements.txt
```

### 모델 준비 (best.pt → TensorRT 엔진, 1회)
```bash
yolo export model=best.pt format=engine half=True imgsz=640   # → best.engine
```
> ⚠ 세현이 커밋한 `best.onnx`는 DeepStream 전용 export(입력명 `input`, 라벨 없음, 전치 출력)라
> ultralytics로는 못 돈다. 반드시 **원본 `best.pt`에서 export한 엔진**을 쓸 것.
> 엔진 경로는 `model_config.ENGINE`에 지정.

## 실행 (pipeline.py)
```bash
# 실제 주행: 카메라→탐지→판정→전송 (기본 HW디코드 30fps, 탐지 on)
python pipeline.py --url ws://<서버IP>:8000/ws/device --gps-source phone --interval 60

# 하드웨어 없이 점검
python pipeline.py --no-camera --no-gps --interval 1 --duration 5
```
주요 플래그: `--engine`(기본 model_config) · `--conf` · `--no-detect` · `--gst-bridge`(세현 전송 켬)
· `--gps-source serial|phone` · `--phone-host/--phone-port/--phone-proto`

## 모델 교체 (블럭 방식)
업그레이드 모델로 바꿀 때 **`model_config.py` 만 수정**:
- 같은 클래스(crow_house/pole)로 재학습 → `ENGINE` 경로만 교체(드롭인)
- 클래스 체계가 다름 → `CLASS_ROLES` / `HAZARD_KIND` 도 갱신
(판정 쪽 `judge.py`는 현재 자체 상수 사용 — 운용점 확정 시 config 연결 예정)

## 성능 (Jetson 실측, 640/720p · YOLOv8n FP16)
- 캡처 병목(MJPG CPU 디코드)을 **NVDEC HW디코드 + 스레드**로 해소 → **15fps → 30fps**
- E2E 지연 66ms → **~20ms**(스레드로 프레임대기 흡수), 탐지 ~13ms
- **30분 연속**: FPS 29.97 / E2E p95 22ms / drop 0.43% / 온도 max 49.9°C(스로틀 87°C 무관) / 크래시 0

## 장애 복구
- 카메라 USB 단절 → 자동 재오픈(backoff) · 네트워크 끊김 → telemetry 재연결+버퍼
- 프레임단위 예외 격리(한 프레임 오류가 주행 전체를 안 죽임) · GPS 끊김 → 재연결

## 평가 (운용점 결정용)
```bash
# 라벨 val셋이 있을 때 (정식): conf별 P/R/F1 + PR curve, 운용점은 사용자가 결정
python eval_model.py --engine best.engine --images valid/images --labels valid/labels --out eval.csv --plot pr.png

# 라벨 없을 때 (거동만, 정확도 아님)
python eval_unlabeled.py --video drive.mp4   # 또는 --images <dir> / --camera 300
```
> P/R/F1은 **정답 라벨(GT)** 없이는 계산 불가. val셋이 없으면 세현 학습 결과의
> `runs/.../F1_curve.png`·`PR_curve.png`로 운용점을 고를 수 있음.

## 알려진 한계 / TODO
- **judge.py 임계값은 임시** — val셋 기반 운용점 확정 후 교체 (수목 판정은 현재 제외, 모델도 2클래스)
- **GPS**: iPhone-WiFi(GPS2IP)는 iOS 절전으로 링크 불안정 — 실차량은 Android USB테더/GPS모듈 권장
- 장시간 RAM 완만 증가(30분 +149MB) — 초장시간 운용 시 모니터링
