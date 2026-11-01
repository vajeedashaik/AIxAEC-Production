"""The only plan context an LLM ever sees: no coordinates and no ids."""

from aec_contracts import FloorPlanModel, PlanBrief, RoomBrief


def build_brief(model: FloorPlanModel) -> PlanBrief:
    cs = model.coordinate_system
    return PlanBrief(
        rooms=[RoomBrief(label=r.label_text, room_type=r.room_type, wall_count=len(r.wall_ids)) for r in model.rooms],
        counts=model.summary(), has_scale=cs.mm_per_pixel is not None,
        image_width=cs.image_width, image_height=cs.image_height,
    )
