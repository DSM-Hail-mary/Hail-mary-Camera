from Hail_Mary.edge import zones

SQUARE_ZONE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_bbox_center_returns_midpoint():
    assert zones.bbox_center([40, 40, 60, 60]) == (50.0, 50.0)


def test_bbox_center_handles_non_square_box():
    assert zones.bbox_center([0, 0, 10, 20]) == (5.0, 10.0)


def test_point_in_zone_true_for_interior_point():
    assert zones.point_in_zone((50, 50), SQUARE_ZONE) is True


def test_point_in_zone_false_for_exterior_point():
    assert zones.point_in_zone((150, 50), SQUARE_ZONE) is False


def test_point_in_zone_false_for_point_outside_on_same_axis():
    assert zones.point_in_zone((50, 150), SQUARE_ZONE) is False


def test_count_people_in_zone_counts_only_interior_detections():
    detections = [
        {"track_id": 1, "bbox": [40, 40, 60, 60]},   # center (50,50) -> inside
        {"track_id": 2, "bbox": [140, 40, 160, 60]},  # center (150,50) -> outside
        {"track_id": 3, "bbox": [10, 10, 30, 30]},   # center (20,20) -> inside
    ]

    assert zones.count_people_in_zone(detections, SQUARE_ZONE) == 2


def test_count_people_in_zone_returns_zero_for_empty_detections():
    assert zones.count_people_in_zone([], SQUARE_ZONE) == 0
