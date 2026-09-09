"""Occupancy detection accuracy validation (제안서.md 4.5절/8.1절 KPI).

KPI: system count vs manual ground-truth count, error within +-1 person or
>=90% accuracy, sampled 20~30 times across different times of day.
AccuracyLog is pure and tested (CSV export uses a real temp file); the live
sampling tool (real camera + real model + a human typing ground truth) is
exercised manually, same as capture.py/preview.py's main().
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Hail_Mary.edge.zones import Point

KPI_TOLERANCE = 1
KPI_MIN_RATE = 0.9
KPI_MIN_SAMPLES = 20


@dataclass
class AccuracySample:
    detected_count: int
    actual_count: int
    label: str = ""


class AccuracyLog:
    def __init__(self) -> None:
        self._samples: list[AccuracySample] = []

    def record(self, detected_count: int, actual_count: int, label: str = "") -> None:
        self._samples.append(AccuracySample(detected_count, actual_count, label))

    def __len__(self) -> int:
        return len(self._samples)

    def mae(self) -> float:
        if not self._samples:
            return 0.0
        return sum(abs(s.detected_count - s.actual_count) for s in self._samples) / len(self._samples)

    def within_tolerance_rate(self, tolerance: int = KPI_TOLERANCE) -> float:
        if not self._samples:
            return 0.0
        hits = sum(1 for s in self._samples if abs(s.detected_count - s.actual_count) <= tolerance)
        return hits / len(self._samples)

    def exact_match_rate(self) -> float:
        return self.within_tolerance_rate(tolerance=0)

    def meets_kpi(
        self,
        tolerance: int = KPI_TOLERANCE,
        min_rate: float = KPI_MIN_RATE,
        min_samples: int = KPI_MIN_SAMPLES,
    ) -> bool:
        """제안서.md 8.1절: 오차 +-1명 이내(또는 정확도 90% 이상), 4.5절: 20~30회 샘플링 필요."""
        if len(self._samples) < min_samples:
            return False
        return self.within_tolerance_rate(tolerance) >= min_rate

    def summary(self) -> dict[str, Any]:
        return {
            "samples": len(self._samples),
            "mae": self.mae(),
            "exact_match_rate": self.exact_match_rate(),
            "within_1_rate": self.within_tolerance_rate(1),
            "meets_kpi": self.meets_kpi(),
        }

    def save_csv(self, path: str | Path) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["label", "detected_count", "actual_count", "abs_error"])
            for s in self._samples:
                writer.writerow([s.label, s.detected_count, s.actual_count,
                                  abs(s.detected_count - s.actual_count)])


def main(
    zone_id: str = "hall_main",
    zone_polygon: Sequence[Point] | None = None,
    out_path: str | Path = "accuracy.csv",
    camera_source: int | str = 0,
    min_conf: float | None = None,
) -> None:  # pragma: no cover -- live loop needs real camera/model/tester
    import cv2

    from Hail_Mary.edge.capture import open_source, stream_frames
    from Hail_Mary.edge.zones import count_people_in_zone
    from Hail_Mary.vision.detect import (
        DEFAULT_MIN_CONF, boxes_from_result, extract_person_detections, load_model,
    )

    if min_conf is None:
        min_conf = DEFAULT_MIN_CONF

    if zone_polygon is None:
        zone_polygon = [(0, 0), (640, 0), (640, 384), (0, 384)]

    model = load_model("yolov8n.pt")
    cap = open_source(backend="opencv", source=camera_source, width=640, height=384)
    if not cap.isOpened():
        raise SystemExit("Failed to open camera")

    log = AccuracyLog()
    print("Watch the camera. Press 'a' to log a sample (you'll be asked for the actual count), "
          "'q' to finish and save.", flush=True)

    try:
        for frame in stream_frames(cap):
            result = model.track(frame, persist=True, verbose=False, classes=[0])[0]
            boxes = boxes_from_result(result)
            detections = extract_person_detections(0, boxes, min_conf=min_conf)["detections"]
            detected_count = count_people_in_zone(detections, zone_polygon)

            cv2.putText(frame, f"system count: {detected_count}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 140, 255), 2)
            cv2.imshow("Hail-Mary accuracy check", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord("a"):
                actual = input(f"system saw {detected_count} -- actual count? ")
                log.record(detected_count=detected_count, actual_count=int(actual))
                print(f"logged ({len(log)} samples so far)", flush=True)
    finally:
        cap.release()
        cv2.destroyAllWindows()

    log.save_csv(out_path)
    print(f"saved {len(log)} samples to {out_path}", flush=True)
    print(log.summary(), flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
