# Demo script (about 6 minutes)

Before you start: the stack is running (docs/RUNBOOK.md §1), you're signed out, and `e2e/fixtures/apartment.png` is at hand (regenerate it with `cd packages/contracts; py -m uv run python fixtures/synthetic_plan.py ../../e2e/fixtures`).

1. **Landing (30 s).** Open http://localhost:3000. The hero runs a live edit on a sample plan. Point out: "the AI reads the instruction; the geometry engine moves the wall; every edit is a version".
2. **Sign up (30 s).** Create an account. The dashboard opens on the first-run panel: "Start with one drawing" → **Create your first project** → name it "Riverside flat".
3. **Upload (45 s).** Drop `apartment.png`. Watch the 8-stage timeline: preprocess, walls, OCR, objects, rooms, calibration, assembly, artifacts (about 3 s). Click **Open plan**.
4. **Read the model (30 s).** The outline lists LIVING, KITCHEN, BEDROOM, HALL, BATH. Vision read the "3600" dimension, so areas are already in m² (Insights tab). Hover rooms; zoom with the wheel; press `F` to fit.
5. **Edit by text (60 s).** Press `/` and type *move the wall between the kitchen and the living room 300 mm left*, then Enter. The ghost shows the wall and both rooms changing. **Apply** → the version chip reads v2.
6. **Clarification (45 s).** Type *delete the door*. The plan has four, so it asks "Which door do you mean?". Hover a chip to locate it on the plan, click one, then Apply.
7. **Guardrails (30 s).** Type *make it look like a banana*: a friendly "didn't understand", and nothing changes. Mention that the language model never edits geometry and its output is re-validated.
8. **Voice (30 s).** Hold `V` and say *rename the bathroom to wet room*; release. The transcript lands in the bar; press Enter, then Apply.
9. **History (45 s).** `Ctrl+Z` twice, then `Ctrl+Shift+Z`. Make a new edit and open **History**: the abandoned branch is shown as *discarded*. Click an old version to view it read-only, then **Back to HEAD**.
10. **Re-process (30 s).** Back in the project, re-process the plan. Open it again and undo once: you're back on your edited model.

Fallback lines: if OmniRoute isn't configured, everything above still works (rules cover these phrasings). If voice is slow the first time, Whisper is loading its model (~15 s once).
