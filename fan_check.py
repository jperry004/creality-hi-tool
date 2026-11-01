#!/usr/bin/env python3
"""
fan_check.py - check the fans on a Creality Hi (uses hi_tool.py's Moonraker connection).

  python fan_check.py 104            read-only: fan states + whether the 50% fan cap is active
  python fan_check.py 104 --watch 60 read-only while PRINTING: samples the part fan for 60 s
  python fan_check.py 104 --test     idle only: M106 -> PWM mapping, then spins each fan so you
                                     can confirm by ear/hand that it really runs
  python fan_check.py 104 --noise    idle only: steps the part fan 50..100%, you enter a dB reading
                                     (phone app) + a 1-5 loudness rating at each step; suggests the
                                     highest level you rated OK and saves a CSV in hi_backups/
       --levels 40,60,80,100         custom steps (%)    --blind   random order, levels hidden
       --ok 2                        highest rating you'd accept (default 3)

Fans on the Hi:
  fan0       part-cooling fan (output_pin, nozzle MCU PA11), power-enabled by fanp0 (PB6)
  hotend_fan heatsink fan (heater_fan, runs automatically when nozzle > 50 C)
  board_fan  mainboard fan (output_pin PA0)
None of them has a tachometer, so the printer CANNOT tell if a fan has died.
"""
import argparse, csv, os, random, sys, time
import datetime as dt
import hi_tool
from hi_tool import Printer, ToolError

OBJS = ("output_pin fan0", "output_pin fanp0", "output_pin board_fan", "heater_fan hotend_fan",
        "gcode_macro Rmode", "gcode_macro Qmode", "gcode_macro PRINTER_PARAM",
        "print_stats", "extruder")

def pct(v):
    return "%3.0f%%" % (100.0 * (v or 0))

def read(p):
    s = p.query(*OBJS)
    g = lambda k, f, d=None: (s.get(k) or {}).get(f, d)
    return {
        "fan0": g("output_pin fan0", "value", 0.0),
        "fanp0": g("output_pin fanp0", "value", 0.0),
        "board": g("output_pin board_fan", "value", 0.0),
        "hotend": g("heater_fan hotend_fan", "speed", 0.0),
        "rmode": int(g("gcode_macro Rmode", "flag", 0) or 0),
        "qmode": int(g("gcode_macro Qmode", "flag", 0) or 0),
        "fan0_min": float(g("gcode_macro PRINTER_PARAM", "fan0_min", 51) or 51),
        "state": g("print_stats", "state", "?"),
        "file": g("print_stats", "filename", ""),
        "temp": g("extruder", "temperature", 0.0),
    }

def is_patched(p):
    """True if hi_tool.py fix-fan is loaded (M106 S255 = true 100%), None if unknown."""
    try:
        cfg = p.configfile().get("config", {})
    except ToolError:
        return None
    g = next((v.get("gcode", "") for k, v in cfg.items() if k.lower() == "gcode_macro m106"), "")
    return "fan0_min]|max" in g

def expected_pwm(S, r):
    """Mirror of [gcode_macro M106] for fan 0 (stock, or with the fix-fan patch). Returns 0..255."""
    if S <= 0:
        return 0.0
    mn = r["fan0_min"]
    if r.get("patched"):
        return min(max(S, mn), 255.0)
    if r["rmode"] == 0:
        v = S / 2 if S > mn * 2 else mn
    else:
        v = (255 - mn) / 255 * S
        if S < mn:
            v = mn
    return min(v, 255.0)

def show(r):
    hi_tool.log("  print state : %s %s" % (r["state"], r["file"]))
    hi_tool.log("  nozzle temp : %.0f C" % r["temp"])
    hi_tool.log("  part fan    : fan0 PWM %s   power enable fanp0=%s" % (pct(r["fan0"]), "ON" if r["fanp0"] else "OFF"))
    hi_tool.log("  hotend fan  : %s  (auto above 50 C)" % pct(r["hotend"]))
    hi_tool.log("  board fan   : %s" % pct(r["board"]))
    hi_tool.log("  modes       : Rmode(sport)=%d  Qmode(quiet)=%d  fan0_min=%d" % (r["rmode"], r["qmode"], r["fan0_min"]))
    if r.get("patched"):
        hi_tool.log("  fan fix     : PRESENT - slicer fan %% = real fan %% (floor %d = %.0f%%)" % (r["fan0_min"], r["fan0_min"] / 2.55))
    elif r["rmode"] == 0:
        hi_tool.log("  ** Stock M106 halves the part fan in normal mode: slicer S255 (100%%) -> PWM %.0f/255 (%s)."
                    % (expected_pwm(255, r), pct(expected_pwm(255, r) / 255)))
        hi_tool.log("     Slicer S51..S102 (20-40%%) all become the 20%% floor.")
    if r["qmode"]:
        hi_tool.log("  ** Quiet mode is ON: speed 40%%, part fan capped further.")
    if r["fan0"] > 0 and not r["fanp0"]:
        hi_tool.log("  !! fan0 has PWM but its power enable (fanp0) is OFF - fan would not spin.", "WARN")

