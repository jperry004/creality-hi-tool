#!/usr/bin/env python3
"""
orca_bottom_fan.py - OrcaSlicer post-processing script.

Forces the part fan to 100% on the WHOLE layer from layer 2 up to --zmax mm,
then hands the fan back to the profile. Layer 1 is left alone (fan off for bed adhesion).
Tested 2026-10-29 on the dice tower bottom (PETG, Creality Hi): fixed the curled bottom fillet.

OrcaSlicer: Print settings > Others > Post-processing scripts:
    python "C:\\path\\to\\orca_bottom_fan.py" --zmax 4
(Orca adds the gcode file path at the end and the script edits it in place.)
"""
import argparse, re

ap = argparse.ArgumentParser()
ap.add_argument("--zmax", type=float, default=4.0, help="force full fan up to this Z (mm)")
ap.add_argument("gcode")
a = ap.parse_args()

with open(a.gcode, encoding="utf-8", errors="ignore") as fh:
    lines = fh.read().split("\n")

if any(l.startswith("; HI bottom fan") for l in lines[:40]):
    raise SystemExit(0)  # already processed

out, layer, orig, inwin = [], 0, 0.0, False
for l in lines:
    if l.startswith(";LAYER_CHANGE"):
        layer += 1
    m = re.match(r";Z:([\d.]+)", l)
    if m:
        z = float(m.group(1))
        if layer >= 2 and z <= a.zmax and not inwin:
            inwin = True
            out += [l, "M106 S255 ; HI bottom fan: full fan up to Z %.1f" % a.zmax]
            continue
        if inwin and z > a.zmax:
            inwin = False
            out += [l, "M106 S%d ; HI bottom fan: back to profile fan" % round(orig)]
            continue
    m = re.match(r"M106 S([\d.]+)", l)
    if m or l.startswith("M107"):
        orig = float(m.group(1)) if m else 0.0
        if inwin:
            out.append("M106 S255")
            continue
    out.append(l)

try:
    i = out.index("; HEADER_BLOCK_END") + 1
except ValueError:
    i = 0
out.insert(i, "; HI bottom fan: part fan 100%% (whole layer) from layer 2 to Z %.1f mm" % a.zmax)
with open(a.gcode, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(out))
