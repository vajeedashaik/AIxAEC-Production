"""ChangeSet: id-diff plus value-diff, in model order."""

from aec_contracts import ChangeSet, FloorPlanModel

_LISTS = ("walls", "doors", "windows", "columns", "stairs", "furniture", "dimensions", "rooms")


def build_changes(before: FloorPlanModel, after: FloorPlanModel) -> ChangeSet:
    changes = ChangeSet()
    for name in _LISTS:
        old = {e.id: e for e in getattr(before, name)}
        new = {e.id: e for e in getattr(after, name)}
        changes.added += [i for i in new if i not in old]
        changes.modified += [i for i in new if i in old and new[i] != old[i]]
        changes.removed += [i for i in old if i not in new]
    return changes
