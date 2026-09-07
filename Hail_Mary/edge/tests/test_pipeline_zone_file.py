from Hail_Mary.edge.calibrate import save_polygon
from Hail_Mary.edge.pipeline import DEFAULT_ZONE_ID, DEFAULT_ZONE_POLYGON, resolve_zone


def test_resolve_zone_uses_defaults_when_no_zone_file_given():
    zone_id, polygon = resolve_zone(DEFAULT_ZONE_ID, DEFAULT_ZONE_POLYGON, zone_file=None)

    assert zone_id == DEFAULT_ZONE_ID
    assert polygon == DEFAULT_ZONE_POLYGON


def test_resolve_zone_loads_from_a_real_calibration_file(tmp_path):
    zone_file = tmp_path / "zone.json"
    save_polygon(zone_file, "front_door", [(0, 0), (200, 0), (200, 150)])

    zone_id, polygon = resolve_zone(DEFAULT_ZONE_ID, DEFAULT_ZONE_POLYGON, zone_file=str(zone_file))

    assert zone_id == "front_door"
    assert polygon == [(0.0, 0.0), (200.0, 0.0), (200.0, 150.0)]