def ask(q):
    try:
        return input(q + " [y/n] ").strip().lower().startswith("y")
    except EOFError:
        return False

def test(p, r):
    hi_tool.log("\n== M106 -> actual PWM (what the slicer asks vs what the fan gets)")
    hi_tool.log("   slicer   expected   measured")
    for S in (51, 102, 128, 191, 255):
        p.gcode("M106 S%d" % S); time.sleep(0.5)
        m = read(p)
        hi_tool.log("   S%-3d %3d%%    %s       %s   fanp0=%s" % (S, S / 2.55, pct(expected_pwm(S, r) / 255), pct(m["fan0"]), "ON" if m["fanp0"] else "OFF"))
    p.gcode("M107")

    results = {}
    hi_tool.log("\n== Physical check. Put your hand under the nozzle / listen.")
    p.gcode("SET_PIN PIN=fan0 VALUE=255"); time.sleep(3)
    results["part fan 100%"] = ask("Part fan at TRUE 100% now. Strong airflow from both sides of the nozzle?")
    p.gcode("SET_PIN PIN=fan0 VALUE=128"); time.sleep(3)
    results["part fan 50% (= slicer 100%)"] = ask("Now 50% - what your prints actually get at 'full' fan. Clearly weaker but still blowing?")
    p.gcode("M107")
    prev = r["board"]
    p.gcode("SET_PIN PIN=board_fan VALUE=1"); time.sleep(3)
    results["board fan"] = ask("Board fan forced ON (back/bottom of the printer). Running?")
    p.gcode("SET_PIN PIN=board_fan VALUE=%s" % (1 if prev else 0))
    if r["temp"] > 55:
        results["hotend fan"] = ask("Nozzle is hot, so the hotend heatsink fan should be running. Is it?")
    else:
        hi_tool.log("  (hotend fan skipped - only runs when the nozzle is above 50 C; heat it and rerun to check)")
    hi_tool.log("\n== Summary")
    for k, v in results.items():
        hi_tool.log("  %-30s %s" % (k, "OK" if v else "PROBLEM - check fan, connector, duct"))

def _num(q):
    while True:
        try:
            v = input(q).strip()
        except EOFError:
            return None
        if not v:
            return None
        try:
            return float(v.replace(",", "."))
        except ValueError:
            print("    a number please (or just Enter to skip)")

def _rating(q):
    while True:
        try:
            v = input(q).strip()
        except EOFError:
            return None
        if v in ("1", "2", "3", "4", "5"):
            return int(v)
        if not v:
            return None
        print("    1-5 please (or Enter to skip)")

