# Hail-Mary To Do

마지막 갱신: 2026-09-09

## 🚨 최우선 (데모 핵심 기능 블로커) — 해결됨

- [x] **`count=0` 버그 해결(2026-09-09)** — 코드 결함 아니었음. 원인은 렌즈 가림/조도 부족(평균 밝기 9/255 완전 블랙아웃). 조명·렌즈 조정 후 `python -m Hail_Mary.vision.preview` 재검증 완료 — 555프레임 동안 `people=1` 안정적으로 잡힘(640×384 해상도 기준)

## Jetson 실기기

- [ ] JetPack 플래싱 (`skill-jetson-flash-checklist` 참고)
- [ ] 카메라 연결 확인 (`ls /dev/video*` 또는 `v4l2-ctl --list-devices`)
- [ ] `capture.py --backend gstreamer --pipeline jetson_csi`(또는 `jetson_usb`)로 실제 프레임 수신 확인
- [ ] `PIPELINE_JETSON_CSI`/`PIPELINE_JETSON_USB`의 sensor-id·해상도를 실제 카메라값으로 조정
- [ ] 실기기에서 YOLOv8n 추론 포함 실측 FPS 측정 (목표 10~15fps)

## Zone 캘리브레이션 (실제 데모 장소 확정 후)

- [ ] `python -m Hail_Mary.edge.calibrate`로 실제 zone 폴리곤 클릭·저장
- [ ] `pipeline.py --zone-file zone.json`으로 반영 확인

## 정확도 검증 (제안서.md 4.5절/8.1절 KPI — 염세현 공식 담당)

- [ ] `python -m Hail_Mary.edge.accuracy`로 실측 20~30회 샘플링
- [ ] `meets_kpi` True 확인 (오차 ±1명 이내 또는 정확도 90%↑) — 미달 시 zone/conf 재조정

## 백엔드 (Hail-mary-Server) — 미구현분

- [ ] **M8**: 절감량(kWh) 계산 + 탄소환산(CO2 kg) — 계산 로직만, 규모 작음
- [ ] **M10/M11**: 통합 대시보드 (실시간 영상·점유율·예측그래프·이상알림·탄소지표 1화면) — 프런트엔드 필요, 규모 큼
- [ ] 서버 실배포 위치 확정 (지금은 로컬 `127.0.0.1:8000`만 검증됨) — Jetson의 `uplink.py` 엔드포인트를 실제 서버 주소로 변경 필요

## 하드웨어/현장

- [ ] 케이스(외장) 설계·제작 (3D프린팅/기성품) — 4주차 마감이라 안 급함
- [ ] 데모 시설 현장답사·설치 캘리브레이션
- [ ] (선택) 실측 파일럿 — 스마트플러그로 실제 기기 전력 소비 실측 병행

## 문서/정리

- [x] ~~`문서/` 폴더 Camera 레포에 커밋~~ — 결정 번복: `문서/`는 로컬 전용으로 유지, `.gitignore`에 추가함(`CLAUDE.md`와 동일 패턴)
- [ ] 발표자료 준비, 백업 시연 영상 촬영 (3주차 이후)

## 완료된 것 (참고)

- [x] M1 캡처 (`capture.py`) — OpenCV/GStreamer 백엔드 스위치
- [x] M1-인식 (`vision/detect.py`, YOLOv8n+ByteTrack) — 원래 이다연 담당, 선제 구현
- [x] M2 (`zones.py` + `aggregator.py`)
- [x] M3 (`buffer.py` + `uplink.py`, 자동 purge 포함)
- [x] 통합 오케스트레이션 (`pipeline.py`, 백엔드 스위치 포함)
- [x] 백엔드 M4~M7, M9 (Feature Store, Forecast Engine/Chronos-2, Ablation, Anomaly Detector, Notification) — `Hail-mary-Server` 레포로 분리, 실제 연동 테스트 완료
- [x] Hail-Mary 로고 방향 3개 (Claude Design 캔버스)
- [x] edge+vision 전체 타입 힌트 보강 + mypy 통과 (2026-09-09)
- [x] systemd 자동재시작 서비스 유닛 작성(`edge/systemd/`, 실기기 검증은 아직) (2026-09-09)
- [x] 카메라 기본 해상도 640×384로 기능명세서와 정렬 (2026-09-09)
