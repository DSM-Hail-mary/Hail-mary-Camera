from Hail_Mary.vision.detect import PERSON_CLASS_ID, extract_person_detections


def _box(cls, conf, xyxy, track_id):
    return {"cls": cls, "conf": conf, "xyxy": xyxy, "track_id": track_id}


def test_extract_person_detections_keeps_only_person_class():
    boxes = [
        _box(cls=PERSON_CLASS_ID, conf=0.9, xyxy=(10, 10, 30, 30), track_id=1),
        _box(cls=2, conf=0.8, xyxy=(50, 50, 90, 90), track_id=2),  # e.g. "car"
    ]

    result = extract_person_detections("2026-09-08T09:00:00Z", boxes)

    assert result["frame_ts"] == "2026-09-08T09:00:00Z"
    assert len(result["detections"]) == 1
    assert result["detections"][0]["track_id"] == 1


def test_extract_person_detections_drops_boxes_without_a_track_id():
    boxes = [
        _box(cls=PERSON_CLASS_ID, conf=0.9, xyxy=(10, 10, 30, 30), track_id=None),
        _box(cls=PERSON_CLASS_ID, conf=0.85, xyxy=(50, 50, 90, 90), track_id=5),
    ]

    result = extract_person_detections("2026-09-08T09:00:00Z", boxes)

    assert len(result["detections"]) == 1
    assert result["detections"][0]["track_id"] == 5


def test_extract_person_detections_matches_the_m2_contract_shape():
    boxes = [_box(cls=PERSON_CLASS_ID, conf=0.87, xyxy=(40, 40, 60, 60), track_id=17)]

    result = extract_person_detections("2026-09-08T09:00:00Z", boxes)

    assert result == {
        "frame_ts": "2026-09-08T09:00:00Z",
        "detections": [{"track_id": 17, "bbox": [40.0, 40.0, 60.0, 60.0], "conf": 0.87}],
    }


def test_extract_person_detections_returns_empty_list_for_no_boxes():
    result = extract_person_detections("2026-09-08T09:00:00Z", [])

    assert result == {"frame_ts": "2026-09-08T09:00:00Z", "detections": []}


def test_extract_person_detections_drops_boxes_below_min_conf():
    boxes = [
        _box(cls=PERSON_CLASS_ID, conf=0.9, xyxy=(10, 10, 30, 30), track_id=1),
        _box(cls=PERSON_CLASS_ID, conf=0.4, xyxy=(50, 50, 90, 90), track_id=2),
    ]

    result = extract_person_detections("2026-09-08T09:00:00Z", boxes, min_conf=0.5)

    assert len(result["detections"]) == 1
    assert result["detections"][0]["track_id"] == 1


def test_extract_person_detections_default_min_conf_keeps_typical_yolo_confidences():
    boxes = [_box(cls=PERSON_CLASS_ID, conf=0.3, xyxy=(10, 10, 30, 30), track_id=1)]

    result = extract_person_detections("2026-09-08T09:00:00Z", boxes)

    assert len(result["detections"]) == 1
