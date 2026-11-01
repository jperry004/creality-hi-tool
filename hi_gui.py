#!/usr/bin/env python3
"""
hi_gui.py - small window on top of hi_tool.py for the Creality Hi printers.

Double-click hi_gui.bat (or: python hi_gui.py). Standard library only (tkinter).
Every button runs the same hi_tool.py command you would type and shows its output below,
so the CLI and the GUI always behave the same - including the dry-run-first safety rules.

Tabs
  Printer   info, errors, config backup, RESTART, send a gcode line, Fluidd camera (preview the Hi's
            built-in camera and add it to Fluidd)
  Ramming   install the ram macro, pick a sliced gcode, readiness check, preview, RAM NOW
  Pressure  pressure advance, in sub-tabs:
            Status & tweak  live/saved K, lock, silent mode, Motion Advance, pre-flight, tweak live, save default
            Line test       our own line-test print (each line a different K)
            Orca tower      settings to type into Orca, check the sliced tower, watch it print, height -> K
            Logs & results  printer console history, all printers at a glance, live-watch CSVs, change log,
                            results notebook per printer + filament (pa_results.csv next to this script)
            Guide           what PA is, how to read the tests, Hi gotchas, to-do checklist
  Fixes     part-fan fix, restart direction-pin bug (check / prove / fix / repro), key22 homing fix + tests
  Recover Z after a Klipper restart with parts still on the plate: home X/Y, paper-test Z at a
            spot clear of the parts (never G28 Z)
"""
import csv
import json
import os
import queue
import shlex
import sys
import threading
import tkinter as tk
import time
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
PA_RESULTS = os.path.join(HERE, "pa_results.csv")
PA_RESULT_COLS = ("date", "printer", "filament", "nozzle_c", "k", "smooth", "method", "notes")
PA_TODO = os.path.join(HERE, "pa_todo.json")
os.chdir(HERE)  # hi_backups/ and printers.txt live next to the scripts
sys.path.insert(0, HERE)
import hi_tool  # noqa: E402


