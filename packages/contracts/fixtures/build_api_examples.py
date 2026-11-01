"""Writes fixtures/api/*.json: one realistic response per public endpoint (CONTRACTS.md §8).

Built from apartment.model.json so ids line up. The example edit is "move the wall between the kitchen and
the living room 300 mm left" (30 px at 10 mm/px), applied for real to the coordinates.
Run after build_models.py: `uv run python fixtures/build_api_examples.py`.
"""

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
OUT = HERE / "api"
T0, T1, T2, T3 = "2026-11-01T10:00:00.000Z", "2026-11-01T10:00:02.000Z", "2026-11-01T10:00:08.412Z", \
    "2026-11-01T10:05:13.250Z"

USER_ID = "6f1c2a8e-3b4d-4e5f-8a9b-0c1d2e3f4a5b"
PROJECT_ID = "a3e1b2c4-d5f6-4a7b-8c9d-e0f1a2b3c4d5"
PROJECT2_ID = "b4f2c3d5-e6a7-4b8c-9d0e-f1a2b3c4d5e6"
JOB_ID = "c5a3d4e6-f7b8-4c9d-8e1f-a2b3c4d5e6f7"
EDIT_ID = "d6b4e5f7-a8c9-4d0e-9f2a-b3c4d5e6f7a8"
UNDO_EDIT_ID = "e7c5f6a8-b9d0-4e1f-8a3b-c4d5e6f7a8b9"
ARTIFACT_IDS = ["f8d6a7b9-c0e1-4f2a-9b4c-d5e6f7a8b9c0", "09e7b8c0-d1f2-4a3b-8c5d-e6f7a8b9c0d1",
                "1af8c9d1-e2a3-4b4c-9d6e-f7a8b9c0d1e2", "2ba9d0e2-f3b4-4c5d-8e7f-a8b9c0d1e2f3"]
STAGES = ["preprocess", "wall_detection", "ocr", "object_detection", "room_detection", "calibration",
          "semantic_assembly", "artifacts"]
STAGE_DETAIL: dict[str, dict[str, Any]] = {
    "preprocess": {"deskew_deg": 0.0, "width": 1600, "height": 1200},
    "wall_detection": {"walls": 17}, "ocr": {"texts": 6}, "object_detection": {"doors": 4, "windows": 3},
    "room_detection": {"rooms": 5}, "calibration": {"mm_per_pixel": 10.0}, "semantic_assembly": {"elements": 34},
    "artifacts": {"count": 4},
}
STORAGE = "http://127.0.0.1:54321/storage/v1/object/sign"


def area(poly: list[dict[str, float]]) -> float:
    n = len(poly)
    return abs(sum(poly[i]["x"] * poly[(i + 1) % n]["y"] - poly[(i + 1) % n]["x"] * poly[i]["y"]
                   for i in range(n))) / 2


def length(w: dict[str, Any]) -> float:
    return float(((w["end"]["x"] - w["start"]["x"]) ** 2 + (w["end"]["y"] - w["start"]["y"]) ** 2) ** 0.5)


def summary(m: dict[str, Any]) -> dict[str, int]:
    return {k: len(m[k]) for k in ("walls", "doors", "windows", "columns", "stairs", "furniture", "dimensions",
                                   "rooms")}


def insights(m: dict[str, Any]) -> dict[str, Any]:
    rooms = m["rooms"]
    areas = [area(r["polygon"]) for r in rooms]
    refs = sorted(zip(areas, rooms, strict=True), key=lambda t: t[0])
    uses: dict[str, int] = {}
    for r in rooms:
        for wid in r["wall_ids"]:
            uses[wid] = uses.get(wid, 0) + 1
    ext = sum(length(w) for w in m["walls"] if uses.get(w["id"], 0) <= 1)
    total_wall = sum(length(w) for w in m["walls"])
    by_type: dict[str, int] = {}
    for r in rooms:
        by_type[r["room_type"]] = by_type.get(r["room_type"], 0) + 1
    mpp = m["coordinate_system"]["mm_per_pixel"]
    out: dict[str, Any] = {
        "counts": summary(m), "total_area_px": sum(areas), "average_room_area_px": sum(areas) / len(areas),
        "largest_room": {"id": refs[-1][1]["id"], "label": refs[-1][1]["label_text"], "area_px": refs[-1][0]},
        "smallest_room": {"id": refs[0][1]["id"], "label": refs[0][1]["label_text"], "area_px": refs[0][0]},
        "total_wall_length_px": total_wall, "exterior_wall_length_px": ext,
        "interior_wall_length_px": total_wall - ext, "rooms_by_type": by_type, "metric": None,
    }
    if mpp:
        a, lm = (mpp / 1000) ** 2, mpp / 1000
        out["metric"] = {
            "total_area_m2": round(out["total_area_px"] * a, 2),
            "average_room_area_m2": round(out["average_room_area_px"] * a, 2),
            "total_wall_length_m": round(total_wall * lm, 2), "exterior_wall_length_m": round(ext * lm, 2),
            "interior_wall_length_m": round((total_wall - ext) * lm, 2),
        }
    return out


