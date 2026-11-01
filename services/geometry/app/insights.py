"""Deterministic plan insights. Areas come from the polygons, never from the stored `area_px`."""

from collections import Counter

from aec_contracts import FloorPlanModel, Insights, MetricInsights, RoomRef, polygon_area

from .engine.geom import room_polygons, rooms_by_side


def build_insights(model: FloorPlanModel) -> Insights:
    areas = [polygon_area(r.polygon) for r in model.rooms]
    total_area = sum(areas)
    average = total_area / len(areas) if areas else 0.0
    refs = [RoomRef(id=r.id, label=r.label_text, area_px=round(a, 2)) for r, a in zip(model.rooms, areas, strict=True)]

    polygons = room_polygons(model)
    total_length = interior = 0.0
    for wall in model.walls:
        total_length += wall.length_px
        one_side, other_side = rooms_by_side(model, wall, polygons)
        if one_side and other_side:
            interior += wall.length_px
    exterior = total_length - interior

    metric = None
    if (mm := model.coordinate_system.mm_per_pixel) is not None:
        m2, m = (mm / 1000) ** 2, mm / 1000
        metric = MetricInsights(total_area_m2=round(total_area * m2, 2), average_room_area_m2=round(average * m2, 2),
                                total_wall_length_m=round(total_length * m, 2),
                                exterior_wall_length_m=round(exterior * m, 2),
                                interior_wall_length_m=round(interior * m, 2))
    return Insights(
        counts=model.summary(),
        total_area_px=round(total_area, 2), average_room_area_px=round(average, 2),
        largest_room=max(refs, key=lambda r: r.area_px, default=None),
        smallest_room=min(refs, key=lambda r: r.area_px, default=None),
        total_wall_length_px=round(total_length, 2), exterior_wall_length_px=round(exterior, 2),
        interior_wall_length_px=round(interior, 2),
        rooms_by_type=Counter(r.room_type for r in model.rooms),
        metric=metric,
    )
