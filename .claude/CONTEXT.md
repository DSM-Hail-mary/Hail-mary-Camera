# Hail-Mary 컨텍스트 스냅샷

> 이 파일은 매 머지(merge) 시점마다 **덮어써서** 최신 상태만 남긴다 (누적 로그 아님). 목적: 세션이 끊겨도 지금까지 결정된 것/진행 상황을 놓치지 않기 위함.

**최종 갱신**: 2026-09-09

## 저장소 구조 (2개로 분리됨)

| 리포 | 로컬 경로 | 내용 |
|---|---|---|
| `Hail-mary-Camera` | `D:\orca_jetson\Jetson` | 엣지(Jetson) 코드 — `Hail_Mary/edge/`, `Hail_Mary/vision/`, 기획 문서(`문서/`, 로컬 전용) |
| `Hail-mary-Server` | `D:\orca_jetson\Hail-mary-Server` | 백엔드(FastAPI) + 대시보드 — `Hail_Mary/server/`, `Hail_Mary/dashboard/` |

- GitHub 계정: `ilfpns` (gh CLI 인증됨), 조직: `DSM-Hail-mary`
- 두 리포 모두 `CLAUDE.md`는 **로컬 전용**(`.gitignore`에 추가, git 추적 안 함) — 사용자 요청
- Camera 리포의 `문서/`(제안서·기능명세서·개발계획서 등)도 **로컬 전용으로 결정**(2026-09-09) — 한 번 커밋했다가 사용자 요청으로 되돌리고 `.gitignore`에 `문서/` 추가함(`CLAUDE.md`와 동일 패턴)
- 두 리포 다 브랜치는 `main`(Camera는 원래 `master`였다가 유지 중 — 아직 rename 안 함, 우선순위 낮음). 이번 세션 작업은 전부 `master`에 직접 커밋(별도 feature 브랜치 안 씀 — 브랜치 전략 문서와 실제 관행이 다른 상태가 계속됨)
- Camera 리포 커밋 규칙: 영어, 설명 없이 최대 7글자 (예: `add tdd`, `add m3`). Server 리포도 동일 규칙 사용 중

## 담당자
- 염세현(사용자): HW·카메라·엣지 파이프라인 담당이지만, 이다연 파트(AI 인식, 백엔드 전체)까지 선제적으로 다 구현함
- 이다연: 원래 AI 모델(YOLOv8n/Chronos-2)·백엔드+프런트·문서 담당 — 아직 실제로 작업 시작했는지는 불명, 염세현이 대신 구현한 상태

## 완료된 것 — Camera 리포 (Hail_Mary/edge/, Hail_Mary/vision/)

- **M1 캡처** (`capture.py`): OpenCV/GStreamer 백엔드 스위치, `open_source()`+`stream_frames()`
- **M1 인식** (`vision/detect.py`, `preview.py`): YOLOv8n+ByteTrack, 실제 웹캠 검증됨(사람 감지·카운트 정상)
- **M2** (`zones.py`, `aggregator.py`): zone 폴리곤 판정 + 1분 윈도우 집계
- **M3** (`buffer.py`, `uplink.py`): SQLite 로컬버퍼(자동 purge 포함) + HTTP 배치 업로드(재시도)
- **통합** (`pipeline.py`): capture→detect→M2→M3 오케스트레이션, CLI로 backend/zone-file/min-conf/iou/purge 전부 조절 가능
- **`calibrate.py`**: 마우스 클릭으로 zone 폴리곤 지정·저장
- **`accuracy.py`**: 제안서.md 8.1절 KPI(오차 ±1명 이내 또는 정확도 90%↑, 20~30 샘플) 검증 도구. `pipeline.py`의 `resolve_zone()`을 재사용해 `--zone-file`/`--min-conf`/`--iou`/`--source` CLI 지원(2026-09-09 추가) — 실제 배포 설정과 동일한 값으로 KPI를 측정할 수 있게 함
- **`edge/systemd/`**(2026-09-09 신규): `hail-mary-pipeline.service` — Jetson 재부팅/크래시 시 파이프라인 자동 재시작(`Restart=on-failure`). 기능명세서 비기능요구사항("가용성") 항목 충족. User/WorkingDirectory 등은 placeholder, 실제 systemctl 검증은 Jetson 실기기에서만 가능(Windows PC엔 systemd 자체가 없어 미검증)
- **명세서-코드 정렬(2026-09-09)**: 카메라 기본 해상도 1280×720→**640×384**(기능명세서 M1 기준)로 통일, `DEFAULT_IOU=0.5` 신규 추가(기존엔 IoU가 아예 설정 안 됐었음), `DEFAULT_MIN_CONF` 0.5→**0.45**(명세서 0.4와 기존 0.5 사이 절충, 사용자 승인)
- **타입 힌트**(2026-09-09): edge+vision 전체 프로덕션 모듈에 타입 힌트 추가, `mypy==2.3.1` dev 의존성 추가, 클린 통과
- 테스트 63개, 커버리지 100%, 전부 모킹 없음(실제 SQLite/HTTP서버/비디오파일/웹캠)
- Hail-Mary 로고(Claude Design 캔버스): https://claude.ai/code/artifact/595d043f-8b8f-4b87-a968-6206303e3e56
- `TODO.md`(리포 루트, git 추적됨) — 전체 프로젝트 체크리스트, 최신 상태로 유지 중

