# Hail-Mary 컨텍스트 스냅샷

> 이 파일은 매 머지(merge) 시점마다 **덮어써서** 최신 상태만 남긴다 (누적 로그 아님). 목적: 세션이 끊겨도 지금까지 결정된 것/진행 상황을 놓치지 않기 위함.

**최종 갱신**: 2026-09-07 (CLAUDE.md 커밋 `221781b` 직후)

## 담당자 (이 리포 기준)
- 염세현: HW·카메라·엣지 파이프라인 (M1 캡처, M2 zone, M3 로컬버퍼·업링크), 케이스 제작, 현장 캘리브레이션
- 이다연: AI 모델(YOLOv8n/Chronos-2)·백엔드+프런트(경량)·문서

## 지금까지 확정된 것
- 저장소 구조: `문서/`(기획), `Hail_Mary/edge/`(엣지 코드), `.claude/skills/`(프로젝트 전용 스킬)
- `Hail_Mary/edge/capture.py`: OpenCV(Windows 개발용)/GStreamer(Jetson용) 백엔드 스위치 가능한 카메라 캡처 스크립트, X버튼/`q` 둘 다 종료 처리 완료
- 개발 규칙(CLAUDE.md): 모킹 금지, 테스트 커버리지 90%, TDD(Red-Green-Refactor), 패키지 버전 고정, 컴포넌트 네이밍 명확화
- 커밋 메시지: 설명 없이 구현 내용만 최대 7글자
- 브랜치 전략: `main` → `feature/*` → 하위 브랜치, 하위→상위 feature→main 순으로 머지
- GitHub 원격 리포 후보: `https://github.com/DSM-Hail-mary/Hail-mary-Camera.git` (확인 시점 기준 커밋 0개, 아직 origin 연결 안 함)
- `.claude/agents/`: ORCA Agent System 4종(planner/developer/reviewer/tester) 정의 완료 — Planner/Reviewer/Tester는 도구 제한으로 코드 수정 불가, Developer만 구현
- `CLAUDE.md`가 로컬 master에 커밋됨(`50178fb` 규칙정리 → `221781b` 에이전트추가, Root AI 오케스트레이션 원칙 포함). `.claude/`, `Hail_Mary/`, `문서/`는 아직 미커밋 상태
- GitHub `Hail-mary-Camera` 리포에 push 완료 — origin 연결(`https://github.com/DSM-Hail-mary/Hail-mary-Camera.git`) 후 `master` → `origin/master`로 push, 트래킹 설정됨(`gh auth login`으로 `ilfpns` 계정 인증)
- 브랜치명이 아직 `master` — 브랜치 전략 문서(`main` 기준)와 이름이 다름, `main`으로 정리 필요 여부 확인 대기 중

## 아직 안 된 것 / 다음에 챙길 것
- Jetson JetPack 플래싱 (내일 예정 — `skill-jetson-flash-checklist` 참고)
- 로컬 브랜치가 아직 `master` — 브랜치 전략(`main` 기준)과 이름이 다름, 정리 필요할 수 있음
- M1(캡처)·M2(zone 집계)·M3(로컬버퍼·업링크) 전부 완료. **더불어 M1-인식(YOLOv8n+ByteTrack, 원래 이다연님 파트)도 염세현님이 선제적으로 프로토타입 완성** — 실제 웹캠으로 사람 감지·추적 확인됨(2026-09-08)
- 다음은 `run_edge.py`(capture→vision.detect→aggregator→buffer→uplink 통합) 또는 이다연님과 인터페이스(해상도, 서버 스키마) 확정. 이제 detector가 실제로 존재하므로 임시 대체 없이 바로 통합 가능
- 서버 `/api/v1/occupancy` 실제 스키마 미확정 — `build_occupancy_payload()`에 격리해둠, 이다연님 실제 엔드포인트 나오면 그 함수만 수정
- capture.py를 실제 프레임 소비하는 곳(이다연의 AI 인식 모듈)과 언제/어떻게 연결할지 인터페이스 합의 필요(해상도 640x384 vs 1280x720)
- 이번에 만든 `.claude/agents/*.md`(ORCA 역할)가 이번 세션에서 인식 안 됨 — 세션 재시작 후 재확인 필요

