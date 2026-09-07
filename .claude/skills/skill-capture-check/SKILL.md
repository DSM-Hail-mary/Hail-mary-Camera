---
name: capture-check
description: Hail-Mary 카메라 캡처 스크립트(edge/capture.py)를 실행하고 FPS·백엔드 상태를 점검한다. 카메라 관련 변경 후, 또는 Jetson에서 새 파이프라인을 시험할 때 사용.
---

# capture-check

## 목적
`Hail_Mary/edge/capture.py`가 정상 동작하는지, 목표 FPS(≥10~15fps, 개발계획서 3.5절 M1 기준)를 만족하는지 빠르게 확인한다.

## 절차

1. 현재 환경 확인
   - Windows 개발 PC: `--backend opencv` (기본값)만 사용 가능 (GStreamer 미지원 빌드)
   - Jetson: `--backend gstreamer --pipeline jetson_csi`(CSI 카메라) 또는 `jetson_usb`(USB 웹캠)

2. 헤드리스로 짧게 열어 FPS 확인 (창 없이, 자동 종료)
   ```
   python Hail_Mary/edge/capture.py --no-preview --duration 5
   ```
   출력의 `fps=` 값이 10~15 미만이면:
   - Windows: 원인 파악만 하고 실제 최적화는 Jetson에서 재확인
   - Jetson: 개발계획서 5장 우선순위 컷 1번(TensorRT 전환) 검토 대상

3. 실제 화면으로 확인이 필요하면 미리보기 실행 (수동 종료: `q` 또는 창 닫기 버튼)
   ```
   python Hail_Mary/edge/capture.py
   ```

4. Jetson에서 새 카메라/파이프라인을 처음 시험할 때
   ```
   python Hail_Mary/edge/capture.py --backend gstreamer --pipeline jetson_csi --no-preview --duration 5
   ```
   `Failed to open capture` 에러가 나면 `capture.py` 상단 `PIPELINE_JETSON_CSI`의 `sensor-id`/해상도가 실제 카메라와 맞는지 먼저 확인.

## 하지 말 것
- 카메라가 없다고 더미 프레임으로 대체해서 "동작하는 척" 하지 않는다 (CLAUDE.md 모킹 금지 규칙)
