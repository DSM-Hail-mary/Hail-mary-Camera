"""
judge.py — 위험 등급 판정 (다연 담당)

detector.py가 낸 탐지결과 스트림을 받아 전주 1건의 위험 등급을 판정한다.
등급은 서버 contract에 맞춘다:  danger(위험) / caution(주의) / safe(양호)

현재 범위: **까치집(crow_house)만** 판정 (수목 판정 안 함).
           전주(pole)는 맥락 정보로만 존재.

── 판정 로직은 이 파일에서 작성 ──
아래 Judge.update()의 TODO 구역이 실제 규칙을 넣는 곳이다.
지금은 파이프라인이 끝까지 돌도록 하는 **최소 기본 규칙**이 들어있다(교체 대상).
활용 가능한 신호: conf(신뢰도) · area_ratio(bbox 크기/근접도) · 연속 검출 프레임 수.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

HAZARD_CLASS = "crow_house"   # 까치집. (수목 미판정)


@dataclass
class Judgement:
    grade: str                 # "danger" | "caution" | "safe"
    hazard_type: str           # 위험 유형 (예: "까치집")
    conf: float
    bbox: tuple                # 크롭용 (x1,y1,x2,y2)
    emit: bool                 # True면 서버로 전송 (전주당 1건 등 중복 억제는 여기서)


class Judge:
    """까치집 위험 판정기.

    프레임마다 update(detections)를 호출하면, 전송할 판정이 있을 때 Judgement를,
    없으면 None을 돌려준다. 연속 검출 수 같은 상태는 내부에서 관리한다.
    """

    def __init__(self, conf_danger: float = 0.60, conf_caution: float = 0.35,
                 min_consecutive: int = 3, cooldown_frames: int = 60):
        # TODO(다연): 아래 임계값은 PR곡선/검증셋으로 보정할 것 (지금은 임시값)
        self.conf_danger = conf_danger        # 이 이상이면 위험 후보
        self.conf_caution = conf_caution      # 이 이상이면 주의 후보
        self.min_consecutive = min_consecutive  # 연속 N프레임 검출돼야 확정(깜빡임 억제)
        self.cooldown_frames = cooldown_frames  # 전송 후 N프레임은 재전송 안 함(중복 억제)
        self._streak = 0
        self._cooldown = 0

    def update(self, detections) -> Optional[Judgement]:
        if self._cooldown > 0:
            self._cooldown -= 1

        # 1) 까치집 후보만 추림 (수목 미판정)
        houses = [d for d in detections if d.cls_name == HAZARD_CLASS]
        if not houses:
            self._streak = 0
            return None

        # 2) 가장 신뢰도 높은 1건 기준 (전주당 대표 1건)
        top = max(houses, key=lambda d: d.conf)
        self._streak += 1

        # ──────────────────────────────────────────────────────────────
        # TODO(다연): 실제 등급 규칙을 여기에 작성.
        #   예시 신호: top.conf, top.area_ratio, self._streak, 연속 재방문 등
        #   아래는 파이프라인 검증용 **임시** 규칙 (반드시 교체):
        if top.conf >= self.conf_danger:
            grade = "danger"
        elif top.conf >= self.conf_caution:
            grade = "caution"
        else:
            grade = "safe"
        # ──────────────────────────────────────────────────────────────

        # 3) 전송 여부: 연속 검출 충족 + 쿨다운 아님 + 위험/주의일 때만
        emit = (self._streak >= self.min_consecutive
                and self._cooldown == 0
                and grade in ("danger", "caution"))
        if emit:
            self._cooldown = self.cooldown_frames

        return Judgement(grade=grade, hazard_type="까치집", conf=round(top.conf, 3),
                         bbox=top.xyxy, emit=emit)
