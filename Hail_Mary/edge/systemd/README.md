# hail-mary-pipeline systemd 유닛

왜 필요한가: `문서/개발_기능명세서.md`의 M1~M3 비기능 요구사항 표 — "가용성: Jetson 재부팅/네트워크
단절 후 자동 복구(M3 재전송) — systemd 재시작 정책 포함" — 을 만족하려면 네트워크 재전송(코드 레벨,
`buffer.py`/`uplink.py`)뿐 아니라 재부팅/프로세스 크래시 시 파이프라인 자체가 다시 뜨는 장치가 필요하다.

## 설치 (Jetson 현장)

```bash
sudo cp Hail_Mary/edge/systemd/hail-mary-pipeline.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hail-mary-pipeline
```

`hail-mary-pipeline.service` 안의 `User`, `WorkingDirectory`, `Environment=PYTHONPATH=...`,
`ExecStart`의 카메라/zone-file/endpoint 값은 placeholder이므로 실제 배포 계정·경로·설정에 맞게
먼저 수정한 뒤 설치할 것.

## 로그 확인

```bash
journalctl -u hail-mary-pipeline -f
```

## 검증 범위 (이 저장소에는 systemd가 없는 Windows 개발 PC라 아래로 한정)

- `systemd-analyze verify`는 실행하지 못했음(개발 PC에 systemd 자체가 없음) — 이 검증은 Jetson
  실기기에 유닛을 설치한 뒤 수행해야 한다.
- 대신 `[Unit]`/`[Service]`/`[Install]` 섹션 구성과 `Restart=`, `RestartSec=`,
  `StartLimitIntervalSec=`/`StartLimitBurst=`(이 두 개는 `[Unit]`에 위치해야 함),
  `WantedBy=multi-user.target`, `ExecStart=` 줄바꿈(`\` 연속) 문법을 systemd.unit(5)/systemd.service(5)
  매뉴얼 기준으로 수동 재검토함.
- 실제 기동/재부팅 복구/재시도 동작(카메라 연결, 모델 로드, 네트워크 단절 시나리오)은 Jetson
  실기기에서만 확인 가능.
