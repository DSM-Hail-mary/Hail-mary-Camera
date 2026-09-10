# Hail-Mary 컨텍스트 스냅샷

> 이 파일은 매 머지(merge) 시점마다 **덮어써서** 최신 상태만 남긴다 (누적 로그 아님). 목적: 세션이 끊겨도 지금까지 결정된 것/진행 상황을 놓치지 않기 위함.

**최종 갱신**: 2026-09-11 (Server 배포 설정 추가)

## 저장소 구조 (3개로 분리됨)

| 리포 | 로컬 경로 | 내용 |
|---|---|---|
| `Hail-mary-Camera` | `D:\orca_jetson\Jetson` | 엣지(Jetson) 코드 — `Hail_Mary/edge/`, `Hail_Mary/vision/`, 기획 문서(`문서/`, 로컬 전용) |
| `Hail-mary-Server` | `D:\orca_jetson\Hail-mary-Server` | 백엔드(FastAPI) — `Hail_Mary/server/`. **`dashboard/`는 Front 리포로 이전, 이 리포에서는 삭제됨(2026-09-10)** |
| `Hail-mary-Front` | `D:\orca_jetson\Hail-mary-Front` | **신설(2026-09-10)** — M11 대시보드(순수 HTML/CSS/JS). Server의 `Hail_Mary/dashboard/`를 이전+전면 재설계 |

- GitHub 계정: `ilfpns` (gh CLI 인증됨), 조직: `DSM-Hail-mary`
- 세 리포 모두 `CLAUDE.md`는 **로컬 전용**(`.gitignore`에 추가, git 추적 안 함)
- Camera 리포의 `문서/`(제안서·기능명세서·개발계획서 등)도 로컬 전용
- 브랜치는 계속 `master`/`main`에 직접 커밋(별도 feature 브랜치 안 씀 — 브랜치 전략 문서와 실제 관행이 다른 상태 유지 중, 우선순위 낮아 방치)
- 커밋 규칙: 영어, 설명 없이 최대 7글자 (예: `add tdd`, `add m3`). 세 리포 다 동일 규칙

## 담당자
- 염세현(사용자): HW·카메라·엣지 파이프라인 담당이지만, 이다연 파트(AI 인식, 백엔드, 프론트 초안)까지 선제적으로 다 구현함. 프론트 비주얼 디자인은 디자이너에게 핸드오프(`Hail-mary-Front/기능명세서.md`)
- 이다연: 원래 AI 모델·백엔드+프런트·문서 담당 — 실제 작업 착수 여부 불명, 염세현이 대신 구현한 상태

## 완료된 것 — Camera 리포

- M1(캡처+인식 YOLOv8n+ByteTrack), M2(zone 집계), M3(로컬버퍼+업링크), 통합 오케스트레이션(`pipeline.py`)
- `calibrate.py`(zone 지정), `accuracy.py`(KPI 검증, CLI 완비: `--zone-file`/`--min-conf`/`--iou`)
- 타입 힌트 전체 적용 + mypy 클린, systemd 자동재시작 서비스(`edge/systemd/`)
- 명세서-코드 정렬: 해상도 640×384, `DEFAULT_IOU=0.5`(신규), `DEFAULT_MIN_CONF=0.45`
- **"마지막 목격 이미지" 캡처**(2026-09-10): `last_seen.py`(`LastSeenTracker`, zone count>0→0 전환 감지) + `last_seen_uplink.py`(멀티파트 업로드) + `pipeline.py` 통합(매 프레임 체크, 전환 시 JPEG 인코딩→로컬 저장(`last_seen/{zone_id}.jpg`, 덮어쓰기)→서버 업로드). `--last-seen-dir`/`--last-seen-base-url` CLI 옵션
- 테스트 74개, 커버리지 100%, mypy 클린, 전부 모킹 없음
- `count=0` 버그였던 것은 실제로는 렌즈/조명 문제였음 — 해결 완료(2026-09-09), 실제 웹캠 재검증됨

## 완료된 것 — Server 리포

