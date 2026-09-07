import json

from Hail_Mary.edge.calibrate import load_polygon, save_polygon


def test_save_polygon_writes_real_json_file(tmp_path):
    out_path = tmp_path / "zone.json"

    save_polygon(out_path, "hall_main", [(10, 20), (110, 20), (110, 120), (10, 120)])

    with open(out_path) as f:
        data = json.load(f)
    assert data == {
        "zone_id": "hall_main",
        "polygon": [[10.0, 20.0], [110.0, 20.0], [110.0, 120.0], [10.0, 120.0]],
    }


def test_load_polygon_reads_back_what_was_saved(tmp_path):
    out_path = tmp_path / "zone.json"
    save_polygon(out_path, "front_door", [(0, 0), (200, 0), (200, 150)])

    zone_id, polygon = load_polygon(out_path)

    assert zone_id == "front_door"
    assert polygon == [(0.0, 0.0), (200.0, 0.0), (200.0, 150.0)]


def test_saved_polygon_works_directly_with_zones_module(tmp_path):
    from Hail_Mary.edge.zones import count_people_in_zone

    out_path = tmp_path / "zone.json"
    save_polygon(out_path, "hall_main", [(0, 0), (100, 0), (100, 100), (0, 100)])
    _, polygon = load_polygon(out_path)

    detections = [
        {"track_id": 1, "bbox": [10, 10, 30, 30]},
        {"track_id": 2, "bbox": [150, 10, 170, 30]},
    ]

    assert count_people_in_zone(detections, polygon) == 1
