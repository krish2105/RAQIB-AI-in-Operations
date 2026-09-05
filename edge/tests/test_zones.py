from pathlib import Path

import pytest

from raqib_edge.zones import Zone, load_site

SITES = Path(__file__).resolve().parents[1] / "sites"


def test_zone_contains_normalised_and_pixel_points():
    z = Zone("q", "queue", "cam1", [(0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6)])
    assert z.contains((0.4, 0.4))
    assert not z.contains((0.9, 0.9))
    assert z.contains((400, 400), frame_wh=(1000, 1000))
    assert not z.contains((900, 900), frame_wh=(1000, 1000))


def test_zone_rejects_bad_kind_naming_the_zone():
    with pytest.raises(ValueError, match="nope"):
        Zone("nope", "parking", "cam1", [(0, 0), (1, 0), (1, 1)])


def test_zone_rejects_unnormalised_coords():
    with pytest.raises(ValueError):
        Zone("z", "queue", "cam1", [(0, 0), (1920, 0), (1920, 1080)])


def test_load_retail_demo_site():
    site = load_site(SITES / "retail_demo.yaml")
    assert site.profile == "retail"
    assert site.tills == 3
    assert {z.kind for z in site.zones} == {"entrance", "queue", "checkout", "shelf"}
    assert len(site.zones_for("cam1", "queue")) == 1
    assert site.threshold("queue_n") == 4
    assert site.threshold("reemit_s") == 300
    assert site.floor["width_m"] == 24


def test_load_factory_site():
    site = load_site(SITES / "greenlam_unit1.yaml")
    assert site.profile == "factory"
    kinds = {z.kind for z in site.zones}
    assert {"work_area", "exclusion", "machine"} <= kinds
    assert site.machines[0]["machine_id"] == 1


def test_zone_unknown_camera_rejected(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        "name: x\nprofile: retail\ncameras: {cam1: {source: file, uri: a.mp4}}\n"
        "zones: [{name: q, kind: queue, camera: cam9, polygon: [[0,0],[1,0],[1,1]]}]\n"
    )
    with pytest.raises(ValueError, match="cam9"):
        load_site(p)
