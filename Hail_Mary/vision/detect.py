"""Person detection (M1-recognition half).

Wraps YOLOv8n (+ built-in ByteTrack via ultralytics' .track()) and converts its
output into the M1->M2 contract: {frame_ts, detections: [{track_id, bbox, conf}]}.
extract_person_detections() is pure and testable without loading a real model;
load_model()/boxes_from_result() are the thin adapter around the actual model.
"""

from collections.abc import Sequence
from typing import Any

PERSON_CLASS_ID = 0  # COCO class index for "person"
DEFAULT_MIN_CONF = 0.45  # 개발_기능명세서.md M1 기본값(0.4)과 기존 보수값(0.5) 사이 절충, applied consistently across pipeline.py/accuracy.py/preview.py
DEFAULT_IOU = 0.5  # 개발_기능명세서.md M1: NMS IoU 기본값 0.5, applied consistently across pipeline.py/accuracy.py/preview.py


def extract_person_detections(
    frame_ts: float | str, boxes: Sequence[dict[str, Any]], min_conf: float = 0.0
) -> dict[str, Any]:
    detections = [
        {
            "track_id": int(box["track_id"]),
            "bbox": [float(v) for v in box["xyxy"]],
            "conf": float(box["conf"]),
        }
        for box in boxes
        if box["cls"] == PERSON_CLASS_ID and box["track_id"] is not None and box["conf"] >= min_conf
    ]
    return {"frame_ts": frame_ts, "detections": detections}


def load_model(weights: str = "yolov8n.pt") -> Any:  # pragma: no cover -- downloads/loads a real model file
    from ultralytics import YOLO
    return YOLO(weights)


def boxes_from_result(result: Any) -> list[dict[str, Any]]:  # pragma: no cover -- depends on real ultralytics Results objects
    boxes = result.boxes
    if boxes is None or boxes.id is None:
        return []
    return [
        {
            "cls": int(boxes.cls[i]),
            "conf": float(boxes.conf[i]),
            "xyxy": tuple(boxes.xyxy[i].tolist()),
            "track_id": int(boxes.id[i]),
        }
        for i in range(len(boxes))
    ]
