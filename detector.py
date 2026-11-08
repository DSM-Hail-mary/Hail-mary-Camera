"""
detector.py — 온디바이스 탐지기 (YOLOv8 TensorRT, 풀-파이썬)

세현 학습모델(best.pt → TensorRT FP16 엔진)로 프레임에서 까치집/전주를 탐지한다.
판정(judge.py)이 쓰기 좋은 정규화된 결과 리스트를 돌려준다.

엔진 준비(best.pt 받은 뒤, 1회):
  source ~/polewatch-env/bin/activate
  yolo export model=best.pt format=engine half=True imgsz=640
  # → best.engine (입력명 images·클래스명·표준출력 포함 → ultralytics 그대로 구동)

주의: 세현이 커밋한 best.onnx는 DeepStream 전용 export(입력명 input, 라벨 없음,
      전치 출력)라 ultralytics로는 못 돈다. 반드시 best.pt에서 export한 엔진을 쓸 것.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import model_config   # 모델 교체 블럭(엔진 경로/클래스 역할)


@dataclass
class Detection:
    cls_id: int
    cls_name: str
    conf: float
    xyxy: tuple          # (x1, y1, x2, y2) 원본 프레임 픽셀 좌표
    area_ratio: float    # bbox 면적 / 프레임 면적 (0~1) — 크기/근접도 지표


class Detector:
    def __init__(self, engine_path: str = model_config.ENGINE, conf: float = 0.25,
                 iou: float = 0.45, imgsz: int = model_config.IMGSZ,
                 names_override: Optional[dict] = None):
        from ultralytics import YOLO
        self.model = YOLO(engine_path, task="detect")
        self.conf, self.iou, self.imgsz = conf, iou, imgsz
        # best.pt에서 export했으면 엔진에 클래스명이 들어있음. 혹시 없으면 override 사용.
        self.names = names_override or self.model.names

    def infer(self, img_bgr) -> list[Detection]:
        """BGR 프레임 1장 → Detection 리스트."""
        r = self.model.predict(img_bgr, conf=self.conf, iou=self.iou,
                               imgsz=self.imgsz, verbose=False)[0]
        h, w = img_bgr.shape[:2]
        frame_area = float(w * h) or 1.0
        out: list[Detection] = []
        for b in r.boxes:
            cid = int(b.cls)
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            out.append(Detection(
                cls_id=cid,
                cls_name=str(self.names.get(cid, cid)),
                conf=float(b.conf),
                xyxy=(x1, y1, x2, y2),
                area_ratio=area / frame_area,
            ))
        return out


def crop_region(img_bgr, xyxy, pad: float = 0.08):
    """탐지 bbox에 여유(pad)를 둔 크롭 영역 (x1,y1,x2,y2) 픽셀. 비정상이면 프레임 전체."""
    h, w = img_bgr.shape[:2]
    x1, y1, x2, y2 = xyxy
    bw, bh = x2 - x1, y2 - y1
    x1 = max(0, int(x1 - bw * pad)); y1 = max(0, int(y1 - bh * pad))
    x2 = min(w, int(x2 + bw * pad)); y2 = min(h, int(y2 + bh * pad))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, w, h
    return x1, y1, x2, y2


def crop_bbox(img_bgr, xyxy, pad: float = 0.08):
    """탐지 bbox 영역을 여유(pad)를 두고 잘라 반환 (best-frame 전송용)."""
    x1, y1, x2, y2 = crop_region(img_bgr, xyxy, pad)
    return img_bgr[y1:y2, x1:x2].copy()


def boxes_in_crop(detections, region) -> list[dict]:
    """프레임 탐지 결과를 크롭 기준 0~1 박스로 변환 (서버 crops.detections 형식).
    크롭과 겹치는 것만, 크롭 밖으로 나간 부분은 잘라서 넣는다. 상세 화면 라벨링 표시용."""
    rx1, ry1, rx2, ry2 = region
    rw, rh = float(rx2 - rx1), float(ry2 - ry1)
    out = []
    for d in detections:
        kind = model_config.DETECTION_KIND.get(d.cls_name)
        if kind is None or rw <= 0 or rh <= 0:
            continue
        x1, y1 = max(d.xyxy[0], rx1), max(d.xyxy[1], ry1)
        x2, y2 = min(d.xyxy[2], rx2), min(d.xyxy[3], ry2)
        if x2 <= x1 or y2 <= y1:
            continue
        out.append({"kind": kind, "score": round(d.conf, 3),
                    "box": {"x": round((x1 - rx1) / rw, 4), "y": round((y1 - ry1) / rh, 4),
                            "w": round((x2 - x1) / rw, 4), "h": round((y2 - y1) / rh, 4)}})
    return out
