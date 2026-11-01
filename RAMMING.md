# Creality Hi - automatic part removal ("ramming") - notes

Last updated 2026-10-23. Read this before touching ramming.cfg, hi_tool.py ram/ram-check/recover-z, or hi_gui.py's Ramming tab.

## What it is
After a print, the Hi pushes finished parts off the front of the plate with the **stock toolhead casing**
(no ram blade). Macro: `REMOVE_PART_DYNAMIC` in `ramming.cfg`, installed on each Hi with
`hi_tool.py install-ram <printer> --apply` (GUI: Ramming tab > Install / update), which adds
`[include ramming.cfg]` to printer.cfg, does a host RESTART, verifies, and rolls back on failure.
Printers are listed in printers.txt (see printers.example.txt).
Never use FIRMWARE_RESTART on a Hi - it locks up and needs a power cycle; host RESTART only.

## Toolhead geometry (measured on the printer, mm from the nozzle centre)
| what | value | variable |
|---|---|---|
| front face (the pusher, -Y side) ahead of nozzle | 41 | casing_front |
| back of casing behind nozzle (carriage/gantry further back, higher) | 30 | casing_back |
| casing left / right of nozzle (symmetric) | 30 / 30 | casing_half_w |
| lowest casing edge above nozzle tip | 3 | casing_gap |
| bottom then slopes back for another | 8 | casing_slope |
| => solid vertical pushing face starts above the tip at | 11 | (gap + slope) |

The sloped bottom matters: a part that only reaches the slope gets wedged down / lifts the head instead of being pushed.
Home 0,0 puts the nozzle at about the plate's front-left corner. Axis limits: X -19..285, Y -7..273, Z max 310.
Same numbers live as CASING_* constants in hi_tool.py (ram_check prefers the printer's macro variables).
The front cover has no nozzle reference - measure from the nozzle, not from a cover model.

## Macro logic (ramming.cfg)
- Guards: refuses if `pos_guess` = 1 (position set by hand by jog-z/recover-z), if not homed xyz, or if the part
  is shorter than `min_nozzle_z + gap + slope + min_contact` = 2 + 3 + 8 + 5 = **18 mm**.
- Cool-down `WAIT` seconds (default 600) before ramming.
- Descent: casing comes down at nozzle Y = `BACK_Y` if given, else `PART_MAX_Y + casing_front + 3`
  (front face 3 mm behind the footprint); **refuses** if that is past Y max (273), i.e. parts reaching back past
  Y ~229. With neither, falls back to `CENTER_Y + 130` clamped to Y max and prints a "guess" warning.
- Lanes: `LANES` if given, else from `PART_MIN_X..PART_MAX_X`: each lane covers 50 mm (casing 60 - 10),
  lanes = 1 + 2*ceil(max(width - 50, 0) / (2*SPACING)) -> 40 mm wide: 1, 100 mm: 3, 220 mm: 7. Else 1.
- Push: toward -Y to Y min by default (`PUSH_TO_EDGE=1`; front face ends ~41 mm past the plate's front edge).
- Heights - chosen for leverage (peel beats shear):
  - **Peel** hits: solid face's bottom edge at `peel_frac` (0.5) of part height, i.e. nozzle Z = top*0.5 - 11,
    capped so >= 5 mm of face is on the part, never below LOW_Z. Repeated `peel_hits` (3) times - there is no
    sensor to know if it let go, repeated impacts fatigue the bond.
  - **Sweep** hits: nozzle at `LOW_Z` (min_nozzle_z = 2, face at 13 mm), `sweep_hits` (1, min 1) times, to push off
    whatever tipped over or slid.
  - If peel and sweep heights are within 2 mm, everything runs at the low height.
  - Examples: 20 mm part -> Z 2/2/2/2; 40 mm -> 9/9/9/2; 90 mm -> 34/34/34/2.
- Lane order: centre, then -S, +S, ... (SPACING default 40). Every height runs all lanes.
  Each stroke: travel at safe Z (top + 30, never lower than current), X/Y to lane + BACK_Y, Z down at F600,
  push Y at `RAM_SPEED` (3000), Z up, `G28 Y`. ~10-15 s per stroke.
- No M84 at the end: END_PRINT runs next and needs homed axes.

Parameters: CENTER_X, CENTER_Y, TOP_Z (required), PART_MIN_X, PART_MAX_X, PART_MAX_Y, WAIT, RAM_SPEED, LANES, SPACING, PUSH_TO_EDGE, BACK_Y,
PEEL_Z (overrides peel_frac), LOW_Z, PEEL_HITS, SWEEP_HITS.
A future **checker app** could set limits (e.g. lower PEEL_Z for tall thin parts that could snap, floors on LOW_Z)
and passes these parameters. The macro deliberately keeps only basic clamps.

## Current OrcaSlicer machine end gcode (Creality Hi)
```
G91
G1 E-4 F2700
G1 E-2 X5 Y5 F2400
G1 Z5 F1200
G90

; Move to part center and 30 mm above finished part
G1 X{first_layer_center_no_wipe_tower[0]} Y{first_layer_center_no_wipe_tower[1]} Z{max_layer_z + 30} F3000

TURN_OFF_HEATERS
M107

; Automatic part removal (footprint -> BACK_Y and lanes are worked out by the macro)
REMOVE_PART_DYNAMIC CENTER_X={first_layer_center_no_wipe_tower[0]} CENTER_Y={first_layer_center_no_wipe_tower[1]} TOP_Z={max_layer_z} PART_MIN_X={first_layer_print_min[0]} PART_MAX_X={first_layer_print_max[0]} PART_MAX_Y={first_layer_print_max[1]}

; Normal Creality Hi end-of-print routine
END_PRINT
```
(Older profiles without the PART_* params still work: 1 lane, BACK_Y guessed as centre + 130.)
Orca facts (checked in OrcaSlicer src/libslic3r/GCode.cpp): `first_layer_print_min/max` = bbox of the first-layer
convex hull **including skirt, brim and wipe tower** (conservative; a big skirt near the back can make the macro
refuse). `first_layer_center_no_wipe_tower` = centre of the objects' first-layer bbox.

## Known gaps / next steps
- Footprint is the first layer only - fine for the Hi (no-overhang designs), wrong for parts that grow wider/deeper
  higher up.
- In-print the descent uses one PART_MAX_Y for all lanes (conservative); hi_tool does it per lane strip.
- Wide plates: 7 lanes x 4 hits = 28 strokes (~6 min). Checker app may want to cap this.
- The new geometry/peel/multi-hit macro is **not yet tested on a printer**; printers still run the old one until
  Install / update (ram-check FAILs the old macro: "guessed casing size").

## Out-of-print use (hi_tool.py / hi_gui.py)
- `ram-check <printer> --gcode FILE` - readiness list (Klipper state, macro version, homing/park, heaters, part
  height, where the casing comes down vs the real part outlines, push distance). Moves nothing.
- `ram <printer> --gcode FILE [--from-park] --apply` - runs it (dry run without --apply). `--from-park` does
  SET_KINEMATIC_POSITION + `G28 X Y` after END_PRINT's M84. **Never G28 Z with parts on the plate.**
  Push to edge is the default; `--stop-short` for the old behaviour. `--casing-depth` is ignored (legacy).
- `recover-z` - after a restart with parts on the plate: home X/Y, go to a spot the whole casing clears, paper test,
  set. Sets pos_guess so the macro refuses until finished.
- Old versions of every edited file: old_versions/*.bak-before-<change> (latest: -geometry, -peel, -multihit).