def noise(p, levels, settle, blind, ok_max):
    hi_tool.log("\n== Part fan noise test")
    hi_tool.log("   1. Put your phone (any dB meter app) at a fixed spot, ~50 cm in front of the nozzle.")
    hi_tool.log("      Don't move it between readings - phone apps aren't calibrated, but the DIFFERENCES are good.")
    hi_tool.log("   2. Other printers/fans nearby off if you can. Read the dB value after it settles (~3 s).")
    hi_tool.log("   3. Rating: 1 barely notice | 2 fine | 3 noticeable, OK | 4 annoying | 5 SCREAMING")
    order = list(levels)
    if blind:
        random.shuffle(order)
        hi_tool.log("   BLIND: levels play in random order, shown only in the summary.")
    rows, amb = [], None
    try:
        p.gcode("M107")
        time.sleep(settle)
        amb = _num("\n  Fan OFF  - ambient dB (Enter to skip): ")
        for i, lv in enumerate(order, 1):
            pwm = int(round(lv * 2.55))
            p.gcode("SET_PIN PIN=fan0 VALUE=%d" % pwm)
            time.sleep(settle)
            got = round(read(p)["fan0"] * 100)
            label = ("#%d" % i) if blind else ("%3d%%" % lv)
            if abs(got - lv) > 2:
                hi_tool.log("  !! asked %d%% but fan0 reads %d%%" % (lv, got), "WARN")
            db = _num("  Fan %s - dB (Enter to skip): " % label)
            rt = _rating("  Fan %s - rating 1-5: " % label)
            rows.append({"level": lv, "pwm": pwm, "fan0_read": got, "db": db, "rating": rt})
    except KeyboardInterrupt:
        hi_tool.log("\n  stopped early", "WARN")
    finally:
        try:
            p.gcode("M107")
            hi_tool.log("  part fan off (M107)")
        except ToolError as e:
            hi_tool.log("  could not turn the fan off: %s - send M107!" % e, "ERROR")
    if not rows:
        return
    rows.sort(key=lambda x: x["level"])

    hi_tool.log("\n== Results %s" % p.host)
    hi_tool.log("   fan    PWM     dB   +dB vs off   rating")
    if amb is not None:
        hi_tool.log("   off      0  %5.1f        -          -" % amb)
    for x in rows:
        d = "%5.1f" % x["db"] if x["db"] is not None else "    -"
        up = "%+5.1f" % (x["db"] - amb) if (x["db"] is not None and amb is not None) else "    -"
        hi_tool.log("   %3d%%  %4d  %s       %s          %s" % (x["level"], x["pwm"], d, up, x["rating"] if x["rating"] else "-"))
    hi_tool.log("   (+3 dB = double the sound energy, +10 dB = sounds about twice as loud)")

    good = [x for x in rows if x["rating"] is not None and x["rating"] <= ok_max]
    if good:
        best = max(good, key=lambda x: x["level"])["level"]
        hi_tool.log("\n  Highest level you rated <= %d: %d%%" % (ok_max, best))
        hi_tool.log("  -> In the slicer, set the filament's max fan speed to %d%% (the fix makes slicer %% = real %%)." % best)
        hi_tool.log("     Bridges/overhangs then get %d%% instead of the old 50%% - %s." % (best, "still more cooling than stock" if best > 50 else "no better than stock!"))
    else:
        hi_tool.log("\n  No level got a rating <= %d." % ok_max)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hi_backups")
    os.makedirs(out, exist_ok=True)
    fn = os.path.join(out, "fan_noise_%s_%s.csv" % (p.host.replace(":", "_"), dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    with open(fn, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["level", "pwm", "fan0_read", "db", "rating", "ambient_db"])
        w.writeheader()
        for x in rows:
            w.writerow(dict(x, ambient_db=amb))
    hi_tool.log("  saved %s" % fn)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="104 or 192.168.1.104 or hi1=104")
    ap.add_argument("--test", action="store_true", help="active test (refuses while printing)")
    ap.add_argument("--watch", type=int, default=0, metavar="SEC", help="sample part fan for SEC seconds (safe while printing)")
    ap.add_argument("--noise", action="store_true", help="part fan noise test, idle only (dB + 1-5 rating per step)")
    ap.add_argument("--levels", default="50,60,70,80,90,100", help="noise test steps in %% (default 50,60,70,80,90,100)")
    ap.add_argument("--settle", type=float, default=4, help="seconds to let the fan spin up before reading (default 4)")
    ap.add_argument("--blind", action="store_true", help="noise test in random order, levels hidden")
    ap.add_argument("--ok", type=int, default=3, help="highest rating you accept (default 3)")
    a = ap.parse_args()
    try:
        levels = [int(v) for v in a.levels.split(",") if v.strip()]
    except ValueError:
        ap.error("--levels must be numbers like 50,70,100")
    if not levels or any(not 1 <= v <= 100 for v in levels):
        ap.error("--levels must be between 1 and 100")
    p = Printer(a.target)
    try:
        p.connect()
        r = read(p)
        r["patched"] = is_patched(p)
        hi_tool.log("== %s" % p.host)
        show(r)
        if a.watch:
            hi_tool.log("\n== Watching part fan for %d s" % a.watch)
            seen = {}
            t0 = time.time()
            while time.time() - t0 < a.watch:
                v = round(read(p)["fan0"] * 100)
                seen[v] = seen.get(v, 0) + 1
                time.sleep(0.5)
            hi_tool.log("  part fan PWM seen: " + ", ".join("%d%% x%d" % (k, n) for k, n in sorted(seen.items())))
            hi_tool.log("  highest: %d%%" % max(seen))
        if a.test:
            p.assert_idle()
            test(p, r)
        if a.noise:
            p.assert_idle()
            noise(p, levels, a.settle, a.blind, a.ok)
    except ToolError as e:
        hi_tool.log(str(e), "ERROR"); sys.exit(1)

if __name__ == "__main__":
    main()
