---
name: jetson-flash-checklist
description: Jetson Orin Nano JetPack 플래싱 및 최초 카메라 연결 체크리스트. 세팅 당일 또는 그 전날 준비 상태 점검용.
---

# jetson-flash-checklist

## 목적
개발계획서 3장 M0(9/3 착수)·1주차 Day1 작업인 JetPack 플래싱을 막히지 않고 끝내기 위한 체크리스트.

## 사전 준비 (플래싱 전날)
- [ ] Jetson Orin Nano 모델(4GB/8GB, Devkit/모듈) 확인 → 대응 JetPack 버전 확인
- [ ] JetPack 이미지 / SDK Manager 미리 다운로드 (수 GB, 당일 받으면 대기시간 손해)
- [ ] 플래싱용 Ubuntu 호스트 PC 준비 여부 확인 (없으면 VM/듀얼부팅 대안 점검)
- [ ] 플래싱 대상 스토리지(SD카드/NVMe/USB) 준비 및 여유 용량 확인
- [ ] 카메라(CSI or USB) 실물 확보 여부 확인 — 미도착 시 개발계획서 3.5절 M0 기준대로 즉시 대체 구매처 가동

## 플래싱 당일
- [ ] JetPack 플래싱 완료 후 최초 부팅 확인
- [ ] 카메라 연결 후 `ls /dev/video*` (USB) 또는 `v4l2-ctl --list-devices`로 인식 확인
- [ ] `Hail_Mary/edge/capture.py --backend gstreamer --pipeline jetson_csi --no-preview --duration 5` 로 실제 프레임 수신 확인 (skill: capture-check)
- [ ] 실패 시 `PIPELINE_JETSON_CSI`/`PIPELINE_JETSON_USB`의 sensor-id·device·해상도를 실제 값으로 수정

## 완료 기준
개발계획서 3.5절 M1(9/9, Day5): Jetson이 실시간으로 사람 수를 세고 서버 DB에 1분마다 적재 — 이 체크리스트는 그 전 단계인 "카메라 프레임이 안정적으로 나온다"까지를 커버한다.
