"""
model_config.py — 탐지 모델 "교체 블럭" (단일 수정 지점)

탐지 모델을 업그레이드/교체할 때 **이 파일만 바꾸면** 되도록 모델 메타데이터를
한 곳에 모은다. 파이프라인·탐지기는 여기 값을 기본값으로 쓴다.

교체 시나리오
  - 같은 클래스(crow_house/pole)로 재학습한 엔진  → ENGINE 경로만 교체(드롭인)
  - 클래스 체계가 다른 새 모델(예: 수목 추가)      → CLASS_ROLES / HAZARD_KIND 도 갱신

주의: judge.py 는 아직 자체 상수(HAZARD_CLASS/HAZARD_KIND)를 쓴다. 모델을 바꿔
      클래스명이 달라지면, 추후 judge.py 가 이 파일을 import 하도록 연결하면 된다
      (지금은 요청에 따라 judge.py 미수정 → 아래 값이 판정 쪽과 일치하는지 확인만).
"""

# ── 현재 모델: 세현 YOLOv8 (best.pt → TensorRT FP16), 2클래스 ──────────────
ENGINE = "/home/jetson_dsm/polewatch/models/best.engine"
IMGSZ = 640

# 모델이 내는 클래스명 → 의미 역할
#   "hazard"  = 위험물(판정 대상)
#   "context" = 맥락 정보(전주 등, 판정 제외)
CLASS_ROLES = {
    "crow_house": "hazard",   # 까치집 = 위험물
    "pole": "context",        # 전주 = 맥락
    # 미래 업그레이드 예) "tree": "hazard",
}

# 위험물 클래스명 → 서버 contract enum (PoleRecord.hazard = Literal["nest","tree"])
HAZARD_KIND = {
    "crow_house": "nest",
    # "tree": "tree",
}


def hazard_classes():
    """위험(hazard)으로 분류된 모델 클래스명 목록."""
    return [c for c, r in CLASS_ROLES.items() if r == "hazard"]
