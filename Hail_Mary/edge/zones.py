"""Zone occupancy counting (M2).

Takes detection bboxes already produced by the vision/AI step (M1) and answers a
pure geometry question: how many of them fall inside a defined zone polygon. No
image data or AI model involved here.
"""

from collections.abc import Sequence
from typing import Any

Point = tuple[float, float]


def bbox_center(bbox: Sequence[float]) -> Point:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def point_in_zone(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at_y:
                inside = not inside
    return inside


def count_people_in_zone(detections: Sequence[dict[str, Any]], polygon: Sequence[Point]) -> int:
    return sum(
        1 for detection in detections
        if point_in_zone(bbox_center(detection["bbox"]), polygon)
    )