def move_x(m: dict[str, Any], old: float, new: float) -> tuple[dict[str, Any], list[str]]:
    """Move every wall endpoint / room vertex at x=old to x=new. Returns the new model and modified ids."""
    m = copy.deepcopy(m)
    modified: list[str] = []
    for el in m["walls"]:
        hit = False
        for p in (el["start"], el["end"]):
            if p["x"] == old:
                p["x"], hit = new, True
        if hit:
            modified.append(el["id"])
    for r in m["rooms"]:
        if any(p["x"] == old for p in r["polygon"]):
            for p in r["polygon"]:
                if p["x"] == old:
                    p["x"] = new
            r["area_px"] = area(r["polygon"])
            modified.append(r["id"])
    return m, modified


def stage_reports(done: int) -> list[dict[str, Any]]:
    out = []
    for i, name in enumerate(STAGES):
        if i < done:
            out.append({"name": name, "status": "ok", "duration_ms": 120 + 37 * i, "error": None,
                        "detail": STAGE_DETAIL[name]})
        else:
            out.append({"name": name, "status": "skipped", "duration_ms": 0, "error": None, "detail": {}})
    return out


def main() -> None:
    model = json.loads((HERE / "apartment.model.json").read_text(encoding="utf-8"))
    fp_id = model["floorplan_id"]
    living_kitchen = next(w for w in model["walls"] if w["start"] == {"x": 600, "y": 100}
                          and w["end"] == {"x": 600, "y": 550})
    moved, modified = move_x(model, 600, 570)
    moved["id"] = "3cb0e1f3-a4c5-4d6e-9f80-b9c0d1e2f3a4"  # every version is a new model document
    changes = {"added": [], "modified": modified, "removed": []}
    resolved = {"operation": "MOVE_WALL", "target_id": living_kitchen["id"], "target_query": None,
                "direction": "LEFT", "distance": {"value": 300, "unit": "mm"}}
    summary_text = "Moved wall 300 mm left; 2 rooms resized."

    job_done = {"id": JOB_ID, "floorplan_id": fp_id, "status": "COMPLETED", "attempts": 1,
                "stages": stage_reports(8), "error_message": None, "created_at": T0, "started_at": T1,
                "finished_at": T2}
    job_pending = {**job_done, "status": "PENDING", "attempts": 0, "stages": [], "started_at": None,
                   "finished_at": None}
    floorplan = {"id": fp_id, "project_id": PROJECT_ID, "version": 1, "original_filename": "apartment.png",
                 "content_type": "image/png", "size_bytes": 48213, "status": "COMPLETED",
                 "current_model_version": 1,
                 "download_url": f"{STORAGE}/floorplans/{PROJECT_ID}/{fp_id}/source.png?token=example",
                 "latest_job": job_done, "warnings": [], "created_at": T0}
    project = {"id": PROJECT_ID, "name": "Riverside Apartment", "description": "Two-bed renovation study.",
               "floorplan_count": 1,
               "thumbnail_url": f"{STORAGE}/artifacts/{PROJECT_ID}/{fp_id}/{JOB_ID}/preprocessed.png?token=example",
               "created_at": T0, "updated_at": T2}
    project2 = {"id": PROJECT2_ID, "name": "Harbour Office Fit-out", "description": None, "floorplan_count": 0,
                "thumbnail_url": None, "created_at": T0, "updated_at": T0}
    kinds = [("preprocessed", "image/png", "png"), ("walls_overlay", "image/png", "png"),
             ("detected_elements", "application/json", "json"), ("semantic_model", "application/json", "json")]

    examples: dict[str, Any] = {
        "healthz": {"status": "ok", "service": "api", "version": "0.1.0"},
        "me": {"id": USER_ID, "clerk_user_id": "user_2xAmpleClerkId", "email": "ada@example.com",
               "display_name": "Ada Architect", "created_at": T0},
        "projects.list": {"items": [project, project2], "total": 2, "limit": 20, "offset": 0},
        "projects.create": project2,
        "projects.get": project,
        "projects.update": {**project, "name": "Riverside Apartment (rev B)", "updated_at": T3},
        "floorplans.list": [floorplan],
        "floorplans.upload": {**floorplan, "status": "PENDING", "current_model_version": None,
                              "latest_job": job_pending},
        "floorplans.get": floorplan,
        "floorplans.process": job_pending,
        "floorplans.job": job_done,
        "floorplans.model": {"floorplan_id": fp_id, "version": 1, "model": model, "summary": summary(model),
                             "insights": insights(model)},
        "floorplans.artifacts": [
            {"id": aid, "job_id": JOB_ID, "kind": k, "content_type": ct, "size_bytes": 20480 + 1024 * i,
             "url": f"{STORAGE}/artifacts/{PROJECT_ID}/{fp_id}/{JOB_ID}/{k}.{ext}?token=example"}
            for i, (aid, (k, ct, ext)) in enumerate(zip(ARTIFACT_IDS, kinds, strict=True))],
        "commands.interpret": {"status": "PREVIEW", "version": 1, "model": moved, "changes": changes,
                               "command": resolved, "summary": summary_text, "question": None, "candidates": [],
                               "stage": None, "detail": None, "transcript": None, "edit_id": None},
        "commands.apply": {"status": "APPLIED", "version": 2, "model": moved, "changes": changes,
                           "command": resolved, "summary": summary_text, "question": None, "candidates": [],
                           "stage": None, "detail": None, "transcript": None, "edit_id": EDIT_ID},
        "commands.clarification": {
            "status": "CLARIFICATION", "version": 1, "model": None, "changes": None, "command": None,
            "summary": None, "question": "Which kitchen wall do you mean?",
            "candidates": [
                {"id": living_kitchen["id"], "kind": "wall", "label": "vertical wall, 450 px long, kitchen | living",
                 "x": 600, "y": 325},
                {"id": next(w["id"] for w in model["walls"] if w["start"] == {"x": 960, "y": 100}
                            and w["end"] == {"x": 960, "y": 550}),
                 "kind": "wall", "label": "vertical wall, 450 px long, kitchen | bedroom", "x": 960, "y": 325},
            ],
            "stage": None, "detail": None, "transcript": None, "edit_id": None},
        "commands.rejected": {
            "status": "REJECTED", "version": 1, "model": None, "changes": None, "command": None, "summary": None,
            "question": None, "candidates": [], "stage": "semantic_validation",
            "detail": "Set a scale first to use millimetres.", "transcript": None, "edit_id": None},
        "commands.voice": {"status": "PREVIEW", "version": 1, "model": moved, "changes": changes,
                           "command": resolved, "summary": summary_text, "question": None, "candidates": [],
                           "stage": None, "detail": None,
                           "transcript": "move the wall between the kitchen and the living room 300 mm left",
                           "edit_id": None},
        "model.undo": {"status": "APPLIED", "version": 1, "model": model, "changes": changes, "command": None,
                       "summary": "Undid: " + summary_text, "question": None, "candidates": [], "stage": None,
                       "detail": None, "transcript": None, "edit_id": UNDO_EDIT_ID},
        "model.redo": {"status": "APPLIED", "version": 2, "model": moved, "changes": changes, "command": None,
                       "summary": "Redid: " + summary_text, "question": None, "candidates": [], "stage": None,
                       "detail": None, "transcript": None, "edit_id": UNDO_EDIT_ID},
        "history": {
            "head_version": 2, "can_undo": True, "can_redo": False,
            "versions": [
                {"version": 1, "origin": "PROCESSING", "parent_version": None, "discarded": False,
                 "is_head": False, "created_at": T2, "edit_id": None},
                {"version": 2, "origin": "EDIT", "parent_version": 1, "discarded": False, "is_head": True,
                 "created_at": T3, "edit_id": EDIT_ID},
            ],
            "edits": [
                {"id": EDIT_ID, "instruction": "move the wall between the kitchen and the living room 300 mm left",
                 "operation": "MOVE_WALL", "status": "APPLIED", "stage": None, "error": None,
                 "parent_version": 1, "result_version": 2, "created_at": T3},
            ]},
        "error.stale_model": {"error": {"code": "stale_model", "message": "The plan changed since you loaded it.",
                                        "details": {"head_version": 2}}},
    }
    OUT.mkdir(exist_ok=True)
    for name, body in examples.items():
        (OUT / f"{name}.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} files to {OUT}")


if __name__ == "__main__":
    main()
