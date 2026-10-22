"""Final canonical assembly (audit stage 10) — regression tests.

Proves the assembler preserves canonical furniture coordinates EXACTLY, never
adds/removes/moves furniture, keeps UNCERTAIN entities, uses wall-ownership for
openings, and is deterministic. Uses the real reference plan as the fixture.
"""

from app.services import canonical_assembly_service as ca
from app.services import floor_plan_service as fps

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
_KEYS = ("uid", "item_id", "cx", "cy", "w", "h", "rotation")


def test_furniture_coordinates_preserved_verbatim():
    raw = {str(f["uid"]): f for f in fps.get_canonical(FID)["furniture"]}
    out = ca.assemble(FID)
    assert len(out["furniture"]) == len(raw)                      # none added/removed
    assert {str(f["uid"]) for f in out["furniture"]} == set(raw)  # same identities
    for f in out["furniture"]:
        src = raw[str(f["uid"])]
        assert f["item_id"] == src["item_id"]                     # type unchanged
        for k in ("cx", "cy", "w", "h", "rotation"):
            assert float(f[k]) == float(src[k]), f"{f['uid']}.{k} changed"  # exact, not moved


def test_no_furniture_key_missing():
    out = ca.assemble(FID)
    for f in out["furniture"]:
        for k in _KEYS:
            assert k in f


def test_deterministic_identical_output():
    a = ca.assemble(FID)
    b = ca.assemble(FID)
    assert a["content_hash"] == b["content_hash"]
    assert a["furniture"] == b["furniture"]
    assert a["architecture"] == b["architecture"]


def test_architecture_preserves_source_geometry():
    out = ca.assemble(FID)
    arch = out["architecture"]
    assert arch["coordinate_space"] == "world_px"
    assert len(arch["walls"]) > 0
    assert all("x1" in w and "y1" in w and "source_wall_ids" in w for w in arch["walls"])
    assert all(r.get("status") in ("CONFIRMED", "UNCERTAIN") for r in arch["rooms"])


def test_openings_use_wall_ownership():
    out = ca.assemble(FID)
    for o in out["architecture"]["openings"]:
        if o.get("status") == "VALID":
            assert o.get("supporting_wall_id") is not None      # attached to a wall


def test_uncertain_entities_preserved():
    out = ca.assemble(FID)
    summ = out["uncertainty_summary"]
    # the reference plan has open-plan/circulation openings + fallback rooms that
    # must remain UNCERTAIN, never fabricated into confident assignments.
    assert summ["counts"]["uncertain_rooms"] >= 1
    assert set(summ["uncertain_rooms"]).issubset(
        {r["id"] for r in out["architecture"]["rooms"] if r["status"] == "UNCERTAIN"})


def test_report_and_summary_present():
    out = ca.assemble(FID)
    for k in ("furniture_count", "walls", "rooms_confirmed", "rooms_uncertain",
              "openings", "text_engine", "vision_status", "stages"):
        assert k in out["report"]
    assert out["report"]["furniture_count"] == len(out["furniture"])
    assert "counts" in out["uncertainty_summary"]


def test_text_and_vision_advisory_off_by_default():
    out = ca.assemble(FID)
    assert out["text"] == []                                    # OCR opt-in
    assert out["vision_validation"]["status"] == "skipped"      # vision opt-in
    assert out["furniture_candidates"] == []                    # detections never in `furniture`


def test_annotated_image_renders_png():
    png = ca.render_annotated_image(FID)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 2000


# ── Pure-unit determinism of the content hash (no DB) ─────────────────────────

def test_content_hash_is_coordinate_sensitive():
    furn = [{"uid": "u1", "item_id": "bed", "cx": 100.0, "cy": 50.0, "w": 40.0,
             "h": 60.0, "rotation": 0.0}]
    arch = {"walls": [], "rooms": [], "openings": []}
    h1 = ca._content_hash(furn, arch)
    h2 = ca._content_hash([{**furn[0]}], {"walls": [], "rooms": [], "openings": []})
    assert h1 == h2                                             # identical input → identical hash
    moved = [{**furn[0], "cx": 101.0}]                          # 1px move
    assert ca._content_hash(moved, arch) != h1                 # detected
