from __future__ import annotations

import time
from typing import Optional

import cv2

COLORS = {"crow_house": (0, 0, 255), "pole": (255, 200, 0)}
LABELS = {"crow_house": "NEST", "pole": "POLE"}
GRADE_COLORS = {"danger": (0, 0, 255), "caution": (0, 200, 255), "safe": (0, 200, 0)}
FONT = cv2.FONT_HERSHEY_SIMPLEX


class Overlay:
    def __init__(self, show: bool = False, record: Optional[str] = None, fps: float = 30.0):
        self.show = show
        self.record = record
        self.fps = fps
        self.writer = None
        self._sent_until = 0.0
        self._sent_text = ""
        self._last = None
        self._fps_now = 0.0

    def mark_sent(self, grade: str, conf: float) -> None:
        self._sent_until = time.time() + 1.0
        self._sent_text = f"SENT -> server  {grade.upper()} {conf:.2f}"

    def draw(self, img, dets, result):
        now = time.time()
        if self._last is not None and now > self._last:
            inst = 1.0 / (now - self._last)
            self._fps_now = inst if self._fps_now == 0 else 0.9 * self._fps_now + 0.1 * inst
        self._last = now

        vis = img.copy()
        for d in dets:
            x1, y1, x2, y2 = map(int, d.xyxy)
            c = COLORS.get(d.cls_name, (200, 200, 200))
            cv2.rectangle(vis, (x1, y1), (x2, y2), c, 2)
            cv2.putText(vis, f"{LABELS.get(d.cls_name, d.cls_name)} {d.conf:.2f}",
                        (x1, max(18, y1 - 6)), FONT, 0.6, c, 2)

        grade = result.grade if result is not None else "-"
        cv2.putText(vis, f"JUDGE {grade.upper()}   {self._fps_now:.1f} fps", (12, 30),
                    FONT, 0.8, GRADE_COLORS.get(grade, (255, 255, 255)), 2)
        if now < self._sent_until:
            h, w = vis.shape[:2]
            cv2.rectangle(vis, (0, h - 44), (w, h), (0, 0, 255), -1)
            cv2.putText(vis, self._sent_text, (12, h - 14), FONT, 0.8, (255, 255, 255), 2)
        return vis

    def emit(self, vis) -> None:
        if self.record:
            if self.writer is None:
                h, w = vis.shape[:2]
                self.writer = cv2.VideoWriter(self.record, cv2.VideoWriter_fourcc(*"mp4v"),
                                              self.fps, (w, h))
            self.writer.write(vis)
        if self.show:
            cv2.imshow("HailMary", vis)
            cv2.waitKey(1)

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        if self.show:
            cv2.destroyAllWindows()