- M4~M10 API 전체(Feature Store, Forecast Engine/Chronos-2, Ablation, Anomaly Detector, Savings/Carbon, Notification)
- 실제 BDG2 데이터, 실제 Chronos-2 모델
- **"마지막 목격 이미지" 저장 API**(2026-09-10): `api/last_seen.py` — `POST /api/v1/last-seen/{zone_id}`(멀티파트 업로드, zone당 1장 upsert), `GET /api/v1/last-seen`(목록), `GET /api/v1/last-seen/{zone_id}/image`(원본 JPEG 서빙). path traversal 방어 포함. `db/schema.py`에 `last_seen_image` 테이블 추가
- **`dashboard/` 삭제**(2026-09-10) — Front 리포로 이전됨, `main.py`의 `DASHBOARD_DIR`/mount 코드도 같이 정리
- 테스트 113개, 커버리지 99%
- Camera↔Server 실 연동 검증 완료(occupancy 업로드 + last-seen 이미지 업로드 둘 다 실제 curl/브라우저로 확인)
- **배포 설정 추가**(2026-09-11): `systemd/hail-mary-server.service`(재부팅/크래시 자동복구, edge 유닛과 동일 패턴) + 루트 `README.md`(프로덕션 실행: `uvicorn ... --host 0.0.0.0 --port 8000`, `HAIL_MARY_DB_PATH` 환경변수). `--host 0.0.0.0` 실제 기동 후 `/health`+실제 API 200 응답 확인(기본값 127.0.0.1로는 Jetson 엣지 기기 접근 불가하다는 점도 이때 확인). systemd 자체 검증은 edge 유닛과 동일한 한계(Windows 개발 PC라 `systemd-analyze verify` 불가, 수동 문법 재검토만)

## 완료된 것 — Front 리포 (2026-09-10 신설)

- Server의 `Hail_Mary/dashboard/`(순수 HTML+JS+CSS, 기능 위주 MVP)를 이전 + `dataviz` 스킬의 검증된 팔레트로 전면 재설계
- 기존 4카드(점유율/예측그래프/이상알림/절감) + 신규 3개:
  - **KPI 요약바**(4타일, 상단) — 그래프만 메인이라는 피드백으로 추가
  - **마지막 목격 이미지 카드** — zone별 갤러리, 상대시간 표시
  - **리포트/인쇄 카드** — `@media print`로 이 카드만 인쇄되도록 격리
- 예측 차트를 canvas→SVG로 교체, 호버 크로스헤어+툴팁, 표(table) 보기 토글 추가(접근성 — 차트엔 항상 표 대안)
- 다크모드 토글(localStorage), 반응형(880/620/520px 브레이크포인트)
- `format.js` 순수함수 33개 테스트(모킹 없음), CSS `grid-auto-flow: dense`로 레이아웃 빈틈 해결
- **실제 엔드투엔드 통합 검증**: Server(FastAPI)+Front를 같은 origin으로 임시 결합해 실제 이미지 업로드→표시까지 브라우저로 확인, 콘솔 에러 0건
- 디자이너 핸드오프용 `기능명세서.md` 작성(화면구성/API/디자인토큰/열린이슈 정리) — 비주얼 리디자인은 디자이너가 이어서 진행할 예정
- **예측 그래프 종류 탭 추가**(2026-09-10): 선/막대/산점도 3종 전환(`#chartTypeToggle`). `format.js`에 `layoutBarGroup()`(그룹 막대 x좌표 계산, 순수함수, TDD로 테스트 3개 추가) + `app.js` `renderForecastChart()`가 `chartType`에 따라 선(path)/막대(rect)/산점도(circle) 분기 렌더링. 표 보기 전환 시 이 탭은 자동 숨김. 실제 Server(FastAPI)+Front를 같은 origin으로 임시 결합, 실제 forecast 데이터로 브라우저에서 3종 전환 모두 스크린샷 검증(콘솔 에러 0건). 테스트 33→36개(전부 통과)

## 개인정보 처리방침 변경 (2026-09-10, 중요)

- 원래 정책: 카메라 원본 영상 저장·전송 안 함, 집계 숫자만 외부 전달
- **변경**: "마지막 목격 이미지" 예외 도입 — zone이 비는 전환 순간의 프레임 1장을 zone당 최신 1장만 저장(누적 로그 아님, 전환마다 교체). 개발자(염세현) 승인으로 도입
- `문서/제안서.md` 9장, `문서/개발_기능명세서.md` M2 섹션에 이 예외 문서화됨(로컬 전용 파일, git 추적 안 됨 — 팀 공유 시 별도 전달 필요)
- **후속 조치 필요(미완)**: 영상정보처리기기 설치 고지판 문구에 "이미지가 일시 저장됨" 반영 — 아직 안 씀

## 아직 안 된 것 (`TODO.md` 참고, Camera 리포 루트)

- Jetson 실기기 세팅(JetPack 플래싱)조차 아직 안 함 — 계속 미뤄지는 중, 1주차 마일스톤(9/9 DoD) 기준 미달 상태 유지
- Zone 실측 캘리브레이션, 정확도 KPI 실측 — Jetson+실제 데모 장소 필요, 도구는 코드 레벨 검증 완료
- 서버 실배포 위치 미정(로컬만 검증됨)
- 케이스 제작, 발표자료/백업영상/리허설
- Front 비주얼 리디자인(디자이너 작업 대기)
- 개인정보 고지판 문구 갱신

## 보안 노출 이력
- GitHub PAT(`ghp_...`)가 채팅에 평문 노출된 적 있음 → 폐기 권장함 (폐기 여부 미확인)