## 최근 완료된 작업 (2026-09-07, 미커밋)
- `Hail_Mary/edge/capture.py` 리팩터: `open_source()`(카메라/영상 소스 활성화, opencv+gstreamer 백엔드, 카메라 인덱스뿐 아니라 파일 경로도 허용)와 `stream_frames()`(연속 프레임 스트리밍 제너레이터)를 재사용 가능한 함수로 분리 — CLI(`main()`)도 이 함수들을 사용하도록 변경
- TDD Red→Green으로 진행: `Hail_Mary/edge/tests/test_capture.py` 7개 테스트, 실제 비디오 파일(cv2.VideoWriter로 생성)로 검증(모킹 없음)
- `capture.py` 커버리지 100% 달성 (`main()`의 인터랙티브 루프만 `# pragma: no cover`로 명시적 제외 — 실제 카메라/디스플레이 필요해서 skill-capture-check로 수동 검증)
- pytest==9.1.1, pytest-cov==7.1.0 설치 및 `Hail_Mary/edge/requirements-dev.txt`에 버전 고정
- 실제 웹캠으로 리팩터 후 정상 동작 재확인(--no-preview --duration 3, ~30fps)
- `Hail_Mary/edge/zones.py` 신규(M2 일부): `bbox_center`, `point_in_zone`(ray-casting), `count_people_in_zone` — 순수 좌표 계산, AI/이미지 처리 없음. TDD Red→Green, 테스트 7개 통과, 커버리지 100%
- `Hail_Mary/edge/aggregator.py` 신규(M2): `aggregate_window()` — 윈도우 마지막 프레임 스냅샷 방식으로 count 산출. 테스트 4개, 커버리지 100%
- `Hail_Mary/edge/buffer.py` 신규(M3): `LocalBuffer`(SQLite insert/fetch_pending/fetch_all/mark_uploaded/purge_older_than). 테스트 6개, 커버리지 100%
- 전체 edge 테스트 스위트 24개 전부 통과, 전체 커버리지 100% (`capture.py`의 인터랙티브 `main()`만 pragma 제외)
- Hail-Mary 로고 방향 3개(Focus Ring 추천/Bolt Monogram/Signal Pulse)를 Claude Design 캔버스로 만들어 게시: https://claude.ai/code/artifact/595d043f-8b8f-4b87-a968-6206303e3e56 (사용자 소유, 편집 가능)
- `Hail_Mary/edge/uplink.py` 신규(M3): `Uplink.upload_batch()`(HTTP 배치 POST, 지수 백오프 재시도), `build_occupancy_payload()`(서버 스키마 미확정이라 이 함수 하나로 격리). 테스트 6개, 실제 로컬 HTTP 서버(성공/실패/커넥션에러/재시도-후-성공)로 검증, 모킹 없음, 커버리지 100%
- 이 커밋으로 M1+M2+M3 전체 edge 테스트 스위트 30개, 커버리지 100%
- `Hail_Mary/vision/` 신규(원래 이다연님 담당, 염세현님이 선제 프로토타입): `detect.py`(`extract_person_detections` — YOLO 출력을 M1→M2 계약 스키마로 변환, 순수함수 테스트 4개 100%), `preview.py`(실시간 웹캠+YOLOv8n+ByteTrack 미리보기, `python -m Hail_Mary.vision.preview`로 실행). `ultralytics==8.4.142`, `torch==2.14.0` 설치 및 버전 고정(`vision/requirements.txt`)
- 실제 웹캠으로 라이브 검증 완료: 사람 감지·트래킹 정상 동작(모킹 없음, 실제 모델+실제 카메라)
- Hail_Mary 전체(edge+vision) 테스트 35개, 커버리지 100%

## 최근 노출 이력 (보안)
- GitHub PAT(`ghp_...`)가 채팅에 평문 노출됨 → 폐기 권장함 (폐기 여부 미확인)