def load_printers():
    out = []
    try:
        with open(os.path.join(HERE, "printers.txt"), encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.split("#", 1)[0].strip()
                if ln:
                    out.append(ln)
    except OSError:
        pass
    return out or ["hi1=101"]


class QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Creality Hi tool")
        self.geometry("980x860")
        self.minsize(800, 620)
        self.q = queue.Queue()
        sys.stdout = sys.stderr = QueueWriter(self.q)  # pythonw has no console; every print lands in Output
        self.watching = False
        self.busy = False
        self.buttons = []
        self.last_cmd = None
        pad = dict(padx=6, pady=3)

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Printer").pack(side="left")
        self.printer = ttk.Combobox(top, values=load_printers(), width=24)
        self.printer.current(0)
        self.printer.pack(side="left", padx=6)
        self.verdict = tk.Label(top, text="", font=("Segoe UI", 11, "bold"), padx=10)
        self.verdict.pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="x", **pad)
        self._printer_tab(nb)
        self._ram_tab(nb)
        self._recover_tab(nb)
        self._pa_tab(nb)
        self._cfs_tab(nb)
        self._fixes_tab(nb)
        nb.select(1)
        hi_tool._ask = self.gui_ask  # interactive steps (diagnose / repro) ask in a dialog instead of the console

        out = ttk.Frame(self)
        out.pack(fill="both", expand=True, **pad)
        bar = ttk.Frame(out)
        bar.pack(fill="x")
        ttk.Label(bar, text="Output").pack(side="left")
        ttk.Button(bar, text="Clear", command=lambda: self.text.delete("1.0", "end")).pack(side="right")
        self.text = tk.Text(out, wrap="none", font=("Consolas", 9), bg="#111", fg="#ddd", insertbackground="#ddd")
        for tag, col in (("ok", "#5fd35f"), ("warn", "#f0c040"), ("fail", "#ff6060"), ("cmd", "#7fb7ff")):
            self.text.tag_configure(tag, foreground=col)
        sb = ttk.Scrollbar(out, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.status = ttk.Label(self, text="ready", anchor="w")
        self.status.pack(fill="x", padx=6, pady=(0, 4))
        self.after(100, self.drain)

    # ================================================================ tabs
    def _printer_tab(self, nb):
        pad = dict(padx=6, pady=4)
        f = ttk.Frame(nb)
        nb.add(f, text="  Printer  ")
        row = ttk.Frame(f)
        row.pack(fill="x", **pad)
        for label, cmd in (("Info", "info"), ("Errors", "errors"), ("Backup config (pull)", "pull"),
                           ("Homing config", "homing"), ("RESTART", "restart")):
            self._btn(row, label, lambda c=cmd: self.run_simple(c)).pack(side="left", padx=2)
        self._btn(row, "RECOVER (Klipper error)", lambda: self.run_args(
            ["recover", self.target(), "--apply"] + self._ssh_args())).pack(side="left", padx=(16, 2))
        bz = ttk.LabelFrame(f, text="Buzzer (over SSH - uses the root password from the Fixes tab)")
        bz.pack(fill="x", padx=6, pady=4)
        self.bz = {k: tk.StringVar(value=v) for k, v in (("freq", str(hi_tool.BEEP_LOUD_HZ)), ("ms", "200"), ("times", "1"))}
        self._btn(bz, "Beep", self.beep).pack(side="left", padx=4, pady=4)
        for k, lbl, w in (("freq", "Hz", 6), ("ms", "ms", 5), ("times", "times", 3)):
            ttk.Entry(bz, textvariable=self.bz[k], width=w).pack(side="left", padx=(6, 1))
            ttk.Label(bz, text=lbl).pack(side="left")
        self._btn(bz, "Find beeper", lambda: self.run_args(
            ["beep", self.target(), "--probe"] + self._ssh_args())).pack(side="left", padx=(18, 2))
        self._btn(bz, "Deep check", lambda: self.run_args(
            ["beep", self.target(), "--deep"] + self._ssh_args())).pack(side="left", padx=2)
        ttk.Label(bz, text="checks are read-only", foreground="#666").pack(side="left", padx=6)
        bz2 = ttk.Frame(f)
        bz2.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Label(bz2, text="Tune").pack(side="left")
        self.bz_tune = ttk.Combobox(bz2, values=sorted(t for t in hi_tool.TUNES if t != "sweep"), width=11, state="readonly")
        self.bz_tune.set("countdown")
        self.bz_tune.pack(side="left", padx=4)
        self._btn(bz2, "Play", lambda: self.play_tune(False)).pack(side="left", padx=2)
        ttk.Label(bz2, text="transpose").pack(side="left", padx=(8, 2))
        self.bz_tr = tk.StringVar(value="0")
        ttk.Spinbox(bz2, from_=-24, to=24, textvariable=self.bz_tr, width=4).pack(side="left")
        self._btn(bz2, "Find loudest pitch", lambda: self.checked_run(
            ["beep", self.target(), "--tune", "sweep"] + self._ssh_args(), "play the pitch sweep")).pack(side="left", padx=(8, 2))
        ttk.Label(bz2, text="or your own notes").pack(side="left", padx=(16, 4))
        self.bz_notes = tk.StringVar(value="C7:150 E7:150 G7:150 -:80 C8:400")
        ttk.Entry(bz2, textvariable=self.bz_notes, width=36).pack(side="left", fill="x", expand=True)
        self._btn(bz2, "Play notes", lambda: self.play_tune(True)).pack(side="left", padx=4)
        ttk.Label(f, text="Notes: C7 / F#6 / Bb7 or a number in Hz, :ms for length (default 150), - for a rest. "
                          "Loudest around octave 7 (2-4 kHz).", foreground="#666").pack(anchor="w", padx=12)
        g = ttk.Frame(f)
        g.pack(fill="x", **pad)
        ttk.Label(g, text="Send gcode").pack(side="left")
        self.gline = tk.StringVar()
        e = ttk.Entry(g, textvariable=self.gline)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Return>", lambda _e: self.send_gcode())
        self._btn(g, "Send", self.send_gcode).pack(side="left")
        ttk.Label(f, text="FIRMWARE_RESTART is blocked (it locks up the Hi). Motion commands refuse while printing.",
                  foreground="#666").pack(anchor="w", **pad)

        jz = ttk.LabelFrame(f, text="Move Z without homing (look at a part that G28 Z would hit)")
        jz.pack(fill="x", **pad)
        r1 = ttk.Frame(jz)
        r1.pack(fill="x", padx=4, pady=2)
        ttk.Label(r1, text="1  The toolhead is roughly at Z").pack(side="left")
        self.jz_z = tk.StringVar(value="")
        ttk.Entry(r1, textvariable=self.jz_z, width=6).pack(side="left", padx=4)
        self._btn(r1, "Unlock Z here", self.jz_unlock).pack(side="left", padx=6)
        ttk.Label(r1, text="nothing moves; a guess is fine - it only sets how far down you can jog",
                  foreground="#666").pack(side="left")
        r2 = ttk.Frame(jz)
        r2.pack(fill="x", padx=4, pady=2)
        ttk.Label(r2, text="2  Jog (watch the nozzle):").pack(side="left")
        for dz in ("-10", "-1", "-0.1", "+0.1", "+1", "+10"):
            self._btn(r2, "Z " + dz, lambda d=dz: self.run_args(
                ["jog-z", self.target(), "--dz", d, "--apply"])).pack(side="left", padx=2)
        self._btn(r2, "Done - lock (motors off)", lambda: self.run_args(
            ["jog-z", self.target(), "--lock", "--apply"])).pack(side="left", padx=12)
        ttk.Label(jz, text="After unlocking, Klipper's X, Y AND Z are guesses - ramming is blocked until you lock and do Recover Z.",
                  foreground="#a00").pack(anchor="w", padx=6, pady=(0, 4))

        cam = ttk.LabelFrame(f, text="Camera in Fluidd (the Hi's built-in camera, port 8000)")
        cam.pack(fill="x", **pad)
        c1 = ttk.Frame(cam)
        c1.pack(fill="x", padx=4, pady=2)
        self._btn(c1, "Preview stream", self.cam_preview).pack(side="left", padx=2)
        self._btn(c1, "Check (dry run)", lambda: self.cam_add([self.target()], False)).pack(side="left", padx=2)
        self._btn(c1, "Add camera to this printer", lambda: self.cam_add([self.target()], True)).pack(side="left", padx=2)
        self._btn(c1, "Add to all printers", lambda: self.cam_add(self.all_printers(), True)).pack(side="left", padx=2)
        c2 = ttk.Frame(cam)
        c2.pack(fill="x", padx=4, pady=2)
        self._btn(c2, "List cameras", lambda: self.run_args(["webcam", "list", self.target()])).pack(side="left", padx=2)
        self._btn(c2, "List all printers", lambda: self.run_args(["webcam", "list"] + self.all_printers())).pack(side="left", padx=2)
        self._btn(c2, "Open Fluidd", self.open_fluidd).pack(side="left", padx=2)
        self._btn(c2, "Remove a camera...", self.cam_remove).pack(side="left", padx=12)
        ttk.Label(cam, text="Only adds the camera entry Fluidd shows (printers that already have it are skipped) - moves nothing, "
                            "safe while printing. Reload Fluidd after.", foreground="#666").pack(anchor="w", padx=6, pady=(0, 4))

    def _ram_tab(self, nb):
        pad = dict(padx=6, pady=3)
        f = ttk.Frame(nb)
        nb.add(f, text="  Ramming  ")

        # 1 macro
        inst = ttk.LabelFrame(f, text="1  Macro on the printer (ramming.cfg)")
        inst.pack(fill="x", **pad)
        self.cfg_path = tk.StringVar(value=hi_tool.default_ram_cfg())
        ttk.Entry(inst, textvariable=self.cfg_path).grid(row=0, column=0, sticky="ew", **pad)
        self._btn(inst, "Browse...", self.pick_cfg).grid(row=0, column=1, **pad)
        self._btn(inst, "Check (dry run)", lambda: self.run_install(False)).grid(row=0, column=2, **pad)
        self._btn(inst, "Install / update", lambda: self.run_install(True)).grid(row=0, column=3, **pad)
        inst.columnconfigure(0, weight=1)

        # 2 part
        part = ttk.LabelFrame(f, text="2  The part")
        part.pack(fill="x", **pad)
        self.gcode_path = tk.StringVar()
        ttk.Label(part, text="Sliced gcode").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(part, textvariable=self.gcode_path).grid(row=0, column=1, columnspan=5, sticky="ew", **pad)
        self._btn(part, "Browse...", self.pick_gcode).grid(row=0, column=6, **pad)
        self.v = {k: tk.StringVar(value=d) for k, d in (
            ("cx", ""), ("cy", ""), ("top", ""), ("wait", "0"), ("lanes", "1"), ("spacing", "40"),
            ("speed", ""), ("depth", "56"))}
        for i, (k, lbl) in enumerate((("cx", "Centre X"), ("cy", "Centre Y"), ("top", "Top Z"))):
            ttk.Label(part, text=lbl).grid(row=1, column=i * 2, sticky="e", **pad)
            ttk.Entry(part, textvariable=self.v[k], width=9).grid(row=1, column=i * 2 + 1, sticky="w", **pad)
        self.foot = ttk.Label(part, text="pick a gcode file to fill these in (it also gives the check the real part outlines)",
                              foreground="#666")
        self.foot.grid(row=2, column=0, columnspan=7, sticky="w", **pad)
        part.columnconfigure(5, weight=1)

        # 3 options
        opt = ttk.LabelFrame(f, text="3  Options")
        opt.pack(fill="x", **pad)
        fields = (("wait", "Wait before ram (s)"), ("lanes", "Lanes"), ("spacing", "Lane spacing (mm)"),
                  ("speed", "Ram speed (mm/min, blank = macro)"))
        for i, (k, lbl) in enumerate(fields):
            r, c = divmod(i, 3)
            ttk.Label(opt, text=lbl).grid(row=r, column=c * 2, sticky="e", **pad)
            ttk.Entry(opt, textvariable=self.v[k], width=8).grid(row=r, column=c * 2 + 1, sticky="w", **pad)
        self.push_edge = tk.BooleanVar(value=True)
        self.from_park = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Push all the way to the front edge", variable=self.push_edge).grid(
            row=2, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(opt, text="Printer is parked after END_PRINT (home X/Y only, keep Z)",
                        variable=self.from_park).grid(row=2, column=3, columnspan=3, sticky="w", **pad)
        preset = ttk.Frame(opt)
        preset.grid(row=3, column=0, columnspan=6, sticky="w", **pad)
        ttk.Label(preset, text="Presets:").pack(side="left")
        ttk.Button(preset, text="Single part", command=lambda: self.preset(1, 40, "")).pack(side="left", padx=2)
        ttk.Button(preset, text="Wide plate (3 lanes)", command=lambda: self.preset(3, 40, "")).pack(side="left", padx=2)
        ttk.Button(preset, text="Gentle (slow 1200)", command=lambda: self.v["speed"].set("1200")).pack(side="left", padx=2)

        # 4 go
        go = ttk.LabelFrame(f, text="4  Go")
        go.pack(fill="x", **pad)
        self._btn(go, "Check ready", lambda: self.run_ram("check")).pack(side="left", padx=4, pady=4)
        self._btn(go, "Preview (dry run)", lambda: self.run_ram("preview")).pack(side="left", padx=4)
        self.ram_btn = self._btn(go, "RAM NOW", lambda: self.run_ram("apply"))
        self.ram_btn.pack(side="left", padx=4)
        self._btn(go, "Motors off (M84)", lambda: self.run_args(["gcode", self.target(), "M84"])).pack(side="left", padx=16)
        ttk.Label(go, text="RAM NOW re-runs the check and refuses on any FAIL.", foreground="#666").pack(side="left")

    def _recover_tab(self, nb):
        pad = dict(padx=6, pady=4)
        f = ttk.Frame(nb)
        nb.add(f, text="  Recover Z  ")
        ttk.Label(f, text="Klipper restarted with parts still on the plate? G28 Z would come down on them. "
                          "This re-finds Z with a paper test at a spot clear of the parts\n"
                          "(found from the gcode picked on the Ramming tab). Don't move the bed or toolhead by hand before step 1.",
                  foreground="#555", justify="left").pack(anchor="w", **pad)
        s1 = ttk.LabelFrame(f, text="1  Home X/Y only")
        s1.pack(fill="x", **pad)
        self.park_x, self.park_y = tk.StringVar(value="0"), tk.StringVar(value="260")
        ttk.Label(s1, text="Toolhead was parked at X").pack(side="left", padx=4)
        ttk.Entry(s1, textvariable=self.park_x, width=6).pack(side="left")
        ttk.Label(s1, text="Y").pack(side="left", padx=4)
        ttk.Entry(s1, textvariable=self.park_y, width=6).pack(side="left")
        ttk.Label(s1, text="(END_PRINT parks at X0 Y260)", foreground="#666").pack(side="left", padx=6)
        self._btn(s1, "Home X/Y (keep Z)", self.rz_home).pack(side="right", padx=6, pady=4)
        s2 = ttk.LabelFrame(f, text="2  Measure the nozzle tip height above the bed with a ruler")
        s2.pack(fill="x", **pad)
        self.rz_h = tk.StringVar()
        ttk.Label(s2, text="Height (mm)").pack(side="left", padx=4)
        ttk.Entry(s2, textvariable=self.rz_h, width=8).pack(side="left")
        ttk.Label(s2, text="Klipper is told 5 mm more than this, so it can't drive into the bed",
                  foreground="#666").pack(side="left", padx=6)
        self._btn(s2, "Go to clear spot", self.rz_goto).pack(side="right", padx=6, pady=4)
        s3 = ttk.LabelFrame(f, text="3  Paper under the nozzle - jog down until it just drags")
        s3.pack(fill="x", **pad)
        for dz in ("-1", "-0.1", "+0.1", "+1"):
            self._btn(s3, "Z " + dz, lambda d=dz: self.run_args(
                ["recover-z", self.target(), "--step", "jog", "--dz", d, "--apply"])).pack(side="left", padx=4, pady=4)
        s4 = ttk.LabelFrame(f, text="4  Done")
        s4.pack(fill="x", **pad)
        self._btn(s4, "Paper drags - set Z here", self.rz_set).pack(side="left", padx=6, pady=4)
        ttk.Label(s4, text="sets Z=0.1 and lifts to Z40. Then ram with 'parked after END_PRINT' unticked.",
                  foreground="#666").pack(side="left")

    def all_printers(self):
        return [t for t in self.printer.cget("values")] or [self.target()]

    def cam_add(self, targets, apply):
        if apply and not messagebox.askyesno("Add camera", "Add the Hi camera (port 8000) to Fluidd on:\n\n  %s\n\n"
                                             "Printers that already have it are skipped. A copy of each printer's "
                                             "current camera list is saved first." % "\n  ".join(targets)):
            return
        self.run_args(["webcam", "add"] + targets + (["--apply"] if apply else []))

    def cam_preview(self):
        """Open the selected printer's camera stream in the browser - nothing is changed."""
        url = hi_tool.hi_cam_entry(hi_tool.Printer(self.target()).host)["stream_url"]
        self.q.put("\n# preview: opening %s\n" % url)
        webbrowser.open(url)

    def cam_remove(self):
        name = simpledialog.askstring("Remove camera", "Name of the camera to remove from %s\n(see List cameras):"
                                      % self.target(), parent=self)
        if not name:
            return
        if messagebox.askyesno("Remove camera", "Remove camera '%s' from %s?" % (name, self.target()), icon="warning"):
            self.run_args(["webcam", "remove", self.target(), "--name", name.strip(), "--apply"])

    def open_fluidd(self):
        webbrowser.open("http://%s:4408" % hi_tool.Printer(self.target()).host)

    def beep(self):
        v = {k: self.bz[k].get().strip() for k in self.bz}
        try:
            f, ms, n = int(v["freq"]), int(v["ms"]), int(v["times"])
        except ValueError:
            messagebox.showwarning("Beep", "Hz, ms and times must be whole numbers.")
            return
        self.checked_run(["beep", self.target(), "--pwm", "6", "--freq", str(f), "--ms", str(ms), "--times", str(n)]
                         + self._ssh_args(), "beep")

    def _bz_freq(self):
        try:
            return str(max(1000, min(8000, int(self.bz["freq"].get()))))
        except ValueError:
            return str(hi_tool.BEEP_LOUD_HZ)

    def install_beeper(self, targets):
        if not messagebox.askyesno("Install M300 beeper", "Install Klipper M300 / BEEP (%s Hz) on:\n\n  %s\n\n"
                                   "Each printer: config backup, restart klipper_mcu + Klipper over SSH, a test beep; it rolls back if Klipper "
                                   "doesn't come back. Printers that are printing are skipped."
                                   % (self._bz_freq(), "\n  ".join(targets))):
            return
        plate = messagebox.askyesno("Parts on the plate?", "Are the plates clear (or you don't need to ram what's on them)?\n\n"
                                    "Yes = go ahead.\nNo = skip printers that are still parked after END_PRINT "
                                    "(the RESTART would make them forget their Z height for RAM NOW).")
        self.run_args(["install-beeper"] + targets + ["--freq", self._bz_freq(), "--apply"] + (["--plate-clear"] if plate else []) + self._ssh_args())

    def remove_beeper(self):
        if messagebox.askyesno("Remove M300 beeper", "Remove the Klipper beeper from %s and RESTART Klipper?\n\nOnly if the plate is clear - the RESTART "
                               "forgets the parked Z height RAM NOW uses." % self.target()):
            self.run_args(["install-beeper", self.target(), "--revert", "--apply", "--plate-clear"] + self._ssh_args())

    def _tr(self):
        try:
            n = int(self.bz_tr.get())
        except ValueError:
            n = 0
        return ["--transpose", str(n)] if n else []

    def play_tune(self, custom):
        if custom:
            notes = self.bz_notes.get().strip()
            try:
                hi_tool.parse_notes(notes)
            except hi_tool.ToolError as e:
                messagebox.showwarning("Notes", str(e))
                return
            self.checked_run(["beep", self.target(), "--notes=" + notes] + self._tr() + self._ssh_args(), "play your tune")
        else:
            self.checked_run(["beep", self.target(), "--tune", self.bz_tune.get()] + self._tr() + self._ssh_args(),
                             "play '%s'" % self.bz_tune.get())

    def jz_unlock(self):
        try:
            z = float(self.jz_z.get())
        except ValueError:
            messagebox.showwarning("Z", "Measure or estimate the nozzle height above the bed and enter it.\n"
                                   "Give your best real estimate - it only sets how far the jog buttons may go.")
            return
        if not messagebox.askyesno("Unlock Z", "Tell %s the toolhead is at Z%.0f so you can jog it down without homing?\n\n"
                                   "Klipper's Z number is a guess after this - watch the nozzle, not the number. "
                                   "Jog down in small steps." % (self.target(), z), icon="warning"):
            return
        self.run_args(["jog-z", self.target(), "--unlock", str(z), "--apply"])

    def rz_home(self):
        if not messagebox.askyesno("Home X/Y", "Home X and Y on %s?\n\nZ is NOT homed. The toolhead must still be where "
                                   "END_PRINT parked it (X%s Y%s) - nobody moved it by hand." %
                                   (self.target(), self.park_x.get(), self.park_y.get())):
            return
        self.run_args(["recover-z", self.target(), "--step", "home-xy", "--park-x", self.park_x.get(),
                       "--park-y", self.park_y.get(), "--apply"])

    def rz_goto(self):
        try:
            h = float(self.rz_h.get())
        except ValueError:
            messagebox.showwarning("Height", "Measure the nozzle tip height above the bed and enter it in mm.")
            return
        args = ["recover-z", self.target(), "--step", "goto", "--height", str(h)]
        gpath = self.gcode_path.get().strip()
        if gpath and os.path.isfile(gpath):
            args += ["--gcode", gpath]
        elif self.v["top"].get().strip():
            messagebox.showwarning("Gcode", "Pick the sliced gcode on the Ramming tab first - it is needed to find a spot clear of the parts.")
            return
        if not messagebox.askyesno("Go to clear spot", "Move to a spot clear of the parts and lower to ~5 mm above the bed?"):
            return
        self.run_args(args + ["--apply"])

    def rz_set(self):
        if messagebox.askyesno("Set Z", "Paper drags under the nozzle? This sets Z here and lifts to Z40."):
            self.run_args(["recover-z", self.target(), "--step", "set", "--apply"])

    def _cfs_tab(self, nb):
        pad = dict(padx=6, pady=4)
        f = ttk.Frame(nb)
        nb.add(f, text="  CFS  ")
        ttk.Label(f, text="Creality Filament System. Status and Debug only read - nothing moves. "
                          "Slot load/unload/change comes next, once we've seen what the box reports.",
                  foreground="#555").pack(anchor="w", **pad)
        r = ttk.LabelFrame(f, text="1  Look")
        r.pack(fill="x", **pad)
        self._btn(r, "Status", lambda: self.run_args(["cfs", "status", self.target()])).pack(side="left", padx=4, pady=4)
        self._btn(r, "Debug (status + slot files + box log, SSH)", lambda: self.run_args(
            ["cfs", "debug", self.target()] + self._ssh_args())).pack(side="left", padx=4)
        ttk.Label(r, text="a full dump is saved in hi_backups/<printer ip>/cfs_*.json", foreground="#666").pack(side="left", padx=8)

    def _pa_tab(self, nb):
        pad = dict(padx=6, pady=3)
        outer = ttk.Frame(nb)
        nb.add(outer, text="  Pressure adv.  ")
        inner = ttk.Notebook(outer)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        f = ttk.Frame(inner)
        inner.add(f, text=" Status & tweak ")
        lt = ttk.Frame(inner)
        inner.add(lt, text=" Line test ")
        ot = ttk.Frame(inner)
        inner.add(ot, text=" Orca tower ")
        lg = ttk.Frame(inner)
        inner.add(lg, text=" Logs & results ")
        gd = ttk.Frame(inner)
        inner.add(gd, text=" Guide ")
        td = ttk.Frame(inner)
        inner.add(td, text=" To do ")
        self.pa_inner = inner
        ttk.Label(f, text="Motion Advance (printer screen > Settings > Print settings) is Creality's automatic pressure-advance "
                          "calibration at print start - it only runs with\nCreality Print's 'Print calibration'. Files from Orca "
                          "etc. print with the value below (or the slicer's own, if it sets one).",
                  foreground="#555", justify="left").pack(anchor="w", **pad)

        c = ttk.LabelFrame(f, text="1  Check")
        c.pack(fill="x", **pad)
        self._btn(c, "Status", lambda: self.run_args(["pa", "status", self.target()])).pack(side="left", padx=4, pady=4)
        self._btn(c, "What does a sliced file use?", self.pa_scan).pack(side="left", padx=4)
        self._btn(c, "Firmware / Motion Advance (SSH)", lambda: self.run_args(
            ["pa", "firmware", self.target()] + self._ssh_args())).pack(side="left", padx=4)
        self._btn(c, "Pre-flight", lambda: self.pa_preflight(False)).pack(side="left", padx=4)
        self._btn(c, "Pre-flight + fix", lambda: self.pa_preflight(True)).pack(side="left", padx=4)
        ttk.Label(c, text="fix = unlock + silent off", foreground="#666").pack(side="left", padx=6)

        rv = ttk.LabelFrame(f, text="1b  Are PA commands obeyed?  sets test K values, reads them back, restores yours")
        rv.pack(fill="x", **pad)
        self._btn(rv, "Respected? (console)", lambda: self.pa_verify(False)).pack(side="left", padx=4, pady=4)
        self._btn(rv, "Respected? (console + print file)", lambda: self.pa_verify(True)).pack(side="left", padx=4)
        ttk.Label(rv, text="print file = no heat, no motion, ~12 s - proves a sliced file's K is applied",
                  foreground="#666").pack(side="left", padx=6)
        t = ttk.LabelFrame(f, text="2  Tweak live (until the next restart - works mid-print)")
        t.pack(fill="x", **pad)
        self.pa_k, self.pa_sm = tk.StringVar(value="0.04"), tk.StringVar(value="")
        ttk.Label(t, text="K").pack(side="left", padx=(6, 2))
        ttk.Entry(t, textvariable=self.pa_k, width=8).pack(side="left")
        for d in ("-0.005", "+0.005"):
            ttk.Button(t, text=d, width=7, command=lambda d=d: self.pa_bump(float(d))).pack(side="left", padx=2)
        ttk.Label(t, text="smooth time").pack(side="left", padx=(10, 2))
        ttk.Entry(t, textvariable=self.pa_sm, width=6).pack(side="left")
        ttk.Label(t, text="(blank = keep)", foreground="#666").pack(side="left", padx=2)
        self._btn(t, "Set now", self.pa_set).pack(side="left", padx=10, pady=4)
        self.pa_live = tk.BooleanVar(value=False)
        ttk.Checkbutton(t, text="allow while printing", variable=self.pa_live).pack(side="left")

        k = ttk.LabelFrame(lt, text="Line test (each line a different K: slow / fast / slow) - our own gcode, no slicer needed")
        k.pack(fill="x", **pad)
        self.pa_v = {n: tk.StringVar(value=d) for n, d in (("start", "0"), ("end", "0.1"), ("step", "0.005"),
                                                            ("noz", "220"), ("bed", "60"), ("fast", "100"),
                                                            ("accel", "5000"), ("line", ""))}
        r1 = ttk.Frame(k)
        r1.pack(fill="x", padx=4, pady=2)
        for key, lbl, w in (("start", "K from", 6), ("end", "to", 6), ("step", "step", 6), ("noz", "nozzle C", 5),
                            ("bed", "bed C", 4), ("fast", "fast mm/s", 5), ("accel", "accel", 6)):
            ttk.Label(r1, text=lbl).pack(side="left", padx=(6, 2))
            ttk.Entry(r1, textvariable=self.pa_v[key], width=w).pack(side="left")
        r2 = ttk.Frame(k)
        r2.pack(fill="x", padx=4, pady=2)
        ttk.Label(r2, text="Presets:").pack(side="left", padx=(6, 2))
        for name, vals in (("PLA", ("0", "0.08", "0.005", "215", "60")), ("PETG", ("0", "0.12", "0.005", "240", "70")),
                           ("Fine (around current K)", None)):
            ttk.Button(r2, text=name, command=lambda v=vals: self.pa_preset(v)).pack(side="left", padx=2)
        ttk.Label(r2, text="bed mesh").pack(side="left", padx=(12, 2))
        self.pa_mesh = ttk.Combobox(r2, values=["load", "calibrate", "none"], width=9, state="readonly")
        self.pa_mesh.set("load")
        self.pa_mesh.pack(side="left")
        r3 = ttk.Frame(k)
        r3.pack(fill="x", padx=4, pady=2)
        self._btn(r3, "Make file only", lambda: self.pa_test("file")).pack(side="left", padx=4)
        self._btn(r3, "Upload to printer", lambda: self.pa_test("upload")).pack(side="left", padx=4)
        self._btn(r3, "Upload + PRINT", lambda: self.pa_test("print")).pack(side="left", padx=4)
        ttk.Label(r3, text="Best line #").pack(side="left", padx=(16, 2))
        ttk.Entry(r3, textvariable=self.pa_v["line"], width=4).pack(side="left")
        self.pa_res = ttk.Label(r3, text="", width=12)
        self.pa_res.pack(side="left", padx=4)
        ttk.Button(r3, text="Use this K", command=self.pa_use_line).pack(side="left")
        for key in ("line", "start", "step"):
            self.pa_v[key].trace_add("write", lambda *_: self.pa_line_k())
        ttk.Label(k, text="Line 1 is at the front, every 5th line has a tick on the right (line 1 a double tick). Pick the line "
                          "whose fast middle is even:\nno blob where it speeds up, no gap where it slows down. Lower K if the "
                          "ends of the fast part are thin, raise it if they bulge.",
                  foreground="#666", justify="left").pack(anchor="w", padx=6, pady=(0, 4))

        sv = ttk.LabelFrame(f, text="3  Save K as the printer's default (printer.cfg, RESTART, rolls back on failure)")
        sv.pack(fill="x", **pad)
        self._btn(sv, "Save (dry run)", lambda: self.pa_save(False)).pack(side="left", padx=4, pady=4)
        self._btn(sv, "Save + RESTART", lambda: self.pa_save(True)).pack(side="left", padx=4)
        ttk.Label(sv, text="refuses while printing; smooth time is saved too if filled in", foreground="#666").pack(side="left", padx=6)
        ttk.Button(sv, text="Log this K as a result...", command=lambda: self.pa_add_result("manual")).pack(side="right", padx=6)
        ttk.Button(k, text="Log the best line as a result...", command=lambda: self.pa_add_result(
            "line test", self.pa_line_k())).pack(anchor="w", padx=6, pady=(0, 4))

        self._pa_orca(ot, pad)
        self._pa_logs(lg, pad)
        self._pa_guide(gd, td)

    # ---- pressure advance helpers
    def _pa_k(self):
        try:
            k = float(self.pa_k.get())
        except ValueError:
            messagebox.showwarning("K", "K must be a number like 0.04")
            return None
        if not 0 <= k <= hi_tool.PA_MAX:
            messagebox.showwarning("K", "K should be between 0 and %.1f" % hi_tool.PA_MAX)
            return None
        return k

    def _pa_smooth_args(self):
        sm = self.pa_sm.get().strip()
        return ["--smooth", sm] if sm else []

    def pa_bump(self, d):
        try:
            self.pa_k.set("%.4f" % max(0.0, float(self.pa_k.get()) + d))
        except ValueError:
            pass

    def pa_set(self):
        k = self._pa_k()
        if k is not None:
            self.run_args(["pa", "set", self.target(), "--k", "%.4f" % k, "--apply"] + self._pa_smooth_args()
                          + (["--force"] if self.pa_live.get() else []))

    def pa_save(self, apply):
        k = self._pa_k()
        if k is None:
            return
        args = ["pa", "save", self.target(), "--k", "%.4f" % k] + self._pa_smooth_args()
        if apply:
            if not messagebox.askyesno("Save pressure advance", "Write pressure_advance %.4f into printer.cfg on %s and "
                                       "RESTART Klipper?\n\nA full config backup is taken first; it rolls back if Klipper "
                                       "doesn't come back with the new value." % (k, self.target())):
                return
            args.append("--apply")
        self.run_args(args)

    def pa_scan(self):
        g = self.gcode_path.get().strip()
        f = filedialog.askopenfilename(title="Sliced gcode", initialdir=os.path.dirname(g) if g else os.path.join(HERE, "..", "gcode"),
                                       filetypes=[("G-code or sliced 3mf", "*.gcode *.3mf"), ("All files", "*.*")])
        if not f:
            return
        if f.lower().endswith(".3mf"):
            f = self.extract_3mf(f)
            if not f:
                return
        self.run_args(["pa", "status", self.target(), "--gcode", f])

    def pa_preset(self, vals):
        if vals is None:  # fine sweep around the K in box 2
            try:
                k = float(self.pa_k.get())
            except ValueError:
                k = 0.04
            vals = ("%.3f" % max(0.0, k - 0.02), "%.3f" % (k + 0.02), "0.002", self.pa_v["noz"].get(), self.pa_v["bed"].get())
        for key, v in zip(("start", "end", "step", "noz", "bed"), vals):
            self.pa_v[key].set(v)

    def pa_line_k(self):
        try:
            n = int(self.pa_v["line"].get())
            k = float(self.pa_v["start"].get()) + (n - 1) * float(self.pa_v["step"].get())
            self.pa_res.configure(text="-> K %.4f" % k if n >= 1 else "")
            return k if n >= 1 else None
        except ValueError:
            self.pa_res.configure(text="")
            return None

    def pa_use_line(self):
        k = self.pa_line_k()
        if k is None:
            messagebox.showwarning("Line", "Type the number of the best line (1 = front).")
            return
        self.pa_k.set("%.4f" % k)
        self.write("K %.4f from line %s - 'Set now' to try it, 'Save + RESTART' to keep it\n" % (k, self.pa_v["line"].get()))

    def pa_test(self, mode):
        v = {key: self.pa_v[key].get().strip() for key in self.pa_v}
        try:
            for key in ("start", "end", "step", "fast"):
                float(v[key])
            for key in ("noz", "bed", "accel"):
                int(v[key])
        except ValueError:
            messagebox.showwarning("Line test", "K from / to / step, temperatures, speed and accel must be numbers.")
            return
        args = ["pa", "test", self.target(), "--start", v["start"], "--end", v["end"], "--step", v["step"],
                "--nozzle-temp", v["noz"], "--bed-temp", v["bed"], "--fast", v["fast"], "--accel", v["accel"],
                "--mesh", self.pa_mesh.get()] + self._pa_smooth_args()
        if mode == "upload":
            args += ["--upload", "--apply"]
        elif mode == "print":
            if not messagebox.askyesno("Print line test", "Upload the line test to %s and START printing it now?\n\n"
                                       "- plate clear and clean\n- right filament loaded (%s C)\n- bed mesh: %s\n\n"
                                       "It homes, heats, prints ~%s lines and moves the bed forward when done."
                                       % (self.target(), v["noz"], self.pa_mesh.get(),
                                          int(round((float(v["end"]) - float(v["start"])) / float(v["step"]))) + 1),
                                       icon="warning"):
                return
            args += ["--print", "--apply"]
        self.run_args(args)

    # ---- pressure advance: Orca tower sub-tab
    def _pa_orca(self, f, pad):
        s1 = ttk.LabelFrame(f, text="1  Type into Orca: Calibration > Pressure Advance > PA Tower, extruder type Direct Drive")
        s1.pack(fill="x", **pad)
        self.ot_v = {n: tk.StringVar(value=d) for n, d in (("start", "0"), ("end", "0.1"), ("step", "0.002"), ("h", ""))}
        self.ot_scan = None
        r = ttk.Frame(s1)
        r.pack(fill="x", padx=4, pady=2)
        for key, lbl in (("start", "Start PA"), ("end", "End PA"), ("step", "PA step")):
            ttk.Label(r, text=lbl).pack(side="left", padx=(6, 2))
            ttk.Entry(r, textvariable=self.ot_v[key], width=7).pack(side="left")
        ttk.Button(r, text="Coarse 0 / 0.1 / 0.002", command=lambda: self.ot_preset("0", "0.1", "0.002")).pack(side="left", padx=(12, 2))
        ttk.Button(r, text="Fine around K", command=self.ot_fine).pack(side="left", padx=2)
        ttk.Button(r, text="TPU 0 / 0.2 / 0.004", command=lambda: self.ot_preset("0", "0.2", "0.004")).pack(side="left", padx=2)
        self.ot_info = ttk.Label(s1, text="", foreground="#555", justify="left", wraplength=920)
        self.ot_info.pack(anchor="w", padx=8, pady=(0, 4))
        for key in ("start", "end", "step"):
            self.ot_v[key].trace_add("write", lambda *_: self.ot_update())

        s2 = ttk.LabelFrame(f, text="2  Before / while it prints")
        s2.pack(fill="x", **pad)
        self._btn(s2, "Check sliced tower file...", self.ot_check_file).pack(side="left", padx=4, pady=4)
        self._btn(s2, "Pre-flight + fix", lambda: self.pa_preflight(True, self.ot_file())).pack(side="left", padx=4)
        self._btn(s2, "Respected?", lambda: self.pa_verify(False)).pack(side="left", padx=4)
        self.watch_btn = ttk.Button(s2, text="Watch live (log K by height)", command=self.pa_watch)
        self.watch_btn.pack(side="left", padx=(14, 4))
        ttk.Button(s2, text="Stop watch", command=self.pa_watch_stop).pack(side="left", padx=2)
        self.ot_file_lbl = ttk.Label(s2, text="no file checked", foreground="#666")
        self.ot_file_lbl.pack(side="left", padx=8)

        s3 = ttk.LabelFrame(f, text="3  Read it: measure from the bed to where the corners look best")
        s3.pack(fill="x", **pad)
        ttk.Label(s3, text="height mm").pack(side="left", padx=(6, 2), pady=4)
        ttk.Entry(s3, textvariable=self.ot_v["h"], width=6).pack(side="left")
        self.ot_res = ttk.Label(s3, text="", width=30)
        self.ot_res.pack(side="left", padx=6)
        self.ot_v["h"].trace_add("write", lambda *_: self.ot_k())
        ttk.Button(s3, text="Use this K", command=self.ot_use).pack(side="left", padx=2)
        self._btn(s3, "Use + Set now", lambda: self.ot_use(True)).pack(side="left", padx=2)
        ttk.Button(s3, text="Log result...", command=lambda: self.pa_add_result("Orca PA tower", self.ot_k())).pack(side="left", padx=2)
        ttk.Label(f, text="Good: sharp corners, even walls right after the corner.  K too LOW: corners bulge / blobby, wall "
                          "after the corner thick.  K too HIGH: corners rounded, thin or gappy wall right after the corner, "
                          "under-extruded starts.  Look at the face away from the seam. Orca prints the K values on the tower "
                          "every few mm.",
                  foreground="#666", justify="left", wraplength=930).pack(anchor="w", padx=8, pady=(0, 4))
        self.ot_update()

    def ot_preset(self, a, b, c):
        self.ot_scan = None
        for key, v in zip(("start", "end", "step"), (a, b, c)):
            self.ot_v[key].set(v)

    def ot_fine(self):
        try:
            k = float(self.pa_k.get())
        except ValueError:
            k = 0.04
        self.ot_preset("%.3f" % max(0.0, k - 0.015), "%.3f" % (k + 0.015), "0.001")
        self.write("fine tower around K %.4f (from the K box on Status & tweak)\n" % k)

    def _ot_nums(self):
        try:
            return float(self.ot_v["start"].get()), float(self.ot_v["end"].get()), float(self.ot_v["step"].get())
        except ValueError:
            return None

    def ot_update(self):
        n = self._ot_nums()
        if not n or n[2] <= 0 or n[1] <= n[0]:
            self.ot_info.configure(text="start < end and step > 0, please")
            return
        st, en, sp = n
        h = (en - st) / sp
        warn = "  - that's a tall tower, use a bigger step" if h > 80 else ""
        self.ot_info.configure(text="-> K changes every 1 mm: tower about %.0f mm tall (~%d K values)%s.   K at height H = %g + "
                                    "whole mm of H x %g.\nPrint it with the filament + process you really use (temp, "
                                    "outer wall speed/accel). Orca switches its own PA off for the test, so no need to "
                                    "touch 'Enable pressure advance'." % (h, int(round(h)) + 1, warn, st, sp))
        self.ot_k()

    def ot_file(self):
        return self.ot_scan["path"] if self.ot_scan else None

    def ot_check_file(self):
        f = filedialog.askopenfilename(title="Sliced Orca PA tower", initialdir=os.path.join(HERE, ".."),
                                       filetypes=[("G-code or sliced 3mf", "*.gcode *.3mf"), ("All files", "*.*")])
        if not f:
            return
        if f.lower().endswith(".3mf"):
            f = self.extract_3mf(f, warn=False)
            if not f:
                return
        try:
            sc = hi_tool.pa_tower_scan(f)
        except Exception as e:
            messagebox.showerror("Tower file", str(e))
            return
        sc["path"] = f
        self.ot_scan = sc if len(sc["bands"]) >= 4 else None
        if self.ot_scan:
            last = sc["bands"][-1][0]
            for key, v in (("start", sc["start"]), ("end", last), ("step", sc["step"])):
                self.ot_v[key].set(("%.4f" % v).rstrip("0").rstrip(".") or "0")
            self.ot_file_lbl.configure(text="%s: K %.3f..%.3f" % (os.path.basename(f), sc["bands"][0][0], last))
        else:
            self.ot_file_lbl.configure(text="%s: not a tower" % os.path.basename(f))
        self.run_args(["pa", "tower", self.target(), "--gcode", f])

    def ot_k(self):
        try:
            h = float(self.ot_v["h"].get())
        except ValueError:
            self.ot_res.configure(text="")
            return None
        if self.ot_scan:
            k = hi_tool.pa_k_at(self.ot_scan, h)
            src = "from the file"
        else:
            n = self._ot_nums()
            if not n:
                return None
            k = n[0] + int(h + 1e-9) * n[2]
            src = "start + %d x step" % int(h + 1e-9)
        if k is None:
            self.ot_res.configure(text="below the first K change")
            return None
        self.ot_res.configure(text="-> K %.4f  (%s)" % (k, src))
        return k

    def ot_use(self, set_now=False):
        k = self.ot_k()
        if k is None:
            messagebox.showwarning("Tower", "Type the height (mm) of the best-looking spot first.")
            return
        self.pa_k.set("%.4f" % k)
        self.write("K %.4f from the tower at %s mm - now in the K box on Status & tweak\n" % (k, self.ot_v["h"].get()))
        if set_now:
            self.pa_set()

    # ---- pressure advance: watch / preflight
    def pa_preflight(self, fix, gcode=None):
        args = ["pa", "preflight", self.target()] + (["--gcode", gcode] if gcode else [])
        if fix:
            args.append("--apply")
        self.verdict.configure(text="")
        self.run_args(args)

    def pa_verify(self, via_print):
        args = ["pa", "verify", self.target()]
        if via_print:
            if not messagebox.askyesno("PA respect test", "Upload and START a tiny print file on %s?\n\n"
                                       "No heating, no movement - it only changes K three times (~12 s) so we can see "
                                       "whether commands inside a print file are obeyed.\n\nThe original K is "
                                       "restored afterwards." % self.target()):
                return
            args += ["--via-print", "--apply"]
        self.verdict.configure(text="")
        self.run_args(args)

    def pa_watch(self):
        if self.watching:
            messagebox.showinfo("Watch", "Already watching - press 'Stop watch' first.")
            return
        if not self.target():
            return
        self.watching = True
        self.watch_btn.state(["disabled"])
        args = ["pa", "watch", self.target()]
        self.q.put("\n$ python hi_tool.py %s   (runs in the background; other buttons still work)\n" % " ".join(args))

        def job():
            try:
                hi_tool.main(args)
            except SystemExit:
                pass
            except Exception as e:
                self.q.put("[ERROR] watch: %s: %s\n" % (type(e).__name__, e))
            finally:
                self.after(0, self._watch_done)

        threading.Thread(target=job, daemon=True).start()

    def _watch_done(self):
        self.watching = False
        self.watch_btn.state(["!disabled"])

    def pa_watch_stop(self):
        hi_tool.PA_STOP.set()

    # ---- pressure advance: logs + results notebook
    def _pa_logs(self, f, pad):
        top = ttk.LabelFrame(f, text="Printer logs")
        top.pack(fill="x", **pad)
        self._btn(top, "PA history (console + recent prints)", lambda: self.run_args(
            ["pa", "history", self.target(), "--lines", "60"])).pack(side="left", padx=4, pady=4)
        self._btn(top, "All printers: K / lock / silent", lambda: self.run_args(
            ["pa-fleet"] + self.all_printers())).pack(side="left", padx=4)
        ttk.Button(top, text="Watch live", command=self.pa_watch).pack(side="left", padx=(12, 2))
        ttk.Button(top, text="Stop", command=self.pa_watch_stop).pack(side="left", padx=2)
        ttk.Button(top, text="Open logs folder", command=lambda: self.open_path(
            os.path.join(HERE, "hi_backups", "pa_logs"))).pack(side="left", padx=(12, 2))
        ttk.Button(top, text="Change log", command=lambda: self.open_path(
            os.path.join(HERE, "hi_backups", "pa_logs", "pa_changes.csv"))).pack(side="left", padx=2)

        nbk = ttk.LabelFrame(f, text="Results notebook - one row per calibration (pa_results.csv)")
        nbk.pack(fill="both", expand=True, **pad)
        bar = ttk.Frame(nbk)
        bar.pack(fill="x", padx=4, pady=2)
        ttk.Button(bar, text="Add result...", command=lambda: self.pa_add_result("manual")).pack(side="left", padx=2)
        ttk.Button(bar, text="Use selected K", command=self.pa_use_result).pack(side="left", padx=2)
        ttk.Button(bar, text="Delete selected", command=self.pa_del_result).pack(side="left", padx=2)
        ttk.Button(bar, text="Open CSV", command=lambda: self.open_path(PA_RESULTS)).pack(side="left", padx=2)
        ttk.Label(bar, text="show").pack(side="left", padx=(14, 2))
        self.res_filter = ttk.Combobox(bar, values=["all printers", "this printer"], width=12, state="readonly")
        self.res_filter.set("all printers")
        self.res_filter.pack(side="left")
        self.res_filter.bind("<<ComboboxSelected>>", lambda e: self.pa_load_results())
        self.printer.bind("<<ComboboxSelected>>", lambda e: self.pa_load_results(), add="+")
        body = ttk.Frame(nbk)
        body.pack(fill="both", expand=True, padx=4)
        widths = (120, 60, 120, 60, 60, 55, 100, 260)
        self.res_tree = ttk.Treeview(body, columns=PA_RESULT_COLS, show="headings", height=6)
        for c, w in zip(PA_RESULT_COLS, widths):
            self.res_tree.heading(c, text=c)
            self.res_tree.column(c, width=w, anchor="w", stretch=(c == "notes"))
        sb = ttk.Scrollbar(body, command=self.res_tree.yview)
        self.res_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.res_tree.pack(fill="both", expand=True)
        self.res_sum = ttk.Label(nbk, text="", foreground="#555", justify="left")
        self.res_sum.pack(anchor="w", padx=6, pady=(2, 4))
        self.pa_load_results()

    def open_path(self, path):
        if not os.path.exists(path):
            if path.endswith(".csv"):
                messagebox.showinfo("Not yet", "%s doesn't exist yet - it's created the first time something is logged."
                                    % os.path.basename(path))
                return
            os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            webbrowser.open("file://" + path)

    def _pa_rows(self):
        try:
            with open(PA_RESULTS, newline="", encoding="utf-8") as fh:
                return [r for r in csv.DictReader(fh)]
        except OSError:
            return []

    def _pa_write_rows(self, rows):
        with open(PA_RESULTS, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=PA_RESULT_COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    def _pname(self):
        return hi_tool.Printer(self.target()).name if self.target() else ""

    def pa_load_results(self):
        if not hasattr(self, "res_tree"):
            return
        rows = self._pa_rows()
        self.res_tree.delete(*self.res_tree.get_children())
        only = self._pname() if self.res_filter.get() == "this printer" else None
        for i, r in enumerate(rows):
            if only and r.get("printer") != only:
                continue
            self.res_tree.insert("", "end", iid=str(i), values=[r.get(c, "") for c in PA_RESULT_COLS])
        self.res_tree.yview_moveto(1.0)
        by = {}
        for r in rows:
            try:
                by.setdefault(r.get("filament", "?") or "?", []).append((float(r["k"]), r.get("printer", "")))
            except (ValueError, KeyError):
                pass
        parts = []
        for fil, ks in sorted(by.items()):
            vals = [k for k, _ in ks]
            avg = sum(vals) / len(vals)
            spread = (" +/-%.3f" % ((max(vals) - min(vals)) / 2)) if len(vals) > 1 else ""
            parts.append("%s: K %.3f%s (%d, on %s)" % (fil, avg, spread, len(vals), "/".join(sorted({p for _, p in ks}))))
        self.res_sum.configure(text=("Per filament:  " + "    ".join(parts)) if parts else
                               "No results yet - after a line test or tower, 'Log result...' keeps the K here per printer + filament.")

    def pa_add_result(self, method, k=None):
        if k is None:
            try:
                k = float(self.pa_k.get())
            except ValueError:
                k = None
        win = tk.Toplevel(self)
        win.title("Log a pressure-advance result")
        win.transient(self)
        rows = self._pa_rows()
        fils = sorted({r.get("filament", "") for r in rows if r.get("filament")} |
                      {"Extrudr PETG", "PLA", "PETG", "PLA Silk", "ABS", "ASA", "TPU 95A"})
        v = {"printer": tk.StringVar(value=self._pname()), "filament": tk.StringVar(value=rows[-1]["filament"] if rows else ""),
             "nozzle_c": tk.StringVar(value=self.pa_v["noz"].get()), "k": tk.StringVar(value="" if k is None else "%.4f" % k),
             "smooth": tk.StringVar(value=self.pa_sm.get() or "0.040"), "method": tk.StringVar(value=method),
             "notes": tk.StringVar()}
        for i, (key, lbl) in enumerate((("printer", "Printer"), ("filament", "Filament (brand + type)"),
                                        ("nozzle_c", "Nozzle C"), ("k", "K"), ("smooth", "smooth time"),
                                        ("method", "Method"), ("notes", "Notes"))):
            ttk.Label(win, text=lbl).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            if key == "filament":
                w = ttk.Combobox(win, textvariable=v[key], values=fils, width=30)
            elif key == "method":
                w = ttk.Combobox(win, textvariable=v[key], width=30,
                                 values=["Orca PA tower", "Orca PA line", "Orca PA pattern", "line test", "manual",
                                         "Creality Motion Advance"])
            else:
                w = ttk.Entry(win, textvariable=v[key], width=32 if key == "notes" else 14)
            w.grid(row=i, column=1, sticky="w", padx=8, pady=3)

        def save():
            try:
                kk = float(v["k"].get())
                if not 0 <= kk <= hi_tool.PA_MAX:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("K", "K must be a number between 0 and %.1f" % hi_tool.PA_MAX, parent=win)
                return
            if not v["filament"].get().strip():
                messagebox.showwarning("Filament", "Which filament? (K is per filament)", parent=win)
                return
            row = {c: v[c].get().strip() for c in PA_RESULT_COLS if c in v}
            row["k"] = "%.4f" % kk
            row["date"] = time.strftime("%Y-%m-%d %H:%M")
            allrows = self._pa_rows()
            allrows.append(row)
            try:
                self._pa_write_rows(allrows)
            except OSError as e:
                messagebox.showerror("Save", "Couldn't write pa_results.csv (open in Excel?)\n%s" % e, parent=win)
                return
            self.write("[OK] logged K %s for %s on %s (%s)\n" % (row["k"], row["filament"], row["printer"], row["method"]))
            win.destroy()
            self.pa_load_results()

        b = ttk.Frame(win)
        b.grid(row=8, column=0, columnspan=2, pady=8)
        ttk.Button(b, text="Save", command=save).pack(side="left", padx=4)
        ttk.Button(b, text="Cancel", command=win.destroy).pack(side="left", padx=4)
        ttk.Label(win, text="Then put the same K into Orca: Filament settings > Advanced > tick 'Enable pressure advance'",
                  foreground="#666").grid(row=9, column=0, columnspan=2, padx=8, pady=(0, 8))
        win.grab_set()

    def _sel_row(self):
        sel = self.res_tree.selection()
        if not sel:
            messagebox.showinfo("Results", "Click a row first.")
            return None, None
        rows = self._pa_rows()
        i = int(sel[0])
        return (i, rows) if i < len(rows) else (None, None)

    def pa_use_result(self):
        i, rows = self._sel_row()
        if i is None:
            return
        self.pa_k.set(rows[i]["k"])
        if rows[i].get("smooth"):
            self.pa_sm.set(rows[i]["smooth"])
        self.write("K %s (%s, %s) is in the K box - 'Set now' on Status & tweak to use it\n"
                   % (rows[i]["k"], rows[i].get("filament"), rows[i].get("printer")))
        if rows[i].get("printer") and rows[i]["printer"] != self._pname():
            self.write("[WARN] that result is from %s, the selected printer is %s - K can differ a bit between "
                       "machines\n" % (rows[i]["printer"], self._pname()))

    def pa_del_result(self):
        i, rows = self._sel_row()
        if i is None:
            return
        r = rows[i]
        if messagebox.askyesno("Delete", "Delete the result K %s / %s / %s?" % (r.get("k"), r.get("filament"), r.get("printer"))):
            del rows[i]
            self._pa_write_rows(rows)
            self.pa_load_results()

    # ---- pressure advance: guide + to-do
    PA_GUIDE = """WHAT IT IS
  When the nozzle speeds up, the melt needs extra push before plastic comes out; when it slows down, the pressure
  keeps oozing. Pressure advance (K) pushes a little extra filament while accelerating and pulls back while
  slowing down. Right K = sharp corners, even lines, cleaner seams, less stringing at the ends of moves.
  K is in seconds: extra filament = K x extrusion speed. It's per FILAMENT (and temperature, nozzle) - not per print.

TYPICAL VALUES (Hi = direct drive, 0.4 nozzle)
  PLA 0.02 - 0.05    PETG 0.03 - 0.08    ABS/ASA 0.02 - 0.05    TPU 0.05 - 0.2    Hi factory default 0.04
  Silk / CF / matte filaments and hotter temps usually want a bit different K - test them separately.

HOW TO CALIBRATE (pick one)
  A. Orca PA tower (Orca tower tab): Calibration > Pressure Advance > PA Tower, Direct Drive.
     Coarse: Start 0, End 0.1, Step 0.002 (~50 mm tower, K changes every 1 mm).
     Fine:   best K -0.015 .. +0.015, Step 0.001 (~30 mm).
     Read:   measure height of the best corners from the bed, K = start + whole mm x step (or 'Check sliced
             tower file' and type the height - the app reads the real K at that height from the gcode).
  B. Line test (Line test tab): our own gcode, 0 .. 0.1 step 0.005, then a fine run around the best line.
     Quicker (5 min, one layer), easier to read on PETG.
  C. Orca PA line / pattern: also fine - same 'Log result' afterwards.

HI GOTCHAS (the app checks these: Status & tweak > Pre-flight)
  * LOCK: Creality's ENABLE_PRESSURE_ADVANCE VALUE=0 makes the printer silently ignore every SET_PRESSURE_ADVANCE.
    A locked printer prints the whole tower with ONE K - every height looks the same. END_PRINT/CANCEL_PRINT
    unlock it; 'Pre-flight + fix' unlocks it now.
  * SILENT MODE (Qmode, screen) forces K 0.05 and lowers accel while it is on - leave it off for calibration
    and for normal prints if you want your own K.
  * MOTION ADVANCE (screen > Settings > Print settings) only runs from Creality Print's 'Print calibration'.
    Orca files don't trigger it. Don't mix: calibrate with one method.
  * ORCA FILAMENT 'Enable pressure advance' (Filament > Advanced) OVERRIDES the printer's saved K at the start
    of every print. Off = printer value (printer.cfg), on = the K in the filament profile. Best: put each
    filament's K in its Orca filament profile, keep a sane default (0.04) in printer.cfg.
  * Your current Orca printer profile is 'Ender-3 V3 Plus' with outer wall accel 1000 - K tuned at low accel
    is fine for that profile; if you later raise accel a lot, re-check K.
  * After a restart the live K goes back to printer.cfg. 'Set now' is temporary; 'Save + RESTART' is permanent.
  * smooth_time (default 0.040) - leave it unless you know why. Higher = softer, less effective PA.

READING TIPS
  Too LOW K : bulging/blobby corners, thicker wall after the corner, blob where a line speeds up.
  Too HIGH K: rounded or thin corners, gap/under-extrusion right after the corner or where a line slows down,
              rough/zitty starts. When two heights look equally good, take the LOWER one.
  Look at the faces away from the seam, with a light from the side. Calipers for the height.

WHEN TO RE-CALIBRATE
  New filament brand/type, a big temperature change, new nozzle/hotend, extruder changes, rotation_distance
  change (e-steps) - do flow/rotation_distance BEFORE pressure advance, PA after."""

    PA_TODO_ITEMS = (
        "Pre-flight each Hi (lock unlocked, silent mode off) - Status & tweak",
        "All printers: K / lock / silent - note what each Hi runs today (Logs tab)",
        "Check Orca filament profiles: is 'Enable pressure advance' on? which K?",
        "One printer: Orca PA tower, your PETG at its print temp, coarse 0 / 0.1 / 0.002 - with 'Watch live'",
        "Same printer: fine tower around the result, step 0.001",
        "Log the result (Logs & results) and type it into the Orca filament profile",
        "Repeat the fine tower on the other printers (same filament) - compare in the notebook",
        "PLA: coarse + fine, log it",
        "Decide the printer.cfg default (Save + RESTART) - the K for your most-used filament",
        "Test print a real part with sharp corners; compare old vs new K",
    )

    def _pa_guide(self, f, td):
        left = ttk.Frame(f)
        left.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        txt = tk.Text(left, wrap="none", height=17, font=("Consolas", 9), relief="flat", bg="#fafafa")
        sb = ttk.Scrollbar(left, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", self.PA_GUIDE)
        for ln_no, ln in enumerate(self.PA_GUIDE.splitlines(), 1):
            if ln and ln == ln.upper() and not ln.startswith(" "):
                txt.tag_add("h", "%d.0" % ln_no, "%d.end" % ln_no)
        txt.tag_configure("h", font=("Consolas", 9, "bold"), foreground="#1b4f9c")
        txt.configure(state="disabled")

        right = ttk.LabelFrame(td, text="Things to do (ticks are saved in pa_todo.json)")
        right.pack(fill="both", expand=True, padx=6, pady=4)
        try:
            with open(PA_TODO, encoding="utf-8") as fh:
                done = json.load(fh)
        except (OSError, ValueError):
            done = {}
        self.todo_vars = []
        for item in self.PA_TODO_ITEMS:
            var = tk.BooleanVar(value=bool(done.get(item)))
            ttk.Checkbutton(right, text=item, variable=var, command=self.pa_save_todo).pack(anchor="w", padx=4, pady=1)
            self.todo_vars.append((item, var))
        ttk.Button(right, text="Clear ticks", command=self.pa_clear_todo).pack(anchor="e", padx=4, pady=4)

    def pa_save_todo(self):
        try:
            with open(PA_TODO, "w", encoding="utf-8") as fh:
                json.dump({item: var.get() for item, var in self.todo_vars}, fh, indent=1)
        except OSError:
            pass

    def pa_clear_todo(self):
        for _, var in self.todo_vars:
            var.set(False)
        self.pa_save_todo()

    def _fixes_tab(self, nb):
        pad = dict(padx=6, pady=3)
        f = ttk.Frame(nb)
        nb.add(f, text="  Fixes  ")
        top = ttk.Frame(f)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Root SSH password (needed for anything over SSH)").pack(side="left")
        self.ssh_pw = tk.StringVar()
        ttk.Entry(top, textvariable=self.ssh_pw, show="*", width=16).pack(side="left", padx=6)
        ttk.Label(top, text="Questions from step-by-step tests pop up as dialogs.", foreground="#666").pack(side="left", padx=10)

        def row(parent, items):
            r = ttk.Frame(parent)
            r.pack(fill="x", padx=4, pady=2)
            for label, fn in items:
                self._btn(r, label, fn).pack(side="left", padx=2)
            return r

        fan = ttk.LabelFrame(f, text="Part fan - stock M106 runs S255 at 50%")
        fan.pack(fill="x", **pad)
        row(fan, [("Check (dry run)", lambda: self.fx(["fix-fan"])),
                  ("Apply fan fix", lambda: self.fx(["fix-fan", "--apply"], "Patch M106 so S255 = 100% and RESTART Klipper?")),
                  ("Revert to stock", lambda: self.fx(["fix-fan", "--revert", "--apply"], "Put the stock (halved) M106 back and RESTART?"))])

        rd = ttk.LabelFrame(f, text="Homing fixes (key22) - DIR-pin resync after RESTART + retry22 (one servo clear + re-home on X/Y key22)")
        rd.pack(fill="x", **pad)
        row(rd, [("Check dir pins", lambda: self.fx1(["check-dir"], "Homes, reads the X/Y DIR pins, RESTARTs, reads them again. Plate must be clear.")),
                 ("Check + home after", lambda: self.fx1(["check-dir", "--home-after"], "Same, then homes straight after the restart. If the pin flipped the bed runs FORWARD into the end. Hand on e-stop.")),
                 ("Prove (both trials)", lambda: self.fx1(["prove-dir"], "Two trials: last Y move backward vs forward, RESTART, home. One is expected to crash on an unpatched Hi. Plate clear, hand on e-stop.")),
                 ("Prove - expect fixed", lambda: self.fx1(["prove-dir", "--expect-fixed"], "After fix-dir: both trials should home normally. Plate clear, hand on e-stop."))])
        row(rd, [("Fix-dir (dry run)", lambda: self.fx(["fix-dir"], ssh=True)),
                 ("Install fix-dir + retry22", lambda: self.fx(["fix-dir", "--apply", "--yes"], "Patch homing.py on the printer over SSH (DIR resync + retry22, adds whichever is missing, backup kept) and restart the Klipper service? Printer must be idle.", ssh=True)),
                 ("Revert fix-dir", lambda: self.fx(["fix-dir", "--revert", "--apply", "--yes"], "Put the original homing.py back (removes DIR resync AND retry22) and restart the Klipper service?", ssh=True)),
                 ("Restart Klipper service", lambda: self.fx(["restart-service", "--yes"], "Restart the Klipper program on the printer (not the motion board)?", ssh=True)),
                 ("Restart Klipper + host MCU", lambda: self.fx(["restart-service", "--with-mcu", "--plate-clear"],
                  "Restart klipper_mcu + Klipper over SSH? Fixes \"MCU 'rpi' ... shutdown\". Host programs only - the motion boards are not reset.", ssh=True))])
        sd = ttk.LabelFrame(f, text="Print-start freeze - a failed CFS reload at print start (e.g. key22) wedges Klipper until power-cycle")
        sd.pack(fill="x", **pad)
        row(sd, [("Fix-sdcard (dry run)", lambda: self.fx(["fix-sdcard"], ssh=True)),
                 ("Install fix-sdcard", lambda: self.fx(["fix-sdcard", "--apply", "--yes"], "Patch virtual_sdcard.py on the printer over SSH (backup kept) and restart the Klipper service? Printer must be idle.", ssh=True)),
                 ("Revert fix-sdcard", lambda: self.fx(["fix-sdcard", "--revert", "--apply", "--yes"], "Put the original virtual_sdcard.py back and restart the Klipper service?", ssh=True))])
        gb = ttk.LabelFrame(f, text="Load button: cold-grab the filament - if the filament sensor is triggered, turn the extruder gears a few mm (cold, nothing extruded) so the filament is held while the nozzle heats")
        gb.pack(fill="x", **pad)
        self.gr_mm = tk.StringVar(value="4")
        self.gr_speed = tk.StringVar(value="5")
        self.gr_clear = tk.BooleanVar(value=False)
        g1 = ttk.Frame(gb)
        g1.pack(fill="x", padx=4, pady=2)
        ttk.Label(g1, text="turn the extruder").pack(side="left")
        ttk.Entry(g1, textvariable=self.gr_mm, width=5).pack(side="left", padx=3)
        ttk.Label(g1, text="mm at").pack(side="left")
        ttk.Entry(g1, textvariable=self.gr_speed, width=5).pack(side="left", padx=3)
        ttk.Label(g1, text="mm/s").pack(side="left")
        ttk.Checkbutton(g1, text="Plate is clear (ok to forget the parked height for the Klipper restart)", variable=self.gr_clear).pack(side="left", padx=12)
        row(gb, [("Check (dry run)", lambda: self.grab([])),
                 ("Install cold-grab", lambda: self.grab(["--apply"], "Add GRAB_FILAMENT to the load button and RESTART Klipper? Printer must be idle.")),
                 ("Revert to stock load button", lambda: self.grab(["--revert", "--apply"], "Put Creality's stock load button back and RESTART Klipper?")),
                 ("Show last load-button run (read only)", lambda: self.fx(["grab-check"], ssh=True))])
        lg = ttk.LabelFrame(f, text="Look back in the printer's logs (read only) - what was pressed on the screen / sent as gcode in a time window")
        lg.pack(fill="x", **pad)
        self.ui_from = tk.StringVar(value="2026-10-29")
        self.ui_to = tk.StringVar(value="2026-10-29")
        r1 = ttk.Frame(lg)
        r1.pack(fill="x", padx=4, pady=2)
        ttk.Label(r1, text="From").pack(side="left")
        ttk.Entry(r1, textvariable=self.ui_from, width=18).pack(side="left", padx=4)
        ttk.Label(r1, text="To").pack(side="left")
        ttk.Entry(r1, textvariable=self.ui_to, width=18).pack(side="left", padx=4)
        ttk.Label(r1, text="(whole days: YYYY-MM-DD, or add HH:MM)", foreground="#666").pack(side="left", padx=6)
        row(lg, [("Pull ALL logs to folder", lambda: self.fx(["pull-logs"], ssh=True))])
        row(lg, [("Find extrude / filament / heat events", lambda: self.fx(
            ["ui-log", "--from", self.ui_from.get().strip(), "--to", self.ui_to.get().strip()], ssh=True))])
        ota = ttk.LabelFrame(f, text="Hide firmware updates - points Creality's update host at 0.0.0.0 in the printer's hosts file (no restart needed)")
        ota.pack(fill="x", **pad)
        self.ota_hosts = tk.StringVar()
        r0 = ttk.Frame(ota)
        r0.pack(fill="x", padx=4, pady=2)
        ttk.Label(r0, text="Extra hosts (optional, comma separated)").pack(side="left")
        ttk.Entry(r0, textvariable=self.ota_hosts, width=48).pack(side="left", padx=6)
        row(ota, [("Watch update check (90 s)", lambda: self.fx(["watch-ota"],
                   "After you click OK, press the firmware update check on the Hi's screen (Settings > About > Check for updates). "
                   "Watches for 90 seconds, read only.", ssh=True))])
        row(ota, [("List cloud hosts (read only)", lambda: self.fx(["cloud-hosts"], ssh=True))])
        row(ota, [("Find update hosts (dry run)", lambda: self.ota([])),
                  ("Block updates", lambda: self.ota(["--apply"], "Add the update hosts above to this printer's /etc/hosts as 0.0.0.0 (backup kept)?")),
                  ("Unblock updates", lambda: self.ota(["--revert", "--apply"], "Remove our block from this printer's /etc/hosts?"))])
        r = row(rd, [("Repro restart failure", self.repro_restart)])
        self.rr_rounds = tk.StringVar(value="3")
        self.rr_m84 = tk.BooleanVar(value=False)
        ttk.Label(r, text="rounds").pack(side="left", padx=(10, 2))
        ttk.Entry(r, textvariable=self.rr_rounds, width=4).pack(side="left")
        ttk.Checkbutton(r, text="motors off before RESTART", variable=self.rr_m84).pack(side="left", padx=8)

        hm = ttk.LabelFrame(f, text="key22 homing crash - 'No trigger on y after full movement'")
        hm.pack(fill="x", **pad)
        row(hm, [("Homing config", lambda: self.fx(["homing"])),
                 ("Fix-homing (dry run)", lambda: self.fx(["fix-homing"])),
                 ("Apply fix-homing", lambda: self.fx(["fix-homing", "--apply"], "Add the servo-fault clear to [homing_override] and RESTART?")),
                 ("Apply + stress test", lambda: self.fx(["fix-homing", "--apply", "--test"], "Apply the fix, RESTART, then park near each corner and re-home. Plate clear, hand on e-stop."))])
        row(hm, [("Corner stress test", lambda: self.fx(["test-home", "--apply"], "Park near each end of travel, release motors and re-home X/Y. On an unpatched Hi this reproduces key22. Plate clear, hand on e-stop.")),
                 ("Repro servo fault", lambda: self.fx1(["repro-fault"], "Pushes the bed slowly into the front end on purpose to make the Y servo fault, then checks homing recovers. Plate clear, hand on e-stop.")),
                 ("Diagnose homing (step by step)", lambda: self.fx1(["diagnose-home"], "Steps through homing near the end of travel and asks what the bed did after each step. Plate clear."))])

    def gui_ask(self, prompt):
        """hi_tool._ask replacement: called from the worker thread, shows a dialog on the UI thread."""
        ev, box = threading.Event(), {}

        def show():
            box["v"] = simpledialog.askstring("Printer question", prompt, parent=self) or ""
            ev.set()

        self.after(0, show)
        ev.wait()
        self.q.put("  >>> %s %s\n" % (prompt, box["v"]))
        return box["v"]

    def _ssh_args(self):
        pw = self.ssh_pw.get().strip()
        return ["--ssh-password", pw] if pw else []

    def fx(self, args, confirm=None, ssh=False):
        """Commands that take the printer as a normal target."""
        if confirm and not messagebox.askyesno(args[0], "%s\n\nPrinter: %s" % (confirm, self.target()), icon="warning"):
            return
        self.run_args([args[0], self.target()] + args[1:] + (self._ssh_args() if ssh else []))

    def grab(self, extra, confirm=None):
        args = ["fix-grab"] + extra + ["--mm", self.gr_mm.get().strip() or "4", "--speed", self.gr_speed.get().strip() or "5"]
        if self.gr_clear.get():
            args.append("--plate-clear")
        self.fx(args, confirm)

    def ota(self, extra, confirm=None):
        h = self.ota_hosts.get().strip()
        self.fx(["block-ota"] + extra + (["--hosts", h] if h and "--revert" not in extra else []), confirm, ssh=True)

    def fx1(self, args, confirm):
        """Single-target test commands that move the printer."""
        if not messagebox.askyesno(args[0], "%s\n\nPrinter: %s" % (confirm, self.target()), icon="warning"):
            return
        self.run_args([args[0], self.target()] + args[1:])

    def repro_restart(self):
        try:
            rounds = int(self.rr_rounds.get())
        except ValueError:
            rounds = 3
        if not messagebox.askyesno("repro-restart", "Park at X130 Y260, RESTART with the motors %s, re-home X/Y - %d round(s). "
                                   "Judged from klippy.log; you'll be asked what you saw.\n\nPlate clear, hand on e-stop.\n\nPrinter: %s"
                                   % ("off" if self.rr_m84.get() else "on", rounds, self.target()), icon="warning"):
            return
        self.run_args(["repro-restart", self.target(), "--rounds", str(rounds)] + (["--m84"] if self.rr_m84.get() else []))

    # ================================================================ helpers
    def _btn(self, parent, text, cmd):
        b = ttk.Button(parent, text=text, command=cmd)
        self.buttons.append(b)
        return b

    def target(self):
        return self.printer.get().strip()

    def preset(self, lanes, spacing, speed):
        self.v["lanes"].set(str(lanes))
        self.v["spacing"].set(str(spacing))
        if speed:
            self.v["speed"].set(speed)

    def write(self, s):
        for line in s.splitlines(True):
            st = line.lstrip()
            tag = ("ok" if st.startswith("[OK]") or st.startswith("READY") else
                   "warn" if st.startswith("[WARN]") else
                   "fail" if st.startswith(("[FAIL]", "[ERROR]", "NOT READY")) else
                   "cmd" if st.startswith("$ ") else None)
            self.text.insert("end", line, tag)
            if st.startswith("NOT READY"):
                self.verdict.configure(text="NOT READY", fg="#c00000")
            elif st.startswith("READY"):
                self.verdict.configure(text="READY" + (" (warnings)" if "warning" in st else ""),
                                       fg="#b07800" if "warning" in st else "#008000")
        self.text.see("end")

    def drain(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item is None:
                    self.set_busy(False)
                else:
                    self.write(item)
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def set_busy(self, busy):
        self.busy = busy
        for b in self.buttons:
            b.state(["disabled"] if busy else ["!disabled"])
        self.status.configure(text="working..." if busy else "ready")

    def run_args(self, args):
        if self.busy:
            return
        if not self.target():
            messagebox.showwarning("Printer", "Pick a printer first.")
            return
        self.set_busy(True)
        shown = ["***" if i and args[i - 1] == "--ssh-password" else x for i, x in enumerate(args)]
        self.q.put("\n$ python hi_tool.py %s\n" % " ".join(shlex.quote(x) for x in shown))

        def job():
            try:
                rc = hi_tool.main(args)
                self.q.put("[exit %s]\n" % rc)
            except SystemExit as e:
                self.q.put("[exit %s]\n" % e.code)
            except Exception as e:  # never kill the window
                self.q.put("[ERROR] %s: %s\n" % (type(e).__name__, e))
            finally:
                self.q.put(None)

        threading.Thread(target=job, daemon=True).start()

    # ================================================================ printer tab
    def run_simple(self, cmd):
        if cmd == "restart" and not messagebox.askyesno("RESTART", "Send a host RESTART to %s?" % self.target()):
            return
        self.run_args([cmd, self.target()])

    def send_gcode(self):
        line = self.gline.get().strip()
        if line:
            self.checked_run(["gcode", self.target(), line], "send '%s'" % line)

    def checked_run(self, args, what):
        """Check the printer isn't printing BEFORE running; if it is, say which job and ask (default No)."""
        if self.busy:
            return
        tgt = self.target()
        self.q.put("\n# checking %s isn't printing before you %s...\n" % (tgt, what))

        def probe():
            try:
                p = hi_tool.Printer(tgt, timeout=5, retries=0)
                st = p.state()
                job = ""
                if st.get("busy"):
                    try:
                        s2 = p.query("print_stats", "virtual_sdcard")
                        fn = s2.get("print_stats", {}).get("filename") or ""
                        pr = s2.get("virtual_sdcard", {}).get("progress")
                        job = fn + (" (%.0f%%)" % (pr * 100) if fn and pr is not None else "")
                    except Exception:
                        pass
                res = (st.get("busy") or [], job, st.get("query_error"))
            except Exception as e:
                res = (None, "", str(e))
            self.after(0, lambda: decide(*res))

        def decide(busy, job, err):
            if busy is None:
                self.q.put("[ERROR] can't reach %s (%s) - not sending\n" % (tgt, err))
                return
            if busy:
                msg = ("%s is BUSY%s:\n  - %s\n\nDo you really want to %s on THIS printer?"
                       % (tgt, (" - " + job) if job else "", "\n  - ".join(busy), what))
                if not messagebox.askyesno("Printer is busy", msg, icon="warning", default="no"):
                    self.q.put("cancelled - %s is busy%s\n" % (tgt, (" (" + job + ")") if job else ""))
                    return
                self.run_args(args + ["--force"])
                return
            self.q.put("%s is idle\n" % tgt)
            self.run_args(args)

        threading.Thread(target=probe, daemon=True).start()

    # ================================================================ ramming tab
    def pick_cfg(self):
        f = filedialog.askopenfilename(title="ramming.cfg", initialdir=HERE,
                                       filetypes=[("Klipper config", "*.cfg"), ("All files", "*.*")])
        if f:
            self.cfg_path.set(f)

    def run_install(self, apply):
        args = ["install-ram", self.target(), "--cfg", self.cfg_path.get()]
        if apply:
            if not messagebox.askyesno("Install", "Upload %s to %s and RESTART Klipper?\n\n"
                                       "A full config backup is taken first and it rolls back if Klipper "
                                       "doesn't come back ready." % (os.path.basename(self.cfg_path.get()), self.target())):
                return
            args.append("--apply")
        self.run_args(args)

    def pick_gcode(self):
        f = filedialog.askopenfilename(title="Sliced gcode", initialdir=os.path.join(HERE, "..", "gcode"),
                                       filetypes=[("G-code or sliced 3mf", "*.gcode *.3mf"), ("G-code", "*.gcode"),
                                                  ("Sliced 3mf (MakerWorld etc.)", "*.3mf"), ("All files", "*.*")])
        if not f:
            return
        if f.lower().endswith(".3mf"):
            f = self.extract_3mf(f)
            if not f:
                return
        self.gcode_path.set(f)
        try:
            g = hi_tool.ram_params_from_gcode(f)
        except Exception as e:
            messagebox.showerror("Gcode", str(e))
            return
        self.v["cx"].set("%.2f" % g["center_x"])
        self.v["cy"].set("%.2f" % g["center_y"])
        self.v["top"].set("%.2f" % g["top_z"])
        b = g["bbox"]
        msg = "footprint X %.1f..%.1f  Y %.1f..%.1f  (%s)" % (b[0], b[2], b[1], b[3], g["source"])
        if g["top_z"] < hi_tool.MIN_RAM_TOP:
            msg += "  -  under %.0f mm: the macro will NOT ram this" % hi_tool.MIN_RAM_TOP
        if g["calls_ram"]:
            msg += "  -  this file already rams at the end of the print"
        if b[2] - b[0] > 120 and self.v["lanes"].get().strip() == "1":
            self.v["lanes"].set("3")
            msg += "  -  wide plate, lanes set to 3"
        self.foot.configure(text=msg)
        self.verdict.configure(text="")

    def extract_3mf(self, path, warn=True):
        """Pull one plate's gcode out of a .gcode.3mf next to it; returns the .gcode path or None."""
        try:
            plates = hi_tool.list_3mf_plates(path)
            if not plates:
                messagebox.showerror("3mf", "%s has no sliced gcode inside - it's a project file. Slice it first."
                                     % os.path.basename(path))
                return None
            plate = plates[0][0]
            if len(plates) > 1:
                plate = simpledialog.askinteger("Which plate?", "%s has sliced plates: %s\nWhich one?" % (
                    os.path.basename(path), ", ".join(str(n) for n, _ in plates)), parent=self,
                    initialvalue=plates[0][0])
                if plate is None:
                    return None
            info = hi_tool.gcode_from_3mf(path, plate)
        except Exception as e:
            messagebox.showerror("3mf", str(e))
            return None
        self.write("extracted plate %d of %s -> %s (sliced for %s)\n" % (
            info["plate"], os.path.basename(path), info["path"], info["printer_model"] or "unknown printer"))
        if not info["is_hi"]:
            self.write("[WARN] this gcode was sliced for %s, not a Creality Hi - re-slice it before printing on a Hi\n"
                       % (info["printer_model"] or "another printer"))
            if warn:
                messagebox.showwarning("Not a Hi gcode", "This gcode was sliced for %s, not a Creality Hi.\n\n"
                                       "Fine for checking ram positions, but re-slice it before printing on a Hi."
                                       % (info["printer_model"] or "another printer"))
        return info["path"]

    def run_ram(self, mode):
        try:
            for k in ("cx", "cy", "top"):
                float(self.v[k].get())
            wait, lanes = int(self.v["wait"].get() or 0), int(self.v["lanes"].get() or 1)
            spacing = float(self.v["spacing"].get() or 40)
            speed = self.v["speed"].get().strip()
            speed = int(speed) if speed else None
        except ValueError:
            messagebox.showwarning("Ram", "Centre X/Y, Top Z and the options must be numbers (pick a gcode file to fill them).")
            return
        args = ["ram-check" if mode == "check" else "ram", self.target(),
                "--wait", str(wait), "--lanes", str(lanes), "--spacing", str(spacing),
                "--cfg", self.cfg_path.get()]
        gpath = self.gcode_path.get().strip()
        if gpath and os.path.isfile(gpath):
            args += ["--gcode", gpath]
        args += ["--center-x", self.v["cx"].get(), "--center-y", self.v["cy"].get(), "--top-z", self.v["top"].get()]
        if speed:
            args += ["--ram-speed", str(speed)]
        if not self.push_edge.get():
            args.append("--stop-short")
        if self.from_park.get():
            args.append("--from-park")
        if mode == "apply":
            if not messagebox.askyesno("RAM NOW", "Ram the plate on %s now?\n\n"
                                       "- bin in front of the printer\n- hand near the e-stop\n"
                                       "- nobody has moved the bed or toolhead since the print ended\n\n"
                                       "The readiness check runs first and stops on any FAIL." % self.target(),
                                       icon="warning"):
                return
            args.append("--apply")
        self.verdict.configure(text="")
        self.run_args(args)


if __name__ == "__main__":
    App().mainloop()
