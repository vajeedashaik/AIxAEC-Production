"""RENAME_ROOM and SET_SCALE: no coordinates change."""

from aec_contracts import CalibrationSource, FloorPlanModel, RenameRoom, SetScale, Source
from aec_contracts.lexicon import room_type_for_text

from ..geom import find


def rename_room(model: FloorPlanModel, command: RenameRoom) -> FloorPlanModel:
    room = find(model.rooms, command.target_id)
    room.label_text = command.name
    room.room_type = command.room_type or room_type_for_text(command.name)[0]
    room.source = room.room_type_source = Source.USER_CONFIRMED
    room.confidence = room.room_type_confidence = 1.0
    return model


def set_scale(model: FloorPlanModel, command: SetScale) -> FloorPlanModel:
    cs = model.coordinate_system
    cs.mm_per_pixel = command.length_mm / find(model.walls, command.target_id).length_px
    cs.calibration_source = CalibrationSource.MANUAL
    cs.calibration_confidence = 1.0
    return model