## 완료된 것 — Server 리포 (Hail_Mary/server/, Hail_Mary/dashboard/)

전부 별도 background 에이전트로 구현 후 직접 검증(테스트 재실행, 코드 리뷰, 실제 서버 기동+curl/API 확인)하고 커밋함.

- **M4/M5 Forecast Engine**: 실제 Amazon Chronos-2(HuggingFace `amazon/chronos-2`, 456MB) 사용
- **데이터**: 실제 BDG2(Building Data Genome Project 2), Panther 사이트 사무용 건물 3개, 2017년 8760시간
- **M6 Ablation Evaluator**, **M7 Anomaly Detector**, **M9 Notification**(WebPush, 가짜 성공처리 없음)
- **M8 Savings/Carbon Calculator** (`core/savings.py`): 실측 vs 시뮬레이션 kWh 비교 계산 공식만 구현
- **M10/M11 대시보드** (`Hail_Mary/dashboard/`): 순수 HTML+JS+fetch, REST 폴링(WebSocket 제외), 4개 위젯
- API: `POST/GET /api/v1/occupancy`(스키마가 Camera의 `uplink.build_occupancy_payload()`와 정확히 일치함을 재확인, 2026-09-09), `GET /api/v1/forecast`, `GET /api/v1/forecast/ablation`, `GET/POST /api/v1/anomaly`, `POST/GET /api/v1/savings`
- 테스트: 백엔드 92개(커버리지 99%) + 대시보드 순수로직 19개(node:test)
- **Camera↔Server 실제 연동 검증 완료**: `uplink.py`로 POST 성공, `/live` 조회 확인, `pipeline.py` 전체 라이브 루프도 실서버에 정상 업로드
- **접근성 검토 아직 안 됨** — 대시보드가 이미 구현됐는데 CLAUDE.md의 "접근성 고려" 규칙은 아직 미적용 상태로 남아있음(2026-09-09 CLAUDE.md 갱신 시 재확인)

## 오늘(2026-09-09) 해결된 핵심 이슈: `preview.py` count=0 버그

- 원인: **코드 결함이 아니었음**. 실제 프레임을 캡처해서 진단한 결과 완전히 새까만 화면(평균 밝기 9/255, YOLO가 사람뿐 아니라 전체 클래스 0개 감지)이었고, `AUTO_EXPOSURE`를 강제로 auto로 바꿔도 3.6초간 변화 없어(8.75→9.22) 노출 설정 문제도 아니었음 → **렌즈 가림/조도 부족**으로 결론
- 사용자가 렌즈/조명 조정 후 `python -m Hail_Mary.vision.preview` 재검증 → 555프레임 동안 `people=1` 안정적으로 감지됨(640×384 해상도 기준). **완전히 해결됨**

## 아직 안 된 것 (`TODO.md` 참고, Camera 리포 루트) — 전부 Jetson 실기기·실제 데모 장소가 있어야 진행 가능

- **Jetson 실기기 세팅(JetPack 플래싱)조차 아직 실제로 안 함** — 계속 미뤄지는 중, 1주차 마일스톤(9/9 DoD: "Jetson이 실시간으로 사람 수를 세고 서버 DB에 1분마다 적재") 기준 미달 상태
- **Zone 실측 캘리브레이션**: 노트북 웹캠으로 미리 해두는 게 무의미하다고 판단(2026-09-09, 사용자 지적) — zone 좌표는 카메라 설치 위치/각도에 종속적이라 실제 Jetson+데모 장소가 있어야 함. 도구(`calibrate.py`) 자체는 코드 레벨 검증 완료, 실행만 미룸
- **정확도 KPI 실측**(20~30샘플, `accuracy.py`): 같은 이유로 노트북 웹캠 실측은 KPI로 못 씀. 도구는 CLI까지 완비(위 참고), 실행만 대기
- 서버 실배포 위치 미정(로컬 127.0.0.1만 검증됨), `uplink.py` 엔드포인트를 실제 서버 주소로 바꿔야 함
- 케이스(외장) 제작 — 4주차 마감이라 안 급함
- 대시보드 접근성 검토

## 카메라 SW 사전구현 가능 항목 — 2026-09-09 기준 소진 확인

명세서(개발_기능명세서.md/개발계획서.md) 대 코드 전수 대조를 두 차례 수행(해상도, confidence, IoU, zone config.yaml 여부, M2/M3 필드명, systemd 가용성 요구사항, 문서 스키마 일치 여부, 패키지 버전 고정, 주차별 일정 항목까지). **결론: Jetson 실기기·실제 데모 장소 없이 지금 코드로 더 할 수 있는 Camera SW 작업은 없음.** 다음에 다시 이 질문이 나오면 이 섹션부터 참고할 것 — 새 코드 변경 없이 같은 대조를 반복하지 않도록.

## 보안 노출 이력
- GitHub PAT(`ghp_...`)가 채팅에 평문 노출된 적 있음 → 폐기 권장함 (폐기 여부 미확인)
