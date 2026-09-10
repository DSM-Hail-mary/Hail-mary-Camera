# Hail-Mary To Do

마지막 갱신: 2026-09-10

## 🚨 최우선 (데모 핵심 기능 블로커) — 해결됨

- [x] **`count=0` 버그 해결(2026-09-09)** — 코드 결함 아니었음. 원인은 렌즈 가림/조도 부족(평균 밝기 9/255 완전 블랙아웃). 조명·렌즈 조정 후 `python -m Hail_Mary.vision.preview` 재검증 완료 — 555프레임 동안 `people=1` 안정적으로 잡힘(640×384 해상도 기준)

## Jetson 실기기

- [ ] JetPack 플래싱 (`skill-jetson-flash-checklist` 참고)
- [ ] 카메라 연결 확인 (`ls /dev/video*` 또는 `v4l2-ctl --list-devices`)
- [ ] `capture.py --backend gstreamer --pipeline jetson_csi`(또는 `jetson_usb`)로 실제 프레임 수신 확인
- [ ] `PIPELINE_JETSON_CSI`/`PIPELINE_JETSON_USB`의 sensor-id·해상도를 실제 카메라값으로 조정
- [ ] 실기기에서 YOLOv8n 추론 포함 실측 FPS 측정 (목표 10~15fps)

## Zone 캘리브레이션 (실제 데모 장소 확정 후) — 아직 시작하면 안 됨

- ⚠️ **노트북 웹캠으로 미리 해두는 게 무의미함**(2026-09-09 확인) — zone 좌표는 카메라 설치 위치·각도에 종속적이라, Jetson 실기기를 실제 데모 장소에 설치한 뒤 그 카메라로 캘리브레이션해야 실사용 가능한 값이 나옴. 도구 자체(`calibrate.py`)는 동작 검증 완료(코드 레벨), 실행만 미루는 것
- [ ] Jetson을 실제 데모 장소에 설치한 뒤 `python -m Hail_Mary.edge.calibrate`로 zone 폴리곤 클릭·저장
- [ ] `pipeline.py --zone-file zone.json`으로 반영 확인

## 정확도 검증 (제안서.md 4.5절/8.1절 KPI — 염세현 공식 담당) — 아직 시작하면 안 됨

- ⚠️ **같은 이유로 노트북 웹캠 실측은 KPI로 못 씀** — 실제 데모 카메라·거리·각도 기준이어야 유효한 수치. `accuracy.py` 자체는 코드 레벨 검증 완료
- [ ] Jetson+실제 장소 확정 후 `python -m Hail_Mary.edge.accuracy`로 실측 20~30회 샘플링
- [ ] `meets_kpi` True 확인 (오차 ±1명 이내 또는 정확도 90%↑) — 미달 시 zone/conf 재조정

## 백엔드/프론트 — 남은 것

- [x] 서버 배포 설정 준비(2026-09-11) — `Hail-mary-Server`에 `systemd/hail-mary-server.service`(재부팅/크래시 자동복구) + 루트 `README.md`(프로덕션 실행법: `--host 0.0.0.0`, `HAIL_MARY_DB_PATH`) 추가, `--host 0.0.0.0 --port 8000` 실제 기동+`/health`/실제 API 응답 확인함
- [ ] 서버 실배포 "위치"(어느 머신/IP) 확정은 여전히 미정 — 배포 도구는 준비됐지만 조직 차원의 결정 필요. 정해지면 Jetson의 `uplink.py`/`last_seen_uplink.py` 엔드포인트를 그 주소로 변경
- [ ] `Hail-mary-Front` 리포에 넘긴 `기능명세서.md` 기준으로 디자이너 비주얼 리디자인 반영 대기

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
- [x] NMS IoU 명시적 설정(`DEFAULT_IOU=0.5`) + confidence 0.45 조정 (2026-09-09)
- [x] "마지막 목격 이미지" 기능 전체 스택(Camera 캡처→Server 저장/API→Front 표시), 개인정보 처리방침 문서 갱신 포함 (2026-09-09)
- [x] `Hail-mary-Front` 리포 신설 — `Hail-mary-Server`의 `dashboard/`를 이전+재설계(KPI 요약바/마지막목격/리포트 카드 추가), 디자이너 핸드오프용 `기능명세서.md` 작성 (2026-09-09)
