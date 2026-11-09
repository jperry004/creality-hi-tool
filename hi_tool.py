#!/usr/bin/env python3
"""
hi_tool.py - talk to Creality Hi printers (Klipper + Moonraker) over the LAN.

Pure standard-library Python 3.8+. Works on Windows, macOS, Linux. No pip installs.

Targets can be just the last number of the IP: 104 means 192.168.1.104 (change SUBNET below).
Full forms also work: HOST[:PORT] or NAME=HOST[:PORT] (e.g. hi1=104, 192.168.1.104:4408).
If no port is given it tries 4408 (Creality web UI proxy), 7125 (Moonraker), then 80.

Commands
  info        connection, Klipper state, versions, homed axes
  pull        back up every config file + klippy.log + moonraker.log
  errors      recent errors from the console and klippy.log, grouped by Creality key code
  homing      homing-related config and any blind "pre-home" moves that cause the key22 crash
  fix-homing  add a servo fault clear to the start of [homing_override], RESTART, verify (dry run unless --apply)
  test-home   park near each corner, release motors, re-home X/Y - reproduces the key22 crash
  gcode       send a gcode line (FIRMWARE_RESTART is blocked)
  restore     upload a backup folder made by pull / fix-homing back to the printer
  fetch-src   copy Creality's Klipper source (/usr/share/klipper/klippy) over SSH (asks for root password)
  ssh         run one shell command on the printer over SSH and print the output
  check-dir   home, read the X/Y direction pins, RESTART, read them again: shows whether a restart
              leaves Y's direction pin flipped (add --home-after to also home and watch the bed)
  prove-dir   two trials: last Y move backward vs forward before a RESTART, then home - proves the
              restart direction-pin bug both ways
  fix-dir     install the fixes in Creality's homing.py over SSH: DIR-pin resync + retry22 (one
              servo-clear + retry when an X/Y homing move ends in key22). Dry run unless --apply,
              --revert puts the original back
  fix-sdcard  patch Creality's virtual_sdcard.py so a failing CFS reload at print start (e.g. key22) ends
              the print with an error instead of wedging Klipper (cancel/RESTART hang until power-cycle).
              Dry run unless --apply, --revert puts the original back
  restart-service  restart the Klipper program on the printer (/etc/init.d/klipper) - needed to load
              changed Python code; shows the init script and asks first
  install-ram upload ramming.cfg (REMOVE_PART_DYNAMIC) and add [include ramming.cfg] to printer.cfg,
              RESTART, verify, roll back on failure (dry run unless --apply; --cfg PATH picks the file)
  ram-check   readiness checklist for ramming (Klipper, macro version, homing/park, heaters, part height,
              where the casing comes down vs the real part outlines, push distance) - moves nothing
  recover-z   after a Klipper restart with parts on the plate: home X/Y, go to a spot clear of the parts,
              paper-test Z there (never G28 Z). Steps: home-xy, goto --height H, jog --dz, set
  jog-z       move Z without homing: --unlock Z (a guess, nothing moves) then --dz jogs, both Z motors together
  ram         run REMOVE_PART_DYNAMIC from outside a print (runs ram-check first). --gcode PATH reads the part centre and
              height from the sliced file; --from-park re-homes X/Y after END_PRINT's M84 without
              touching Z (dry run unless --apply)
  fix-fan     stock M106 halves the part fan (S255 -> 50%); patch it so S255 = true 100% (dry run unless
              --apply, --revert undoes it), checks the real PWM before and after
  block-ota   stop the printer finding Creality firmware updates: scans it over SSH for Creality update hosts and
              points them at 0.0.0.0 in /etc/hosts (marked block, backup kept). Dry run unless --apply;
              --hosts a.com,b.com adds names by hand; --revert --apply removes the block
  watch-ota   read only: for ~90 s record the printer's outside connections and new log lines, to spot the update
              server's host name while you press 'check for update' on its screen
  restart     host RESTART only (FIRMWARE_RESTART is never used), waits for Klipper + servo init
  pa          pressure advance: 'pa status 104 [--gcode F]' live/saved value, the Creality lock, silent mode,
              what a sliced file sets; 'pa set 104 --k 0.035' live (works mid-print); 'pa save 104 --k 0.035'
              writes printer.cfg + RESTART (rollback on failure); 'pa test 104 --start 0 --end 0.1
              --step 0.005 [--upload|--print]' line-test gcode; 'pa firmware 104' Motion Advance over SSH;
              'pa preflight 104 [--gcode F] [--apply]' ready for a calibration print? (--apply unlocks / leaves
              silent mode); 'pa tower 104 --gcode F [--height H]' Z -> K map of a sliced Orca PA tower;
              'pa watch 104 [--minutes 180]' logs every K change with Z while it prints (CSV in
              hi_backups/pa_logs); 'pa history 104' PA commands/answers in the console log + recent prints.
              'pa verify 104 [--via-print --apply]' are PA commands obeyed? sets test values from the console
              (SET_PRESSURE_ADVANCE, M900, smooth_time, the Creality lock) and optionally from a tiny print file
              (no heat, no motion), reads them back, always restores the original K.
  pa-fleet    one line per printer: live / saved K, lock, silent mode ('pa-fleet 104 105 106').
              Dry run unless --apply.
  install-beeper  Klipper M300 / BEEP macros on the Hi's buzzer (pwmchip0/pwm6 via [mcu rpi]); pitch fixed by
              --freq; restarts klipper_mcu + Klipper over SSH, test beep, rolls back on failure.
  recover     Klipper in error? reads why; host MCU (rpi) / Klipper problems -> restarts klipper_mcu + Klipper
              over SSH; a shut-down motion board -> tells you to power-cycle (--apply to act)
  cfs         CFS filament box: 'cfs status 105' Klipper's box objects; 'cfs debug 105' also the slot data
              files and recent box lines from klippy.log over SSH (read-only)
  webcam      Fluidd camera: 'webcam add 104 105 106 --apply' puts the Hi's built-in camera
              (http://IP:8000/?action=stream, shown as an iframe) into Fluidd on each printer;
              'webcam list 104' shows the cameras and whether the stream answers;
              'webcam remove 105 --name HICAM --apply' takes one out. Dry run unless --apply.
              ('webcam copy 105 --from 104' copies whatever another printer has, for non-Hi setups)
  repro-restart  reproduce a restart-then-home failure: park, RESTART with motors still on, re-home X/Y;
              repeats N rounds and judges each from klippy.log (Y servo status byte, key codes)
  repro-fault    make the Y servo fault on purpose (slow controlled push into the front end), then show
              whether homing recovers by itself - proves the fault mechanism and the fix
  diagnose-home  step through homing one stage at a time near the end of travel and ask what
              the bed did after each step; saves a report + the matching klippy.log section

Safety rules built in
  * Never sends FIRMWARE_RESTART (locks up the Hi). Only the host RESTART is used.
  * Refuses to write, restart, or move if the printer is printing or paused (unless --force).
  * Always takes a full backup before changing a file, verifies each upload by checksum,
    and rolls back automatically if Klipper does not come back "ready" after RESTART.
  * Motion gcode is never retried automatically (a timeout does not mean it did not run).
  * One printer failing never stops the others; a summary is printed at the end.

Examples
  python hi_tool.py info hi1=101
  python hi_tool.py errors 104
  python hi_tool.py homing 104
  python hi_tool.py fix-homing 104   (dry run, shows the diff)
  python hi_tool.py fix-homing --apply --test 104   (patch, restart, stress test)
  python hi_tool.py pull -f printers.txt   (one target per line)
"""

import argparse
import csv
import datetime as dt
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import tarfile
import io
import posixpath
import sys
import threading
import time
import uuid
import zipfile
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"
DEFAULT_PORTS = (4408, 7125, 80)
SUBNET = "192.168.1."   # change to your LAN, e.g. "192.168.0."
# Root password for SSH on the Hi printers (override with --ssh-password or the HI_SSH_PASSWORD env var).
DEFAULT_SSH_PASSWORD = ""   # blank = ask for it (or set it in the GUI Fixes tab / HI_SSH_PASSWORD env var)
MARK = "HI-FIX"
BLOCKED_GCODE = re.compile(r"^\s*FIRMWARE_RESTART\b", re.I | re.M)
BUSY_STATES = ("printing", "paused")

try:  # never crash on a Windows console because of an odd character
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

_LOG_FH = None
# Printers are on the LAN: ignore any system/corporate proxy settings (Windows registry, env vars).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(msg="", level="INFO"):
    line = msg if level == "INFO" else "[%s] %s" % (level, msg)
    print(line, flush=True)
    if _LOG_FH:
        try:
            _LOG_FH.write("%s %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))
            _LOG_FH.flush()
        except Exception:
            pass


class ToolError(Exception):
    pass


# --------------------------------------------------------------------------- HTTP / Moonraker

class Printer:
    def __init__(self, target, api_key=None, timeout=10.0, retries=3):
        self.target = target.strip()
        name, _, hostport = self.target.rpartition("=")
        hostport = hostport.replace("http://", "").replace("https://", "").strip("/")
        if re.fullmatch(r"\d{1,3}(:\d+)?", hostport):
            hostport = SUBNET + hostport
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
            self.ports = (int(port),)
        else:
            host, self.ports = hostport, DEFAULT_PORTS
        self.host = host
        self.name = name or host
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.base = None

    # ---- low level
    def _open(self, method, url, data=None, headers=None, timeout=None, retries=None):
        """Returns (status, body). Retries only network errors and 5xx."""
        retries = self.retries if retries is None else retries
        timeout = self.timeout if timeout is None else timeout
        hdrs = {"User-Agent": "creality-hi-tool/" + VERSION}
        if self.api_key:
            hdrs["X-Api-Key"] = self.api_key
        hdrs.update(headers or {})
        last = None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
                with _OPENER.open(req, timeout=timeout) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                body = b""
                try:
                    body = e.read()
                except Exception:
                    pass
                if e.code >= 500 and attempt < retries:
                    last = "HTTP %s" % e.code
                else:
                    return e.code, body
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
                last = getattr(e, "reason", e)
            if attempt < retries:
                time.sleep(min(1.5 * (2 ** attempt), 8))
        raise ToolError("%s %s failed: %s" % (method, url, last))

    def connect(self):
        errs = []
        for p in self.ports:
            base = "http://%s:%s" % (self.host, p)
            try:
                st, body = self._open("GET", base + "/server/info", timeout=5, retries=1)
                if st == 401 or st == 403:
                    errs.append("%s: HTTP %s (needs --api-key?)" % (p, st))
                    continue
                j = json.loads(body.decode("utf-8", "replace"))
                if "result" in j:
                    self.base = base
                    return j["result"]
                errs.append("%s: not Moonraker" % p)
            except Exception as e:
                errs.append("%s: %s" % (p, e))
        raise ToolError("no Moonraker at %s (%s)" % (self.host, "; ".join(errs)))

    def req(self, method, path, params=None, body=None, headers=None, timeout=None, retries=None, raw=False):
        if not self.base:
            self.connect()
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
            headers = dict(headers or {}, **{"Content-Type": "application/json"})
        st, data = self._open(method, url, data=body, headers=headers, timeout=timeout, retries=retries)
        if st >= 400:
            raise ToolError("HTTP %s on %s: %s" % (st, path, _err_msg(data)))
        if raw:
            return data
        try:
            j = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            raise ToolError("bad JSON from %s" % path)
        return j.get("result", j)

    # ---- helpers
    def query(self, *objects):
        url_q = "&".join(urllib.parse.quote(o) for o in objects)
        res = self.req("GET", "/printer/objects/query?" + url_q)
        return res.get("status", {})

    def printer_info(self):
        return self.req("GET", "/printer/info")

    def state(self):
        try:
            s = self.query("print_stats", "webhooks", "toolhead", "virtual_sdcard", "idle_timeout",
                           "extruder", "heater_bed")
        except ToolError as e:
            return {"klippy": "unavailable", "print": "unknown", "homed": "", "message": "", "position": None,
                    "query_error": str(e), "busy": []}
        ps, vs, it = s.get("print_stats", {}), s.get("virtual_sdcard", {}), s.get("idle_timeout", {})
        ext, bed = s.get("extruder", {}), s.get("heater_bed", {})
        busy = []
        if ps.get("state") in BUSY_STATES:
            busy.append("print_stats says %s" % ps.get("state"))
        if vs.get("is_active"):
            busy.append("a file is being printed from the SD card (virtual_sdcard active)")
        if it.get("state") == "Printing":
            busy.append("Klipper is executing gcode right now (idle_timeout: Printing)")
        if ext.get("target", 0) > 0 or bed.get("target", 0) > 0:
            busy.append("heaters are on (hotend target %.0f, bed target %.0f) - a print may be running from "
                        "the screen or Creality app" % (ext.get("target", 0), bed.get("target", 0)))
        return {
            "klippy": s.get("webhooks", {}).get("state", "?"),
            "message": s.get("webhooks", {}).get("state_message", ""),
            "print": ps.get("state", "?"),
            "homed": s.get("toolhead", {}).get("homed_axes", ""),
            "position": s.get("toolhead", {}).get("position"),
            "z_max": (s.get("toolhead", {}).get("axis_maximum") or [0, 0, 0])[2],
            "busy": busy,
        }

    def assert_idle(self, force=False, keep_position=False):
        """Refuse unless the printer is clearly idle. Fails CLOSED: if Klipper says it is ready but the status
        can't be read, we refuse rather than guess. keep_position=True also refuses when the printer is
        parked unhomed above the bed (a RESTART would throw away the parked position, e.g. before a ram)."""
        st = self.state()
        if force:
            return st
        if st.get("query_error"):
            try:
                info = self.req("GET", "/printer/info", timeout=5, retries=1)
            except ToolError:
                info = {}
            if info.get("state") == "ready":
                raise ToolError("couldn't read the printer status (%s) - refusing, it might be printing"
                                % st["query_error"])
            return st  # Klipper itself is down (error/shutdown/startup) - nothing can be printing
        if st["busy"]:
            raise ToolError("printer looks busy - refusing (use --force only if you are sure):\n    - "
                            + "\n    - ".join(st["busy"]))
        pos = st.get("position") or [0, 0, 0]
        if keep_position and st["klippy"] == "ready" and not st["homed"] and pos[2] > 5:
            raise ToolError("printer is parked unhomed at Z%.1f after END_PRINT. This would forget that height, which "
                            "only matters if parts on the plate are still waiting to be rammed (RAM NOW 'parked after "
                            "END_PRINT'). Plate already clear / not ramming? add --plate-clear" % pos[2])
        return st

    def list_config(self):
        res = self.req("GET", "/server/files/list", params={"root": "config"})
        out = []
        for f in res if isinstance(res, list) else []:
            p = f.get("path") or f.get("filename")
            if p:
                out.append({"path": p, "size": f.get("size", 0), "perm": f.get("permissions", "rw")})
        return out

    def get_config(self, path):
        return self.req("GET", "/server/files/config/" + urllib.parse.quote(path, safe="/"),
                        raw=True, timeout=max(self.timeout, 30))

    def upload_config(self, path, data):
        folder, fname = os.path.split(path)
        boundary = "----hi" + uuid.uuid4().hex
        parts = []
        for k, v in (("root", "config"), ("path", folder)):
            parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                          % (boundary, k, v)).encode())
        parts.append(('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
                      'Content-Type: application/octet-stream\r\n\r\n' % (boundary, fname)).encode())
        parts.append(data + b"\r\n")
        parts.append(("--%s--\r\n" % boundary).encode())
        self.req("POST", "/server/files/upload", body=b"".join(parts),
                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                 timeout=60, retries=2)
        back = self.get_config(path)
        if sha(back) != sha(data):
            raise ToolError("upload verify failed for %s (checksum mismatch)" % path)

    def get_log(self, name):
        for path in ("/server/files/logs/" + name, "/server/files/" + name):
            try:
                return self.req("GET", path, raw=True, timeout=180, retries=1)
            except ToolError:
                continue
        return None

    def gcode(self, script, timeout=120):
        if BLOCKED_GCODE.search(script):
            raise ToolError("FIRMWARE_RESTART is blocked - it locks up the Hi. Use RESTART.")
        # never retried: a timeout does not mean the move did not happen
        return self.req("POST", "/printer/gcode/script", body={"script": script},
                        timeout=timeout, retries=0)

    def restart(self, wait=180, check=True):
        """Host RESTART only. Never FIRMWARE_RESTART. Re-checks the printer is idle right before sending
        (a print could have started while we were backing up / uploading); rollbacks pass check=False."""
        if check:
            st = self.state()
            if st.get("busy"):
                raise ToolError("not restarting - the printer became busy:\n    - " + "\n    - ".join(st["busy"]))
        log("  sending RESTART (host restart, not FIRMWARE_RESTART)")
        try:
            self.req("POST", "/printer/restart", timeout=15, retries=0)
        except ToolError as e:
            log("  restart request: %s (continuing to wait)" % e, "WARN")
        time.sleep(3)
        return self.wait_ready(wait)

    def wait_ready(self, wait=180):
        t0, last = time.time(), None
        while time.time() - t0 < wait:
            try:
                info = self.req("GET", "/printer/info", timeout=5, retries=0)
                last = info.get("state"), info.get("state_message", "")
                if last[0] == "ready":
                    log("  Klipper ready after %.0fs" % (time.time() - t0))
                    return True, ""
                if last[0] in ("error", "shutdown"):
                    time.sleep(3)  # give it a moment; errors at startup are final
                    info = self.req("GET", "/printer/info", timeout=5, retries=0)
                    if info.get("state") in ("error", "shutdown"):
                        return False, info.get("state_message", "")
            except ToolError:
                pass
            time.sleep(2)
        return False, "timed out waiting for ready (last: %s)" % (last,)

    def configfile(self):
        return self.query("configfile").get("configfile", {})


def _err_msg(data):
    try:
        j = json.loads(data.decode("utf-8", "replace"))
        e = j.get("error", j)
        return e.get("message", str(e)) if isinstance(e, dict) else str(e)
    except Exception:
        return data[:300].decode("utf-8", "replace")


def sha(b):
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- config analysis

SECTION_RE = re.compile(r"^\[([^\]]+)\]")
G28_RE = re.compile(r"\bG28(?:\.\d+)?\b([^;#\n]*)", re.I)
HOMECALL_RE = re.compile(r"\b_?HOME_([XYZ]{1,3})\b", re.I)
MOVE_RE = re.compile(r"^\s*G0?[01]\b(.*)$", re.I)
AXIS_RE = re.compile(r"(?<![A-Za-z_])([XY])\s*(?=[-+\d.{])", re.I)
FORCE_RE = re.compile(r"^\s*FORCE_MOVE\b.*STEPPER\s*=\s*stepper_([xy])", re.I)


def sections(text):
    lines = text.splitlines(True)
    out, cur, start = [], None, 0
    for i, ln in enumerate(lines):
        m = SECTION_RE.match(ln)
        if m:
            if cur is not None:
                out.append((cur, start, i))
            cur, start = m.group(1).strip(), i
    if cur is not None:
        out.append((cur, start, len(lines)))
    return lines, out


def is_homing_section(name):
    n = name.lower()
    if n == "homing_override":
        return True
    if n.startswith("gcode_macro"):
        macro = n.split(None, 1)[1] if " " in n else ""
        return macro in ("g28",) or "home" in macro and "homing" not in macro
    return False


def find_premoves(text):
    """Blind X/Y moves inside homing macros that run before that axis has been homed."""
    lines, secs = sections(text)
    findings = []
    for name, s, e in secs:
        if not is_homing_section(name):
            continue
        body = lines[s + 1:e]
        if not any(G28_RE.search(l) or HOMECALL_RE.search(l) for l in body if not l.lstrip().startswith(("#", ";"))):
            continue
        homed = set()
        for off, ln in enumerate(body):
            code = ln.split("#", 1)[0].split(";", 1)[0]
            if not code.strip():
                continue
            for m in G28_RE.finditer(code):
                axes = set(c for c in m.group(1).upper() if c in "XYZ")
                homed |= axes or {"X", "Y", "Z"}
            for m in HOMECALL_RE.finditer(code):
                homed |= set(m.group(1).upper())
            axes = set()
            mm = MOVE_RE.match(code)
            if mm:
                axes = set(a.upper() for a in AXIS_RE.findall(mm.group(1)))
            fm = FORCE_RE.match(code)
            if fm:
                axes = {fm.group(1).upper()}
            blind = axes - homed
            if blind:
                findings.append({
                    "section": name, "line": s + 1 + off, "text": ln.rstrip("\r\n"),
                    "axes": "".join(sorted(blind)),
                    "auto": "{%" not in ln,
                })
    return findings


def patch_text(text, findings):
    lines = text.splitlines(True)
    for f in findings:
        if not f["auto"]:
            continue
        ln = lines[f["line"]]
        indent = ln[: len(ln) - len(ln.lstrip())]
        eol = "\r\n" if ln.endswith("\r\n") else "\n"
        lines[f["line"]] = "%s# %s blind pre-home move disabled: %s%s" % (indent, MARK, ln.strip(), eol)
    return "".join(lines)


# --------------------------------------------------------------------------- backups

def backup(p, root, label="pull"):
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s_%s" % (p.name, p.host)) if p.name != p.host else p.host
    d = os.path.join(root, safe, "%s_%s" % (ts, label))
    os.makedirs(os.path.join(d, "config"), exist_ok=True)
    manifest = {"target": p.target, "base": p.base, "time": ts, "files": {}, "skipped": []}
    files = {}
    for f in p.list_config():
        path = f["path"]
        try:
            data = p.get_config(path)
        except ToolError as e:
            manifest["skipped"].append({"path": path, "error": str(e)})
            log("  could not read %s: %s" % (path, e), "WARN")
            continue
        dest = os.path.join(d, "config", *path.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        manifest["files"][path] = {"sha256": sha(data), "size": len(data), "perm": f["perm"]}
        files[path] = data
    os.makedirs(os.path.join(d, "logs"), exist_ok=True)
    for name in ("klippy.log", "moonraker.log"):
        data = p.get_log(name)
        if data:
            with open(os.path.join(d, "logs", name), "wb") as fh:
                fh.write(data)
    try:
        cf = p.configfile()
        with open(os.path.join(d, "configfile_settings.json"), "w", encoding="utf-8") as fh:
            json.dump(cf.get("settings", {}), fh, indent=1, default=str)
    except ToolError:
        pass
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    log("  backup: %s  (%d config files)" % (d, len(files)))
    return d, files


# --------------------------------------------------------------------------- commands

def cmd_info(p, a):
    srv = p.connect()
    log("  url:        %s" % p.base)
    log("  moonraker:  %s   klippy: %s" % (srv.get("moonraker_version", "?"), srv.get("klippy_state", "?")))
    try:
        info = p.printer_info()
        log("  klipper:    %s" % info.get("software_version", "?"))
        log("  hostname:   %s" % info.get("hostname", "?"))
        log("  config:     %s" % info.get("config_file", "?"))
    except ToolError as e:
        log("  printer/info: %s" % e, "WARN")
    st = p.state()
    log("  state:      klippy=%s print=%s homed=[%s]" % (st["klippy"], st["print"], st["homed"]))
    if st["message"] and st["klippy"] != "ready":
        log("  message:    %s" % st["message"].strip())
    try:
        log("  cfg files:  %d" % len(p.list_config()))
    except ToolError as e:
        log("  cfg files:  %s" % e, "WARN")
    return True


def cmd_pull(p, a):
    p.connect()
    backup(p, a.backup_dir)
    return True


ERR_PATTERNS = [
    ("creality_key", re.compile(r'"code"\s*:\s*"(key\d+)"')),
    ("error", re.compile(r"^!! |\bError\b|\bexception\b|Traceback|No trigger|Endstop .* still triggered|"
                         r"Lost communication|Timer too close|MCU '.*' shutdown|Move out of range|"
                         r"TMC .* reports error|shutdown", re.I)),
]


def cmd_errors(p, a):
    p.connect()
    st = p.state()
    log("  klippy=%s print=%s homed=[%s]" % (st["klippy"], st["print"], st["homed"]))
    if st["message"] and st["klippy"] != "ready":
        log("  state message: %s" % st["message"].strip())

    try:
        store = p.req("GET", "/server/gcode_store", params={"count": 300}).get("gcode_store", [])
    except ToolError as e:
        store = []
        log("  gcode_store: %s" % e, "WARN")
    hits = [g for g in store if g.get("message", "").startswith("!!") or "error" in g.get("message", "").lower()]
    log("  console: %d error lines in last %d messages" % (len(hits), len(store)))
    seen = []
    for g in hits:
        t = dt.datetime.fromtimestamp(g.get("time", 0)).strftime("%m-%d %H:%M:%S")
        msg = g["message"].strip()
        if seen and seen[-1][1] == msg:
            seen[-1][2] += 1
            continue
        seen.append([t, msg, 1])
    for t, msg, n in seen[-a.lines:]:
        log("    %s  %s%s" % (t, msg[:220], ("   (x%d)" % n) if n > 1 else ""))

    data = p.get_log("klippy.log")
    if not data:
        log("  klippy.log not available", "WARN")
        return True
    text = data.decode("utf-8", "replace").splitlines()
    codes, matches, starts = {}, [], 0
    noise, saves = 0, []
    for i, ln in enumerate(text):
        if "logging_callback" in ln and "b'buf" in ln:
            noise += 1          # CFS RS-485 debug dump logged at ERROR level - not a fault
            continue
        if "HI retry22:" in ln and ("homing once more" in ln or "second try homed" in ln):
            saves.append((i + 1, ln.strip()))
        if ln.startswith("Start printer at") or ln.startswith("===== Config file"):
            starts += 1 if ln.startswith("Start printer") else 0
        k = ERR_PATTERNS[0][1].search(ln)
        if k:
            codes[k.group(1)] = codes.get(k.group(1), 0) + 1
        if k or ERR_PATTERNS[1][1].search(ln):
            if not ln.startswith(("Stats ", "Receive:", "Sent ")):
                matches.append((i + 1, ln.strip()))
    log("  klippy.log: %d lines, %d restarts, %d error lines (+%d CFS buf_len debug lines hidden)"
        % (len(text), starts, len(matches), noise))
    if saves:
        log("  retry22 (homing.py fix) caught %d key22 trip(s):" % sum(1 for _, l in saves if "once more" in l))
        for n, ln in saves[-10:]:
            log("    L%-7d %s" % (n, ln[:220]))
    if codes:
        log("  Creality key codes: " + ", ".join("%s x%d" % kv for kv in sorted(codes.items(), key=lambda x: -x[1])))
    prev = None
    for n, ln in matches[-a.lines:]:
        if ln == prev:
            continue
        prev = ln
        log("    L%-7d %s" % (n, ln[:220]))
    if a.save:
        d = os.path.join(a.backup_dir, p.host, "logs")
        os.makedirs(d, exist_ok=True)
        fn = os.path.join(d, "klippy_%s.log" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        with open(fn, "wb") as fh:
            fh.write(data)
        log("  saved %s" % fn)
    return True


def _scan_files(p):
    files, results, readonly = {}, {}, set()
    for f in p.list_config():
        if not f["path"].lower().endswith(".cfg") or BACKUP_CFG_RE.match(os.path.basename(f["path"])):
            continue
        try:
            data = p.get_config(f["path"])
        except ToolError as e:
            log("  could not read %s: %s" % (f["path"], e), "WARN")
            continue
        files[f["path"]] = data
        if "w" not in f["perm"]:
            readonly.add(f["path"])
        fnd = find_premoves(data.decode("utf-8", "replace"))
        if fnd:
            results[f["path"]] = fnd
    return files, results, readonly


def cmd_homing(p, a):
    p.connect()
    cf = {}
    try:
        cf = p.configfile()
    except ToolError as e:
        log("  configfile query failed: %s" % e, "WARN")
    settings = cf.get("settings", {}) or {}
    raw = cf.get("config", {}) or {}
    keys = ("position_min", "position_max", "position_endstop", "homing_positive_dir", "homing_speed",
            "second_homing_speed", "homing_retract_dist", "endstop_pin")
    for ax in ("x", "y"):
        s = settings.get("stepper_" + ax, {})
        log("  [stepper_%s] " % ax + "  ".join("%s=%s" % (k, s[k]) for k in keys if k in s))
        for sec, val in settings.items():
            if sec.startswith("tmc") and sec.endswith("stepper_" + ax):
                tk = ("run_current", "home_current", "driver_sgthrs", "driver_sgt", "diag_pin", "diag1_pin")
                log("  [%s] " % sec + "  ".join("%s=%s" % (k, val[k]) for k in tk if k in val))
    for sec in raw:
        if is_homing_section(sec):
            g = raw[sec].get("gcode", "")
            log("  --- [%s] (effective) ---" % sec)
            for ln in g.strip("\n").splitlines()[: a.lines * 3]:
                log("    " + ln)

    files, results, readonly = _scan_files(p)
    if not results:
        log("  no blind pre-home X/Y moves found in the editable config files.")
        homing_secs = [s for s in raw if is_homing_section(s)]
        found_in_files = set()
        for data in files.values():
            _, secs = sections(data.decode("utf-8", "replace"))
            found_in_files |= {n for n, _, _ in secs}
        outside = [s for s in homing_secs if s not in found_in_files]
        if outside:
            log("  these homing sections are defined OUTSIDE the editable config folder: %s" % outside, "WARN")
            log("  -> they must be edited over SSH (or overridden with a later section in printer.cfg)", "WARN")
        return True
    for path, fnd in results.items():
        log("  %s%s:" % (path, "  (READ-ONLY)" if path in readonly else ""))
        for f in fnd:
            log("    line %-5d [%s] moves %s before it is homed%s:  %s" % (
                f["line"] + 1, f["section"], f["axes"], "" if f["auto"] else " (Jinja inline - manual)", f["text"].strip()))
    return True


BACKUP_CFG_RE = re.compile(r"^printer-\d{8}_\d{6}\.cfg$")
FIX_TAG = "# HI-FIX servo-clear"
FIX_LINES = [
    FIX_TAG + ": clear a latched X/Y servo fault (key789 tracking error after a crash) so it can't block homing",
    "MOTOR_STALL_MODE DATA=2",
    "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11",
]


def _find_override(p):
    """Returns (path, text) of the live config file that holds [homing_override]."""
    hits = []
    for f in p.list_config():
        path = f["path"]
        if not path.lower().endswith(".cfg") or BACKUP_CFG_RE.match(os.path.basename(path)):
            continue
        if "w" not in f["perm"]:
            continue
        text = p.get_config(path).decode("utf-8")
        if re.search(r"^\[homing_override\]", text, re.M):
            hits.append((path, text))
    if not hits:
        raise ToolError("no editable file with [homing_override] found")
    if len(hits) > 1:
        log("  [homing_override] found in several files %s - using the last one Klipper loads" % [h[0] for h in hits], "WARN")
    return hits[-1]


def patch_override(text):
    """Insert the servo fault clear at the top of [homing_override]. Returns new text or None if already done."""
    if FIX_TAG in text:
        return None
    lines = text.splitlines(True)
    _, secs = sections(text)
    for name, s, e in secs:
        if name != "homing_override":
            continue
        for i in range(s + 1, e):
            code = lines[i].split("#", 1)[0]
            if re.match(r"^\s*MOTOR_STALL_MODE\s+DATA=1\b", code, re.I):
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                eol = "\r\n" if lines[i].endswith("\r\n") else "\n"
                ins = [indent + l + eol for l in FIX_LINES]
                return "".join(lines[:i] + ins + lines[i:])
        raise ToolError("[homing_override] has no 'MOTOR_STALL_MODE DATA=1' line - unexpected Creality config, not patching")
    raise ToolError("[homing_override] section not found")


def cmd_fix(p, a):
    p.connect()
    st = p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    log("  state: klippy=%s print=%s" % (st["klippy"], st["print"]))
    path, old = _find_override(p)
    new = patch_override(old)
    if new is None:
        log("  %s already has the fix (%s). Nothing to do." % (path, FIX_TAG))
        return True
    for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), "a/" + path, "b/" + path, lineterm="", n=3):
        log("    " + ln)
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply to upload.")
        return True

    bdir, originals = backup(p, a.backup_dir, "before-fix")
    if sha(originals.get(path, b"")) != sha(old.encode("utf-8")):
        raise ToolError("%s changed on the printer while we were working - aborting" % path)
    try:
        p.upload_config(path, new.encode("utf-8"))
        log("  uploaded + verified %s" % path)
        ok, msg = p.restart()
    except ToolError as e:
        ok, msg = False, str(e)
    if ok:
        time.sleep(a.motor_wait)  # servo parameters are re-flashed after every restart
        g = p.configfile().get("config", {}).get("homing_override", {}).get("gcode", "")
        i_chk = g.find("MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11")
        i_mode = g.find("MOTOR_STALL_MODE DATA=1")
        if i_chk == -1 or i_chk > i_mode:
            ok, msg = False, "Klipper did not load the new [homing_override] (another file overrides it?)"
    if not ok:
        log("  problem: %s" % msg.strip(), "ERROR")
        log("  rolling back %s from %s" % (path, bdir), "ERROR")
        try:
            p.upload_config(path, originals[path])
        except ToolError as e:
            log("  rollback upload failed: %s" % e, "ERROR")
        ok2, msg2 = p.restart(check=False)  # rollback: no idle check (we caused this restart)
        log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    log("  fix applied and loaded. Backup of the original: %s" % bdir)
    if a.test:
        return cmd_test(p, a)
    return True


def _home_xy(p, a):
    try:
        p.gcode("G28 X Y", timeout=a.home_timeout)
        return True, ""
    except ToolError as e:
        return False, str(e)


def cmd_test(p, a):
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    cf = p.configfile().get("settings", {})
    sx, sy = cf.get("stepper_x", {}), cf.get("stepper_y", {})
    try:
        x0, x1 = float(sx["position_min"]), float(sx["position_max"])
        y0, y1 = float(sy["position_min"]), float(sy["position_max"])
    except (KeyError, TypeError, ValueError):
        raise ToolError("could not read X/Y travel limits from config")
    m = a.margin
    corners = [("max/max", x1 - m, y1 - m), ("min/min", x0 + m, y0 + m),
               ("max/min", x1 - m, y0 + m), ("min/max", x0 + m, y1 - m)]
    log("  travel X %.0f..%.0f  Y %.0f..%.0f   margin %.0f mm" % (x0, x1, y0, y1, m))

    ok, err = _home_xy(p, a)
    if not ok:
        log("  initial G28 X Y FAILED: %s" % err, "ERROR")
        return False
    st = p.state()
    if "z" in st["homed"].lower() and st["position"] and st["position"][2] < 5:
        p.gcode("G91\nG1 Z5 F600\nG90", timeout=30)

    fails = 0
    for i in range(a.rounds):
        for label, x, y in corners:
            try:
                p.gcode("G90\nG1 X%.2f Y%.2f F%d\nM400" % (x, y, a.speed), timeout=60)
                p.gcode("M84", timeout=15)
                time.sleep(0.5)
            except ToolError as e:
                log("  move to %s failed: %s" % (label, e), "ERROR")
                return False
            ok, err = _home_xy(p, a)
            log("  round %d  %-8s X%.0f Y%.0f -> M84 -> G28 X Y : %s" % (i + 1, label, x, y, "OK" if ok else "FAIL  " + err[:160]))
            if not ok:
                fails += 1
                if not a.keep_going:
                    return False
                ok, err = _home_xy(p, a)  # recover before next corner
                if not ok:
                    return False
    p.gcode("G90\nG1 X%.2f Y%.2f F%d" % ((x0 + x1) / 2, (y0 + y1) / 2, a.speed), timeout=60)
    log("  stress test: %s" % ("PASSED" if not fails else "%d FAILURES" % fails))
    return fails == 0


def cmd_gcode(p, a):
    p.connect()
    script = " ".join(a.script).replace("\\n", "\n")
    if not a.force and re.search(r"^\s*(G0|G1|G28|M84|RESTART|SAVE_CONFIG)\b", script, re.I | re.M):
        p.assert_idle(False)
    try:
        before = p.req("GET", "/server/gcode_store", params={"count": 1}).get("gcode_store", [])
        t_last = before[-1]["time"] if before else 0
    except ToolError:
        t_last = None
    err = None
    try:
        res = p.gcode(script, timeout=a.home_timeout)
        log("  -> %s" % res)
    except ToolError as e:
        err = e
    if t_last is not None:
        time.sleep(0.5)
        try:
            new = [g for g in p.req("GET", "/server/gcode_store", params={"count": 200}).get("gcode_store", [])
                   if g.get("time", 0) > t_last]
            for g in new:
                if g.get("type") == "command":
                    continue
                log("  | " + g.get("message", "").rstrip())
        except ToolError:
            pass
    if err:
        raise err
    return True


def cmd_restore(p, a):
    p.connect()
    p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    src = os.path.join(a.folder, "config") if os.path.isdir(os.path.join(a.folder, "config")) else a.folder
    if not os.path.isdir(src):
        raise ToolError("backup folder not found: %s" % a.folder)
    changes = []
    for root, _, fnames in os.walk(src):
        for fn in fnames:
            local = os.path.join(root, fn)
            rel = os.path.relpath(local, src).replace(os.sep, "/")
            with open(local, "rb") as fh:
                data = fh.read()
            try:
                cur = p.get_config(rel)
            except ToolError:
                cur = None
            if cur is None or sha(cur) != sha(data):
                changes.append((rel, data))
    if not changes:
        log("  printer already matches the backup.")
        return True
    for rel, _ in changes:
        log("  will restore %s" % rel)
    if not a.apply:
        log("  DRY RUN - re-run with --apply to upload.")
        return True
    backup(p, a.backup_dir, "before-restore")
    for rel, data in changes:
        p.upload_config(rel, data)
        log("  restored %s" % rel)
    ok, msg = p.restart()
    log("  %s %s" % ("ready" if ok else "NOT ready:", msg))
    return ok


# --------------------------------------------------------------------------- SSH (uses the system ssh client)

def _ssh_base(p, a):
    exe = shutil.which("ssh")
    if not exe:
        raise ToolError("no 'ssh' command found. On Windows 10/11: Settings > Apps > Optional features > OpenSSH Client")
    return [exe, "-p", str(a.ssh_port),
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=10",
            "%s@%s" % (a.ssh_user, p.host)]


_PARAMIKO = None


def _paramiko():
    """paramiko lets us pass the password (Windows' ssh.exe can't). Installed on first use if missing."""
    global _PARAMIKO
    if _PARAMIKO is not None:
        return _PARAMIKO or None
    try:
        import paramiko
        _PARAMIKO = paramiko
    except ImportError:
        log("  installing 'paramiko' (one time, so SSH can use the stored password) ...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "paramiko"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            import site
            import importlib
            if site.getusersitepackages() not in sys.path:
                sys.path.append(site.getusersitepackages())
            importlib.invalidate_caches()
            import paramiko
            _PARAMIKO = paramiko
        except Exception:
            log("  could not install paramiko (%s) - falling back to ssh.exe, which will ask for the password"
                % r.stderr.decode("utf-8", "replace").strip()[-200:], "WARN")
            _PARAMIKO = False
    return _PARAMIKO or None


def _ssh_password(a):
    pw = getattr(a, "ssh_password", None) or os.environ.get("HI_SSH_PASSWORD") or DEFAULT_SSH_PASSWORD
    if not pw and not (sys.stdin and sys.stdin.isatty()):
        # no console to type into (e.g. started from the GUI) - ssh.exe would hang waiting for a password
        raise ToolError("no root SSH password set - enter it in the GUI's Fixes tab "
                        "(or use --ssh-password / the HI_SSH_PASSWORD env var)")
    return pw


def _ssh_run(p, a, remote_cmd, timeout=300, data=None):
    """Runs a remote command. Returns (rc, stdout bytes, stderr text).
    Uses the stored password via paramiko; falls back to ssh.exe (which prompts) if that is unavailable."""
    pw = _ssh_password(a)
    pk = _paramiko() if pw else None
    if pk:
        c = pk.SSHClient()
        c.set_missing_host_key_policy(pk.AutoAddPolicy())
        try:
            c.connect(p.host, port=a.ssh_port, username=a.ssh_user, password=pw, timeout=10,
                      banner_timeout=15, auth_timeout=15, allow_agent=False, look_for_keys=False)
        except pk.AuthenticationException:
            raise ToolError("SSH login refused for %s@%s - wrong password? (use --ssh-password)" % (a.ssh_user, p.host))
        except Exception as e:
            raise ToolError("SSH connect to %s failed: %s" % (p.host, e))
        try:
            stdin, stdout, stderr = c.exec_command(remote_cmd, timeout=timeout)
            if data is not None:
                stdin.write(data)
                stdin.flush()
            stdin.channel.shutdown_write()
            out = stdout.read()
            err = stderr.read()
            rc = stdout.channel.recv_exit_status()
        except Exception as e:
            raise ToolError("SSH command failed on %s: %s" % (p.host, e))
        finally:
            c.close()
        return rc, out, err.decode("utf-8", "replace").strip()
    cmd = _ssh_base(p, a) + [remote_cmd]
    try:
        r = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError("ssh timed out after %ss" % timeout)
    return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace").strip()


def _safe_extract(tar_bytes, dest):
    dest_abs = os.path.abspath(dest)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        for m in tf.getmembers():
            if not (m.isfile() or m.isdir()):
                continue  # skip links/devices
            target = os.path.abspath(os.path.join(dest, m.name))
            if not target.startswith(dest_abs + os.sep) and target != dest_abs:
                continue  # path traversal guard
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tf.extractfile(m)
            if src is None:
                continue
            with open(target, "wb") as fh:
                shutil.copyfileobj(src, fh)
            n += 1
    return n


def cmd_fetch_src(p, a):
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(a.backup_dir, p.host, "klippy_src_" + ts)
    os.makedirs(dest, exist_ok=True)
    log("  ssh %s@%s - enter the printer's root password if asked" % (a.ssh_user, p.host))
    remote = ("cd %s && tar cf - --exclude='*.pyc' --exclude='__pycache__' %s 2>/dev/null"
              " || tar cf - %s" % (posixpath.dirname(a.src_path.rstrip('/')) or "/",
                                  posixpath.basename(a.src_path.rstrip('/')),
                                  posixpath.basename(a.src_path.rstrip('/'))))
    rc, out, err = _ssh_run(p, a, remote, timeout=600)
    if not out:
        raise ToolError("nothing received over ssh (rc=%s): %s" % (rc, err[-400:]))
    try:
        n = _safe_extract(out, dest)
    except tarfile.TarError as e:
        raise ToolError("could not unpack what ssh returned (%s). stderr: %s" % (e, err[-300:]))
    log("  saved %d files to %s" % (n, dest))
    # quick inventory so we know what is readable source vs compiled
    py = so = 0
    for root, _, files in os.walk(dest):
        for f in files:
            py += f.endswith(".py")
            so += f.endswith(".so")
    log("  %d .py files, %d compiled .so files" % (py, so))
    # also grab a few things that help diagnose homing
    extra = ("cat /etc/os-release 2>/dev/null; echo ---; ls -la /usr/share/klipper/klippy/extras | head -400;"
             " echo ---; ps w 2>/dev/null | grep -i klipp | grep -v grep")
    rc2, out2, _ = _ssh_run(p, a, extra, timeout=60)
    if out2:
        with open(os.path.join(dest, "_system_info.txt"), "wb") as fh:
            fh.write(out2)
    return n > 0


def cmd_ssh(p, a):
    remote = " ".join(a.remote)
    if BLOCKED_GCODE.search(remote):
        raise ToolError("FIRMWARE_RESTART is blocked.")
    rc, out, err = _ssh_run(p, a, remote, timeout=a.ssh_timeout)
    sys.stdout.write(out.decode("utf-8", "replace"))
    if err:
        log(err, "WARN")
    log("  exit code %s" % rc)
    return rc == 0


# --------------------------------------------------------------------------- interactive homing diagnosis

def _ask(prompt):
    try:
        return input("  >>> " + prompt + " ").strip()
    except EOFError:
        return ""


def cmd_diagnose(p, a):
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    ax = a.axis.upper()
    cf = p.configfile().get("settings", {})
    rail = cf.get("stepper_" + ax.lower(), {})
    lo, hi = float(rail.get("position_min", 0)), float(rail.get("position_max", 0))
    target = a.target_pos if a.target_pos is not None else (260.0 if ax == "Y" else 250.0)
    if not (lo < target < hi):
        raise ToolError("target %s outside %s travel %.0f..%.0f" % (target, ax, lo, hi))
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "diag_%s_%s%.0f" % (ts, ax, target))
    os.makedirs(d, exist_ok=True)
    report = []

    def note(step, answer):
        t = dt.datetime.now().strftime("%H:%M:%S")
        report.append({"time": t, "step": step, "answer": answer})
        log("  [%s] %s -> %s" % (t, step, answer or "-"))

    def run(step, script, timeout=60, ask=True):
        t0 = time.time()
        try:
            res = p.gcode(script, timeout=timeout)
            out = "ok"
        except ToolError as e:
            res, out = None, "ERROR: %s" % e
        dur = time.time() - t0
        log("  %s  (%s, %.1fs)" % (script.replace("\n", " | "), out[:200], dur))
        ans = _ask("Did the bed/toolhead move? (n, or describe: which way, how far, hit the end?)") if ask else ""
        note(step, "%s | gcode %s in %.1fs" % (ans, out, dur))
        return out == "ok"

    log("  This test stands the printer near the end of %s travel and steps through homing." % ax)
    log("  Watch the %s. After each step you will be asked what it did." % ("bed" if ax == "Y" else "toolhead"))
    log("  It may crash into the end on the last step - that is the point. Ctrl+C to stop any time.")
    if not st["homed"] or ax.lower() not in st["homed"] or "x" not in st["homed"]:
        _ask("Printer is not homed. Motors will be turned off. Push the bed AND toolhead to the MIDDLE by hand, then press Enter.")
        p.gcode("M84", timeout=15)
        _ask("Motors are off now. Push the bed and toolhead to the middle, then press Enter.")
        if not run("baseline G28 X Y from the middle", "G28 X Y", timeout=a.home_timeout, ask=False):
            log("  baseline homing failed even from the middle - stopping.", "ERROR")
            _finish(p, d, report)
            return False
    if not run("move %s to %.1f" % (ax, target),
               "G90\nG1 %s%.2f F%d\nM400" % (ax, target, a.speed), timeout=60):
        _finish(p, d, report)
        return False
    if a.by_hand:
        run("M84 (motors off)", "M84", timeout=15)
        _ask("Now push the %s to the far end by hand (where it sits after you pull it forward), then press Enter."
             % ("bed" if ax == "Y" else "toolhead"))
        note("moved by hand", "user moved it")
    else:
        run("M84 (motors off)", "M84", timeout=15)
    if a.restart_first:
        log("  RESTART (host only) - Klipper restarts and re-initialises the servos")
        okr, msgr = p.restart()
        if not okr:
            note("RESTART", "failed: %s" % msgr)
            _finish(p, d, report)
            return False
        time.sleep(a.motor_wait)
        note("RESTART", _ask("Klipper is back. Did the bed/toolhead move during the restart? (n, or describe)"))
    run("MOTOR_STALL_MODE DATA=1 (servos to homing mode, same as homing_override)", "MOTOR_STALL_MODE DATA=1", timeout=30)
    run("enable shared motor line (what the Z lift does just before homing)",
        "SET_STEPPER_ENABLE STEPPER=stepper_z ENABLE=1", timeout=15)
    _ask("Last step: G28 %s. Watch closely at the very START of the move. Press Enter to go." % ax)
    ok = run("G28 %s" % ax, "G28 %s" % ax, timeout=a.home_timeout)
    if not ok:
        log("  homing failed - restoring servo mode like Creality's own error path")
        for scr in ("MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11", "MOTOR_STALL_MODE DATA=2"):
            try:
                p.gcode(scr, timeout=30)
            except ToolError as e:
                log("  %s: %s" % (scr, e), "WARN")
    _finish(p, d, report)
    return True


def _finish(p, d, report):
    with open(os.path.join(d, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    data = p.get_log("klippy.log")
    if data:
        lines = data.decode("utf-8", "replace").splitlines()
        tail = lines[-6000:]
        with open(os.path.join(d, "klippy_tail.log"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(tail))
    try:
        store = p.req("GET", "/server/gcode_store", params={"count": 200}).get("gcode_store", [])
        with open(os.path.join(d, "console.json"), "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=1)
    except ToolError:
        pass
    log("  report saved: %s" % d)


# --------------------------------------------------------------------------- restart repro

_RE_START = "Start printer at"
_RE_STALL = re.compile(r"data_send:b'\\x8([12])\\x04\\x00\\x11\\x01' recv_result:b'\\xf7\\x8[12]\\x04\\x([0-9a-f]{2})")
_RE_PROT = re.compile(r"data_send:b'\\x8([12])\\x04\\x00\\x0c\\x0b' recv_result:b'\\xf7\\x8[12]\\x0b\\x([0-9a-f]{2})\\x0c((?:\\x[0-9a-f]{2}|[^\\'])*)")
_RE_KEY = re.compile(r'"code"\s*:\s*"(key\d+)"[^}]*"msg"\s*:\s*"([^"]*)"')


def _log_since_last_start(p, min_starts=1):
    data = p.get_log("klippy.log")
    if not data:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    idx = [i for i, l in enumerate(lines) if _RE_START in l]
    return lines[idx[-1]:] if idx else lines[-5000:]


def _servo_facts(lines):
    """Pull servo status bytes, protection reads and key codes out of klippy.log lines."""
    facts = {"stall_status": [], "prot": [], "keys": [], "homing_moves": 0}
    seen_keys = set()
    for l in lines:
        m = _RE_STALL.search(l)
        if m:
            facts["stall_status"].append(("X" if m.group(1) == "1" else "Y", m.group(2)))
        m = _RE_PROT.search(l)
        if m:
            facts["prot"].append(("X" if m.group(1) == "1" else "Y", m.group(2)))
        m = _RE_KEY.search(l)
        if m and "_respond_error" in l or (m and "!!" in l):
            k = (l[:23], m.group(1))
            if k not in seen_keys:
                seen_keys.add(k)
                facts["keys"].append("%s %s" % (m.group(1), m.group(2)))
        if "_handle_homing_move_begin" in l:
            facts["homing_moves"] += 1
    return facts


def cmd_repro(p, a):
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "repro_%s" % ts)
    os.makedirs(d, exist_ok=True)
    results = []
    log("  Repro of 12:19: home, park X%.0f Y%.0f, RESTART with motors ON, then G28 X Y. %d round(s)."
        % (a.x, a.y, a.rounds))
    log("  Watch the bed at the very start of each G28. Ctrl+C to stop.")

    def recover():
        for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
            try:
                p.gcode(scr, timeout=30)
            except ToolError as e:
                log("  %s: %s" % (scr, e), "WARN")

    for r in range(1, a.rounds + 1):
        log("  --- round %d/%d ---" % (r, a.rounds))
        st = p.state()
        if "x" not in st["homed"] or "y" not in st["homed"]:
            try:
                p.gcode("G28 X Y", timeout=a.home_timeout)
            except ToolError as e:
                log("  setup homing failed (%s) - clearing servo faults and retrying once" % str(e)[:120], "WARN")
                recover()
                p.gcode("G28 X Y", timeout=a.home_timeout)
        p.gcode("G90\nG1 X%.2f Y%.2f F%d\nM400" % (a.x, a.y, a.speed), timeout=60)
        if a.m84:
            p.gcode("M84", timeout=15)
        log("  parked. RESTART (host) ...")
        ok, msg = p.restart()
        if not ok:
            log("  Klipper did not come back: %s" % msg, "ERROR")
            results.append({"round": r, "result": "restart failed", "msg": msg})
            break
        time.sleep(a.motor_wait)
        during = _ask("Did the bed/toolhead move during the restart? (n / describe)") if a.ask else ""
        t0 = time.time()
        try:
            p.gcode("G28 X Y", timeout=a.home_timeout)
            res, err = "OK", ""
        except ToolError as e:
            res, err = "FAIL", str(e)
        dur = time.time() - t0
        seen = _ask("What did the bed do at the start of G28? (n / describe)") if a.ask else ""
        facts = _servo_facts(_log_since_last_start(p))
        y_status = [s for ax, s in facts["stall_status"] if ax == "Y"]
        y_prot = [s for ax, s in facts["prot"] if ax == "Y"]
        rec = {"round": r, "result": res, "error": err[:300], "seconds": round(dur, 1),
               "y_status_before_homing": y_status[0] if y_status else None,
               "y_status_all": y_status, "y_fault_reads": y_prot, "keys": facts["keys"],
               "moved_during_restart": during, "seen_at_g28": seen}
        results.append(rec)
        log("  round %d: G28 X Y %s in %.1fs | Y servo status before homing: %s | faults read: %s | codes: %s"
            % (r, res, dur, rec["y_status_before_homing"], y_prot or "-", ", ".join(facts["keys"]) or "-"))
        if res == "FAIL":
            log("  REPRODUCED on round %d. Clearing the servo fault and re-homing to recover." % r)
            recover()
            try:
                p.gcode("G28 X Y", timeout=a.home_timeout)
                log("  recovered: X/Y homed again")
            except ToolError as e:
                log("  recovery homing failed: %s" % str(e)[:200], "ERROR")
            if not a.keep_going:
                break
    with open(os.path.join(d, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    lines = _log_since_last_start(p)
    with open(os.path.join(d, "klippy_since_last_restart.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    fails = sum(1 for x in results if x["result"] == "FAIL")
    log("  === %d of %d rounds failed. Saved: %s" % (fails, len(results), d))
    return True


_RE_STALL_ANY = re.compile(r"data_send:b'\\x82\\x04\\x00\\x11\\x0([12])' recv_result:b'\\xf7\\x82\\x04\\x([0-9a-f]{2})")


def _log_lines(p):
    data = p.get_log("klippy.log")
    return data.decode("utf-8", "replace").splitlines() if data else []


def _fix_loaded(p):
    g = p.configfile().get("config", {}).get("homing_override", {}).get("gcode", "")
    i_chk, i_mode = g.find("MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"), g.find("MOTOR_STALL_MODE DATA=1")
    return i_chk != -1 and i_chk < i_mode


def cmd_repro_fault(p, a):
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    fixed = _fix_loaded(p)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "repro_fault_%s" % ts)
    os.makedirs(d, exist_ok=True)
    out = {"fix_loaded": fixed, "steps": []}

    def step(name, **kv):
        kv["step"] = name
        out["steps"].append(kv)

    log("  servo-clear fix loaded on this printer: %s | push in %s mode" % (
        "YES" if fixed else "NO", "HOMING (stall-detect)" if a.homing_mode else "normal"))
    log("  expected: %s" % ("G28 Y clears key789 and homes normally" if fixed
                            else "G28 Y fails with key22 and the bed does NOT move"))
    if "x" not in st["homed"] or "y" not in st["homed"]:
        p.gcode("G28 X Y", timeout=a.home_timeout)
    p.gcode("G90\nG1 X%.2f Y%.2f F6000\nM400" % (a.x, a.y), timeout=60)
    ans = _ask("Bed is at Y%.0f. Next it pushes the bed FORWARD %.0f mm at %.0f mm/s so it runs into the front end "
               "and the servo faults. Type GO to continue:" % (a.y, a.push, a.push_speed))
    if ans.strip().upper() != "GO":
        log("  cancelled.")
        return False

    n0 = len(_log_lines(p))
    if a.homing_mode:
        # Same mode the servos are in during homing: the fault line is the endstop, so Creality's
        # auto fault-clear (which works in normal mode) cannot fire. This is how 12:19 latched.
        p.gcode("MOTOR_STALL_MODE DATA=1", timeout=30)
    # Klipper now believes the bed is a.push mm further back than it is, so the move runs past the real end.
    p.gcode("SET_KINEMATIC_POSITION Y=%.2f" % (a.y - a.push), timeout=15)
    try:
        p.gcode("G91\nG1 Y%.2f F%d\nG90\nM400" % (a.push, a.push_speed * 60), timeout=60)
        push = "move finished"
    except ToolError as e:
        push = "move error: %s" % e
    time.sleep(1.0)
    seen = _ask("What did the bed do? (e.g. hit the end and buzzed / stopped / nothing)")
    # Read Y's state WITHOUT clearing it: a stall-mode command returns the status byte.
    # Stay in homing mode (DATA=1) so switching back to normal mode can't trigger the auto-clear.
    p.gcode("MOTOR_STALL_MODE DATA=%d" % (1 if a.homing_mode else 2), timeout=30)
    lines = _log_lines(p)[n0:]
    st_bytes = [b for _, b in _RE_STALL_ANY.findall("\n".join(lines))]
    y_after_push = st_bytes[-1] if st_bytes else None
    step("push into end", push=push, seen=seen, y_status=y_after_push)
    log("  after the push: Y servo status %s (%s)" % (y_after_push, "FAULTED" if y_after_push not in (None, "00")
                                                       else "healthy" if y_after_push == "00" else "unknown"))

    p.gcode("M84", timeout=15)
    _ask("Motors off. Next: G28 Y. Watch whether the bed moves at all. Press Enter.")
    n1 = len(_log_lines(p))
    t0 = time.time()
    try:
        p.gcode("G28 Y", timeout=a.home_timeout)
        res, err = "OK", ""
    except ToolError as e:
        res, err = "FAIL", str(e)
    dur = time.time() - t0
    seen2 = _ask("Did the bed move during G28 Y? (n / describe)")
    lines = _log_lines(p)[n1:]
    facts = _servo_facts(lines)
    y_stat = [s for ax, s in facts["stall_status"] if ax == "Y"]
    step("G28 Y", result=res, error=err[:300], seconds=round(dur, 1), seen=seen2,
         y_status_at_homing_start=y_stat[:1], codes=facts["keys"])
    log("  G28 Y: %s in %.1fs | Y status at homing start: %s | codes: %s"
        % (res, dur, y_stat[0] if y_stat else "?", ", ".join(facts["keys"]) or "-"))

    if fixed:
        verdict = ("FIX PROVEN: servo was faulted (%s), homing cleared it and homed" % y_after_push
                   if res == "OK" and y_after_push not in (None, "00") else
                   "fault did not trip - push again with --push 60" if y_after_push == "00" else
                   "FIX DID NOT HELP - send me the folder below")
    else:
        verdict = ("FAULT REPRODUCED: servo faulted (%s) and G28 Y failed - this is the 12:19 lockout" % y_after_push
                   if res == "FAIL" and y_after_push not in (None, "00") else
                   "fault did not trip - push again with --push 60" if y_after_push == "00" else
                   "unexpected - send me the folder below")
    out["verdict"] = verdict
    log("  === %s" % verdict)

    if res == "FAIL":
        log("  recovering: clear servo fault, re-home")
        for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
            try:
                p.gcode(scr, timeout=30)
            except ToolError as e:
                log("  %s: %s" % (scr, e), "WARN")
        try:
            p.gcode("G28 X Y", timeout=a.home_timeout)
            log("  recovered: X/Y homed")
        except ToolError as e:
            log("  recovery failed: %s" % str(e)[:200], "ERROR")
    with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    with open(os.path.join(d, "klippy_during_test.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(_log_lines(p)[n0:]))
    log("  saved: %s" % d)
    return True


def cmd_restart(p, a):
    p.connect()
    p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    ok, msg = p.restart()
    if ok:
        time.sleep(a.motor_wait)
        log("  ready (waited %.0fs extra for servo init)" % a.motor_wait)
    else:
        log("  not ready: %s" % msg, "ERROR")
    return ok


# --------------------------------------------------------------------------- direction-pin check

def _gcode_capture(p, script, timeout=60):
    """Run gcode, return (ok, error, console messages produced by it)."""
    try:
        before = p.req("GET", "/server/gcode_store", params={"count": 1}).get("gcode_store", [])
        t_last = before[-1]["time"] if before else 0
    except ToolError:
        t_last = 0
    ok, err = True, ""
    try:
        p.gcode(script, timeout=timeout)
    except ToolError as e:
        ok, err = False, str(e)
    time.sleep(0.7)
    msgs = []
    try:
        for g in p.req("GET", "/server/gcode_store", params={"count": 300}).get("gcode_store", []):
            if g.get("time", 0) > t_last and g.get("type") != "command":
                msgs.append(g.get("message", "").rstrip())
    except ToolError:
        pass
    return ok, err, msgs


def _pin_levels(lines, pins):
    """Best-effort: find 'PBx ... 0/1' in the pin-read output."""
    out = {}
    for pin in pins:
        for l in lines:
            m = re.search(r"pin:!?%s\b.*?'status':\s*([01])" % re.escape(pin), l) or \
                re.search(r"\b%s\b\D{0,40}?\b([01])\b" % re.escape(pin), l)
            if m:
                out[pin] = m.group(1)
    return out


def cmd_check_dir(p, a):
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    pins = ["PB7", "PB9", "PB8", "PB10"]   # Y dir, X dir, Y step, X step
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "dirpin_%s" % ts)
    os.makedirs(d, exist_ok=True)
    rep = {}

    def read_pins(label):
        n0 = len(_log_lines(p))
        ok, err, msgs = _gcode_capture(p, "MOTOR_READ_ALL_PIN_IO", timeout=60)
        logl = [l for l in _log_lines(p)[n0:] if re.search(r"pin|gpio", l, re.I)]
        levels = _pin_levels(msgs + logl, pins)
        rep[label] = {"ok": ok, "error": err, "console": msgs, "log": logl, "levels": levels}
        log("  [%s] pin read %s" % (label, "ok" if ok else "FAILED: " + err[:150]))
        for m in msgs:
            log("    | " + m[:200])
        log("    levels: %s" % (", ".join("%s=%s" % kv for kv in sorted(levels.items())) or "could not parse - see saved file"))
        return levels

    log("  1) clear any servo fault and home X/Y (resets the direction pins)")
    for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
        try:
            p.gcode(scr, timeout=30)
        except ToolError as e:
            log("  %s: %s" % (scr, e), "WARN")
    ok, err, _ = _gcode_capture(p, "G28 X Y", timeout=a.home_timeout)
    if not ok:
        log("  homing failed (%s). Run it once more - the failed move resets the pin." % err[:150], "ERROR")
        rep["home"] = err
        _save_json(d, rep)
        return False
    before = read_pins("after homing")

    log("  2) host RESTART")
    okr, msgr = p.restart()
    if not okr:
        log("  Klipper did not come back: %s" % msgr, "ERROR")
        _save_json(d, rep)
        return False
    time.sleep(a.motor_wait)
    after = read_pins("after restart")

    y0, y1 = before.get("PB7"), after.get("PB7")
    x0, x1 = before.get("PB9"), after.get("PB9")
    if y0 is not None and y1 is not None:
        if y0 != y1:
            verdict = "PROVEN: Y dir pin PB7 changed %s -> %s across the restart (X PB9 %s -> %s). " \
                      "The first Y move after a restart runs backwards." % (y0, y1, x0, x1)
        else:
            verdict = "NOT the dir pin: PB7 is %s before and after the restart (X PB9 %s -> %s)." % (y0, y1, x0, x1)
    else:
        verdict = "could not read PB7 from the output - send me the saved folder"
    rep["verdict"] = verdict
    log("  === " + verdict)

    if a.home_after:
        _ask("--home-after: next is G28 X Y straight after the restart. If PB7 flipped, the bed will run FORWARD. "
             "Press Enter to go (Ctrl+C to skip).")
        ok, err, msgs = _gcode_capture(p, "G28 X Y", timeout=a.home_timeout)
        seen = _ask("Which way did the bed go? (back = normal / forward = wrong)")
        rep["home_after"] = {"ok": ok, "error": err, "seen": seen}
        log("  G28 X Y after restart: %s" % ("OK" if ok else "FAIL " + err[:150]))
        if not ok:
            for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
                try:
                    p.gcode(scr, timeout=30)
                except ToolError:
                    pass
            log("  servo fault cleared; home again to recover (the failed move reset the pin)")
    _save_json(d, rep)
    return True


def _save_json(d, obj):
    with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    log("  saved: %s" % d)


def cmd_prove_dir(p, a):
    """Two trials: last Y move BACKWARD before RESTART (should home fine) vs FORWARD (should crash)."""
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("klippy not ready: %s" % st["message"])
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "provedir_%s" % ts)
    os.makedirs(d, exist_ok=True)
    rep = {"trials": []}

    def clear_and_home():
        for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
            try:
                p.gcode(scr, timeout=30)
            except ToolError:
                pass
        for attempt in (1, 2):   # a failed homing resets the pin, so a 2nd try always works
            ok, err, _ = _gcode_capture(p, "G28 X Y", timeout=a.home_timeout)
            if ok:
                return True
            log("  setup homing attempt %d failed: %s" % (attempt, err[:120]), "WARN")
            for scr in ("MOTOR_STALL_MODE DATA=2", "MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11"):
                try:
                    p.gcode(scr, timeout=30)
                except ToolError:
                    pass
        return False

    trials = [("BACKWARD", a.y + a.step, a.y, "OK - homes normally"),
              ("FORWARD", a.y - a.step, a.y,
               "OK - homes normally (fix installed)" if a.expect_fixed else "FAIL - bed runs forward and crashes")]
    if a.only:
        trials = [t for t in trials if t[0].lower() == a.only.lower()]
    for name, y_from, y_to, expect in trials:
        log("  ===== trial: last Y move %s before RESTART (expect: %s)" % (name, expect))
        if not clear_and_home():
            log("  could not home for setup - stopping", "ERROR")
            break
        p.gcode("G90\nG1 X130 Y%.1f F6000\nG1 Y%.1f F3000\nM400" % (y_from, y_to), timeout=60)
        pins_b = _pin_levels(_gcode_capture(p, "MOTOR_READ_ALL_PIN_IO", 60)[2], ["PB7"])
        okr, msgr = p.restart()
        if not okr:
            log("  Klipper did not come back: %s" % msgr, "ERROR")
            break
        time.sleep(a.motor_wait)
        pins_a = _pin_levels(_gcode_capture(p, "MOTOR_READ_ALL_PIN_IO", 60)[2], ["PB7"])
        _ask("PB7 before restart=%s, after=%s. Next: G28 X Y - watch which way the bed goes. Enter to go."
             % (pins_b.get("PB7"), pins_a.get("PB7")))
        ok, err, _ = _gcode_capture(p, "G28 X Y", timeout=a.home_timeout)
        seen = _ask("Which way did the bed go? (back / forward+crash)")
        res = "OK" if ok else "FAIL"
        match = (res == "OK") if a.expect_fixed else ((res == "OK") == (name == "BACKWARD"))
        rep["trials"].append({"last_y_move": name, "pb7_before": pins_b.get("PB7"), "pb7_after": pins_a.get("PB7"),
                              "home_result": res, "error": err[:200], "seen": seen, "as_predicted": match})
        log("  trial %s: PB7 %s -> %s | G28 X Y %s | %s"
            % (name, pins_b.get("PB7"), pins_a.get("PB7"), res, "AS PREDICTED" if match else "NOT as predicted"))
        if not ok:
            clear_and_home()
    allm = rep["trials"] and all(t["as_predicted"] for t in rep["trials"])
    if a.expect_fixed:
        rep["verdict"] = ("FIX PROVEN: homing after RESTART works whichever way Y last moved"
                          if allm and len(rep["trials"]) == 2 else "fix NOT proven - send me the saved folder")
    else:
        rep["verdict"] = ("PROVEN: the first Y homing after a RESTART runs backwards exactly when the last Y move "
                          "before the restart was forward" if allm and len(rep["trials"]) == 2 else
                          "not conclusive - send me the saved folder")
    log("  === " + rep["verdict"])
    _save_json(d, rep)
    return True


# --------------------------------------------------------------------------- DIR-pin fix (patches homing.py over SSH)

HOMING_PY = "/usr/share/klipper/klippy/extras/homing.py"
DIRSYNC_TAG = "# HI-FIX dirsync"
DIRSYNC_ANCHOR = "        hi = rails[0].get_homing_info()\n"
DIRSYNC_BLOCK = (
    "        " + DIRSYNC_TAG + ": after a host RESTART, Creality's servo setup rewrites the X/Y DIR pins\n"
    "        # while the MCU still remembers the last direction, so the first homing move can run the\n"
    "        # wrong way and crash (key22). A zero-length homing move makes the MCU stop these steppers,\n"
    "        # which resets the DIR pin and the MCU's direction state together. Nothing moves.\n"
    "        if any(r.get_name() in ('stepper_x', 'stepper_y') for r in rails):\n"
    "            try:\n"
    "                HomingMove(self.printer, endstops).homing_move(\n"
    "                    list(startpos), hi.speed, check_triggered=False)\n"
    "                self.toolhead.set_position(startpos, homing_axes=homing_axes)\n"
    "                logging.info('HI dirsync done for %s' % [r.get_name() for r in rails])\n"
    "            except Exception as e:\n"
    "                logging.info('HI dirsync skipped: %s' % (e,))\n"
)


RETRY22_TAG = "# HI-FIX retry22"
RETRY22_ANCHOR_RE = re.compile(r"(        else:\n            hmove\.homing_move\(homepos, hi\.speed\))[ \t]*\n")
RETRY22_BLOCK = (
    "        else:\n"
    "            " + RETRY22_TAG + ": an X/Y homing move that runs its full length without the servo stall\n"
    "            # line firing (key22) is retried once after clearing the servos and re-syncing DIR, instead\n"
    "            # of killing the print. A second key22 is raised as before (a real fault stays a fault).\n"
    "            try:\n"
    "                hmove.homing_move(homepos, hi.speed)\n"
    "            except self.printer.command_error as e:\n"
    "                if '\"key22\"' not in str(e) or not any(\n"
    "                        r.get_name() in ('stepper_x', 'stepper_y') for r in rails):\n"
    "                    raise\n"
    "                names = [r.get_name() for r in rails]\n"
    "                logging.info('HI retry22: %s on %s - clearing servos, homing once more' % (e, names))\n"
    "                gcode = self.printer.lookup_object('gcode')\n"
    "                for scr in ('MOTOR_STALL_MODE DATA=2', 'MOTOR_CHECK_PROTECTION_AFTER_HOME DATA=11',\n"
    "                            'MOTOR_STALL_MODE DATA=1'):\n"
    "                    try:\n"
    "                        gcode.run_script_from_command(scr)\n"
    "                    except Exception as e2:\n"
    "                        logging.info('HI retry22: %s failed: %s' % (scr, e2))\n"
    "                self.toolhead.dwell(0.5)\n"
    "                self.toolhead.set_position(startpos, homing_axes=homing_axes)\n"
    "                try:\n"
    "                    HomingMove(self.printer, endstops).homing_move(\n"
    "                        list(startpos), hi.speed, check_triggered=False)\n"
    "                    self.toolhead.set_position(startpos, homing_axes=homing_axes)\n"
    "                except Exception as e3:\n"
    "                    logging.info('HI retry22: dirsync skipped: %s' % (e3,))\n"
    "                hmove = HomingMove(self.printer, endstops)\n"
    "                hmove.homing_move(homepos, hi.speed)\n"
    "                logging.info('HI retry22: second try homed %s OK' % (names,))\n"
)


def patch_homing_py(text):
    """Apply every missing HI fix to Creality's homing.py. Returns None if all are already there."""
    orig = text
    if DIRSYNC_TAG not in text:
        if text.count(DIRSYNC_ANCHOR) != 1:
            raise ToolError("homing.py does not look like the version this fix was written for - not patching")
        i = text.index(DIRSYNC_ANCHOR) + len(DIRSYNC_ANCHOR)
        head = text[:i]
        if "endstops = [es for rail in rails" not in head[-400:] or "startpos = self._fill_coord(forcepos)" not in head[-700:]:
            raise ToolError("homing.py home_rails() differs from the expected layout - not patching")
        text = text[:i] + DIRSYNC_BLOCK + text[i:]
    if RETRY22_TAG not in text:
        if len(RETRY22_ANCHOR_RE.findall(text)) != 1:
            raise ToolError("homing.py first-home call differs from the expected layout - retry22 not patched")
        if text.index(DIRSYNC_TAG) > RETRY22_ANCHOR_RE.search(text).start():
            raise ToolError("homing.py: retry22 anchor is before the dirsync block - not patching")
        text = RETRY22_ANCHOR_RE.sub(lambda m: RETRY22_BLOCK, text, count=1)
    return None if text == orig else text


# --------------------------------------------------------------------------- SD-print guard (patches virtual_sdcard.py)

SDCARD_PY = "/usr/share/klipper/klippy/extras/virtual_sdcard.py"
SDGUARD_TAG = "# HI-FIX sdguard"
SDGUARD_ANCHOR_RE = re.compile(r'( +)self\.gcode\.run_script\(f"\{last_T\}"\)\n')


def patch_sdcard_py(text):
    """Creality's work_handler runs the CFS 'reload last T' gcode with no error handling before the print loop.
    If it fails (e.g. key22 while homing) the exception escapes the SD timer, work_timer is never cleared and
    every later cancel / reset / RESTART waits forever. Wrap it so the print ends in an error instead."""
    if SDGUARD_TAG in text:
        return None
    m = list(SDGUARD_ANCHOR_RE.finditer(text))
    if len(m) != 1:
        raise ToolError("virtual_sdcard.py: CFS 'last T' call not found exactly once - not patching")
    m = m[0]
    head = text[:m.start()]
    if "CFS print resume" not in head[-300:] or "error_message = None" not in head[-4000:]:
        raise ToolError("virtual_sdcard.py work_handler differs from the expected layout - not patching")
    ind = m.group(1)
    block = (
        ind + SDGUARD_TAG + ": if the CFS reload fails (key22 homing, box error) end the print with that\n" +
        ind + "# error instead of letting it escape the SD timer, which wedges every later cancel/RESTART.\n" +
        ind + "try:\n" +
        ind + '    self.gcode.run_script(f"{last_T}")\n' +
        ind + "except Exception as hi_e:\n" +
        ind + "    logging.exception('HI sdguard: %s before the print loop failed - ending the print' % last_T)\n" +
        ind + "    error_message = str(hi_e)\n" +
        ind + "    self.must_pause_work = True\n")
    return text[:m.start()] + block + text[m.end():]


def _ssh_patch_py(p, a, remote_file, patcher, tag, label):
    """Read remote_file over SSH, patch it, show the diff, and (with --apply) install it with a backup
    (<file>.hi-orig), compile check, md5 verify and a Klipper service restart; rolls back on failure."""
    p.connect()
    p.assert_idle(a.force)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "%s_%s" % (label, ts))
    os.makedirs(d, exist_ok=True)
    base = os.path.basename(remote_file)
    py = "PY=/usr/share/klippy-env/bin/python3; [ -x $PY ] || PY=python3; "
    if a.revert:
        log("  reverting %s from %s.hi-orig " % (remote_file, remote_file))
        rc, out, err = _ssh_run(p, a, "set -e; F=%s; [ -f $F.hi-orig ] || { echo NO_BACKUP; exit 3; }; "
                                      "cp $F.hi-orig $F; echo REVERTED" % remote_file, timeout=60)
        log("  %s %s" % (out.decode().strip(), err[-200:]))
        if rc != 0:
            return False
        ok, msg = _service_restart(p, a, confirm=not a.yes)
        log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg))
        return ok
    log("  reading %s over SSH " % remote_file)
    rc, cur, err = _ssh_run(p, a, "cat %s" % remote_file, timeout=60)
    if rc != 0 or not cur:
        raise ToolError("could not read %s: %s" % (base, err[-300:]))
    with open(os.path.join(d, base + ".orig"), "wb") as fh:
        fh.write(cur)
    text = cur.decode("utf-8")
    new = patcher(text)
    if new is None:
        log("  %s on disk already has the fix (%s)." % (base, tag))
        if a.apply:
            log("  restarting the Klipper service so the running program actually loads it")
            ok, msg = _service_restart(p, a, confirm=not a.yes)
            log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg))
            return ok
        return True
    for ln in difflib.unified_diff(text.splitlines(), new.splitlines(), "a/" + base, "b/" + base, lineterm="", n=2):
        log("    " + ln)
    with open(os.path.join(d, base + ".patched"), "wb") as fh:
        fh.write(new.encode("utf-8"))
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply.")
        return True
    md5_old = hashlib.md5(cur).hexdigest()
    md5_new = hashlib.md5(new.encode("utf-8")).hexdigest()
    remote = (py + "F=%s; T=/tmp/hi_%s; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo CHANGED_ON_PRINTER; exit 3; }; "
              "[ -f $F.hi-orig ] || cp $F $F.hi-orig || exit 4; "
              "cat > $T || exit 5; "
              "$PY -m py_compile $T || { echo COMPILE_FAILED; exit 6; }; "
              "cp $T $F || exit 7; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo VERIFY_FAILED; cp $F.hi-orig $F; exit 8; }; "
              "rm -f $T; echo INSTALLED" % (remote_file, base, md5_old, md5_new))
    log("  installing patched %s " % base)
    rc, out, err = _ssh_run(p, a, remote, timeout=120, data=new.encode("utf-8"))
    res = out.decode("utf-8", "replace").strip()
    log("  printer says: %s %s" % (res, err[-200:] if rc else ""))
    if rc != 0 or "INSTALLED" not in res:
        log("  install failed - printer left unchanged (original kept)", "ERROR")
        return False
    ok, msg = _service_restart(p, a, confirm=not a.yes)
    if not ok and msg == "cancelled":
        log("  file installed but NOT loaded yet. Load it later with Restart Klipper service", "WARN")
        return False
    if not ok:
        log("  Klipper did not come back (%s) - restoring the original %s" % (msg, base), "ERROR")
        rc, out, err = _ssh_run(p, a, "cp %s.hi-orig %s && echo RESTORED" % (remote_file, remote_file), timeout=60)
        log("  %s" % out.decode().strip())
        ok2, msg2 = _service_restart(p, a, confirm=False)
        log("  after restore: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    log("  fix installed and Klipper is ready. Original saved on the printer as %s.hi-orig and here: %s" % (base, d))
    return True


def cmd_fix_sdcard(p, a):
    return _ssh_patch_py(p, a, SDCARD_PY, patch_sdcard_py, SDGUARD_TAG, "fixsd")


def cmd_fix_dir(p, a):
    p.connect()
    p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "fixdir_%s" % ts)
    os.makedirs(d, exist_ok=True)
    py = "PY=/usr/share/klippy-env/bin/python3; [ -x $PY ] || PY=python3; "

    if a.revert:
        log("  reverting %s from %s.hi-orig " % (HOMING_PY, HOMING_PY))
        rc, out, err = _ssh_run(p, a, "set -e; F=%s; [ -f $F.hi-orig ] || { echo NO_BACKUP; exit 3; }; "
                                      "cp $F.hi-orig $F; echo REVERTED" % HOMING_PY, timeout=60)
        log("  %s %s" % (out.decode().strip(), err[-200:]))
        if rc != 0:
            return False
        ok, msg = _service_restart(p, a, confirm=not a.yes)
        log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg))
        return ok

    log("  reading %s over SSH " % HOMING_PY)
    rc, cur, err = _ssh_run(p, a, "cat %s" % HOMING_PY, timeout=60)
    if rc != 0 or not cur:
        raise ToolError("could not read homing.py: %s" % err[-300:])
    with open(os.path.join(d, "homing.py.orig"), "wb") as fh:
        fh.write(cur)
    text = cur.decode("utf-8")
    new = patch_homing_py(text)
    if new is None:
        log("  homing.py on disk already has every fix (%s, %s)." % (DIRSYNC_TAG, RETRY22_TAG))
        if a.apply:
            log("  restarting the Klipper service so the running program actually loads it")
            ok, msg = _service_restart(p, a, confirm=not a.yes)
            log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg))
            return ok
        return True
    for ln in difflib.unified_diff(text.splitlines(), new.splitlines(), "a/homing.py", "b/homing.py", lineterm="", n=2):
        log("    " + ln)
    with open(os.path.join(d, "homing.py.patched"), "wb") as fh:
        fh.write(new.encode("utf-8"))
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply.")
        return True

    md5_old = hashlib.md5(cur).hexdigest()
    md5_new = hashlib.md5(new.encode("utf-8")).hexdigest()
    remote = (py + "F=%s; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo CHANGED_ON_PRINTER; exit 3; }; "
              "[ -f $F.hi-orig ] || cp $F $F.hi-orig || exit 4; "
              "cat > /tmp/hi_homing.py || exit 5; "
              "$PY -m py_compile /tmp/hi_homing.py || { echo COMPILE_FAILED; exit 6; }; "
              "cp /tmp/hi_homing.py $F || exit 7; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo VERIFY_FAILED; cp $F.hi-orig $F; exit 8; }; "
              "rm -f /tmp/hi_homing.py; echo INSTALLED" % (HOMING_PY, md5_old, md5_new))
    log("  installing patched homing.py ")
    rc, out, err = _ssh_run(p, a, remote, timeout=120, data=new.encode("utf-8"))
    res = out.decode("utf-8", "replace").strip()
    log("  printer says: %s %s" % (res, err[-200:] if rc else ""))
    if rc != 0 or "INSTALLED" not in res:
        log("  install failed - printer left unchanged (original kept)", "ERROR")
        return False
    # A host RESTART keeps the old Python code loaded - the service must restart to load the new homing.py.
    ok, msg = _service_restart(p, a, confirm=not a.yes)
    if not ok and msg == "cancelled":
        log("  file installed but NOT loaded yet. Load it later with: restart-service", "WARN")
        return False
    if not ok:
        log("  Klipper did not come back (%s) - restoring the original homing.py" % msg, "ERROR")
        rc, out, err = _ssh_run(p, a, "cp %s.hi-orig %s && echo RESTORED" % (HOMING_PY, HOMING_PY), timeout=60)
        log("  %s" % out.decode().strip())
        ok2, msg2 = _service_restart(p, a, confirm=False)
        log("  after restore: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    log("  fix installed and Klipper is ready. Original saved on the printer as homing.py.hi-orig and here: %s" % d)
    log("  prove it:  python hi_tool.py prove-dir %s --expect-fixed" % p.host.split(".")[-1])
    return True


KLIPPER_INIT = "/etc/init.d/klipper"


def _service_restart(p, a, confirm=True):
    """Restart the klippy *process* (needed to load changed Python code). Never FIRMWARE_RESTART."""
    log("  reading %s " % KLIPPER_INIT)
    rc, out, err = _ssh_run(p, a, "cat %s; echo '--- running klippy:'; ps w | grep klippy.py | grep -v grep"
                            % KLIPPER_INIT, timeout=60)
    txt = out.decode("utf-8", "replace")
    for ln in txt.splitlines():
        log("    | " + ln)
    risky = [w for w in ("reset", "flash", "mcu_update", "FIRMWARE", "gpio", "dfu") if w.lower() in txt.lower()]
    if risky:
        log("  the init script mentions: %s - read it above before continuing" % ", ".join(risky), "WARN")
    if confirm and _ask("Restart the Klipper service now (host program only, motion board is not reset)? Type YES:") \
            .strip().upper() != "YES":
        log("  not restarted.")
        return False, "cancelled"
    log("  restarting Klipper service ")
    rc, out, err = _ssh_run(p, a, "%s restart >/tmp/hi_klipper_restart.log 2>&1; echo RC=$?" % KLIPPER_INIT,
                            timeout=120)
    log("  %s %s" % (out.decode().strip(), err[-200:]))
    time.sleep(5)
    ok, msg = p.wait_ready(240)
    if ok:
        time.sleep(a.motor_wait)
    return ok, msg


def cmd_restart_service(p, a):
    p.connect()
    p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    if getattr(a, "with_mcu", False):
        # "MCU 'rpi' ... shutdown": klipper_mcu (Klipper's host MCU) has to be restarted too
        ok, msg = _restart_stack(p, a)
        log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg), "OK" if ok else "ERROR")
        return ok
    ok, msg = _service_restart(p, a, confirm=not a.yes)
    log("  Klipper %s %s" % ("ready" if ok else "NOT ready:", msg))
    return ok



# --------------------------------------------------------------------------- part fan (M106) fix

FAN_TAG = "# HI-FAN true-100"
FAN_LINES = [
    FAN_TAG + ": stock M106 halves the part fan outside sport mode (S255 -> 50%). Undo with: hi_tool.py fix-fan --revert",
    "{% if fan == 0 and tmp > 0 %}{% set value = [tmp, printer['gcode_macro PRINTER_PARAM'].fan0_min]|max %}{% endif %}",
]


def _find_section(p, section):
    """Returns (path, text) of the live, editable config file that defines [section]."""
    hits = []
    pat = re.compile(r"^\[" + re.escape(section) + r"\]\s*$", re.M)
    for f in p.list_config():
        path = f["path"]
        if not path.lower().endswith(".cfg") or BACKUP_CFG_RE.match(os.path.basename(path)):
            continue
        if "w" not in f["perm"]:
            continue
        text = p.get_config(path).decode("utf-8")
        if pat.search(text):
            hits.append((path, text))
    if not hits:
        raise ToolError("no editable file defines [%s]" % section)
    if len(hits) > 1:
        raise ToolError("[%s] is defined in several files %s - not guessing which one wins" % (section, [h[0] for h in hits]))
    return hits[0]


def patch_m106(text):
    """Insert the true-100% override just before the stock 'fan in [1, 2, 3]' dispatch. None if already patched."""
    if FAN_TAG in text:
        return None
    lines = text.splitlines(True)
    _, secs = sections(text)
    for name, s, e in secs:
        if name != "gcode_macro M106":
            continue
        body = "".join(lines[s:e])
        if "tmp / 2" not in body or "Rmode" not in body:
            raise ToolError("[gcode_macro M106] is not the stock Creality version (no 'tmp / 2' / Rmode) - not patching")
        for i in range(s + 1, e):
            if re.match(r"^\s*\{%\s*if fan in \[1, 2, 3\]\s*%\}", lines[i]):
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                eol = "\r\n" if lines[i].endswith("\r\n") else "\n"
                return "".join(lines[:i] + [indent + l + eol for l in FAN_LINES] + lines[i:])
        raise ToolError("[gcode_macro M106] has no '{% if fan in [1, 2, 3] %}' line - unexpected layout, not patching")
    raise ToolError("[gcode_macro M106] section not found")


def unpatch_m106(text):
    lines = text.splitlines(True)
    out, skip = [], 0
    for ln in lines:
        if skip:
            skip -= 1
            continue
        if FAN_TAG in ln:
            skip = len(FAN_LINES) - 1
            continue
        out.append(ln)
    new = "".join(out)
    return None if new == text else new


def _fan_probe(p):
    """Send M106 at a few values, read back the real PWM of output_pin fan0. Returns {S: pwm_0_255}."""
    res = {}
    try:
        for S in (128, 191, 255):
            p.gcode("M106 S%d" % S, timeout=30)
            time.sleep(0.4)
            v = p.query("output_pin fan0").get("output_pin fan0", {}).get("value", 0.0)
            res[S] = round(v * 255)
    finally:
        try:
            p.gcode("M107", timeout=30)
        except ToolError:
            pass
    return res


def cmd_fix_fan(p, a):
    p.connect()
    st = p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    log("  state: klippy=%s print=%s" % (st["klippy"], st["print"]))
    if st["klippy"] == "ready":
        before = _fan_probe(p)
        log("  part fan now: " + ", ".join("M106 S%d -> PWM %d/255 (%d%%)" % (S, v, v / 2.55) for S, v in before.items()))
    path, old = _find_section(p, "gcode_macro M106")
    new = unpatch_m106(old) if a.revert else patch_m106(old)
    if new is None:
        log("  %s: %s" % (path, "fix not present - nothing to revert" if a.revert else "already patched (%s)" % FAN_TAG))
        return True
    for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), "a/" + path, "b/" + path, lineterm="", n=2):
        log("    " + ln)
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply to upload.")
        return True

    bdir, originals = backup(p, a.backup_dir, "before-fan-revert" if a.revert else "before-fan-fix")
    if sha(originals.get(path, b"")) != sha(old.encode("utf-8")):
        raise ToolError("%s changed on the printer while we were working - aborting" % path)
    try:
        p.upload_config(path, new.encode("utf-8"))
        log("  uploaded + verified %s" % path)
        ok, msg = p.restart()
    except ToolError as e:
        ok, msg = False, str(e)
    if ok:
        time.sleep(a.motor_wait)
        cfg = p.configfile().get("config", {})
        g = next((v.get("gcode", "") for k, v in cfg.items() if k.lower() == "gcode_macro m106"), "")
        if ("fan0_min]|max" in g) == a.revert:
            ok, msg = False, "Klipper did not load the changed [gcode_macro M106] (another file overrides it?)"
    if ok:
        after = _fan_probe(p)
        log("  part fan now: " + ", ".join("M106 S%d -> PWM %d/255 (%d%%)" % (S, v, v / 2.55) for S, v in after.items()))
        want = 128 if a.revert else 255
        if abs(after.get(255, 0) - want) > 3:
            ok, msg = False, "M106 S255 gives PWM %s, expected %d" % (after.get(255), want)
    if not ok:
        log("  problem: %s" % msg.strip(), "ERROR")
        log("  rolling back %s from %s" % (path, bdir), "ERROR")
        try:
            p.upload_config(path, originals[path])
        except ToolError as e:
            log("  rollback upload failed: %s" % e, "ERROR")
        ok2, msg2 = p.restart(check=False)  # rollback: no idle check (we caused this restart)
        log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    log("  %s. Backup of the original: %s" % ("reverted to stock M106" if a.revert else "part fan fix applied: M106 S255 = true 100%", bdir))
    if not a.revert:
        log("  NOTE: slicer fan values are now real - your old '20% min' really is 20% now, and '100%' is about 2x the airflow you had.")
        log("  NOTE: a Creality firmware update may overwrite gcode_macro.cfg - re-run fix-fan after updating.")
    return True

# --------------------------------------------------------------------------- block-ota (hide firmware updates)

HOSTS_FILE = "/etc/hosts"
HOSTS_BEGIN = "# hi-block-ota begin"
HOSTS_END = "# hi-block-ota end"
OTA_HINTS = ("ota", "upgrade", "update", "firmware", "fw", "download")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _hosts_with_block(text, hosts):
    pat = re.compile(r"\r?\n?%s.*?%s\r?\n?" % (re.escape(HOSTS_BEGIN), re.escape(HOSTS_END)), re.S)
    base = pat.sub("\n", text).rstrip("\n") + "\n"
    if not hosts:
        return base
    lines = [HOSTS_BEGIN]
    for h in hosts:
        lines += ["0.0.0.0 %s" % h, ":: %s" % h]
    lines.append(HOSTS_END)
    return base + "\n".join(lines) + "\n"


def _scan_creality_hosts(p, a):
    """Creality hostnames found anywhere on the printer's own filesystem (read only). Returns a sorted list."""
    cmd = ("timeout 110 sh -c \"find / -xdev \\( -path /proc -o -path /sys -o -path /dev -o -path '*/gcodes' -o -path '*/printer_data/logs' \\) -prune "
           "-o -type f -size -30000k -print 2>/dev/null | xargs grep -aohiE '[a-z0-9][a-z0-9.-]*creality[a-z0-9.-]*[.][a-z][a-z]+' 2>/dev/null "
           "| sort -u | head -400\"")
    rc, out, err = _ssh_run(p, a, cmd, timeout=150)
    found = set()
    for ln in out.decode("utf-8", "replace").split():
        h = ln.strip().strip(".").lower()
        if HOST_RE.match(h):
            found.add(h)
    return sorted(found)


def _ota_diag(p, a):
    """Nothing found: show what the printer is running / connected to so the update host can be picked by hand."""
    cmds = [("DNS server in use", "cat /etc/resolv.conf 2>&1 | head -5"),
            ("update-looking programs/files", "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o -type f \\( -iname '*ota*' -o -iname '*upgrade*' -o -iname '*update*' \\) -print 2>/dev/null | grep -v -E 'python|klippy-env|/lib/modules|\\.pyc' | head -40"),
            ("update-looking processes", "ps 2>&1 | grep -i -E 'ota|upgrade|update|cloud|creality|mqtt' | grep -v grep | head -20"),
            ("current internet connections", "(netstat -tn 2>/dev/null || ss -tn 2>/dev/null) | head -40")]
    cmds += [("who owns the connections (PID/program)", "netstat -tnp 2>&1 | head -30"),
             ("tools on the printer", "for t in tcpdump nslookup dig iptables nft wget curl; do which $t; done 2>&1"),
             ("running programs", "ps 2>&1 | grep -v -E '[[]|ps$' | head -70"),
             ("host-like text inside upgrade-server", "grep -aoE '[A-Za-z0-9._/:-]{5,}' /usr/bin/upgrade-server | grep -iE 'http|[.](com|cn|net|io)|ota|server|url' | sort -u | head -50"),
             ("cloud / mqtt settings in config files", "find /etc /usr/data /overlay -xdev -type f -size -300k 2>/dev/null | xargs grep -IiE '(mqtt|cloud|ota|upgrade)[^ ]*[.](com|cn|net)|:1883|\"url\"|server_url' 2>/dev/null | head -40")]
    for title, c in cmds:
        rc, out, err = _ssh_run(p, a, c, timeout=90)
        log("  --- %s:" % title)
        for ln in out.decode("utf-8", "replace").splitlines()[:60]:
            log("    " + ln)


WATCH_SCRIPT = r"""
D=/tmp/hi_watch
rm -rf $D; mkdir -p $D
find /var/log /tmp /run /root /usr/data /mnt/UDISK -xdev -type f -size -20000k 2>/dev/null | grep -a -v -E '/hi_watch|gcode|[.]stl$|[.]3mf$|[.]jpg$|[.]jpeg$|[.]png$|[.]bin$|[.]img$|klippy[.]log|moonraker[.]log' > $D/files
while read f; do [ -r "$f" ] || continue; echo "$(wc -c < "$f" 2>/dev/null | tr -d ' ') $f"; done < $D/files > $D/before
touch $D/start
i=0
while [ $i -lt __W__ ]; do
  netstat -tunp 2>/dev/null | awk 'NR>2 && $5 !~ /^(192[.]168|127[.]|10[.]|0[.]0[.]0[.]0|:::|::1|[*])/ {print $5, $6, $7}' >> $D/conns
  i=$((i+1)); sleep 1
done
echo "##CONNS"; sort $D/conns 2>/dev/null | uniq -c | sort -rn | head -40
echo "##PTR"
for ip in $(awk '{split($1,a,":"); print a[1]}' $D/conns 2>/dev/null | sort -u | head -15); do echo "$ip $(nslookup $ip 2>/dev/null | grep -i -E 'name *=|Name:' | head -1)"; done
echo "##LOGS"
while read s f; do
  [ -r "$f" ] || continue
  n=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
  if [ -n "$n" ] && [ "$n" -gt "$s" ] 2>/dev/null; then
    echo "== $f"; tail -c +$((s+1)) "$f" 2>/dev/null | grep -a -i -E 'https?://|[a-z0-9-]+[.](com|cn|net|io|cloud)|ota|upgrade|download|update' | head -12 | cut -c1-300
  fi
done < $D/before
echo "##NEWFILES"
find /var/log /tmp /run /root /usr/data /mnt/UDISK -xdev -type f -newer $D/start 2>/dev/null | grep -a -v -E '/hi_watch|gcode|klippy|moonraker' | head -20
rm -rf $D
"""


def cmd_watch_ota(p, a):
    secs = max(20, min(int(a.seconds), 300))
    rc0, cur0, _e = _ssh_run(p, a, "cat %s" % HOSTS_FILE, timeout=30)
    blk = re.search(r"%s(.*?)%s" % (re.escape(HOSTS_BEGIN), re.escape(HOSTS_END)), cur0.decode("utf-8", "replace"), re.S)
    names = sorted(set(re.findall(r"^0\.0\.0\.0\s+(\S+)", blk.group(1), re.M))) if blk else []
    log("  our hosts block during this watch: %s" % (", ".join(names) if names else "NONE (nothing blocked)"))
    log("  WATCHING for %d s. Press the firmware update check on the Hi's screen NOW (Settings > About > Check for updates)." % secs)
    script = WATCH_SCRIPT.replace("__W__", str(secs))
    rc, out, err = _ssh_run(p, a, "cat > /tmp/hi_watch.sh && sh /tmp/hi_watch.sh; rm -f /tmp/hi_watch.sh",
                            timeout=secs + 120, data=script.encode("utf-8"))
    text = out.decode("utf-8", "replace")
    for ln in text.splitlines():
        log("    " + ln)
    if err:
        log(err[-300:], "WARN")
    seen = sorted(set(m.lower() for m in re.findall(r"[A-Za-z0-9][A-Za-z0-9.-]*[.](?:com|cn|net|io|cloud)\b", text.split("##LOGS", 1)[-1])
                      if HOST_RE.match(m.lower()) and not m.lower().startswith(("localhost",))))
    log("  host names seen in new log lines (%d):" % len(seen))
    for h in seen:
        log("    " + h)
    log("  Pick the one that looks like the update/firmware server and put it in 'Extra hosts', then Find update hosts (dry run) / Block updates. "
        "If nothing useful shows, try again and press the check a few seconds after it starts.")
    return True


CLOUDHOSTS_SCRIPT = r"""
for f in /usr/bin/app-server /usr/bin/master-server /usr/bin/web-server /usr/bin/display-server /usr/bin/upgrade-server; do
  [ -r "$f" ] || continue
  echo "##BIN $f"
  grep -aoE '(https?://)?[A-Za-z0-9._-]+[.](com|cn|net|io|cloud)[A-Za-z0-9._/?=&%-]*' "$f" | sort -u | head -80
done
echo "##PATHS in app-server (upgrade/firmware/ota)"
grep -aoE '[A-Za-z0-9._/-]*(upgrade|firmware|[Oo]ta|version)[A-Za-z0-9._/-]*' /usr/bin/app-server 2>/dev/null | grep '/' | sort -u | head -60
echo "##CONFIG"
grep -rIE 'https?://|[.](com|cn)[^A-Za-z]' /etc/appetc /mnt/UDISK/creality/userdata/config /mnt/UDISK/creality/userdata/cloud 2>/dev/null | cut -c1-240 | head -80
"""


def cmd_cloud_hosts(p, a):
    log("  reading the Hi's own programs and config for Creality host names (read only) ")
    rc, out, err = _ssh_run(p, a, "cat > /tmp/hi_ch.sh && sh /tmp/hi_ch.sh; rm -f /tmp/hi_ch.sh",
                            timeout=150, data=CLOUDHOSTS_SCRIPT.encode("utf-8"))
    text = out.decode("utf-8", "replace")
    for ln in text.splitlines():
        log("    " + ln)
    if err:
        log(err[-300:], "WARN")
    seen = sorted(set(m.lower() for m in re.findall(r"[A-Za-z0-9][A-Za-z0-9.-]*[.](?:com|cn|net|io|cloud)\b", text)
                      if HOST_RE.match(m.lower())))
    log("  host names seen (%d):" % len(seen))
    for h in seen:
        log("    " + h)
    return True


UILOG_SCRIPT = r"""
L=/mnt/UDISK/creality/userdata/log
PAT='extrud|filament|feed|unload|[^d]load|material|cfs|G1 E|M83|heat|retract'
echo "##LOG FILES"; ls -la $L 2>&1 | head -40
for f in $L/display-server.log $L/master-server.log $L/app-server.log $L/web-server.log; do
  [ -r "$f" ] || continue
  echo "##COVERAGE $f  first: $(head -1 "$f" | cut -c1-24)  last: $(tail -1 "$f" | cut -c1-24)"
done
for f in $L/display-server.log* $L/master-server.log* $L/app-server.log*; do
  [ -r "$f" ] || continue
  case "$f" in *.gz|*.tar*) continue;; esac
  echo "##UI/APP $f"
  awk -v a="__A__" -v b="__B__" 'substr($0,2,19)>=a && substr($0,2,19)<=b' "$f" | grep -a -i -E "$PAT" | cut -c1-260 | head -200
done
K=/mnt/UDISK/printer_data/logs
for f in $K/klippy.log $K/klippy.log.*; do
  [ -r "$f" ] || continue
  case "$f" in *.gz) continue;; esac
  echo "##KLIPPY $f  first: $(head -1 "$f" | cut -c1-40)"
  awk -v a="__C__" -v b="__D__" 'substr($0,8,19)>=a && substr($0,8,19)<=b' "$f" | grep -a -E 'G1 E|M83|EXTRUDE|extrude|LOAD_FILAMENT|UNLOAD|FILAMENT|M104|M109' | cut -c1-220 | head -150
done
for f in $K/moonraker.log $K/moonraker.log.*; do
  [ -r "$f" ] || continue
  case "$f" in *.gz) continue;; esac
  echo "##MOONRAKER $f"
  awk -v a="__C__" -v b="__D__" 'substr($0,1,19)>=a && substr($0,1,19)<=b' "$f" | grep -a -i -E 'gcode/script|extrude|filament|load' | cut -c1-240 | head -150
done
echo "##DONE"
"""


def cmd_ui_log(p, a):
    def norm(t, end):
        t = t.strip().replace("T", " ")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
            return t + (" 23:59:59" if end else " 00:00:00")
        if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$", t):
            raise ToolError("use a date like 2026-10-29 (whole day) or 2026-10-29 17:00")
        return t + (":59" if end and len(t) == 16 else ":00" if len(t) == 16 else "")
    t0, t1 = norm(a.time_from, False), norm(a.time_to, True)
    sc = (UILOG_SCRIPT.replace("__A__", t0.replace("-", "/").replace(" ", "-"))
          .replace("__B__", t1.replace("-", "/").replace(" ", "-")).replace("__C__", t0).replace("__D__", t1))
    log("  searching the Hi's logs from %s to %s (printer clock) for extrude / filament / heat events (read only) " % (t0, t1))
    rc, out, err = _ssh_run(p, a, "cat > /tmp/hi_ui.sh && sh /tmp/hi_ui.sh; rm -f /tmp/hi_ui.sh",
                            timeout=170, data=sc.encode("utf-8"))
    for ln in out.decode("utf-8", "replace").splitlines():
        log("    " + ln)
    if err:
        log(err[-300:], "WARN")
    return True


def cmd_pull_logs(p, a):
    """Save ALL of the Hi's logs (screen/app/master/web servers, Klipper + Moonraker incl. rotated ones, system messages)
    into hi_backups/<printer>/<time>_logs/ . Read only on the printer."""
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "%s_logs" % ts)
    os.makedirs(d, exist_ok=True)
    log("  packing the printer's logs over SSH (can be 30+ MB, takes a minute) ")
    remote = ("cd / && tar czf - mnt/UDISK/creality/userdata/log mnt/UDISK/printer_data/logs "
              "var/log/messages tmp/log 2>/dev/null")
    rc, out, err = _ssh_run(p, a, remote, timeout=540)
    if not out:
        raise ToolError("nothing came back from tar (%s)" % (err[-200:] or "rc %s" % rc))
    tgz = os.path.join(d, "logs.tar.gz")
    with open(tgz, "wb") as fh:
        fh.write(out)
    n = 0
    with tarfile.open(tgz, "r:gz") as tf:
        for m in tf.getmembers():
            name = m.name.replace("\\\\", "/")
            if name.startswith("/") or ".." in name.split("/") or not (m.isfile() or m.isdir()):
                continue
            tf.extract(m, os.path.join(d, "logs"))
            n += 1 if m.isfile() else 0
    log("  saved %d log files (%.1f MB packed) to %s" % (n, len(out) / 1e6, d))
    for root, _dirs, files in os.walk(os.path.join(d, "logs")):
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            log("    %s  (%d KB)" % (os.path.relpath(fp, d), os.path.getsize(fp) // 1024))
    return True


# --------------------------------------------------------------------------- fix-grab (load button holds the filament)

GRAB_BEGIN = "# HI-GRAB begin"
GRAB_END = "# HI-GRAB end"
GRAB_CALL = "  GRAB_FILAMENT"


def grab_block(mm, speed):
    return [
        GRAB_BEGIN,
        "# Load button: if the filament sensor is triggered, turn the extruder gears a few mm COLD so they grab and hold",
        "# the filament while the nozzle heats. Nothing is extruded from the hot end. Undo: hi_tool.py fix-grab --revert",
        "[gcode_macro GRAB_FILAMENT]",
        "variable_mm: %g" % mm,
        "variable_speed: %g" % speed,
        "gcode:",
        "  {% set mm = printer['gcode_macro GRAB_FILAMENT'].mm|float %}",
        "  {% set speed = printer['gcode_macro GRAB_FILAMENT'].speed|float %}",
        "  {% set ps = printer.print_stats.state %}",
        "  {% if ps in ['printing', 'paused'] %}",
        "    RESPOND MSG=\"GRAB_FILAMENT: skipped, print state is {ps}\"",
        "  {% elif printer['filament_switch_sensor filament_sensor'].filament_detected %}",
        "    FORCE_MOVE STEPPER=extruder DISTANCE={mm} VELOCITY={speed} ACCEL=200",
        "    RESPOND MSG=\"GRAB_FILAMENT: turned the extruder {mm} mm\"",
        "  {% else %}",
        "    RESPOND MSG=\"GRAB_FILAMENT: filament sensor not triggered, nothing to do\"",
        "  {% endif %}",
        GRAB_END,
    ]


def unpatch_grab(text):
    """Remove our macro block and the call line in LOAD_MATERIAL. Returns the text (unchanged if we are not there)."""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(True)
    out, skipping = [], False
    for ln in lines:
        s = ln.strip()
        if s == GRAB_BEGIN:
            skipping = True
            if out and out[-1].strip() == "":
                out.pop()
            continue
        if skipping:
            if s == GRAB_END:
                skipping = False
            continue
        out.append(ln)
    text2 = "".join(out)
    lines2, secs = sections(text2)
    for name, s, e in secs:
        if name == "gcode_macro LOAD_MATERIAL":
            lines2 = [l for i, l in enumerate(lines2) if not (s < i < e and l.rstrip("\r\n") == GRAB_CALL)]
            break
    return "".join(lines2)


def patch_grab(text, mm, speed):
    """Add the GRAB_FILAMENT macro and a call to it in LOAD_MATERIAL, right after BOX_GO_TO_EXTRUDE_POS. None if no change."""
    base = unpatch_grab(text)
    eol = "\r\n" if "\r\n" in base else "\n"
    lines, secs = sections(base)
    target = [(s, e) for name, s, e in secs if name == "gcode_macro LOAD_MATERIAL"]
    if len(target) != 1:
        raise ToolError("[gcode_macro LOAD_MATERIAL] not found exactly once - not patching")
    s, e = target[0]
    body = lines[s:e]
    if not any(l.strip() == "BOX_GO_TO_EXTRUDE_POS" for l in body):
        raise ToolError("[gcode_macro LOAD_MATERIAL] has no BOX_GO_TO_EXTRUDE_POS line - not the stock Creality layout, not patching")
    if not any(l.strip() == "FILAMENT_RACK_SET_TEMP" for l in body):
        raise ToolError("[gcode_macro LOAD_MATERIAL] has no FILAMENT_RACK_SET_TEMP line - not the stock Creality layout, not patching")
    idx = next(i for i in range(s, e) if lines[i].strip() == "BOX_GO_TO_EXTRUDE_POS")
    # the call must come BEFORE the heating line
    idx_heat = next(i for i in range(s, e) if lines[i].strip() == "FILAMENT_RACK_SET_TEMP")
    if idx > idx_heat:
        raise ToolError("BOX_GO_TO_EXTRUDE_POS comes after FILAMENT_RACK_SET_TEMP - unexpected order, not patching")
    # earliest point: before IF_NEED_HOME (homing) and the move to the purge spot. The extruder gears do not depend on
    # the toolhead position, so the filament is gripped the moment the load button is pressed. Fallback: just before
    # the move to the purge spot.
    home = [i for i in range(s, e) if lines[i].strip() == "IF_NEED_HOME" and i < idx]
    at = home[0] if home else idx
    lines.insert(at, GRAB_CALL + eol)
    # put the macro block after the end of the LOAD_MATERIAL section (skip trailing blank/comment lines of the section)
    e2 = e + 1
    while e2 > idx + 2 and (lines[e2 - 1].strip() == "" or lines[e2 - 1].lstrip().startswith("#")):
        e2 -= 1
    block = [""] + grab_block(mm, speed)
    lines[e2:e2] = [b + eol for b in block]
    return "".join(lines)


def cmd_fix_grab(p, a):
    p.connect()
    st = p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    log("  state: klippy=%s print=%s" % (st["klippy"], st["print"]))
    path, old = _find_section(p, "gcode_macro LOAD_MATERIAL")
    new = unpatch_grab(old) if a.revert else patch_grab(old, a.mm, a.speed)
    if new == old:
        log("  %s: %s" % (path, "fix not present - nothing to revert" if a.revert else "already installed with these settings (%g mm at %g mm/s)" % (a.mm, a.speed)))
        return True
    for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), "a/" + path, "b/" + path, lineterm="", n=2):
        log("    " + ln)
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply to upload.")
        return True

    bdir, originals = backup(p, a.backup_dir, "before-grab-revert" if a.revert else "before-grab-fix")
    if sha(originals.get(path, b"")) != sha(old.encode("utf-8")):
        raise ToolError("%s changed on the printer while we were working - aborting" % path)
    try:
        p.upload_config(path, new.encode("utf-8"))
        log("  uploaded + verified %s" % path)
        ok, msg = p.restart()
    except ToolError as e:
        ok, msg = False, str(e)
    if ok:
        time.sleep(a.motor_wait)
        cfg = p.configfile().get("config", {})
        have = any(k.lower() == "gcode_macro grab_filament" for k in cfg)
        load = next((v.get("gcode", "") for k, v in cfg.items() if k.lower() == "gcode_macro load_material"), "")
        if a.revert and (have or "GRAB_FILAMENT" in load):
            ok, msg = False, "Klipper still has GRAB_FILAMENT after the revert"
        if not a.revert and not (have and "GRAB_FILAMENT" in load):
            ok, msg = False, "Klipper did not load GRAB_FILAMENT / the changed LOAD_MATERIAL"
    if not ok:
        log("  problem: %s" % msg.strip(), "ERROR")
        log("  rolling back %s from %s" % (path, bdir), "ERROR")
        try:
            p.upload_config(path, originals[path])
        except ToolError as e:
            log("  rollback upload failed: %s" % e, "ERROR")
        ok2, msg2 = p.restart(check=False)
        log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    if a.revert:
        log("  reverted: the load button is stock again. Backup of the previous file: %s" % bdir)
    else:
        log("  installed. Load button now: FIRST, if the filament sensor is triggered, turn the extruder %g mm cold at %g mm/s -> then home / go to the purge spot, heat and load as normal." % (a.mm, a.speed))
        log("  Backup of the original: %s" % bdir)
        log("  Test: insert filament until the sensor triggers, press load on the screen, then press 'Show last load-button run'. "
            "If it says the screen did not call GRAB_FILAMENT, the screen uses its own fixed list and this hook needs a different spot.")
        log("  NOTE: a Creality firmware update may overwrite gcode_macro.cfg - re-install after updating.")
    return True


def cmd_grab_check(p, a):
    """Read only: what the screen's last 'load material' sent to Klipper, and what GRAB_FILAMENT answered."""
    cmd = ("L=/mnt/UDISK/creality/userdata/log; "
           "for f in $L/master-server.log; do "
           "echo '== last load-material lists the screen built:'; grep -a 'load material = ' $f | tail -3 | cut -c1-420; "
           "echo '== GRAB_FILAMENT lines (script sent / answer):'; grep -a 'GRAB_FILAMENT' $f | tail -8 | cut -c1-300; done")
    rc, out, err = _ssh_run(p, a, cmd, timeout=60)
    for ln in out.decode("utf-8", "replace").splitlines():
        log("    " + ln)
    txt = out.decode("utf-8", "replace")
    if "load material = " not in txt:
        log("  no load-material run in the current screen log yet - press load on the Hi's screen first.", "WARN")
    elif "GRAB_FILAMENT" not in txt.split("== GRAB_FILAMENT", 1)[0] and "GRAB_FILAMENT" not in txt.split("== GRAB_FILAMENT", 1)[-1]:
        log("  the screen did NOT call GRAB_FILAMENT - it uses its own fixed list. Tell me and I'll hook a different command.", "WARN")
    else:
        log("  GRAB_FILAMENT is being called by the load button.")
    return True


def cmd_block_ota(p, a):
    log("  reading %s over SSH " % HOSTS_FILE)
    rc, cur, err = _ssh_run(p, a, "cat %s" % HOSTS_FILE, timeout=60)
    if rc != 0:
        raise ToolError("could not read %s: %s" % (HOSTS_FILE, err[-300:]))
    text = cur.decode("utf-8", "replace")
    already = re.findall(r"^(?:0\.0\.0\.0|::)\s+(\S+)\s*$",
                         (re.search(r"%s(.*?)%s" % (re.escape(HOSTS_BEGIN), re.escape(HOSTS_END)), text, re.S) or [None, ""])[1], re.M)
    if already:
        log("  currently blocked by us: %s" % ", ".join(sorted(set(already))))
    else:
        log("  nothing blocked by us right now")

    if a.revert:
        new = _hosts_with_block(text, [])
        hosts = []
    else:
        manual = [h.strip().lower() for h in (a.hosts or "").replace(" ", ",").split(",") if h.strip()]
        for h in manual:
            if not HOST_RE.match(h):
                raise ToolError("'%s' is not a valid host name" % h)
        log("  scanning the printer for Creality host names (takes up to a minute) ")
        found = _scan_creality_hosts(p, a)
        guess = [h for h in found if any(w in h.replace("-", ".").split(".") or w in h for w in OTA_HINTS)]
        log("  Creality host names found on the printer (%d):" % len(found))
        for h in found:
            log("    %s%s" % (h, "   <- looks like an update host" if h in guess else ""))
        hosts = sorted(set(guess) | set(manual) | (set(already) if a.keep else set()))
        if not found and not manual:
            _ota_diag(p, a)
        if not hosts:
            log("  no update-looking host found and none given. Nothing to block. Pick names from the list above and run "
                "again with --hosts (GUI: 'Extra hosts' box).", "WARN")
            return True
        log("  would block: %s" % ", ".join(hosts))
        new = _hosts_with_block(text, hosts)

    for ln in difflib.unified_diff(text.splitlines(), new.splitlines(), "a/hosts", "b/hosts", lineterm="", n=1):
        log("    " + ln)
    if new == text:
        log("  /etc/hosts already in that state - nothing to do.")
        return True
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply.")
        return True

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(a.backup_dir, p.host, "blockota_%s" % ts)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "hosts.orig"), "wb") as fh:
        fh.write(cur)
    md5_old = hashlib.md5(cur).hexdigest()
    md5_new = hashlib.md5(new.encode("utf-8")).hexdigest()
    remote = ("F=%s; T=/tmp/hi_hosts; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo CHANGED_ON_PRINTER; exit 3; }; "
              "[ -f $F.hi-orig ] || cp $F $F.hi-orig || exit 4; "
              "cat > $T || exit 5; "
              "cat $T > $F || exit 7; "
              "[ \"$(md5sum $F | cut -d' ' -f1)\" = \"%s\" ] || { echo VERIFY_FAILED; cat $F.hi-orig > $F; exit 8; }; "
              "rm -f $T; echo INSTALLED" % (HOSTS_FILE, md5_old, md5_new))
    rc, out, err = _ssh_run(p, a, remote, timeout=60, data=new.encode("utf-8"))
    res = out.decode("utf-8", "replace").strip()
    log("  printer says: %s %s" % (res, err[-200:] if rc else ""))
    if rc != 0 or "INSTALLED" not in res:
        log("  failed - /etc/hosts left as it was", "ERROR")
        return False
    if hosts:
        rc, out, err = _ssh_run(p, a, "for h in %s; do echo \"$h -> $(ping -c1 -W2 $h 2>&1 | head -1)\"; done" % " ".join(hosts), timeout=30)
        for ln in out.decode("utf-8", "replace").splitlines():
            log("    " + ln)
        log("  done. Each name above should show (0.0.0.0) in the ping line. Original kept as /etc/hosts.hi-orig and in " + d)
        log("  NOTE: a reboot or a firmware update could rebuild /etc/hosts - re-run Check/Block if the Hi ever shows an update again.")
    else:
        log("  block removed. Backup of the previous file: " + d)
    return True


# --------------------------------------------------------------------------- ram (REMOVE_PART_DYNAMIC)

RAM_MACRO = "REMOVE_PART_DYNAMIC"
RAM_REMOTE = "ramming.cfg"
RAM_SECTION_RE = re.compile(r"^\[gcode_macro\s+REMOVE_PART_DYNAMIC\]\s*$", re.I | re.M)
EXCL_RE = re.compile(r"^EXCLUDE_OBJECT_DEFINE\b.*?POLYGON=(\[\[.*?\]\])", re.I)
MAXZ_RE = re.compile(r"^;\s*max_z_height\s*[:=]\s*([\d.]+)", re.I)
GMOVE_RE = re.compile(r"^G[0-3]\b", re.I)
WORD_RE = re.compile(r"([XYZE])\s*(-?\d*\.?\d+)", re.I)


def default_ram_cfg():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), RAM_REMOTE)


PLATE_GCODE_RE = re.compile(r"^Metadata/plate_(\d+)\.gcode$", re.I)


def list_3mf_plates(path):
    """[(plate_number, bytes)] of the sliced gcode inside a .gcode.3mf (MakerWorld / Bambu / Orca / Creality Print)."""
    with zipfile.ZipFile(path) as z:
        out = []
        for i in z.infolist():
            m = PLATE_GCODE_RE.match(i.filename)
            if m:
                out.append((int(m.group(1)), i.file_size))
    return sorted(out)


def gcode_from_3mf(path, plate=None, out_dir=None):
    """Write one plate's gcode out of a .gcode.3mf next to it (never overwrites). Returns
    {path, plate, printer_model, printer_settings_id, is_hi}."""
    plates = list_3mf_plates(path)
    if not plates:
        raise ToolError("%s has no sliced gcode inside (it's a project file - slice it first)" % os.path.basename(path))
    if plate is None:
        if len(plates) > 1:
            raise ToolError("%s has %d sliced plates (%s) - pick one" % (os.path.basename(path), len(plates),
                            ", ".join(str(n) for n, _ in plates)))
        plate = plates[0][0]
    if plate not in [n for n, _ in plates]:
        raise ToolError("plate %s is not in %s (has %s)" % (plate, os.path.basename(path), [n for n, _ in plates]))
    stem = re.sub(r"(\.gcode)?\.3mf$", "", os.path.basename(path), flags=re.I)
    d = out_dir or os.path.dirname(os.path.abspath(path))
    dst = os.path.join(d, "%s_plate%d.gcode" % (stem, plate))
    k = 2
    with zipfile.ZipFile(path) as z:
        data = z.read("Metadata/plate_%d.gcode" % plate)
        while os.path.exists(dst):
            with open(dst, "rb") as fh:
                if sha(fh.read()) == sha(data):
                    break  # identical copy already extracted
            dst = os.path.join(d, "%s_plate%d_%d.gcode" % (stem, plate, k))
            k += 1
        else:
            with open(dst, "wb") as fh:
                fh.write(data)
    info = {"path": dst, "plate": plate, "printer_model": "", "printer_settings_id": ""}
    for m in re.finditer(rb"^;\s*(printer_model|printer_settings_id)\s*=\s*(.*)$", data, re.M):
        info[m.group(1).decode()] = m.group(2).decode("utf-8", "replace").strip()
    info["is_hi"] = "creality hi" in (info["printer_model"] + " " + info["printer_settings_id"]).lower()
    return info


def ram_params_from_gcode(path):
    """Part centre + top Z the way the slicer end gcode passes them:
    centre = centre of the first-layer footprint (union of EXCLUDE_OBJECT polygons, else the
    first-layer extrusion bbox), top = '; max_z_height' header (else the highest extrusion)."""
    xs, ys, top, n_obj = [], [], None, 0
    polys = []
    calls_ram = False
    fl = [1e9, 1e9, -1e9, -1e9]
    x = y = z = 0.0
    e_abs = False
    first_z = None
    seen_type = False
    max_ext_z = 0.0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.startswith(";"):
                if top is None:
                    m = MAXZ_RE.match(ln)
                    if m:
                        top = float(m.group(1))
                if ln.startswith((";TYPE:", "; FEATURE:")):
                    kind = ln.split(":", 1)[1].strip().lower()
                    seen_type = not kind.startswith(("custom", "skirt", "brim", "prime", "wipe", "purge"))
                continue
            if ln.startswith("EXCLUDE_OBJECT_DEFINE"):
                m = EXCL_RE.match(ln)
                if m:
                    n_obj += 1
                    poly = json.loads(m.group(1))
                    polys.append(poly)
                    for px, py in poly:
                        xs.append(px)
                        ys.append(py)
                continue
            if RAM_MACRO in ln.upper():
                calls_ram = True
                continue
            u = ln[:4].upper()
            if u.startswith("M82"):
                e_abs = True
            elif u.startswith("M83"):
                e_abs = False
            if not GMOVE_RE.match(ln):
                continue
            w = {k.upper(): float(v) for k, v in WORD_RE.findall(ln.split(";", 1)[0])}
            nx, ny, z = w.get("X", x), w.get("Y", y), w.get("Z", z)
            extr = "E" in w and w["E"] > 0 and not e_abs
            if extr and seen_type:
                if first_z is None:
                    first_z = z
                if abs(z - first_z) < 1e-3:
                    fl = [min(fl[0], nx, x), min(fl[1], ny, y), max(fl[2], nx, x), max(fl[3], ny, y)]
                max_ext_z = max(max_ext_z, z)
            x, y = nx, ny
    if xs:
        bbox, src = (min(xs), min(ys), max(xs), max(ys)), "%d object outlines" % n_obj
    elif fl[0] < 1e9:
        bbox, src = tuple(fl), "first-layer extrusion"
    else:
        raise ToolError("could not find any part outline or first-layer extrusion in %s" % path)
    if top is None:
        top = max_ext_z
    return {
        "center_x": round((bbox[0] + bbox[2]) / 2, 2), "center_y": round((bbox[1] + bbox[3]) / 2, 2),
        "top_z": round(top, 2), "bbox": [round(v, 1) for v in bbox], "source": src, "calls_ram": calls_ram,
        "polys": polys,
    }


def _add_include(text, name):
    """Add [include name] after the last [include ...] line (always above the SAVE_CONFIG block).
    Returns None if it is already there."""
    if re.search(r"^\[include\s+" + re.escape(name) + r"\s*\]", text, re.I | re.M):
        return None
    lines = text.splitlines(True)
    eol = "\r\n" if text.count("\r\n") > text.count("\n") / 2 else "\n"
    idx = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#*#"):
            break
        if re.match(r"^\[include\s+", ln, re.I):
            idx = i + 1
    if idx is None:  # no includes: put it before the first section
        idx = next((i for i, ln in enumerate(lines) if SECTION_RE.match(ln)), 0)
    return "".join(lines[:idx] + ["[include %s]%s" % (name, eol)] + lines[idx:])


def _restore_park(p, parked):
    """After a RESTART Klipper has forgotten where the toolhead is. Put the pre-restart X/Y/Z back and turn the motors
    off again: that is the same 'not homed, position still known' state END_PRINT's M84 leaves, so ram --from-park /
    'parked after END_PRINT' keeps working. Nothing moves (SET_KINEMATIC_POSITION only changes what Klipper believes)."""
    try:
        # xyz_ready.z_ready/z_moved reset to 0 on every Klipper restart. With z_ready=0 the next G28 X/Y runs _IF_HOME_Z's
        # first-home branch (SET_KINEMATIC_POSITION Z=0 + UP_SAFE_Z = physically +15 mm, belief ~10): every Z after that is
        # ~175 mm too high. Marking Z as already homed makes G28 X Y leave Z alone, as it does when Klipper never restarted.
        p.gcode("SET_KINEMATIC_POSITION X=%.3f Y=%.3f Z=%.3f\n%s\nM84" % (tuple(parked) + ("SET_GCODE_VARIABLE MACRO=xyz_ready VARIABLE=z_ready VALUE=1\nSET_GCODE_VARIABLE MACRO=xyz_ready VARIABLE=z_moved VALUE=1",)), timeout=20)
        st = p.state()
        pos = st.get("position") or [0, 0, 0]
        if (st.get("homed") or "") == "" and abs(pos[2] - parked[2]) < 0.5:
            log("  keep-park: restored parked position X%.2f Y%.2f Z%.2f, motors off, not homed (nothing moved)" % tuple(parked))
            return True
        log("  keep-park: tried to restore X%.2f Y%.2f Z%.2f but Klipper now says homed='%s' pos=%s - check before ramming; "
            "Recover Z tab is the fallback" % (parked[0], parked[1], parked[2], st.get("homed"), pos[:3]), "WARN")
    except ToolError as e:
        log("  keep-park: could not restore the parked position (%s) - Recover Z tab is the fallback" % e, "WARN")
    return False


def cmd_install_ram(p, a):
    local = a.cfg or default_ram_cfg()
    if not os.path.isfile(local):
        raise ToolError("ramming file not found: %s" % local)
    with open(local, "rb") as fh:
        new_ram = fh.read()
    new_txt = new_ram.decode("utf-8")
    if not RAM_SECTION_RE.search(new_txt):
        raise ToolError("%s has no [gcode_macro %s] section - wrong file?" % (local, RAM_MACRO))
    if BLOCKED_GCODE.search(new_txt):
        raise ToolError("%s contains FIRMWARE_RESTART - refusing to install it on a Hi" % local)
    remote = a.remote_name
    p.connect()
    keep_park = getattr(a, "keep_park", False)
    st = p.assert_idle(a.force, keep_position=not (getattr(a, "plate_clear", False) or keep_park))
    log("  state: klippy=%s print=%s" % (st["klippy"], st["print"]))
    parked = None
    if keep_park:
        kp = st.get("position") or [0, 0, 0]
        if kp[2] >= 5:
            parked = [float(x) for x in kp[:3]]
            log("  keep-park: Klipper holds X%.2f Y%.2f Z%.2f (homed='%s'); it will be restored after the RESTART, "
                "nothing moves" % (parked[0], parked[1], parked[2], st.get("homed") or ""))
        else:
            log("  keep-park: Klipper holds no parked position right now (Z%.1f) - nothing to keep, installing normally" % kp[2],
                "WARN")
    log("  local file: %s (sha %s)" % (local, sha(new_ram)[:12]))

    files = {f["path"]: f for f in p.list_config()}
    for path, f in files.items():
        if path == remote or not path.lower().endswith(".cfg") or BACKUP_CFG_RE.match(os.path.basename(path)):
            continue
        if RAM_SECTION_RE.search(p.get_config(path).decode("utf-8", "replace")):
            raise ToolError("[gcode_macro %s] is already defined in %s - remove it there first "
                            "(Klipper refuses duplicate sections)" % (RAM_MACRO, path))
    old_ram = p.get_config(remote) if remote in files else None
    pc_old = p.get_config("printer.cfg").decode("utf-8")
    pc_new = _add_include(pc_old, remote)

    if old_ram is not None and sha(old_ram) == sha(new_ram) and pc_new is None:
        log("  %s on the printer is already this version and printer.cfg includes it. Nothing to do." % remote)
        return True
    if old_ram is None:
        log("  %s: new file (%d bytes)" % (remote, len(new_ram)))
    elif sha(old_ram) != sha(new_ram):
        for ln in difflib.unified_diff(old_ram.decode("utf-8", "replace").splitlines(), new_txt.splitlines(),
                                       "a/" + remote, "b/" + remote, lineterm="", n=1):
            log("    " + ln)
    else:
        log("  %s already up to date" % remote)
    if pc_new is not None:
        for ln in difflib.unified_diff(pc_old.splitlines(), pc_new.splitlines(), "a/printer.cfg", "b/printer.cfg",
                                       lineterm="", n=2):
            log("    " + ln)
    else:
        log("  printer.cfg already has [include %s]" % remote)
    if not a.apply:
        log("  DRY RUN - nothing changed. Re-run with --apply to upload.")
        return True

    bdir, originals = backup(p, a.backup_dir, "before-ram")
    if sha(originals.get("printer.cfg", b"")) != sha(pc_old.encode("utf-8")):
        raise ToolError("printer.cfg changed on the printer while we were working - aborting")
    try:
        p.upload_config(remote, new_ram)
        log("  uploaded + verified %s" % remote)
        if pc_new is not None:
            p.upload_config("printer.cfg", pc_new.encode("utf-8"))
            log("  uploaded + verified printer.cfg")
        ok, msg = p.restart()
    except ToolError as e:
        ok, msg = False, str(e)
    if ok:
        time.sleep(a.motor_wait)
        cfg = p.configfile().get("config", {})
        sec = next((v for k, v in cfg.items() if k.lower() == "gcode_macro " + RAM_MACRO.lower()), None)
        if sec is None:
            ok, msg = False, "Klipper did not load [gcode_macro %s]" % RAM_MACRO
        elif "push_to_edge" in new_txt.lower() and "push_to_edge" not in sec.get("gcode", "").lower():
            ok, msg = False, "Klipper loaded an older %s (another file overrides it?)" % RAM_MACRO
    if not ok:
        log("  problem: %s" % msg.strip(), "ERROR")
        log("  rolling back from %s" % bdir, "ERROR")
        try:
            if pc_new is not None:
                p.upload_config("printer.cfg", originals["printer.cfg"])
            if old_ram is not None:
                p.upload_config(remote, old_ram)
            else:
                p.req("DELETE", "/server/files/config/" + urllib.parse.quote(remote))
        except ToolError as e:
            log("  rollback failed: %s" % e, "ERROR")
        ok2, msg2 = p.restart(check=False)  # rollback: no idle check (we caused this restart)
        log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        if ok2 and parked:
            _restore_park(p, parked)
        return False
    if parked:
        _restore_park(p, parked)
    log("  %s installed and loaded. Backup of the previous config: %s" % (RAM_MACRO, bdir))
    return True


# Toolhead geometry, measured on the Hi (mm from the nozzle centre). ramming.cfg carries the same
# numbers as variables; ram_check uses the printer's values when the installed macro has them.
CASING_HALF_W = 30.0   # casing reaches 30 mm left and right of the nozzle
CASING_FRONT = 41.0    # front face (the pusher, -Y side) is 41 mm in front of the nozzle
CASING_BACK = 30.0     # back of the casing; carriage/gantry sit further back but higher
CASING_GAP = 3.0       # lowest casing edge is 3 mm above the nozzle tip ...
CASING_SLOPE = 8.0     # ... then slopes back 8 mm more: the solid face starts 11 mm above the tip
MIN_NOZZLE_Z = 2.0     # lowest nozzle height while pushing
MIN_CONTACT = 5.0      # solid face must overlap the part by this much
MIN_RAM_TOP = MIN_NOZZLE_Z + CASING_GAP + CASING_SLOPE + MIN_CONTACT   # 18 mm


def _ram_inputs(a):
    if a.gcode_file and a.gcode_file.lower().endswith(".3mf"):
        info = gcode_from_3mf(a.gcode_file, getattr(a, "plate", None))
        log("  extracted plate %d -> %s (sliced for %s)" % (info["plate"], info["path"], info["printer_model"] or "?"))
        if not info["is_hi"]:
            log("  this gcode was NOT sliced for a Creality Hi - don't print or ram it on a Hi as-is", "WARN")
        a.gcode_file = info["path"]
    if a.gcode_file:
        g = ram_params_from_gcode(a.gcode_file)
        log("  %s: centre X%.2f Y%.2f, top Z%.2f, footprint X %.1f..%.1f Y %.1f..%.1f (from %s)"
            % (os.path.basename(a.gcode_file), g["center_x"], g["center_y"], g["top_z"],
               g["bbox"][0], g["bbox"][2], g["bbox"][1], g["bbox"][3], g["source"]))
    else:
        g = {"center_x": None, "center_y": None, "top_z": None, "bbox": None, "polys": [], "calls_ram": False}
    for k, v in (("center_x", a.center_x), ("center_y", a.center_y), ("top_z", a.top_z)):
        if v is not None:
            g[k] = v
    if None in (g["center_x"], g["center_y"], g["top_z"]):
        raise ToolError("need --gcode FILE or all of --center-x --center-y --top-z")
    return g


def _lane_xs(cx, lanes, spacing, xmin, xmax):
    """Same order and clamping as the macro: centre, then alternating -/+ spacing."""
    out = []
    for i in range(max(1, lanes)):
        step = ((i + 1) // 2) * spacing
        off = step if i % 2 == 0 else -step
        out.append(min(max(cx + off, xmin), xmax))
    return out


def _max_y_in_strip(g, x0, x1):
    """Highest Y any part reaches between x0 and x1 (None if nothing is there)."""
    best = None
    for poly in g.get("polys") or []:
        for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
            for k in range(21):
                t = k / 20.0
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                if x0 <= x <= x1 and (best is None or y > best):
                    best = y
    if best is None and g.get("bbox") and not g.get("polys"):
        bx0, by0, bx1, by1 = g["bbox"]
        if bx1 >= x0 and bx0 <= x1:
            best = by1
    return best


def ram_check(p, a, g):
    """Readiness checklist. Logs [OK]/[WARN]/[FAIL] lines; returns (ok, plan)."""
    fails, warns = [], []

    def ok(m):
        log("  [OK]   " + m)

    def warn(m):
        warns.append(m)
        log("  [WARN] " + m)

    def fail(m):
        fails.append(m)
        log("  [FAIL] " + m)

    cx, cy, top = g["center_x"], g["center_y"], g["top_z"]
    plan = {"pre": None, "back_y": None, "lanes": []}
    p.connect()
    objs = p.req("GET", "/printer/objects/list").get("objects", [])
    mname = "gcode_macro %s" % RAM_MACRO
    want = ["webhooks", "print_stats", "toolhead", "extruder", "heater_bed"] + ([mname] if mname in objs else [])
    s = p.query(*want)
    wh, ps, th = s.get("webhooks", {}), s.get("print_stats", {}), s.get("toolhead", {})

    # --- Klipper / print state
    if wh.get("state") != "ready":
        fail("Klipper is %s: %s" % (wh.get("state"), (wh.get("state_message") or "").strip()))
    else:
        ok("Klipper ready")
    pst = ps.get("state", "?")
    other_busy = [b for b in p.state().get("busy", []) if "print_stats" not in b and "heaters" not in b]
    for b in other_busy:
        fail("printer is busy: " + b)
    if pst in BUSY_STATES:
        fail("printer is %s - only ram a finished or cancelled print" % pst)
    elif pst == "error":
        warn("last print ended in an error (%s) - check the parts are complete" % ps.get("message", ""))
    else:
        ok("print state: %s" % pst)

    # --- macro installed and current
    if mname not in objs:
        fail("%s is not installed - Ramming tab > Install / update (hi_tool.py install-ram)" % RAM_MACRO)
        v = {}
    else:
        v = s.get(mname, {})
        cfg = p.configfile().get("config", {})
        gc = next((x.get("gcode", "") for k, x in cfg.items() if k.lower() == mname.lower()), "")
        if "pos_guess" not in gc.lower():
            fail("the printer has an older %s (no position-guess guard) - reinstall ramming.cfg" % RAM_MACRO)
        elif int(v.get("pos_guess", 0) or 0) == 1:
            fail("the toolhead position was SET BY HAND (Move-Z unlock or an unfinished Recover Z), not homed - "
                 "Klipper's X/Y/Z are guesses. Finish Recover Z (step 4 'set') first.")
        if "back_y" not in gc.lower() or "casing_slope" not in gc.lower() or "part_max_y" not in gc.lower():
            fail("the printer has an older %s (guessed casing size / no footprint support) - reinstall ramming.cfg"
                 % RAM_MACRO)
        else:
            ok("%s installed and current" % RAM_MACRO)
        local = a.cfg or default_ram_cfg()
        try:
            with open(local, "rb") as fh:
                loc = fh.read()
            if sha(p.get_config(RAM_REMOTE)) != sha(loc):
                warn("printer's %s differs from %s - Install / update if you edited it" % (RAM_REMOTE, local))
        except (OSError, ToolError):
            pass
    end_after = float(v.get("ram_end_after_center", 130.0))
    start_before = float(v.get("ram_start_before_center", 100.0))
    front = float(v.get("casing_front", CASING_FRONT))
    half_w = float(v.get("casing_half_w", CASING_HALF_W))
    min_top = (float(v.get("min_nozzle_z", MIN_NOZZLE_Z)) + float(v.get("casing_gap", CASING_GAP))
               + float(v.get("casing_slope", CASING_SLOPE)) + float(v.get("min_contact", MIN_CONTACT)))

    # --- position / homing
    xmin, ymin = (th.get("axis_minimum") or [-19, -7])[:2]
    xmax, ymax = (th.get("axis_maximum") or [285, 273])[:2]
    pos = th.get("position") or [0, 0, 0, 0]
    homed = (th.get("homed_axes") or "").lower()
    if homed == "xyz":
        ok("homed, toolhead at X%.1f Y%.1f Z%.1f" % tuple(pos[:3]))
        if pos[2] < top + 2:
            warn("nozzle (Z%.1f) is below the part top (Z%.1f) - the macro lifts straight up first, "
                 "make sure the toolhead isn't parked over a part" % (pos[2], top))
    elif pos[2] >= top + 10:
        if a.from_park:
            ok("not homed, parked at Z%.1f (clear of the %.1f mm part): will SET_KINEMATIC_POSITION + G28 X Y, never Z"
               % (pos[2], top))
            # z_ready/z_moved=1: stops _IF_HOME_Z re-zeroing Z (and lifting 15 mm) during G28 X Y after a Klipper restart
            plan["pre"] = ("SET_KINEMATIC_POSITION X=%.3f Y=%.3f Z=%.3f\nSET_GCODE_VARIABLE MACRO=xyz_ready VARIABLE=z_ready VALUE=1\nSET_GCODE_VARIABLE MACRO=xyz_ready VARIABLE=z_moved VALUE=1\nG28 X Y" % (pos[0], pos[1], pos[2]))
        else:
            fail("not homed. It looks parked (Z%.1f) - tick 'parked after END_PRINT' / --from-park. Never G28 Z with parts on the plate."
                 % pos[2])
    else:
        fail("not homed and Klipper thinks Z is %.1f - the position was lost (restart?). Use the Recover Z tab (hi_tool.py recover-z), or take the parts off by hand."
             % pos[2])

    # --- heaters
    ext, bed = s.get("extruder", {}), s.get("heater_bed", {})
    if ext.get("target", 0) > 0 or ext.get("temperature", 0) > 80:
        warn("hotend is %.0f C (target %.0f) - it will ooze onto the parts; TURN_OFF_HEATERS first"
             % (ext.get("temperature", 0), ext.get("target", 0)))
    else:
        ok("hotend off (%.0f C)" % ext.get("temperature", 0))
    bt = bed.get("temperature", 0)
    if bed.get("target", 0) > 0:
        warn("bed heater is on (target %.0f C) - parts won't release; TURN_OFF_HEATERS" % bed.get("target", 0))
    elif bt > 40 and a.wait < 300:
        warn("bed still %.0f C - PETG lets go better cold; set Wait to 600 or come back later" % bt)
    else:
        ok("bed %.0f C" % bt)

    # --- the part
    if top < min_top:
        fail("part is %.2f mm tall - the casing's flat face starts too high to push it (min %.0f mm); "
             "it would only wedge it with the sloped edge" % (top, min_top))
    else:
        ok("part height %.2f mm" % top)
    if g.get("bbox"):
        bx0, by0, bx1, by1 = g["bbox"]
        if bx0 < xmin or bx1 > xmax or by0 < ymin or by1 > ymax:
            warn("footprint X %.0f..%.0f Y %.0f..%.0f is outside the axis limits - wrong file/printer?" % (bx0, bx1, by0, by1))
    else:
        warn("no gcode file - can't check the descent point against the real part outlines")

    # --- lanes and where the casing comes down
    lanes = _lane_xs(cx, a.lanes, a.spacing, xmin, xmax)
    plan["lanes"] = lanes
    if len(lanes) > 1 and a.spacing > 2 * half_w:
        warn("lane spacing %.0f mm is wider than the casing (%.0f mm) - parts between lanes can be missed"
             % (a.spacing, 2 * half_w))
    need = None
    for x in lanes:
        top_y = _max_y_in_strip(g, x - half_w - 2.0, x + half_w + 2.0)
        if top_y is not None:
            n = top_y + front + 3.0
            need = n if need is None else max(need, n)
            log("         lane X%.1f: parts reach back to Y%.1f -> casing must come down at Y>=%.1f" % (x, top_y, n))
    default_back = min(cy + end_after, ymax)
    if need is None:
        plan["back_y"] = default_back
        warn("no part found under any lane - check centre / lanes")
    elif need > ymax:
        fail("the casing can't get behind the parts: needs Y%.1f, Y max is %.1f - it would come down on a part. "
             "Use fewer/closer lanes or take these off by hand." % (need, ymax))
    else:
        plan["back_y"] = round(max(default_back, need), 2)
        ok("descent at Y%.1f is behind every part (front face %.0f mm ahead of the nozzle)" % (plan["back_y"], front))

    # --- does the push clear the bed?
    if a.push_to_edge:
        ok("pushes to the Y minimum (%.1f) - parts go off the front edge" % ymin)
    else:
        stop = max(cy - start_before, ymin)
        face = stop - front
        if face > -10.0:
            warn("push stops with the front face at Y%.1f - parts may stay on the plate; push to the front edge"
                 % face)
        else:
            ok("push stops with the front face at Y%.1f, past the plate's front edge" % face)
    if g.get("calls_ram"):
        warn("this gcode already rams at the end of the print - it may have run already")

    log("  " + ("NOT READY - %d problem(s)" % len(fails) if fails else
                "READY%s" % (" with %d warning(s)" % len(warns) if warns else "")))
    return not fails, plan


def ram_script(a, g, plan):
    parts = ["%s CENTER_X=%.2f CENTER_Y=%.2f TOP_Z=%.2f" % (RAM_MACRO, g["center_x"], g["center_y"], g["top_z"]),
             "WAIT=%d" % a.wait, "LANES=%d" % a.lanes, "SPACING=%g" % a.spacing,
             "PUSH_TO_EDGE=%d" % (1 if a.push_to_edge else 0)]
    if plan.get("back_y") is not None:
        parts.append("BACK_Y=%.2f" % plan["back_y"])
    if a.ram_speed:
        parts.append("RAM_SPEED=%d" % a.ram_speed)
    return " ".join(parts)


def cmd_ram_check(p, a):
    g = _ram_inputs(a)
    ready, plan = ram_check(p, a, g)
    log("  ram command would be: " + ram_script(a, g, plan))
    return ready


def cmd_ram(p, a):
    g = _ram_inputs(a)
    ready, plan = ram_check(p, a, g)
    if not ready and not a.skip_check:
        raise ToolError("not ready - fix the [FAIL] lines above (or --skip-check if you are sure)")
    script = ram_script(a, g, plan)
    if plan["pre"]:
        log("  homing step: " + plan["pre"].replace("\n", " | "))
    log("  ram command: " + script)
    if not a.apply:
        log("  DRY RUN - nothing moved. Re-run with --apply (bin in front, hand near e-stop).")
        return True
    if plan["pre"]:
        p.gcode(plan["pre"], timeout=a.home_timeout)
        st = p.state()
        if st["homed"].lower() != "xyz":
            raise ToolError("still not homed after G28 X Y (homed=[%s]) - not ramming" % st["homed"])
        log("  homed X/Y, Z kept at %.2f" % st["position"][2])
    log("  ramming... (wait %ds first)" % a.wait)
    try:
        p.gcode(script, timeout=a.wait + 1200)
    except ToolError as e:
        if "timed out" in str(e).lower():
            log("  request timed out but the macro may still be running - watch the printer", "WARN")
        raise
    log("  ram finished. Motors are still on - send M84 when the plate is clear.")
    return True


# --------------------------------------------------------------------------- recover-z (after a restart with parts on the plate)

def _rect_hits_part(g, x, y, hw, d_front, d_back):
    """Does the casing footprint (nozzle at x,y: x+-hw, y-d_front .. y+d_back) touch any part?"""
    for poly in g.get("polys") or []:
        for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
            for k in range(41):
                t = k / 40.0
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                if x - hw <= px <= x + hw and y - d_front <= py <= y + d_back:
                    return True
        for cx, cy in ((x, y), (x - hw, y - d_front), (x + hw, y + d_back), (x - hw, y + d_back), (x + hw, y - d_front)):
            inside = False
            for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
                if (ay > cy) != (by > cy) and cx < ax + (bx - ax) * (cy - ay) / (by - ay):
                    inside = not inside
            if inside:
                return True
    if not g.get("polys") and g.get("bbox"):
        bx0, by0, bx1, by1 = g["bbox"]
        if not (x + hw < bx0 or x - hw > bx1 or y + d_back < by0 or y - d_front > by1):
            return True
    return False


def clear_spot(g, casing_depth=None, bed=(0.0, 0.0, 260.0, 260.0)):
    """A bed position where the whole casing (measured CASING_* + margin) is clear of every part.
    casing_depth is ignored (kept so old callers still work).
    Prefers the four corners (front-left first) so you can see the nozzle for the paper test."""
    hw, d_front, d_back = CASING_HALF_W + 2.0, CASING_FRONT + 3.0, CASING_BACK + 3.0
    x0, y0, x1, y1 = bed[0] + 10, bed[1] + 10, bed[2] - 10, bed[3] - 10
    prefs = [(20, 20), (x1 - 10, 20), (20, y1 - 10), (x1 - 10, y1 - 10)]
    for x, y in prefs:
        if not _rect_hits_part(g, x, y, hw, d_front, d_back):
            return float(x), float(y)
    for y in range(int(y0), int(y1) + 1, 5):
        for x in range(int(x0), int(x1) + 1, 5):
            if not _rect_hits_part(g, x, y, hw, d_front, d_back):
                return float(x), float(y)
    return None


def _set_pos_guess(p, value):
    """Tell REMOVE_PART_DYNAMIC whether the position is a hand-set guess (1) or real (0). No-op if not installed."""
    try:
        if "gcode_macro %s" % RAM_MACRO in p.req("GET", "/printer/objects/list").get("objects", []):
            p.gcode("SET_GCODE_VARIABLE MACRO=%s VARIABLE=pos_guess VALUE=%d" % (RAM_MACRO, value), timeout=20)
    except ToolError as e:
        log("  could not set the position-guess flag: %s" % e, "WARN")


def cmd_recover_z(p, a):
    """Re-find Z without G28 Z (which would come down on the parts) - paper test at a clear spot.
    Steps: home-xy -> (measure the nozzle height) goto --height H -> jog --dz ... -> set."""
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("Klipper is not ready (%s)" % st["message"].strip())
    homed = st["homed"].lower()
    pos = st["position"] or [0, 0, 0, 0]
    step = a.step

    if step == "home-xy":
        if homed == "xyz":
            log("  already homed (X%.1f Y%.1f Z%.1f). If Z is still right you don't need this; "
                "otherwise carry on with goto." % tuple(pos[:3]))
            script = "G28 X Y"
        else:
            script = "SET_KINEMATIC_POSITION X=%.3f Y=%.3f Z=150\nG28 X Y" % (a.park_x, a.park_y)
            log("  assuming the toolhead is still where END_PRINT parked it (X%.0f Y%.0f) and nobody moved it"
                % (a.park_x, a.park_y))
        log("  sending: " + script.replace("\n", " | "))
        if not a.apply:
            log("  DRY RUN - add --apply")
            return True
        p.gcode(script, timeout=a.home_timeout)
        _set_pos_guess(p, 1)
        log("  X/Y homed. Klipper's Z is NOT trustworthy now (the Hi's homing macro resets it). Ramming is blocked until step 'set'.")
        log("  NEXT: measure the nozzle tip height above the bed with a ruler, then: recover-z --step goto --height H")
        return True

    if homed != "xyz":
        raise ToolError("run --step home-xy first")

    if step == "goto":
        if a.height is None:
            raise ToolError("--height H (measured nozzle tip height above the bed, mm) is required")
        if a.gcode_file:
            g = ram_params_from_gcode(a.gcode_file)
        else:
            g = {"polys": [], "bbox": None, "top_z": None}
        top = a.top_z if a.top_z is not None else g.get("top_z")
        if a.spot:
            sx, sy = (float(v) for v in a.spot.split(","))
        else:
            if not g.get("polys") and not g.get("bbox"):
                raise ToolError("need --gcode FILE (to find a spot clear of the parts) or --spot X,Y")
            spot = clear_spot(g, a.casing_depth)
            if spot is None:
                raise ToolError("no spot on the bed is clear of the parts for the whole casing - do this by hand")
            sx, sy = spot
        if top is None:
            raise ToolError("need --gcode FILE or --top-z to know how tall the parts are")
        believed = a.height + 5.0
        lines = ["SET_KINEMATIC_POSITION Z=%.3f" % believed, "G90"]
        if a.height < top + 10:
            lift = top + 15 - a.height
            lines += ["G91", "G1 Z%.2f F600" % lift, "G90"]
            log("  nozzle is only %.1f mm up and the parts are %.1f mm - lifting %.1f mm before travelling" % (a.height, top, lift))
        lines += ["G1 X%.2f Y%.2f F6000" % (sx, sy), "G1 Z10 F600"]
        log("  Klipper will be told Z=%.1f (your %.1f + 5 mm safety), so every move stops ~5 mm above where it thinks" % (believed, a.height))
        log("  clear spot for the paper test: X%.0f Y%.0f (whole casing clear of every part)" % (sx, sy))
        log("  sending: " + " | ".join(lines))
        if not a.apply:
            log("  DRY RUN - add --apply")
            return True
        _set_pos_guess(p, 1)
        p.gcode("\n".join(lines), timeout=120)
        log("  nozzle should now be about 5 mm above the bed at X%.0f Y%.0f." % (sx, sy))
        log("  NEXT: put paper under it and jog down: recover-z --step jog --dz -1 (then -0.1 near the bed)")
        return True

    if step == "jog":
        if a.dz is None:
            raise ToolError("--dz is required (e.g. -1, -0.1, 0.1, 1)")
        if abs(a.dz) > 5:
            raise ToolError("jogs are limited to 5 mm")
        new_z = pos[2] + a.dz
        zmin = (p.query("toolhead").get("toolhead", {}).get("axis_minimum") or [0, 0, -5])[2]
        if new_z < zmin + 0.3:
            raise ToolError("Klipper thinks Z would be %.2f, past its lower limit %.1f - your measured height was "
                            "probably too low. Raise with +1 and re-run goto with a bigger --height." % (new_z, zmin))
        script = "G91\nG1 Z%.3f F300\nG90" % a.dz
        if not a.apply:
            log("  DRY RUN - would jog Z %+.2f (Klipper Z %.2f -> %.2f)" % (a.dz, pos[2], new_z))
            return True
        p.gcode(script, timeout=60)
        log("  jogged Z %+.2f  (Klipper Z now %.2f - not the real height yet)" % (a.dz, new_z))
        return True

    if step == "set":
        script = "SET_KINEMATIC_POSITION Z=%.3f\nG1 Z40 F600" % a.paper
        log("  paper drags -> nozzle is at Z%.2f. Setting it and lifting to Z40." % a.paper)
        if not a.apply:
            log("  DRY RUN - add --apply")
            return True
        p.gcode(script, timeout=60)
        _set_pos_guess(p, 0)
        log("  Z recovered. You can ram now - untick 'parked after END_PRINT' (it is properly homed).")
        return True
    raise ToolError("unknown step %s" % step)


# --------------------------------------------------------------------------- jog-z (move Z without homing)

def cmd_jog_z(p, a):
    """Move Z without homing it - e.g. to lower the toolhead and look at a part G28 Z would crash into.
    Both Z motors move together through a normal G1 (FORCE_MOVE would move only one of the Hi's two Z
    steppers and rack the gantry). --unlock Z tells Klipper the toolhead is at Z (a guess is fine: it only
    sets how far you may jog), then --dz jogs in small steps while you watch."""
    p.connect()
    st = p.assert_idle(a.force)
    if st["klippy"] != "ready":
        raise ToolError("Klipper is not ready (%s)" % st["message"].strip())
    th = p.query("toolhead").get("toolhead", {})
    zmin = (th.get("axis_minimum") or [0, 0, -5])[2]
    zmax = (th.get("axis_maximum") or [0, 0, 300])[2]
    pos = th.get("position") or [0, 0, 0, 0]
    homed = (th.get("homed_axes") or "").lower()
    if a.unlock is not None:
        z = min(max(a.unlock, zmin + 1), zmax)
        script = "SET_KINEMATIC_POSITION Z=%.3f" % z
        log("  telling Klipper the toolhead is at Z%.1f (nothing moves). You can now jog down about %.0f mm." % (z, z - zmin))
        if "x" not in homed or "y" not in homed:
            log("  X/Y were not homed - only jog Z from here; don't send X/Y moves until you home X/Y", "WARN")
        if not a.apply:
            log("  DRY RUN - add --apply")
            return True
        p.gcode(script, timeout=30)
        _set_pos_guess(p, 1)
        log("  unlocked. Klipper's position is a GUESS now - watch the nozzle, not the number.")
        log("  Ramming is blocked until you lock again (motors off) and do Recover Z.")
        return True
    if a.lock:
        if not a.apply:
            log("  DRY RUN - would send M84 (motors off, nothing homed)")
            return True
        p.gcode("M84", timeout=30)
        log("  locked: motors off, nothing is homed now. Klipper refuses moves until you home or recover.")
        return True
    if a.dz is None:
        raise ToolError("give --unlock Z, --dz MM or --lock")
    if "z" not in homed:
        raise ToolError("Z is locked (not homed) - unlock it first with --unlock (e.g. 300 when the head is near the top)")
    if abs(a.dz) > 20:
        raise ToolError("jogs are limited to 20 mm per step")
    new_z = pos[2] + a.dz
    if new_z < zmin + 0.2:
        raise ToolError("Klipper's Z would be %.1f, past its lower limit %.1f. If the nozzle is still clearly above "
                        "everything, unlock again with a bigger number." % (new_z, zmin))
    if new_z > zmax:
        raise ToolError("Klipper's Z would be %.1f, past its upper limit %.1f" % (new_z, zmax))
    if not a.apply:
        log("  DRY RUN - would move Z %+.1f mm" % a.dz)
        return True
    p.gcode("G91\nG1 Z%.3f F%d\nG90" % (a.dz, a.speed), timeout=120)
    log("  moved Z %+.1f mm (Klipper Z %.1f - a guess unless Z was homed)" % (a.dz, new_z))
    return True


# --------------------------------------------------------------------------- pressure advance
# The Hi runs normal Klipper pressure advance ([extruder] pressure_advance, SET_PRESSURE_ADVANCE) with two Creality
# extras: ENABLE_PRESSURE_ADVANCE VALUE=0/1 locks/unlocks SET_PRESSURE_ADVANCE (a locked printer silently ignores it),
# and silent mode (Qmode macro) forces 0.05 during a print. "Motion Advance" (firmware V1.1.0.65+, screen
# Settings > Print settings) is Creality's automatic PA calibration at print start, driven by Creality Print's
# "Print calibration" - a slicer that doesn't support it (Orca etc.) gets the printer's normal value instead.
PA_MAX = 0.3
PA_SET_RE = re.compile(r"^\s*(SET_PRESSURE_ADVANCE\b.*|M900\b.*|ENABLE_PRESSURE_ADVANCE\b.*)$", re.I)
PA_SLICER_RE = re.compile(r"^;\s*(enable_pressure_advance|pressure_advance|adaptive_pressure_advance|"
                          r"print_calibration|enable_print_calibration|motion_advance\w*)\s*=\s*(.*)$", re.I)
PA_LINE_RE = re.compile(r"^(\s*pressure_advance\s*[:=]\s*)([\d.]+)(.*)$", re.M)
PA_SMOOTH_RE = re.compile(r"^(\s*pressure_advance_smooth_time\s*[:=]\s*)([\d.]+)(.*)$", re.M)
PA_START_GCODE = """M220 S100
M221 S100
G90
M83
M140 S{bed}
M104 S120            ; Hi probes with a warm (not hot) nozzle
M190 S{bed}
G28
M109 S{nozzle}
{mesh}
ENABLE_PRESSURE_ADVANCE VALUE=1
SET_VELOCITY_LIMIT ACCEL={accel} ACCEL_TO_DECEL={accel}
M106 S0
G92 E0
"""
PA_END_GCODE = """G1 E-2 F2100
G91
G1 Z10 F600
G90
G1 X5 Y240 F6000     ; bring the bed forward to look at it
M104 S0
M140 S0
M106 S0
SET_PRESSURE_ADVANCE ADVANCE={k_restore}
M84 X Y E
"""


def _pa_state(p):
    s = p.query("extruder", "configfile", "print_stats", "gcode_macro Qmode")
    ext = s.get("extruder", {})
    cfg = (s.get("configfile", {}).get("settings", {}) or {}).get("extruder", {})
    return {"k": ext.get("pressure_advance"), "smooth": ext.get("smooth_time"),
            "k_cfg": cfg.get("pressure_advance"), "smooth_cfg": cfg.get("pressure_advance_smooth_time"),
            "lock_cfg": cfg.get("pressure_advance_enabled", True),
            "print": s.get("print_stats", {}).get("state", "?"),
            "qmode": (s.get("gcode_macro Qmode") or {}).get("flag")}


def _pa_lock(p):
    """True = SET_PRESSURE_ADVANCE works, False = locked by ENABLE_PRESSURE_ADVANCE VALUE=0, None = unknown.
    Sending SET_PRESSURE_ADVANCE with no values re-applies the current values (changes nothing)."""
    ok, err, msgs = _gcode_capture(p, "SET_PRESSURE_ADVANCE", timeout=15)
    txt = " ".join(msgs).lower()
    if "is disabled" in txt:
        return False
    if "is enabled" in txt or "pressure_advance:" in txt:
        return True
    return None


def pa_scan_gcode(path):
    """What a sliced file does with pressure advance. Returns dict."""
    sets, slicer, calib = [], {}, []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, ln in enumerate(fh, 1):
            if ln.startswith(";"):
                m = PA_SLICER_RE.match(ln.strip())
                if m:
                    slicer[m.group(1).lower()] = m.group(2).strip()[:80]
                continue
            m = PA_SET_RE.match(ln)
            if m:
                sets.append((n, m.group(1).split(";")[0].strip()))
            elif re.match(r"^\s*(PRINT_CALIBRATION|CX_PRINT\w*|\w*PA_CALIB\w*|\w*MOTION_ADVANCE\w*)\b", ln, re.I):
                calib.append((n, ln.strip()[:80]))
    return {"sets": sets, "slicer": slicer, "calib": calib}


def _pa_report_gcode(path, st):
    g = pa_scan_gcode(path)
    log("  file: %s" % os.path.basename(path))
    for k, v in sorted(g["slicer"].items()):
        log("    slicer setting  %s = %s" % (k, v))
    vals = sorted({c for _, c in g["sets"]})
    if g["sets"]:
        log("    the file sends %d pressure-advance command(s): %s" % (len(g["sets"]), "; ".join(vals[:6])
            + (" ..." if len(vals) > 6 else "")))
        log("    first at line %d - before that the printer's own value (%s) is used" % (g["sets"][0][0], st.get("k")))
        if st.get("lock") is False and any("SET_PRESSURE_ADVANCE" in c.upper() for c in vals) and \
                not any("ENABLE_PRESSURE_ADVANCE VALUE=1" in c.upper() for c in vals):
            log("    the printer is LOCKED - these commands will be ignored", "WARN")
    else:
        log("    the file sets no pressure advance - it prints with the printer's value (%s)" % st.get("k"))
    for n, c in g["calib"][:5]:
        log("    calibration hook at line %d: %s (Creality Print / Motion Advance)" % (n, c))
    return g


def cmd_pa(p, a):
    act = a.action
    if act == "tower":   # local file only - no printer needed
        return _pa_tower(a)
    p.connect()
    if act == "test":
        return _pa_test(p, a)
    if act == "firmware":
        return _pa_firmware(p, a)
    if act == "watch":
        return _pa_watch(p, a)
    if act == "history":
        return _pa_history(p, a)
    if act == "preflight":
        return _pa_preflight(p, a)
    if act == "verify":
        return _pa_verify(p, a)
    st = _pa_state(p)

    if act == "status":
        st["lock"] = _pa_lock(p) if st["print"] not in BUSY_STATES or a.force else None
        log("  live pressure advance:  %s   smooth_time %s" % (st["k"], st["smooth"]))
        log("  saved default (cfg):    %s   smooth_time %s" % (st["k_cfg"], st["smooth_cfg"]))
        if st["k"] is not None and st["k_cfg"] is not None and abs(st["k"] - st["k_cfg"]) > 1e-6:
            log("live value differs from the saved one (changed by a print, the slicer or 'pa set')", "WARN")
        if st["lock"] is True:
            log("SET_PRESSURE_ADVANCE is unlocked (slicer / M900 values are applied)", "OK")
        elif st["lock"] is False:
            log("SET_PRESSURE_ADVANCE is LOCKED (ENABLE_PRESSURE_ADVANCE VALUE=0) - slicer values are ignored. "
                "'pa set' unlocks it.", "WARN")
        else:
            log("  lock state not checked (printing) - END_PRINT / CANCEL_PRINT always unlock it")
        if st["qmode"]:
            log("silent mode is ON - Creality forces pressure advance 0.05 while it is on", "WARN")
        log("  print: %s" % st["print"])
        if a.gcode_file:
            _pa_report_gcode(a.gcode_file, st)
        return True

    if act == "set":
        if a.k is None and a.smooth is None:
            raise ToolError("pa set needs --k (and/or --smooth)")
        k = st["k"] if a.k is None else a.k
        sm = st["smooth"] if a.smooth is None else a.smooth
        if not (0 <= k <= PA_MAX) or not (0 < sm <= 0.2):
            raise ToolError("pressure advance must be 0..%.1f and smooth_time 0..0.2 (got %s / %s)" % (PA_MAX, k, sm))
        log("  %s -> pressure advance %.4f, smooth_time %.3f (live, until the next restart)" % (st["k"], k, sm))
        if st["print"] in BUSY_STATES:
            log("  printing: takes effect on the next moves (a SET_PRESSURE_ADVANCE in the file can override it)")
        if not a.apply:
            log("  DRY RUN - add --apply")
            return True
        p.gcode("ENABLE_PRESSURE_ADVANCE VALUE=1\nSET_PRESSURE_ADVANCE ADVANCE=%.4f SMOOTH_TIME=%.3f" % (k, sm), timeout=20)
        now = _pa_state(p)
        if abs((now["k"] or 0) - k) > 1e-4:
            raise ToolError("printer reports %s after setting %.4f" % (now["k"], k))
        log("pressure advance is now %.4f (smooth %.3f). 'pa save' makes it the default." % (now["k"], now["smooth"]), "OK")
        _pa_changelog(a, p, "set (live)", st["k"], now["k"], now["smooth"])
        return True

    if act == "save":
        k = a.k if a.k is not None else st["k"]
        if k is None or not (0 <= k <= PA_MAX):
            raise ToolError("give --k 0..%.1f (or 'pa set' it live first)" % PA_MAX)
        if a.smooth is not None and not (0 < a.smooth <= 0.2):
            raise ToolError("--smooth must be 0..0.2")
        p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
        path = "printer.cfg"
        old = p.get_config(path).decode("utf-8")
        body, sep, auto = old.partition("#*# <---------------------- SAVE_CONFIG")
        sec = re.search(r"^\[extruder\]\s*$(.*?)(?=^\[|\Z)", body, re.M | re.S)
        if not sec:
            raise ToolError("no [extruder] section in printer.cfg")
        block = sec.group(1)
        new_block = block
        if PA_LINE_RE.search(block):
            new_block = PA_LINE_RE.sub(lambda m: "%s%.4f%s" % (m.group(1), k, m.group(3)), new_block, count=1)
        else:
            new_block = "\npressure_advance: %.4f" % k + new_block
        if a.smooth is not None:
            if PA_SMOOTH_RE.search(new_block):
                new_block = PA_SMOOTH_RE.sub(lambda m: "%s%.3f%s" % (m.group(1), a.smooth, m.group(3)), new_block, count=1)
            else:
                new_block = PA_LINE_RE.sub(lambda m: m.group(0) + "\npressure_advance_smooth_time: %.3f" % a.smooth,
                                           new_block, count=1)
        if re.search(r"^#\*#\s*pressure_advance", auto, re.M):
            raise ToolError("printer.cfg's SAVE_CONFIG block also sets pressure_advance - edit that by hand")
        new = body[:sec.start(1)] + new_block + body[sec.end(1):] + sep + auto
        if new == old:
            log("printer.cfg already has pressure_advance %.4f - nothing to do" % k, "OK")
            return True
        for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), "a/" + path, "b/" + path, lineterm="", n=1):
            log("    " + ln)
        if not a.apply:
            log("  DRY RUN - nothing changed. --apply uploads it and RESTARTs Klipper.")
            return True
        bdir, originals = backup(p, a.backup_dir, "before-pa-save")
        if sha(originals.get(path, b"")) != sha(old.encode("utf-8")):
            raise ToolError("printer.cfg changed on the printer while we were working - aborting")
        try:
            p.upload_config(path, new.encode("utf-8"))
            log("  uploaded + verified %s" % path)
            ok, msg = p.restart()
        except ToolError as e:
            ok, msg = False, str(e)
        if ok:
            time.sleep(a.motor_wait)
            now = _pa_state(p)
            if now["k_cfg"] is None or abs(now["k_cfg"] - k) > 1e-4:
                ok, msg = False, "Klipper loaded pressure_advance %s, expected %.4f" % (now["k_cfg"], k)
        if not ok:
            log("  problem: %s - rolling back printer.cfg from %s" % (msg.strip(), bdir), "ERROR")
            try:
                p.upload_config(path, originals[path])
            except ToolError as e:
                log("  rollback upload failed: %s" % e, "ERROR")
            ok2, msg2 = p.restart(check=False)
            log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
            return False
        log("default pressure advance is now %.4f (backup: %s)" % (k, bdir), "OK")
        _pa_changelog(a, p, "save (printer.cfg)", st["k_cfg"], k, a.smooth if a.smooth is not None else st["smooth_cfg"],
                      "backup " + os.path.basename(bdir))
        log("  slicers that set their own value (Orca 'enable pressure advance', Creality Print / Motion Advance) still override it")
        return True
    raise ToolError("unknown pa action %s" % act)


# ---- pressure advance: logs, Orca tower, preflight, watch, fleet
PA_STOP = threading.Event()   # set by the GUI 'Stop' button to end 'pa watch'
PA_K_RE = re.compile(r"^\s*(?:SET_PRESSURE_ADVANCE\b[^;]*?\bADVANCE\s*=\s*([\d.]+)|M900\b[^;]*?\bK\s*([\d.]+))", re.I)
ZCOMMENT_RE = re.compile(r"^;\s*Z\s*:\s*([\d.]+)")
GZ_RE = re.compile(r"^G[0-3]\b[^;]*?\bZ\s*(-?[\d.]+)", re.I)
GEXT_RE = re.compile(r"^G[123]\b(?=[^;]*\b[XY]\s*-?[\d.])[^;]*?\bE\s*([\d.]+)", re.I)
PA_LOCK_IN_FILE_RE = re.compile(r"^\s*ENABLE_PRESSURE_ADVANCE\b[^;]*VALUE\s*=\s*0", re.I)
PA_QMODE_IN_FILE_RE = re.compile(r"^\s*Qmode\b", re.I)


def _pa_logdir(a):
    d = os.path.join(getattr(a, "backup_dir", "hi_backups"), "pa_logs")
    os.makedirs(d, exist_ok=True)
    return d


def _fk(k):
    return "-" if k is None else "%.4f" % k


def _pa_changelog(a, p, action, old, new, smooth=None, note=""):
    """Every change this tool makes to pressure advance goes into hi_backups/pa_logs/pa_changes.csv."""
    try:
        path = os.path.join(_pa_logdir(a), "pa_changes.csv")
        fresh = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if fresh:
                w.writerow(["time", "printer", "action", "old_k", "new_k", "smooth_time", "note"])
            w.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p.name, action,
                        "" if old is None else "%.4f" % old, "" if new is None else "%.4f" % new,
                        "" if smooth is None else "%.3f" % smooth, note])
    except Exception as e:
        log("  could not write pa_changes.csv: %s" % e, "WARN")


def pa_tower_scan(path):
    """Where a sliced file changes pressure advance, by height. Returns dict with
    sets [(z, k, line)] (z None = before/after any printing), bands [(k, z_from, z_to)], start, step, mm_per_step."""
    z, sets, pending = 0.0, [], []
    lock_lines, qmode_lines, maxz = [], [], 0.0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, ln in enumerate(fh, 1):
            s = ln.strip()
            if not s:
                continue
            if s[0] == ";":
                m = ZCOMMENT_RE.match(s)
                if m:
                    z = float(m.group(1))
                continue
            m = PA_K_RE.match(s)
            if m:
                rec = [None, float(m.group(1) or m.group(2)), n]
                sets.append(rec)
                pending.append(rec)
                continue
            if PA_LOCK_IN_FILE_RE.match(s):
                lock_lines.append(n)
            elif PA_QMODE_IN_FILE_RE.match(s):
                qmode_lines.append(n)
            m = GZ_RE.match(s)
            if m:
                z = float(m.group(1))
            if pending:
                m = GEXT_RE.match(s)
                if m and float(m.group(1)) > 0:
                    for rec in pending:
                        rec[0] = z
                    pending = []
                    maxz = max(maxz, z)
            elif GEXT_RE.match(s):
                maxz = max(maxz, z)
    placed = [(zz, k, n) for zz, k, n in sets if zz is not None]
    bands = []
    for i, (zz, k, n) in enumerate(placed):
        if bands and abs(bands[-1][0] - k) < 1e-9:
            continue
        if bands:
            bands[-1][2] = zz
        bands.append([k, zz, None])
    if bands:
        bands[-1][2] = maxz
    out = {"sets": [tuple(x) for x in sets], "bands": [tuple(b) for b in bands], "start": None, "step": None,
           "mm_per_step": None, "lock_lines": lock_lines, "qmode_lines": qmode_lines, "max_z": maxz}
    if len(bands) >= 4:
        dk = sorted(bands[i + 1][0] - bands[i][0] for i in range(len(bands) - 1))
        dz = sorted(bands[i + 1][1] - bands[i][1] for i in range(len(bands) - 1))
        step, mm = dk[len(dk) // 2], dz[len(dz) // 2]
        if step > 0:
            out.update(start=bands[0][0], step=step, mm_per_step=mm)
    return out


def pa_k_at(scan, h):
    """K the file was printing with at height h (mm above the bed)."""
    k = None
    for kk, z0, z1 in scan["bands"]:
        if z0 is not None and z0 <= h + 1e-6:
            k = kk
    return k


def _pa_tower(a):
    if not a.gcode_file:
        if a.height is None:
            raise ToolError("pa tower needs --gcode FILE (the sliced Orca tower), or --height with --start/--step")
        k = a.start + int(a.height) * a.step
        log("  Orca PA tower: K = start + whole mm of height x step = %.4f + %d x %.4f = %.4f"
            % (a.start, int(a.height), a.step, k), "OK")
        return True
    sc = pa_tower_scan(a.gcode_file)
    log("  file: %s   (printed height %.1f mm)" % (os.path.basename(a.gcode_file), sc["max_z"]))
    g = pa_scan_gcode(a.gcode_file)
    for k, v in sorted(g["slicer"].items()):
        log("    slicer setting  %s = %s" % (k, v))
    ok = True
    if sc["lock_lines"]:
        log("the file LOCKS pressure advance (ENABLE_PRESSURE_ADVANCE VALUE=0, line %s) - every K change after it is "
            "ignored" % sc["lock_lines"][0], "FAIL")
        ok = False
    if sc["qmode_lines"]:
        log("the file switches silent mode on (line %s) - that forces K 0.05" % sc["qmode_lines"][0], "WARN")
    for n, c in g["calib"][:3]:
        log("calibration hook at line %d: %s - Motion Advance may run its own PA calibration" % (n, c), "WARN")
    if not sc["bands"]:
        log("this file never changes pressure advance - not a PA tower (prints with the printer's value)", "WARN")
        return False
    if len(sc["bands"]) < 4:
        for k, z0, z1 in sc["bands"]:
            log("    from Z %.2f: K %.4f" % (z0, k))
        log("only %d K value(s) - a normal print with a fixed K, not a tower" % len(sc["bands"]), "WARN")
        return ok
    log("  %d K steps: K %.4f at the bottom .. %.4f at the top, +%.4f every %.2f mm"
        % (len(sc["bands"]), sc["bands"][0][0], sc["bands"][-1][0], sc["step"], sc["mm_per_step"]))
    rows = ["Z %5.1f-%5.1f  K %.4f" % (z0, z1 if z1 is not None else z0, k) for k, z0, z1 in sc["bands"]]
    for i in range(0, len(rows), 3):
        log("    " + "     ".join(rows[i:i + 3]))
    if a.height is not None:
        k = pa_k_at(sc, a.height)
        if k is None:
            log("height %.1f mm is below the first K change" % a.height, "WARN")
        else:
            log("best height %.1f mm -> K %.4f  ('pa set --k %.4f' to try it, then put it in Orca's filament)"
                % (a.height, k, k), "OK")
    log("  measure from the bed to the best spot (sharp corners, no bulge, no gap after the corner)")
    if ok:
        log("tower file looks right - run 'pa preflight' on the printer before you start it", "OK")
    return ok


def _pa_preflight(p, a):
    """Is the printer in a state where a PA calibration print will actually change K?"""
    st = _pa_state(p)
    bad, warn = [], []
    busy = st["print"] in BUSY_STATES
    lock = None if busy else _pa_lock(p)
    log("  live K %s   saved K %s   smooth %s   print: %s" % (_fk(st["k"]), _fk(st["k_cfg"]),
        "-" if st["smooth"] is None else "%.3f" % st["smooth"], st["print"]))
    if busy:
        bad.append("printer is %s" % st["print"])
    if lock is False:
        bad.append("SET_PRESSURE_ADVANCE is LOCKED - every K the slicer/tower sends would be ignored")
    elif lock is True:
        log("SET_PRESSURE_ADVANCE unlocked - the tower's K changes will be applied", "OK")
    elif not busy:
        warn.append("could not tell whether SET_PRESSURE_ADVANCE is locked")
    if st["qmode"]:
        bad.append("silent mode is ON - Creality forces K 0.05 while it is on")
    else:
        log("silent mode off", "OK")
    if st["k"] is not None and st["k_cfg"] is not None and abs(st["k"] - st["k_cfg"]) > 1e-6:
        warn.append("live K %.4f differs from the saved %.4f (a print or 'pa set' changed it)" % (st["k"], st["k_cfg"]))
    if a.gcode_file:
        sc = pa_tower_scan(a.gcode_file)
        if sc["lock_lines"]:
            bad.append("the file locks pressure advance at line %s" % sc["lock_lines"][0])
        if sc["qmode_lines"]:
            bad.append("the file turns silent mode on at line %s" % sc["qmode_lines"][0])
        if len(sc["bands"]) >= 4:
            log("file is a PA tower: K %.4f .. %.4f, +%.4f every %.2f mm" % (sc["bands"][0][0], sc["bands"][-1][0],
                sc["step"], sc["mm_per_step"]), "OK")
        elif sc["bands"]:
            warn.append("the file sets a fixed K (%s) - fine for a normal print, not a calibration"
                        % ", ".join("%.4f" % b[0] for b in sc["bands"][:3]))
        else:
            warn.append("the file sets no K - it prints with the printer's %s" % _fk(st["k"]))
    fixable = (lock is False) or st["qmode"]
    if fixable and a.apply and not busy:
        script = []
        if st["qmode"]:
            script.append("Qmode_exit")
        script.append("ENABLE_PRESSURE_ADVANCE VALUE=1")
        log("  sending: %s" % " / ".join(script))
        p.gcode("\n".join(script), timeout=30)
        time.sleep(0.5)
        st2 = _pa_state(p)
        lock2 = _pa_lock(p)
        bad = [b for b in bad if not (("LOCKED" in b and lock2) or ("silent mode is ON" in b and not st2["qmode"]))]
        log("  after fix: lock %s, silent mode %s" % ("unlocked" if lock2 else "STILL LOCKED",
            "ON" if st2["qmode"] else "off"), "OK" if lock2 and not st2["qmode"] else "WARN")
    for w in warn:
        log(w, "WARN")
    for b in bad:
        log(b, "FAIL")
    if fixable and not a.apply and not busy:
        log("  'pa preflight --apply' unlocks pressure advance / leaves silent mode")
    if bad:
        log("NOT READY for a pressure-advance calibration print")
        return False
    log("READY for a pressure-advance calibration print" + (" (warnings)" if warn else ""))
    log("  tip: start 'pa watch' when the print starts - it logs the K the printer really uses at every height")
    return True


def _pa_history(p, a):
    store = p.req("GET", "/server/gcode_store", params={"count": a.count}).get("gcode_store", [])
    pat = re.compile(r"PRESSURE_ADVANCE|pressure_advance|\bM900\b|Qmode|smooth_time|START_PRINT|END_PRINT|"
                     r"CANCEL_PRINT|SDCARD_PRINT_FILE|PRINT_CALIBRATION|motion.?advance", re.I)
    hits = [g for g in store if pat.search(g.get("message", ""))
            and not (g.get("type") == "command" and g.get("message", "").strip().upper() == "SET_PRESSURE_ADVANCE")]
    span = ""
    if store:
        span = " (console log covers %s .. %s)" % (time.strftime("%m-%d %H:%M", time.localtime(store[0].get("time", 0))),
                                                   time.strftime("%m-%d %H:%M", time.localtime(store[-1].get("time", 0))))
    log("  %d pressure-advance related console lines in the last %d%s" % (len(hits), len(store), span))
    log("  (commands typed / sent by tools, plus the printer's answers - K lines inside a print file show up as "
        "'pressure_advance: ...' answers)")
    for g in hits[-a.lines:]:
        msg = " | ".join(x.strip() for x in g.get("message", "").splitlines() if x.strip())
        log("    %s  %-8s %s" % (time.strftime("%m-%d %H:%M:%S", time.localtime(g.get("time", 0))),
                                 "sent" if g.get("type") == "command" else "answer", msg[:160]))
    try:
        jobs = p.req("GET", "/server/history/list", params={"limit": 10, "order": "desc"}).get("jobs", [])
        if jobs:
            log("  recent prints:")
        for j in jobs:
            log("    %s  %-10s %6.0f min  %s" % (time.strftime("%m-%d %H:%M", time.localtime(j.get("start_time") or 0)),
                j.get("status", "?"), (j.get("total_duration") or 0) / 60.0, j.get("filename", "?")))
    except ToolError as e:
        log("  print history not available: %s" % e)
    path = os.path.join(_pa_logdir(a), "pa_changes.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            rows = [r for r in csv.reader(fh)][1:]
        mine = [r for r in rows if len(r) > 2 and r[1] == p.name]
        log("  changes made by this tool on %s (pa_logs/pa_changes.csv): %d" % (p.name, len(mine)))
        for r in mine[-10:]:
            log("    %s  %-20s %s -> %s  %s" % (r[0], r[2], r[3] or "-", r[4] or "-", r[6] if len(r) > 6 else ""))
    return True


def _pa_watch(p, a):
    """Poll the printer and log every K / silent-mode / state change with the height it happened at."""
    PA_STOP.clear()
    objs = ("extruder", "print_stats", "gcode_move", "gcode_macro Qmode")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", p.name)
    path = os.path.join(_pa_logdir(a), "watch_%s_%s.csv" % (safe, time.strftime("%Y%m%d-%H%M%S")))
    t_end = time.time() + a.minutes * 60
    last, bands, seen_print, errors = {}, [], False, 0
    zmin = None
    log("  watching %s every %gs for up to %g min%s - CSV: %s" % (p.name, a.interval, a.minutes,
        " (stops when the print ends)" if a.until_done else "", path))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "state", "file", "z", "layer", "k", "smooth_time", "silent_mode", "nozzle_c", "event"])
        t_row = 0
        while time.time() < t_end and not PA_STOP.is_set():
            try:
                s = p.query(*objs)
                errors = 0
            except ToolError as e:
                errors += 1
                log("  %s  no answer (%s)" % (time.strftime("%H:%M:%S"), e), "WARN")
                if errors > 20:
                    log("printer gone for too long - stopping", "FAIL")
                    break
                PA_STOP.wait(max(a.interval, 5))
                continue
            ext, ps, gm = s.get("extruder", {}), s.get("print_stats", {}), s.get("gcode_move", {})
            k, sm = ext.get("pressure_advance"), ext.get("smooth_time")
            pos = gm.get("gcode_position") or [0, 0, 0, 0]
            z = pos[2] if len(pos) > 2 else 0.0
            layer = (ps.get("info") or {}).get("current_layer")
            state, fn = ps.get("state"), ps.get("filename")
            q = bool((s.get("gcode_macro Qmode") or {}).get("flag"))
            ev = []
            if not last:
                ev.append("start: K %s, smooth %s, %s%s" % (_fk(k), sm, state, ", SILENT MODE ON" if q else ""))
            else:
                if k != last["k"]:
                    ev.append("K %s -> %s" % (_fk(last["k"]), _fk(k)))
                if sm != last["sm"]:
                    ev.append("smooth %s -> %s" % (last["sm"], sm))
                if state != last["state"]:
                    ev.append("%s -> %s" % (last["state"], state))
                if fn != last["fn"] and fn:
                    ev.append("file %s" % fn)
                if q != last["q"]:
                    ev.append("silent mode %s" % ("ON (K forced 0.05)" if q else "off"))
            if state == "printing":
                seen_print = True
                if z > 0:
                    zmin = z if zmin is None else min(zmin, z)
                if not bands or abs((bands[-1][0] or 0) - (k or 0)) > 1e-9:
                    bands.append([k, z, z])
                else:
                    bands[-1][2] = max(bands[-1][2], z)
            now = time.time()
            if ev or now - t_row >= 30:
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), state, fn, "%.2f" % z, layer, _fk(k), sm, int(q),
                            ext.get("temperature"), "; ".join(ev)])
                fh.flush()
                t_row = now
            if ev:
                lvl = "WARN" if any("silent mode ON" in e or "SILENT" in e for e in ev) else "INFO"
                log("  %s  Z%7.2f  layer %-4s K %s  %s" % (time.strftime("%H:%M:%S"), z, layer if layer is not None else "-",
                                                           _fk(k), "; ".join(ev)), lvl)
            last = {"k": k, "sm": sm, "state": state, "fn": fn, "q": q}
            if a.until_done and seen_print and state in ("complete", "cancelled", "error", "standby"):
                log("  print ended (%s)" % state)
                break
            PA_STOP.wait(a.interval)
    if PA_STOP.is_set():
        log("  stopped")
    if bands:
        log("  K by height while printing (what the printer really used):")
        rows = ["Z %6.2f-%6.2f  K %s" % (b[1], b[2], _fk(b[0])) for b in bands]
        for i in range(0, len(rows), 3):
            log("    " + "     ".join(rows[i:i + 3]))
        rise = bands[-1][2] - (zmin or 0)
        if len(bands) == 1 and rise > 8:
            log("K never changed over %.0f mm of printing - if this was a PA tower the printer ignored it "
                "(locked / silent mode / Motion Advance). Run 'pa preflight'." % rise, "WARN")
    log("watch log saved: %s" % path, "OK")
    return True


PA_VERIFY_FILE = "hi_pa_verify.gcode"
PA_VERIFY_GCODE = """; HI pressure advance respect test - generated by hi_tool.py. NO heating, NO movement.
; Changes K a few times so 'pa verify' can see whether commands inside a print file are obeyed.
SET_PRESSURE_ADVANCE ADVANCE={k1:.4f}
G4 P{hold}
M900 K{k2:.4f}
G4 P{hold}
SET_PRESSURE_ADVANCE ADVANCE={k3:.4f} SMOOTH_TIME={s3:.3f}
G4 P{hold}
SET_PRESSURE_ADVANCE ADVANCE={k0:.4f} SMOOTH_TIME={s0:.3f}
"""


def _pa_verify(p, a):
    """Send pressure-advance commands and read back what the printer actually uses. Always restores K."""
    st = _pa_state(p)
    if st["print"] in BUSY_STATES and not a.force:
        raise ToolError("printer is %s - verify changes K, run it when idle (or --force)" % st["print"])
    k0 = st["k"] if st["k"] is not None else (st["k_cfg"] or 0.04)
    s0 = st["smooth"] if st["smooth"] else 0.04
    # odd test values nobody uses, all different from the current K
    tv = [v for v in (0.0123, 0.0234, 0.0345, 0.0456, 0.0567) if abs(v - k0) > 0.002][:4]
    t_sm = 0.033 if abs(s0 - 0.033) > 1e-4 else 0.037
    res = []   # (name, passed, detail)

    def now():
        s = _pa_state(p)
        return s["k"], s["smooth"]

    def check(name, cmd, want_k, want_sm=None, expect=True):
        ok, err, msgs = _gcode_capture(p, cmd, timeout=20)
        time.sleep(0.3)
        k, sm = now()
        applied = k is not None and abs(k - want_k) < 1e-4 and (want_sm is None or abs((sm or 0) - want_sm) < 1e-4)
        passed = applied == expect
        txt = " | ".join(x.strip().lstrip("/ ") for m in msgs for x in m.splitlines() if x.strip())[:110]
        detail = "sent '%s' -> printer K %s smooth %s%s%s" % (cmd.replace("\n", " / "), _fk(k), sm,
                                                               "" if ok else " ERROR " + err, (" (" + txt + ")") if txt else "")
        res.append((name, passed, detail))
        log(("  %-34s " % name) + detail, "OK" if passed else "FAIL")
        return applied

    log("  starting point: K %s smooth %s (saved %s), silent mode %s, print %s"
        % (_fk(k0), s0, _fk(st["k_cfg"]), "ON" if st["qmode"] else "off", st["print"]))
    lock0 = _pa_lock(p)
    log("  lock before the test: %s" % {True: "unlocked", False: "LOCKED", None: "unknown"}[lock0],
        "WARN" if lock0 is False else "INFO")
    if st["qmode"]:
        log("silent mode is ON - its K 0.05 is only forced when it is switched on; commands still change K. "
            "Turn it off for normal printing with your own K.", "WARN")
    try:
        if lock0 is False:
            log("  printer is locked - first test shows that, then we unlock and test again")
            check("locked: SET_PRESSURE_ADVANCE", "SET_PRESSURE_ADVANCE ADVANCE=%.4f" % tv[0], tv[0], expect=False)
            p.gcode("ENABLE_PRESSURE_ADVANCE VALUE=1", timeout=15)
        check("console SET_PRESSURE_ADVANCE", "SET_PRESSURE_ADVANCE ADVANCE=%.4f" % tv[0], tv[0])
        check("console M900 K (Creality macro)", "M900 K%.4f" % tv[1], tv[1])
        check("smooth_time", "SET_PRESSURE_ADVANCE ADVANCE=%.4f SMOOTH_TIME=%.3f" % (tv[2], t_sm), tv[2], t_sm)
        p.gcode("SET_PRESSURE_ADVANCE SMOOTH_TIME=%.3f" % s0, timeout=15)
        # the Creality lock really blocks changes, and unlocking works
        check("lock ON blocks changes", "ENABLE_PRESSURE_ADVANCE VALUE=0\nSET_PRESSURE_ADVANCE ADVANCE=%.4f" % tv[3],
              tv[3], expect=False)
        check("lock OFF lets them through", "ENABLE_PRESSURE_ADVANCE VALUE=1\nSET_PRESSURE_ADVANCE ADVANCE=%.4f" % tv[3],
              tv[3])

        if a.via_print:
            if not a.apply:
                log("  --via-print needs --apply (it uploads and starts a tiny no-heat, no-motion print)")
            else:
                p.assert_idle(a.force)
                hold = 4000
                text = PA_VERIFY_GCODE.format(k1=tv[0], k2=tv[1], k3=tv[2], s3=t_sm, k0=k0, s0=s0, hold=hold)
                boundary = "----hi" + uuid.uuid4().hex
                body = b"".join([
                    ('--%s\r\nContent-Disposition: form-data; name="root"\r\n\r\ngcodes\r\n' % boundary).encode(),
                    ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
                     'Content-Type: application/octet-stream\r\n\r\n' % (boundary, PA_VERIFY_FILE)).encode(),
                    text.encode("utf-8"), ("\r\n--%s--\r\n" % boundary).encode()])
                p.req("POST", "/server/files/upload", body=body, timeout=60, retries=1,
                      headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
                p.gcode("SET_PRESSURE_ADVANCE ADVANCE=%.4f" % k0, timeout=15)
                p.req("POST", "/printer/print/start", params={"filename": PA_VERIFY_FILE}, retries=0)
                log("  print file started (no heat, no motion, ~%ds) - watching K" % (3 * hold // 1000))
                seen, t_end, started = [], time.time() + 3 * hold / 1000.0 + 40, False
                while time.time() < t_end:
                    s = p.query("extruder", "print_stats")
                    k = s.get("extruder", {}).get("pressure_advance")
                    state = s.get("print_stats", {}).get("state")
                    started = started or state == "printing"
                    if k is not None and (not seen or abs(seen[-1] - k) > 1e-6):
                        seen.append(k)
                        log("    %s  K %s  (%s)" % (time.strftime("%H:%M:%S"), _fk(k), state))
                    if started and state in ("complete", "cancelled", "error", "standby"):
                        break
                    time.sleep(0.4)
                for want, name in ((tv[0], "print file SET_PRESSURE_ADVANCE"), (tv[1], "print file M900 K"),
                                   (tv[2], "print file K + smooth_time")):
                    got = any(abs(v - want) < 1e-4 for v in seen)
                    res.append((name, got, "K %.4f %s" % (want, "seen" if got else "NEVER seen")))
                    log(("  %-34s K %.4f " % (name, want)) + ("applied" if got else "NOT applied"), "OK" if got else "FAIL")
                if not started:
                    log("  the print never reached 'printing' - the screen may need a tap, or another job ran", "WARN")
                try:
                    p.req("DELETE", "/server/files/gcodes/" + urllib.parse.quote(PA_VERIFY_FILE), retries=0)
                except ToolError:
                    pass
    finally:
        try:
            p.gcode("ENABLE_PRESSURE_ADVANCE VALUE=1\nSET_PRESSURE_ADVANCE ADVANCE=%.4f SMOOTH_TIME=%.3f" % (k0, s0),
                    timeout=20)
            k, sm = now()
            good = k is not None and abs(k - k0) < 1e-4
            log("restored K %s smooth %s%s" % (_fk(k), sm, "" if lock0 is not False else " (and left it UNLOCKED)"),
                "OK" if good else "FAIL")
        except ToolError as e:
            log("could not restore K %.4f: %s - set it by hand" % (k0, e), "ERROR")
    failed = [r for r in res if not r[1]]
    if failed:
        log("NOT RESPECTED: " + ", ".join(r[0] for r in failed))
        return False
    log("READY - pressure-advance commands are respected (%d checks)" % len(res))
    return True


def cmd_pa_fleet(p, a):
    p.connect()
    st = _pa_state(p)
    busy = st["print"] in BUSY_STATES
    lock = None if busy else _pa_lock(p)
    log("  %-12s live K %-7s saved K %-7s smooth %-6s %-9s silent %-3s  %s"
        % (p.name, _fk(st["k"]), _fk(st["k_cfg"]), "-" if st["smooth"] is None else "%.3f" % st["smooth"],
           {True: "unlocked", False: "LOCKED", None: "lock ?"}[lock], "ON" if st["qmode"] else "off", st["print"]),
        "WARN" if lock is False or st["qmode"] else "INFO")
    return True


def pa_test_gcode(start, end, step, nozzle=220, bed=60, slow=20.0, fast=100.0, accel=5000, layer=0.25,
                  width=0.5, nozzle_d=0.4, filament=1.75, x0=60.0, y0=40.0, spacing=4.0, mesh="load",
                  k_restore=0.04, smooth=None):
    """Klipper-style line test: per line SET_PRESSURE_ADVANCE, then slow 20 / fast 60 / slow 20 mm.
    The best line has an even fast section with no blob where it speeds up and no gap where it slows down."""
    if step <= 0 or end <= start:
        raise ToolError("need end > start and step > 0")
    n = int(round((end - start) / step)) + 1
    if n > 45:
        raise ToolError("%d lines won't fit - use a bigger step or a smaller range (max 45)" % n)
    if end > PA_MAX:
        raise ToolError("end %.3f is above %.1f - not a sensible pressure advance" % (end, PA_MAX))
    area = layer * (width - layer) + math.pi * (layer / 2) ** 2      # slic3r extrusion cross-section
    epm = area / (math.pi * (filament / 2) ** 2)                      # mm filament per mm of line
    seg = (20.0, 60.0, 20.0)
    xend = x0 + sum(seg)
    yend = y0 + (n - 1) * spacing
    if xend + 12 > 255 or yend + 6 > 255:
        raise ToolError("pattern runs off the 260 mm bed")
    meshcmd = {"load": "BED_MESH_PROFILE LOAD=default", "calibrate": "BED_MESH_CALIBRATE",
               "none": "; no bed mesh"}[mesh]
    o = ["; HI pressure advance line test - generated by hi_tool.py %s" % VERSION,
         "; start=%.4f end=%.4f step=%.4f lines=%d nozzle=%d bed=%d slow=%g fast=%g mm/s accel=%d"
         % (start, end, step, n, nozzle, bed, slow, fast, accel),
         "; line 1 is at the FRONT (Y%.0f). Every 5th line has a tick on the right, line 1 a double tick." % y0,
         "; pick the line whose fast middle section is even, with no blob where it speeds up and no thin gap",
         "; where it slows down. K = start + (line - 1) * step"]
    table = []
    for i in range(n):
        k = start + i * step
        table.append((i + 1, round(k, 4), y0 + i * spacing))
        o.append(";   line %2d  Y%.0f  K=%.4f" % (i + 1, y0 + i * spacing, k))
    o.append(PA_START_GCODE.format(bed=bed, nozzle=nozzle, mesh=meshcmd, accel=accel).rstrip())
    # prime + anchor line along the left edge of the pattern
    o += ["G1 Z5 F1200", "G1 X%.2f Y%.2f F9000" % (x0 - 5, y0 - 6), "G1 Z%.2f F600" % layer, "G1 E2 F300",
          "G1 Y%.2f E%.4f F%d" % (yend + 4, (yend + 10 - y0) * epm * 1.2, slow * 60), "G1 E-0.8 F2100"]
    ks = ("SET_PRESSURE_ADVANCE ADVANCE=%.4f" + (" SMOOTH_TIME=%.3f" % smooth if smooth else ""))
    for i, k, y in table:
        o += ["; line %d K=%.4f" % (i, k), ks % k, "G1 Z%.2f F1200" % (layer + 0.4),
              "G1 X%.2f Y%.2f F9000" % (x0, y), "G1 Z%.2f F600" % layer, "G1 E0.8 F2100"]
        x = x0
        for length, sp in zip(seg, (slow, fast, slow)):
            x += length
            o.append("G1 X%.2f E%.4f F%d" % (x, length * epm, sp * 60))
        ticks = 2 if i == 1 else (1 if i % 5 == 0 else 0)
        if ticks:
            o += ["G1 X%.2f E%.4f F%d" % (x + 3 + 4 * ticks, (3 + 4 * ticks) * epm, slow * 60)]
        o.append("G1 E-0.8 F2100")
    o.append(PA_END_GCODE.format(k_restore="%.4f" % k_restore).rstrip())
    return "\n".join(o) + "\n", table


def _pa_test(p, a):
    st = _pa_state(p)
    k_restore = st["k_cfg"] if st["k_cfg"] is not None else 0.04
    text, table = pa_test_gcode(a.start, a.end, a.step, nozzle=a.nozzle_temp, bed=a.bed_temp, slow=a.slow,
                                fast=a.fast, accel=a.accel, mesh=a.mesh, k_restore=k_restore, smooth=a.smooth)
    name = a.name or "hi_pa_test_%s_%s-%s.gcode" % (a.nozzle_temp, ("%.3f" % a.start).rstrip("0").rstrip("."),
                                                     ("%.3f" % a.end).rstrip("0").rstrip("."))
    d = os.path.join(a.backup_dir, "pa_tests")
    os.makedirs(d, exist_ok=True)
    local = os.path.join(d, name)
    with open(local, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    log("  wrote %s - %d lines, K %.4f .. %.4f step %.4f" % (local, len(table), a.start, a.end, a.step))
    log("  line 1 at the front = K %.4f, line %d at the back = K %.4f; every 5th line has a tick on the right"
        % (table[0][1], table[-1][0], table[-1][1]))
    log("  after the test the printer goes back to K %.4f (its saved default)" % k_restore)
    if not (a.upload or a.print_it):
        return True
    if not a.apply:
        log("  DRY RUN - add --apply to %s" % ("upload and start it" if a.print_it else "upload it"))
        return True
    boundary = "----hi" + uuid.uuid4().hex
    body = b"".join([
        ('--%s\r\nContent-Disposition: form-data; name="root"\r\n\r\ngcodes\r\n' % boundary).encode(),
        ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
         'Content-Type: application/octet-stream\r\n\r\n' % (boundary, name)).encode(),
        text.encode("utf-8"), ("\r\n--%s--\r\n" % boundary).encode()])
    p.req("POST", "/server/files/upload", body=body, timeout=60, retries=1,
          headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    log("uploaded %s to the printer's gcode files" % name, "OK")
    if a.print_it:
        p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
        p.req("POST", "/printer/print/start", params={"filename": name}, retries=0)
        log("print started - watch the first line go down. When it's done, find the best line and use 'pa set'.", "OK")
        _pa_changelog(a, p, "line test printed", None, None, a.smooth, "%s K %.4f..%.4f step %.4f %dC"
                      % (name, a.start, a.end, a.step, a.nozzle_temp))
    return True


def _pa_firmware(p, a):
    """Over SSH: firmware version and where (if anywhere) Motion Advance / auto PA lives."""
    cmd = ("echo '== version'; for f in /etc/openwrt_version /etc/version /usr/data/creality/version* "
           "/usr/data/version* /etc/os-release; do [ -f \"$f\" ] && { echo \"-- $f\"; head -5 \"$f\"; }; done 2>/dev/null; "
           "echo '== motion advance / auto pressure advance'; "
           "grep -rIil -e 'motion.\\?advance' -e 'motionadvance' -e 'auto_pa' -e 'pa_calib' -e 'pressure_advance_calib' "
           "/usr/data /usr/share/klipper/klippy /etc 2>/dev/null | grep -v -e '/gcodes/' -e '\\.log' | head -25; "
           "echo '== settings that mention it'; "
           "grep -rIih -e 'motion.\\?advance' /usr/data/creality /usr/data/printer_data/config 2>/dev/null | head -10")
    rc, out, err = _ssh_run(p, a, cmd, timeout=a.ssh_timeout)
    for ln in out.decode("utf-8", "replace").splitlines():
        log("  " + ln)
    if err:
        log(err, "WARN")
    return rc == 0



# --------------------------------------------------------------------------- beeper (discovery)
# Klipper on the Hi has no beeper ([output_pin beeper] / M300 don't exist). If there is a buzzer or speaker it
# belongs to Linux / Creality's screen app. 'beep --probe' looks for it over SSH (read-only).
BEEP_PROBE = r"""
echo '== asound.conf'; cat /etc/asound.conf 2>&1 | head -40
echo '== audio files'; ls -la /etc/sysConfig/audio /etc/sysConfig/audio/* 2>&1 | head -40
echo '== devices'; ls /dev | grep -i 'snd\|dsp\|audio\|pcm\|buzz\|beep\|i2s\|pwm\|spk'
echo '== pwm'; ls -l /sys/class/pwm/pwmchip0/device 2>&1; cat /sys/kernel/debug/pwm 2>/dev/null | head -20; for c in /sys/class/pwm/pwmchip0/pwm*; do echo "$c en=$(cat $c/enable) period=$(cat $c/period) duty=$(cat $c/duty_cycle)"; done 2>/dev/null
echo '== modules'; lsmod 2>/dev/null | grep -i 'snd\|pwm\|audio\|buzz'
echo '== audio-server'; P=$(pidof audio-server); echo "pid $P"; cat /proc/$P/cmdline 2>/dev/null | tr '\0' ' '; echo; ls -l /proc/$P/fd 2>/dev/null | grep -v 'null$'
echo '== audio-server strings'; grep -a -o '[[:print:]]\{5,\}' /usr/bin/audio-server 2>/dev/null | grep -i 'beep\|wav\|mp3\|play\|pwm\|/dev/\|/tmp/\|/sys/\|sock\|volume\|mute\|ubus\|dbus\|topic\|cmd\|json' | sort -u | head -80
echo '== ipc'; ubus list 2>/dev/null | head -30; ls -la /tmp 2>/dev/null | grep -i 'sock\|audio\|ipc\|fifo\|^s\|^p' | head -20
echo '== sound settings'; grep -rIi -o '"[a-z_]*\(sound\|volume\|mute\|beep\|buzz\)[a-z_]*" *: *[^,}]*' /usr/data /mnt/UDISK/creality /etc/sysConfig 2>/dev/null | grep -v material_database | head -20
"""


# The Hi has a small speaker, not a buzzer: Creality's audio-server plays .wav files with 'aplay' (its log:
# "audio file name ... path = /etc/sysConfig/audio/<language>/1.sound_button_technology.wav"). We do the same.
BEEP_DEEP = r"""
echo '== kernel'; uname -a; cat /proc/device-tree/model 2>/dev/null; echo; cat /proc/device-tree/compatible 2>/dev/null | tr '\0' ' '; echo
echo '== device tree: sound / codec / buzzer nodes'
find /proc/device-tree -maxdepth 4 \( -iname '*codec*' -o -iname '*sound*' -o -iname '*audio*' -o -iname '*i2s*' -o -iname '*buzz*' -o -iname '*beep*' -o -iname '*spk*' -o -iname '*speaker*' -o -iname '*pa_*' \) 2>/dev/null | while read n; do
  st=$(cat "$n/status" 2>/dev/null | tr -d '\0'); echo "$n  status=${st:-?}"; done | head -30
echo '== platform devices (driver bound?)'
for d in /sys/bus/platform/devices/*; do case "$(basename $d)" in *codec*|*sound*|*audio*|*i2s*|*buzz*|*beep*|*spk*|*pwm*|*dmic*|*daudio*) echo "$(basename $d) -> $(basename $(readlink $d/driver 2>/dev/null) 2>/dev/null)";; esac; done
echo '== kernel config (sound)'; (zcat /proc/config.gz 2>/dev/null || cat /boot/config* 2>/dev/null) | grep -i 'CONFIG_SND_SOC_SUNXI\|CONFIG_SND=\|CONFIG_SND_SUN\|CONFIG_INPUT_PWM_BEEPER\|CONFIG_PWM_SUNXI' | head -20
echo '== sound modules on disk'; find /lib/modules -iname '*snd*' -o -iname '*codec*' -o -iname '*sound*' -o -iname '*beep*' 2>/dev/null | head -20
echo '== loaded modules'; cat /proc/modules 2>/dev/null | cut -d' ' -f1 | tr '\n' ' '; echo
echo '== boot log'; (dmesg; logread) 2>/dev/null | grep -i 'codec\|sound\|snd\|audio\|i2s\|buzz\|beep\|pwm\|sunxi-pa\|spk' | head -25
echo '== screen programs mentioning a buzzer'
for b in /usr/bin/display-server /usr/bin/master-server /usr/bin/app-server /usr/bin/device_manager /usr/bin/Monitor; do
  h=$(grep -a -o '[[:print:]]\{5,\}' $b 2>/dev/null | grep -i 'buzz\|beep\|/sys/class/pwm\|/sys/class/gpio\|aplay\|\.wav\|tone\|alarm_sound' | sort -u | head -12)
  [ -n "$h" ] && { echo "-- $b"; echo "$h"; }
done
"""

# Creality: "The built-in buzzer will give off corresponding sounds when the print task is finished or paused".
# Linux has no sound card, but PWM channel 6 sits configured at 4 kHz / 50 % and disabled - a piezo buzzer drive.
BEEP_PWM_CH = 6
BEEP_PWM_HEAD = r"""
C=/sys/class/pwm/pwmchip0; N=%(ch)d; P=$C/pwm$N
nap() { command -v usleep >/dev/null && usleep $1 || sleep $2; }
exported=0
if [ ! -d $P ]; then echo $N > $C/export 2>/dev/null || { echo "EXPORT_FAIL pwm$N is claimed by a driver"; exit 3; }; exported=1; nap 100000 0.1; fi
op=$(cat $P/period); od=$(cat $P/duty_cycle); oe=$(cat $P/enable)
if [ "$oe" = 1 ] && [ "$od" != 0 ]; then echo "BUSY pwm$N is sounding right now - not touching"; [ $exported = 1 ] && echo $N > $C/unexport; exit 4; fi
echo "== pwm$N before: period=$op duty=$od"
t() { echo 0 > $P/duty_cycle; echo $1 > $P/period; echo $2 > $P/duty_cycle; echo 1 > $P/enable; nap $3 $4; echo 0 > $P/enable; nap 20000 0.02; }
"""
BEEP_PWM_TAIL = r"""
echo 0 > $P/enable
if [ "$op" != 0 ]; then echo 0 > $P/duty_cycle; echo $op > $P/period; echo $od > $P/duty_cycle; fi
echo $oe > $P/enable   # Klipper's beeper (if installed) keeps it enabled at duty 0
[ $exported = 1 ] && echo $N > $C/unexport
echo "PWM_DONE pwm$N %(desc)s - restored (period=$op duty=$od), enable=0"
"""

# Original jingles (not copies of any song). Piezo buzzers are loudest around 2-4 kHz, so they live in octaves 6-8.
# Format: NOTE[:ms] (C7, F#6, Bb7), HZ:ms (2500:200), or -:ms for a rest. Default length 150 ms.
BEEP_LOUD_HZ = 4200   # loudest pitch on a Hi buzzer (sweep 2026-10-20: 4000 / 4500 Hz loudest)
# Each tune is centred on BEEP_LOUD_HZ (time-weighted average pitch within a semitone of 4.2 kHz).
TUNES = {
    "countdown":  "A#7:110 -:390 A#7:110 -:390 A#7:110 -:390 D8:450 -:150 F7:110 G7:110 A#7:110 C8:110 -:60 A#7:110 C8:110 D8:650",
    "fanfare":    "G#7:120 G#7:120 G#7:120 C#8:380 -:70 A#7:120 B7:120 C8:120 C#8:120 D#8:520",
    "done":       "G7:110 A#7:110 C8:110 D8:320",
    "alert":      "C8:120 -:80 C8:120 -:80 C8:120 -:320 C8:120 -:80 C8:120 -:80 C8:120",
    "doorbell":   "D#8:300 -:40 A#7:520",
    "error":      "F8:240 -:60 C8:240 -:60 A7:520",
}

# 'sweep': 8 tones with gaps; the loudest one is the buzzer's resonance (log says which number is which Hz)
SWEEP_HZ = (2000, 2500, 2800, 3100, 3500, 4000, 4500, 5000)
TUNES["sweep"] = " -:600 ".join("%d:350" % hz for hz in SWEEP_HZ)
NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(\d)$")
SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def parse_notes(text, default_ms=150, transpose=0):
    """'C7:150 E7 -:100 2500:200' -> [(hz, ms), ...]; hz 0 = rest."""
    out = []
    for tok in text.replace(",", " ").split():
        name, _, ms = tok.partition(":")
        ms = int(ms) if ms else default_ms
        if not 10 <= ms <= 3000:
            raise ToolError("note %r: length must be 10..3000 ms" % tok)
        if name in ("-", "r", "R", "rest"):
            out.append((0, ms))
            continue
        m = NOTE_RE.match(name)
        if m:
            n = 12 * (int(m.group(3)) + 1) + SEMI[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
            hz = 440.0 * 2 ** ((n - 69) / 12.0)
        else:
            try:
                hz = float(name)
            except ValueError:
                raise ToolError("can't read note %r (use C7, F#6, Bb7, 2500 or - for a rest)" % tok)
        hz *= 2 ** (transpose / 12.0)
        if not 200 <= hz <= 10000:
            raise ToolError("note %r is %.0f Hz - keep it 200..10000" % (tok, hz))
        out.append((hz, ms))
    if not out:
        raise ToolError("no notes")
    if len(out) > 120 or sum(ms for _, ms in out) > 20000:
        raise ToolError("tune too long (max 120 notes / 20 s)")
    return out


def pwm_notes_script(ch, notes, desc):
    lines = [BEEP_PWM_HEAD % {"ch": ch}]
    for hz, ms in notes:
        if hz <= 0:
            lines.append("nap %d %.3f" % (ms * 1000, ms / 1000.0))
        else:
            per = int(1e9 / hz)
            lines.append("t %d %d %d %.3f" % (per, per // 2, ms * 1000, ms / 1000.0))
    lines.append(BEEP_PWM_TAIL % {"desc": desc})
    return "\n".join(lines)


BEEP_WAV = "/etc/sysConfig/audio/chinese/1.button_beep.wav"
BEEP_SCRIPT = r"""
F='%(file)s'
[ -f "$F" ] || F=$(ls /etc/sysConfig/audio/*/1.button_beep.wav /etc/sysConfig/audio/*/*.wav 2>/dev/null | head -1)
echo "== sound devices"; cat /proc/asound/cards 2>&1 | head -4; aplay -l 2>&1 | head -4
[ -n "$F" ] || { echo "NO_WAV"; exit 3; }
echo "== playing $F x%(times)d"
i=0; rc=0
while [ $i -lt %(times)d ]; do
  aplay -q "$F" 2>&1; rc=$?
  [ $rc -eq 0 ] || break
  i=$((i+1))
done
echo "APLAY_RC=$rc"
"""


def cmd_beep(p, a):
    if a.probe or a.deep:
        rc, out, err = _ssh_run(p, a, BEEP_DEEP if a.deep else BEEP_PROBE, timeout=a.ssh_timeout)
    else:
        if not (1 <= a.times <= 10):
            raise ToolError("--times 1..10")
        if a.tune or a.notes:
            a.pwm = BEEP_PWM_CH if a.pwm is None else a.pwm
        if a.pwm is not None:
            if a.pwm in (5, 7):
                raise ToolError("pwm5 is the screen backlight and pwm7 the CPU voltage - not touching those")
            if not 0 <= a.pwm <= 7:
                raise ToolError("--pwm 0..7")
            if a.notes:
                notes, desc = parse_notes(a.notes, transpose=a.transpose), "custom tune"
            elif a.tune:
                if a.tune not in TUNES:
                    raise ToolError("unknown tune %r - pick one of: %s" % (a.tune, ", ".join(sorted(TUNES))))
                notes, desc = parse_notes(TUNES[a.tune], transpose=0 if a.tune == "sweep" else a.transpose), \
                    "tune '%s'" % a.tune
                if a.tune == "sweep":
                    log("  sweep: " + ", ".join("%d = %d Hz" % (i + 1, hz) for i, hz in enumerate(SWEEP_HZ))
                        + "  - which number was loudest?")
            else:
                if not (200 <= a.freq <= 10000 and 20 <= a.ms <= 3000):
                    raise ToolError("--freq 200..10000, --ms 20..3000")
                notes = []
                for i in range(a.times):
                    notes += [(a.freq, a.ms)] + ([(0, 150)] if i < a.times - 1 else [])
                desc = "%d Hz %d ms x%d" % (a.freq, a.ms, a.times)
            log("  playing %s: %d notes, %.1f s" % (desc, sum(1 for h, _ in notes if h), sum(m for _, m in notes) / 1000.0))
            rc, out, err = _ssh_run(p, a, pwm_notes_script(a.pwm, notes, desc), timeout=max(a.ssh_timeout, 60))
            text = out.decode("utf-8", "replace")
            for ln in text.splitlines():
                log("  " + ln)
            if err:
                log(err, "WARN")
            if "PWM_DONE" in text:
                log("played on pwm%d" % a.pwm, "OK")
                return True
            log("pwm%d not used - see above, nothing changed" % a.pwm, "WARN")
            return False
        if not re.fullmatch(r"[\w./-]+\.wav", a.file):
            raise ToolError("--file must be a .wav path on the printer")
        rc, out, err = _ssh_run(p, a, BEEP_SCRIPT % {"file": a.file, "times": a.times}, timeout=a.ssh_timeout)
    text = out.decode("utf-8", "replace")
    for ln in text.splitlines():
        log("  " + ln)
    if err:
        log(err, "WARN")
    if not (a.probe or a.deep):
        if "APLAY_RC=0" in text:
            log("aplay played it without an error - did you hear it?", "OK")
        elif "no soundcards" in text.lower() or "no soundcards found" in text.lower():
            log("Linux sees no sound card right now, so nothing can play - see the aplay error above", "WARN")
        else:
            log("aplay failed - the error above says why", "WARN")
        return rc == 0 and "APLAY_RC=0" in text
    return rc == 0


# --------------------------------------------------------------------------- webcam (Fluidd camera)
# Fluidd reads its cameras from Moonraker (/server/webcams/*). Database entries can be added/removed over
# the API; entries from moonraker.conf ([webcam ...], source "config") are read-only.
WEBCAM_FIELDS = ("name", "location", "service", "enabled", "icon", "target_fps", "target_fps_idle",
                 "stream_url", "snapshot_url", "flip_horizontal", "flip_vertical", "rotation",
                 "aspect_ratio", "extra_data")


# The Creality Hi serves its camera page on port 8000 of its own IP. Fluidd shows it as an iframe.
# Same entry Hi-3 had when it was set up by hand in Fluidd.
HI_CAM_NAME = "HICAM"
HI_CAM_PORT = 8000


def hi_cam_entry(host, name=HI_CAM_NAME, port=HI_CAM_PORT):
    return {"name": name, "service": "iframe", "enabled": True, "icon": "mdiWebcam",
            "stream_url": "http://%s:%d/?action=stream" % (host, port),
            "snapshot_url": "http://%s:%d/?action=snapshot" % (host, port)}


def _webcams(p):
    res = p.req("GET", "/server/webcams/list")
    cams = res.get("webcams", []) if isinstance(res, dict) else []
    return [c for c in cams if isinstance(c, dict)]


def _cam_urls(p, url):
    """Absolute URLs to try for a camera URL. Relative ones resolve against the web UI the way Fluidd does."""
    if not url:
        return []
    if re.match(r"^[a-z]+://", url, re.I):
        return [url]
    if not url.startswith("/"):
        url = "/" + url
    out = []
    for base in ([p.base] if p.base else []) + ["http://%s:4408" % p.host, "http://%s" % p.host]:
        if base + url not in out:
            out.append(base + url)
    return out


def _probe_one(url, timeout=5):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "creality-hi-tool/" + VERSION})
        with _OPENER.open(req, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            head = r.read(4096)  # a stream never ends - a few bytes is enough
            st = r.status
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except Exception as e:
        return False, str(getattr(e, "reason", e))
    if head.startswith(b"\xff\xd8") or "image" in ctype or "multipart" in ctype:
        return True, "HTTP %s %s" % (st, ctype or "jpeg")
    return False, "answers (HTTP %s %s) but no picture" % (st, ctype or "?")


def _probe_cam(p, cam):
    """(ok, detail) - is there a picture (or, for iframe/webrtc cameras, a camera page) on this printer?"""
    service = str(cam.get("service", "")).lower()
    tried = []
    if "iframe" in service or "webrtc" in service:
        # Fluidd embeds the stream URL as a web page - an HTML page that loads is the expected answer
        for url in _cam_urls(p, cam.get("stream_url", "")):
            try:
                st, body = p._open("GET", url, timeout=5, retries=0)
            except ToolError as e:
                tried.append("%s (%s)" % (url, e))
                continue
            if st < 400:
                return True, "%s -> camera page answers (HTTP %s, %d bytes) - %s camera" % (url, st, len(body), service)
            tried.append("%s (HTTP %s)" % (url, st))
        return False, "; ".join(tried) or "no stream URL"
    for key in ("snapshot_url", "stream_url"):
        for url in _cam_urls(p, cam.get(key, "")):
            ok, why = _probe_one(url)
            if ok:
                return True, "%s -> %s" % (url, why)
            tried.append("%s (%s)" % (url, why))
    return False, "; ".join(tried) or "no stream/snapshot URL"


def _retarget_url(url, src_host, dst_host):
    if not url:
        return url
    m = re.match(r"^([a-z]+://)([^/:]+)(.*)$", url, re.I)
    if m and m.group(2) == src_host:
        return m.group(1) + dst_host + m.group(3)
    return url


def _show_cams(p, cams):
    if not cams:
        log("  no cameras configured in Fluidd/Moonraker")
        return True
    good = True
    for c in cams:
        ok, why = _probe_cam(p, c)
        good = good and ok
        log("  %s  '%s'  service=%s  enabled=%s  source=%s" % ("[OK]" if ok else "[WARN]", c.get("name"),
            c.get("service", "?"), c.get("enabled", True), c.get("source", "?")))
        log("      stream:   %s" % (c.get("stream_url") or "-"))
        log("      snapshot: %s" % (c.get("snapshot_url") or "-"))
        log("      %s" % (("picture: " + why) if ok else ("no picture: " + why)))
    return good


def _cam_db(p):
    """Fluidd's own camera records: database namespace 'webcams', {uuid: {name, enabled, urlStream, ...}}.
    Fluidd 1.27 (on the Hi) shows only entries with enabled: true. The Hi's old Moonraker drops 'enabled' when a
    camera is added through /server/webcams/item, so we read and write these records directly."""
    try:
        res = p.req("GET", "/server/database/item", params={"namespace": "webcams"})
    except ToolError as e:
        if "404" in str(e):
            return {}
        raise
    val = res.get("value") if isinstance(res, dict) else None
    return {k: v for k, v in (val or {}).items() if isinstance(v, dict)}


def _to_db(cam, old=None):
    """Moonraker-style camera dict -> Fluidd database record (keeps any extra fields the old record had)."""
    rec = dict(old or {})
    rec.update({
        "name": cam.get("name"), "enabled": True, "service": cam.get("service", "iframe"),
        "urlStream": cam.get("stream_url", ""), "urlSnapshot": cam.get("snapshot_url", ""),
        "targetFps": int(cam.get("target_fps", 15) or 15), "targetFpsIdle": int(cam.get("target_fps_idle", 5) or 5),
        "flipX": bool(cam.get("flip_horizontal", False)), "flipY": bool(cam.get("flip_vertical", False)),
        "rotation": int(cam.get("rotation", 0) or 0), "aspectRatio": cam.get("aspect_ratio") or "16:9",
        "location": cam.get("location", "printer"), "icon": cam.get("icon") or "mdi-webcam",
    })
    return rec


def _from_db(rec):
    return {"name": rec.get("name"), "service": rec.get("service", ""), "enabled": rec.get("enabled", False),
            "stream_url": rec.get("urlStream", ""), "snapshot_url": rec.get("urlSnapshot", ""),
            "target_fps": rec.get("targetFps", 15), "target_fps_idle": rec.get("targetFpsIdle", 5),
            "flip_horizontal": rec.get("flipX", False), "flip_vertical": rec.get("flipY", False),
            "rotation": rec.get("rotation", 0), "aspect_ratio": rec.get("aspectRatio"),
            "location": rec.get("location", "printer"), "icon": rec.get("icon")}


def _db_put(p, key, rec):
    p.req("POST", "/server/database/item", body={"namespace": "webcams", "key": key, "value": rec}, retries=0)


def cmd_webcam(p, a):
    p.connect()
    db = _cam_db(p)
    by_name = {r.get("name"): (k, r) for k, r in db.items()}

    if a.action == "list":
        if not db:
            log("  no cameras in Fluidd")
            return True
        for k, r in db.items():
            cam = _from_db(r)
            ok, why = _probe_cam(p, cam)
            shown = r.get("enabled") is True
            log("  %s  '%s'  service=%s  %s" % ("[OK]" if ok and shown else "[WARN]", cam["name"], cam["service"],
                "shown in Fluidd" if shown else "HIDDEN in Fluidd (not enabled) - run 'webcam add' to fix"))
            log("      stream:   %s" % (cam["stream_url"] or "-"))
            log("      snapshot: %s" % (cam["snapshot_url"] or "-"))
            log("      %s" % (("picture: " + why) if ok else ("no picture: " + why)))
            if cam["stream_url"] and p.host not in cam["stream_url"] and re.match(r"^[a-z]+://", cam["stream_url"], re.I):
                log("      this points at ANOTHER printer's camera, not %s's own ('webcam add --replace' fixes it)"
                    % p.host, "WARN")
        return True

    if a.action == "remove":
        if not a.name:
            raise ToolError("webcam remove needs --name (see 'webcam list')")
        if a.name not in by_name:
            raise ToolError("no camera called '%s' (has: %s)" % (a.name, ", ".join(map(str, by_name)) or "none"))
        key, rec = by_name[a.name]
        if not a.apply:
            log("  DRY RUN - would remove camera '%s' (%s). Add --apply." % (a.name, rec.get("urlStream")))
            return True
        _save_cams(p, a, db, "before-remove")
        p.req("DELETE", "/server/database/item", params={"namespace": "webcams", "key": key}, retries=0)
        if a.name in {r.get("name") for r in _cam_db(p).values()}:
            raise ToolError("camera '%s' is still there after delete" % a.name)
        log("[OK] removed camera '%s' - reload Fluidd (F5)" % a.name)
        return True

    if a.action == "add":
        src_host = p.host
        src_cams = [hi_cam_entry(p.host, a.name or HI_CAM_NAME, a.port)]
    else:  # copy from another printer
        if not a.src:
            raise ToolError("webcam copy needs --from PRINTER (the one whose camera works in Fluidd)")
        src = Printer(a.src, api_key=a.api_key, timeout=a.timeout, retries=a.retries)
        src.connect()
        src_host = src.host
        if src.host == p.host:
            log("  this is the source printer itself - nothing to copy")
            return True
        src_cams = [_from_db(r) for r in _cam_db(src).values() if not a.name or r.get("name") == a.name]
        if not src_cams:
            raise ToolError("%s has no camera%s to copy" % (a.src, (" called '%s'" % a.name) if a.name else ""))

    todo = []
    for c in src_cams:
        new = dict(c)
        for k in ("stream_url", "snapshot_url"):
            new[k] = _retarget_url(new.get(k, ""), src_host, p.host)
        name = new.get("name")
        key, old = by_name.get(name, (None, None))
        if old:
            same = old.get("urlStream") == new.get("stream_url") and old.get("service") == new.get("service")
            if same and old.get("enabled") is True:
                log("  '%s' already here and shown in Fluidd - nothing to do" % name, "OK")
                continue
            if not same and not a.replace:
                log("  '%s' already here but points at %s - skipped (--replace to point it at %s)"
                    % (name, old.get("urlStream"), new.get("stream_url")), "WARN")
                continue
            action = "fix (mark enabled so Fluidd shows it)" if same else "replace"
        else:
            action = "add"
        ok, why = _probe_cam(p, new)
        log("  %s '%s' (%s)" % (action, name, new.get("service", "?")))
        log("      stream:   %s" % (new.get("stream_url") or "-"))
        log("      snapshot: %s" % (new.get("snapshot_url") or "-"))
        if ok:
            log("picture on this printer: %s" % why, "OK")
        else:
            log("no picture from this printer's camera yet (%s) - the entry still gets added, but Fluidd will "
                "show a blank tile until the camera on this printer is running" % why, "WARN")
        todo.append((key or str(uuid.uuid4()), _to_db(new, old)))
    if not todo:
        return True
    if not a.apply:
        log("  DRY RUN - nothing changed. Add --apply to write %d camera(s)." % len(todo))
        return True
    _save_cams(p, a, db, "before-webcam")
    for key, rec in todo:
        _db_put(p, key, rec)
    now = _cam_db(p)
    bad = [rec["name"] for key, rec in todo if (now.get(key) or {}).get("enabled") is not True]
    if bad:
        raise ToolError("written but not read back as enabled: %s" % ", ".join(bad))
    log("[OK] %d camera(s) written and enabled - reload Fluidd (F5) on %s" % (len(todo), p.host))
    return True


def _save_cams(p, a, cams, label):
    d = os.path.join(a.backup_dir, p.host)
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, "webcams_%s_%s.json" % (dt.datetime.now().strftime("%Y%m%d-%H%M%S"), label))
    with open(fn, "w", encoding="utf-8") as fh:
        json.dump(cams, fh, indent=2)
    log("  saved current camera list -> %s" % fn)


# --------------------------------------------------------------------------- Klipper beeper (M300)
# Klipper's Linux helper ([mcu rpi], klipper_mcu) can drive the buzzer as a hardware PWM pin, so slicer
# end-gcode can beep. This Klipper can't change a hardware PWM's period at runtime, so the pitch is fixed
# at install time (--freq); M300 P (length) works, S (pitch) is ignored.
BEEPER_REMOTE = "hi_beeper.cfg"
BEEPER_PIN_RE = re.compile(r"^\[(output_pin\s+hi_beeper|gcode_macro\s+(M300|BEEP))\]\s*$", re.I | re.M)


def beeper_cfg_text(freq):
    return """# hi_beeper.cfg - the Creality Hi's built-in piezo buzzer for Klipper. Installed by hi_tool.py.
# The buzzer sits on the Linux PWM controller (pwmchip0, channel 6), driven through Klipper's host MCU [mcu rpi].
#   M300 P500                       beep 500 ms (S = pitch is ignored: fixed at %(freq)d Hz, see cycle_time)
#   BEEP COUNT=3 MS=150 GAP=150      a few beeps
# M300 / BEEP use G4, so mid-print they pause motion for that long (like Marlin). Fine in end gcode.

[output_pin hi_beeper]
pin: rpi:pwmchip0/pwm6
pwm: True
hardware_pwm: True
cycle_time: %(cycle).8f
value: 0
shutdown_value: 0

[gcode_macro M300]
description: Beep the Hi buzzer. P=length ms (default 100). S ignored (fixed %(freq)d Hz)
gcode:
  {%% set ms = [[params.P|default(100)|int, 10]|max, 5000]|min %%}
  SET_PIN PIN=hi_beeper VALUE=0.5
  G4 P{ms}
  SET_PIN PIN=hi_beeper VALUE=0

[gcode_macro BEEP]
description: BEEP [COUNT=1] [MS=150] [GAP=150]
gcode:
  {%% set n = [[params.COUNT|default(1)|int, 1]|max, 10]|min %%}
  {%% set ms = [[params.MS|default(150)|int, 10]|max, 3000]|min %%}
  {%% set gap = [[params.GAP|default(150)|int, 10]|max, 3000]|min %%}
  {%% for i in range(n) %%}
    SET_PIN PIN=hi_beeper VALUE=0.5
    G4 P{ms}
    SET_PIN PIN=hi_beeper VALUE=0
    {%% if not loop.last %%}G4 P{gap}{%% endif %%}
  {%% endfor %%}
""" % {"freq": freq, "cycle": 1.0 / freq}


KLIPPER_MCU_INIT = "/etc/init.d/klipper_mcu"


def _check_mcu_init(p, a):
    """Show /etc/init.d/klipper_mcu and refuse anything that could flash or reset a motion board."""
    rc, out, err = _ssh_run(p, a, "cat %s 2>&1 | head -40; echo '--- running:'; ps w | grep -e klipper_mcu -e klippy.py "
                            "| grep -v grep" % KLIPPER_MCU_INIT, timeout=60)
    txt = out.decode("utf-8", "replace")
    for ln in txt.splitlines():
        log("    | " + ln)
    script = txt.split("--- running:")[0]
    # DEPEND= only orders services at boot; what a restart runs is in start_service()
    body = "\n".join(ln for ln in script.splitlines() if not ln.strip().startswith(("DEPEND=", "#")))
    risky = [w for w in ("flash", "mcu_update", "FIRMWARE", "dfu", "stm32", "gd32", "reboot") if w.lower() in body.lower()]
    if "No such file" in txt:
        log("  %s not found on this printer" % KLIPPER_MCU_INIT, "WARN")
        return False
    if risky:
        log("  klipper_mcu's init script mentions: %s" % ", ".join(risky), "WARN")
        return False
    return True


def _restart_stack(p, a):
    """Klipper's host MCU (klipper_mcu) stays shut down after a config change on the Hi, so restart it together with
    klippy: stop klippy, restart klipper_mcu, start klippy. Host programs only - the motion boards are not reset."""
    log("  restarting klipper_mcu + Klipper over SSH (host programs only)")
    rc, out, err = _ssh_run(p, a, "/etc/init.d/klipper stop >/tmp/hi_stack.log 2>&1; sleep 1; "
                            "%s restart >>/tmp/hi_stack.log 2>&1; sleep 2; echo MCU_PID=$(pidof klipper_mcu); "
                            "/etc/init.d/klipper start >>/tmp/hi_stack.log 2>&1; echo RC=$?" % KLIPPER_MCU_INIT,
                            timeout=120)
    txt = " ".join(out.decode("utf-8", "replace").split())
    log("  %s" % txt)
    if not re.search(r"MCU_PID=\d", txt):
        log("  klipper_mcu did not come back (see /tmp/hi_stack.log on the printer)", "WARN")
    time.sleep(5)
    ok, msg = p.wait_ready(240)
    if ok:
        time.sleep(a.motor_wait)
    return ok, msg


def cmd_install_beeper(p, a):
    if not a.revert:
        raise ToolError("install-beeper is not possible on the Hi: Creality's klipper_mcu refuses the buzzer PWM "
                        "('Unable to config pwm device'), Klipper then shuts down every MCU incl. the main board, and "
                        "only a power cycle recovers (tested on hi2, 2026-10-20). Use 'beep' over SSH instead. "
                        "(--revert still works to clean up)")
    if not 1000 <= a.freq <= 8000:
        raise ToolError("--freq 1000..8000")
    p.connect()
    st = p.assert_idle(a.force, keep_position=not getattr(a, "plate_clear", False))
    log("  state: klippy=%s print=%s" % (st["klippy"], st["print"]))
    remote = BEEPER_REMOTE
    files = {f["path"]: f for f in p.list_config()}
    pc_old = p.get_config("printer.cfg").decode("utf-8")
    old_cfg = p.get_config(remote) if remote in files else None

    if a.revert:
        pc_new = re.sub(r"^\[include\s+" + re.escape(remote) + r"\s*\]\s*\r?\n", "", pc_old, flags=re.I | re.M)
        if pc_new == pc_old and old_cfg is None:
            log("  beeper not installed - nothing to remove")
            return True
        log("  will remove [include %s] from printer.cfg and delete %s" % (remote, remote))
        new_cfg = None
    else:
        new_txt = beeper_cfg_text(a.freq)
        new_cfg = new_txt.encode("utf-8")
        for path in files:
            if path == remote or not path.lower().endswith(".cfg") or BACKUP_CFG_RE.match(os.path.basename(path)):
                continue
            m = BEEPER_PIN_RE.search(p.get_config(path).decode("utf-8", "replace"))
            if m:
                raise ToolError("[%s] already exists in %s - Klipper refuses duplicates, remove it there first"
                                % (m.group(1), path))
        if re.search(r"rpi:pwmchip0/pwm6", pc_old):
            raise ToolError("printer.cfg already uses rpi:pwmchip0/pwm6 - not touching it")
        pc_new = _add_include(pc_old, remote) or pc_old
        if old_cfg is not None and sha(old_cfg) == sha(new_cfg) and pc_new == pc_old:
            log("  beeper already installed (%d Hz) - nothing to do. Test it with: gcode %s M300 P300" % (a.freq, p.name), "OK")
            return True
        log("  %s: %s, %d Hz" % (remote, "new file" if old_cfg is None else "update", a.freq))
        if pc_new != pc_old:
            for ln in difflib.unified_diff(pc_old.splitlines(), pc_new.splitlines(), "a/printer.cfg", "b/printer.cfg",
                                           lineterm="", n=1):
                log("    " + ln)
    ok_init = _check_mcu_init(p, a)
    if not a.apply:
        log("  DRY RUN - nothing changed. --apply uploads, restarts klipper_mcu + Klipper over SSH and test-beeps "
            "(rolls back the same way on failure).")
        return True
    if not ok_init:
        raise ToolError("the klipper_mcu init script looks unusual (see above) - not restarting it automatically")

    bdir, originals = backup(p, a.backup_dir, "before-beeper-remove" if a.revert else "before-beeper")
    if sha(originals.get("printer.cfg", b"")) != sha(pc_old.encode("utf-8")):
        raise ToolError("printer.cfg changed on the printer while we were working - aborting")
    try:
        if new_cfg is not None:
            p.upload_config(remote, new_cfg)
            log("  uploaded + verified %s" % remote)
        if pc_new != pc_old:
            p.upload_config("printer.cfg", pc_new.encode("utf-8"))
            log("  uploaded + verified printer.cfg")
        if a.revert and old_cfg is not None:
            p.req("DELETE", "/server/files/config/" + urllib.parse.quote(remote))
        ok, msg = _restart_stack(p, a)
    except ToolError as e:
        ok, msg = False, str(e)
    if ok and not a.revert:
        time.sleep(a.motor_wait)
        cfg = p.configfile().get("config", {})
        if not any(k.lower() == "output_pin hi_beeper" for k in cfg):
            ok, msg = False, "Klipper did not load [output_pin hi_beeper]"
        else:
            okb, errb, msgs = _gcode_capture(p, "M300 P300", timeout=20)
            if not okb:
                ok, msg = False, "M300 failed: %s" % errb
    if not ok:
        log("  problem: %s" % (msg.strip() or "Klipper didn't come back ready after RESTART (the beeper pin was refused?)"), "ERROR")
        log("  rolling back from %s" % bdir, "ERROR")
        try:
            p.upload_config("printer.cfg", originals["printer.cfg"])
            if old_cfg is not None:
                p.upload_config(remote, old_cfg)
            elif new_cfg is not None:
                p.req("DELETE", "/server/files/config/" + urllib.parse.quote(remote))
        except ToolError as e:
            log("  rollback failed: %s" % e, "ERROR")
        ok2, msg2 = _restart_stack(p, a)
        log("  after rollback: %s %s" % ("ready" if ok2 else "NOT ready", msg2), "ERROR")
        return False
    if a.revert:
        log("beeper removed (backup: %s)" % bdir, "OK")
    else:
        log("beeper installed - it just played M300 P300. Did you hear it? (backup: %s)" % bdir, "OK")
        log("  slicer end gcode:  M300 P500    or   BEEP COUNT=3")
    return True


# --------------------------------------------------------------------------- CFS (Creality Filament System)
# Creality's compiled box module (extras/box_wrapper*.so) talks to the CFS over RS485 (/dev/ttyS5) and keeps slot
# data in /mnt/UDISK/creality/userdata/box/tn_data.json. 'cfs status' / 'cfs debug' are read-only.
CFS_OBJ_RE = re.compile(r"box|filament|rack|material|motor_control|serial_485|auto_addr", re.I)
CFS_SSH = r"""
D=/mnt/UDISK/creality/userdata
echo '== box files'; ls -la $D/box 2>&1 | head -30
for f in $D/box/tn_data.json $D/box/material_box_info.json $D/config/material_box_info.json $D/config/material_box_config.json; do
  [ -f "$f" ] && { echo "== $f"; head -c 6000 "$f"; echo; }
done
echo '== klippy.log: box / CFS / 485 lines (last 60)'
grep -a -i -e 'box' -e 'cfs' -e 'T[0-9][A-D]' -e 'rfid' -e 'remain_len' -e 'key[0-9]' /mnt/UDISK/printer_data/logs/klippy.log 2>/dev/null \
  | grep -v -e 'objects/query' -e 'subscribe' | tail -60
"""


def _cfs_objects(p):
    objs = p.req("GET", "/printer/objects/list").get("objects", [])
    return [o for o in objs if CFS_OBJ_RE.search(o)]


def cfs_slots(box):
    """box status -> list of dicts, one per slot of every connected box."""
    out = []
    for b in range(1, 5):
        u = box.get("T%d" % b) or {}
        if u.get("state") in (None, "None", "-1"):
            continue
        for i, letter in enumerate("ABCD"):
            def g(key, i=i):
                v = u.get(key)
                return v[i] if isinstance(v, list) and len(v) > i else None
            col = g("color_value")
            out.append({"slot": "T%d%s" % (b, letter), "box": b, "loaded": u.get("filament") == letter,
                        "material": g("material_type"), "color": None if col in (None, "-1") else "#" + col[-6:],
                        "remain": g("remain_len"), "vendor": g("vender"),
                        "empty": g("material_type") in (None, "-1") and g("remain_len") in (None, "-1")})
    return out


def _cfs_summary(st):
    box = st.get("box") or {}
    if not box:
        log("  no 'box' object - no CFS configured on this printer", "WARN")
        return
    names = {m[0]: m[3] for m in box.get("same_material") or [] if len(m) > 3}
    log("  CFS: %s, auto refill %s, enabled %s, filament %s, cutter %s"
        % (box.get("state"), "on" if box.get("auto_refill") else "off", box.get("enable"),
           "loaded" if box.get("filament") else "none", "ok" if box.get("cut_state") else "NOT OK"))
    for b in range(1, 5):
        u = box.get("T%d" % b) or {}
        if u.get("state") in (None, "None", "-1"):
            continue
        log("  box T%d: %s  %s C  %s %% RH  fw %s  sn %s  mode %s"
            % (b, u.get("state"), u.get("temperature"), u.get("dry_and_humidity"), u.get("version"), u.get("sn"), u.get("mode")))
    for sl in cfs_slots(box):
        if sl["empty"]:
            log("    %s  (empty)" % sl["slot"])
            continue
        mat = names.get(sl["material"], sl["material"])
        log("    %s  %-6s %-9s remaining %s%s" % (sl["slot"], mat, sl["color"] or "-", sl["remain"],
                                                 "   <- LOADED in the toolhead" if sl["loaded"] else ""),
            "OK" if sl["loaded"] else "INFO")
    sens = {k.split(" ", 1)[1]: v for k, v in st.items() if k.startswith("filament_switch_sensor ")}
    if sens:
        log("  sensors: " + ", ".join("%s=%s%s" % (k, "filament" if v.get("filament_detected") else "empty",
                                                   "" if v.get("enabled") else " (off)") for k, v in sens.items()))


def cmd_cfs(p, a):
    p.connect()
    objs = [o for o in _cfs_objects(p) if not o.startswith("gcode_macro ")]
    st = p.query(*objs) if objs else {}
    d = os.path.join(a.backup_dir, p.host)
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, "cfs_%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    with open(fn, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1, default=str)
    log("  CFS-related Klipper objects: %s" % (", ".join(objs) or "none"))
    _cfs_summary(st)
    if a.action == "debug":
        for name in objs:
            if name == "box":
                continue
            log("  [%s] %s" % (name, json.dumps(st.get(name, {}), default=str)[:400]))
    log("  full status saved -> %s" % fn)
    if a.action == "debug":
        rc, out, err = _ssh_run(p, a, CFS_SSH, timeout=a.ssh_timeout)
        for ln in out.decode("utf-8", "replace").splitlines():
            log("  " + ln)
        if err:
            log(err, "WARN")
    return True



MATDB = "/mnt/UDISK/creality/userdata/box/material_database.json"


def cmd_cfs_material(p, a):
    """Read only: save the CFS material database and list the entries that mention a material (default PETG)."""
    rc, out, err = _ssh_run(p, a, "cat %s" % MATDB, timeout=a.ssh_timeout)
    if rc != 0 or not out:
        raise ToolError("could not read %s (rc=%s) %s" % (MATDB, rc, err))
    d = os.path.join(a.backup_dir, p.host)
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, "material_database_%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    with open(fn, "wb") as fh:
        fh.write(out)
    log("  saved %d bytes -> %s" % (len(out), fn))
    try:
        data = json.loads(out.decode("utf-8", "replace"))
    except ValueError as e:
        log("  not valid JSON (%s); first 600 chars:" % e, "WARN")
        log(out[:600].decode("utf-8", "replace"))
        return True
    log("  top level: %s" % (("keys " + ", ".join(list(data)[:20])) if isinstance(data, dict) else "list of %d" % len(data)))
    want = a.material.lower()
    hits = []

    def walk(o, path):
        if isinstance(o, dict):
            if any(isinstance(v, str) and want in v.lower() for v in o.values()):
                hits.append((path, o))
                return
            for k, v in o.items():
                walk(v, path + "/" + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + "[%d]" % i)
    walk(data, "")
    log("  entries mentioning '%s': %d" % (a.material, len(hits)))
    for path, o in hits[:12]:
        log("  %s  %s" % (path, json.dumps(o, ensure_ascii=False)[:700]))
    if not hits:
        log("  nothing matched; first 800 chars of the file:")
        log(out[:800].decode("utf-8", "replace"))
    return True


def _shutdown_board(msg):
    """Which MCU a Klipper error says is shut down: "MCU 'mcu' shutdown: ..." or "Can not update MCU rpi config as it
    is shutdown" (key298). None if no board is named."""
    m = re.search(r"MCU '([^']+)'[^\"]*shutdown", msg) or re.search(r"MCU (\w+) config as it is shutdown", msg)
    return m.group(1) if m else None


def cmd_recover(p, a):
    """Klipper not ready? Read why and do the right fix: host problems -> restart klipper_mcu + Klipper over SSH;
    a shut-down motion board -> say so (only a power cycle helps on the Hi; FIRMWARE_RESTART doesn't)."""
    p.connect()
    try:
        info = p.req("GET", "/printer/info", timeout=5, retries=1)
    except ToolError as e:
        info = {"state": "unreachable", "state_message": str(e)}
    state, msg = info.get("state", "?"), (info.get("state_message") or "").strip()
    log("  Klipper: %s" % state)
    if msg:
        log("  message: %s" % msg)
    if state == "ready":
        log("Klipper is ready - nothing to recover", "OK")
        return True
    board = _shutdown_board(msg)
    if board and board != "rpi":
        log("the '%s' board is shut down - on the Hi only a power cycle clears that (FIRMWARE_RESTART does not). "
            "Switch the printer off and on." % board, "WARN")
        return False
    log("  %s - restarting klipper_mcu + Klipper over SSH" % ("host MCU (rpi) is shut down" if board == "rpi"
                                                              else "Klipper is not ready"))
    if not a.apply:
        log("  DRY RUN - add --apply")
        return True
    ok, msg2 = _restart_stack(p, a)
    if ok:
        log("recovered - Klipper is ready", "OK")
        return True
    log("still not ready: %s" % (msg2 or "?"), "ERROR")
    b2 = _shutdown_board(msg2 or "")
    if b2 and b2 != "rpi":
        log("now the '%s' board is shut down - power-cycle the printer" % b2, "WARN")
    return False


# --------------------------------------------------------------------------- printing guard
# Every command that can change or move anything first checks the printer is NOT printing (or paused, or heating
# for a print started from the screen/app). Only plain reads and dry runs skip the check. --force overrides.
READ_ONLY_CMDS = {"grab-check", "pull-logs", "ui-log", "watch-ota", "cloud-hosts", "cfs", "info", "pull", "errors", "homing", "fetch-src", "pa-fleet", "ram-check"}
READ_ONLY_ACTIONS = {"pa": {"status", "firmware", "preflight", "tower", "watch", "history"}, "webcam": {"list"}}
DRY_RUN_CMDS = {"recover", "install-beeper", "fix-homing", "fix-fan", "fix-dir", "fix-sdcard", "block-ota", "fix-grab", "install-ram", "ram", "recover-z", "jog-z", "restore",
                "webcam", "test-home"}


def _is_read_only(a):
    if a.cmd in READ_ONLY_CMDS:
        return True
    if getattr(a, "action", None) in READ_ONLY_ACTIONS.get(a.cmd, ()):
        return True
    if a.cmd == "beep" and (getattr(a, "probe", False) or getattr(a, "deep", False)):
        return True
    if a.cmd == "pa" and a.action in ("set", "save", "test") and not getattr(a, "apply", False):
        return True
    if a.cmd in DRY_RUN_CMDS and getattr(a, "apply", None) is False:
        return True
    return False


def guard_not_printing(p, a):
    """Raise ToolError if the printer is printing / paused / heating. Names the job so a wrong pick is obvious."""
    try:
        p.assert_idle(getattr(a, "force", False))
    except ToolError as e:
        job = ""
        try:
            s = p.query("print_stats", "virtual_sdcard")
            fn = s.get("print_stats", {}).get("filename") or ""
            pr = s.get("virtual_sdcard", {}).get("progress")
            if fn:
                job = " - job: %s%s" % (fn, " (%.0f%%)" % (pr * 100) if pr is not None else "")
        except ToolError:
            pass
        raise ToolError("%s is BUSY%s. Not doing '%s'. (wrong printer? add --force only if you're sure)\n    %s"
                        % (p.name, job, a.cmd + (" " + a.action if getattr(a, "action", None) else ""), e))


COMMANDS = {
    "info": cmd_info, "pull": cmd_pull, "errors": cmd_errors, "homing": cmd_homing,
    "fix-homing": cmd_fix, "test-home": cmd_test, "gcode": cmd_gcode, "restore": cmd_restore,
    "fetch-src": cmd_fetch_src, "ssh": cmd_ssh, "diagnose-home": cmd_diagnose, "repro-restart": cmd_repro, "repro-fault": cmd_repro_fault, "restart": cmd_restart, "check-dir": cmd_check_dir, "prove-dir": cmd_prove_dir, "fix-dir": cmd_fix_dir, "fix-sdcard": cmd_fix_sdcard, "restart-service": cmd_restart_service, "fix-fan": cmd_fix_fan, "block-ota": cmd_block_ota, "watch-ota": cmd_watch_ota, "cloud-hosts": cmd_cloud_hosts, "ui-log": cmd_ui_log, "pull-logs": cmd_pull_logs, "fix-grab": cmd_fix_grab, "grab-check": cmd_grab_check,
    "install-ram": cmd_install_ram, "ram": cmd_ram, "ram-check": cmd_ram_check, "recover-z": cmd_recover_z, "jog-z": cmd_jog_z,
    "webcam": cmd_webcam, "pa": cmd_pa, "pa-fleet": cmd_pa_fleet, "beep": cmd_beep, "install-beeper": cmd_install_beeper, "cfs": cmd_cfs, "cfs-material": cmd_cfs_material, "recover": cmd_recover,
}


def main(argv=None):
    global _LOG_FH
    ap = argparse.ArgumentParser(description="Creality Hi / Klipper Moonraker tool", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("Commands", 1)[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp, targets=True):
        if targets:
            sp.add_argument("targets", nargs="*", help="last IP number (104), HOST[:PORT] or NAME=HOST[:PORT]")
            sp.add_argument("-f", "--file", help="file with one target per line (# comments ok)")
        sp.add_argument("--api-key")
        sp.add_argument("--timeout", type=float, default=10)
        sp.add_argument("--retries", type=int, default=3)
        sp.add_argument("--backup-dir", default="hi_backups")
        sp.add_argument("--force", action="store_true", help="allow while printing/paused")
        sp.add_argument("--plate-clear", action="store_true",
                        help="ok to forget the parked END_PRINT height (nothing on the plate waiting to be rammed)")
        sp.add_argument("--lines", type=int, default=30)
        sp.add_argument("--home-timeout", type=float, default=120)

    def ssh_opts(sp):
        sp.add_argument("--ssh-password", help="root password (default: DEFAULT_SSH_PASSWORD in this file)")
        sp.add_argument("--ssh-user", default="root")
        sp.add_argument("--ssh-port", type=int, default=22)
        sp.add_argument("--ssh-timeout", type=float, default=120)

    sp = sub.add_parser("check-dir")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--motor-wait", type=float, default=15)
    sp.add_argument("--home-after", action="store_true",
                    help="also home straight after the restart (crashes forward if the pin flipped)")

    sp = sub.add_parser("prove-dir")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--y", type=float, default=150.0, help="where the last Y move ends")
    sp.add_argument("--step", type=float, default=50.0, help="length of the last Y move")
    sp.add_argument("--only", choices=["backward", "forward"], help="run just one trial")
    sp.add_argument("--expect-fixed", action="store_true", help="after fix-dir: both trials should home normally")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("fix-dir")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--revert", action="store_true", help="put the original homing.py back")
    sp.add_argument("--yes", action="store_true", help="don't ask before restarting the service")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("fix-sdcard")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--revert", action="store_true", help="put the original virtual_sdcard.py back")
    sp.add_argument("--yes", action="store_true", help="don't ask before restarting the service")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("watch-ota", help="watch outside connections + new log lines while you press 'check for update' on the printer (read only)")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--seconds", type=int, default=90)

    sp = sub.add_parser("cloud-hosts", help="read only: list Creality host names/URL paths inside the Hi's own programs and config")
    common(sp)
    ssh_opts(sp)

    sp = sub.add_parser("ui-log", help="read only: search the Hi's UI/Klipper/Moonraker logs for extrude/filament/heat events in a time window")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--from", dest="time_from", default="2026-10-29", help="a date (whole day) or '2026-10-29 16:30'")
    sp.add_argument("--to", dest="time_to", default="2026-10-29")

    sp = sub.add_parser("pull-logs", help="read only: save ALL the Hi's logs (UI/app servers, Klipper, Moonraker, system) to hi_backups/")
    common(sp)
    ssh_opts(sp)

    sp = sub.add_parser("fix-grab", help="load button: if the filament sensor is triggered, turn the extruder a few mm cold so it holds the filament while heating (dry run unless --apply)")
    common(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--revert", action="store_true", help="back to Creality's stock load button")
    sp.add_argument("--mm", type=float, default=4.0, help="how far to turn the extruder, mm (default 4)")
    sp.add_argument("--speed", type=float, default=5.0, help="mm/s (default 5)")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("grab-check", help="read only: did the load button call GRAB_FILAMENT?")
    common(sp)
    ssh_opts(sp)

    sp = sub.add_parser("block-ota", help="hide Creality firmware updates by pointing update hosts at 0.0.0.0 (dry run unless --apply)")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--revert", action="store_true", help="remove our block from /etc/hosts")
    sp.add_argument("--hosts", help="extra host names to block, comma separated")
    sp.add_argument("--keep", action="store_true", help="keep hosts we already blocked even if the scan no longer lists them")

    sp = sub.add_parser("restart-service")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--yes", action="store_true", help="don't ask before restarting")
    sp.add_argument("--with-mcu", action="store_true",
                    help="also restart klipper_mcu (fixes \"MCU 'rpi' ... shutdown\"); host programs only")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("fix-fan", help="make M106 S255 a true 100%% part fan (dry run unless --apply)")
    common(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--revert", action="store_true", help="remove the fix, back to Creality's halved fan")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("install-ram", help="install/update ramming.cfg (REMOVE_PART_DYNAMIC); dry run unless --apply")
    common(sp)
    sp.add_argument("--cfg", help="local ramming file (default: ramming.cfg next to hi_tool.py)")
    sp.add_argument("--remote-name", default=RAM_REMOTE, help="file name in the printer's config folder")
    sp.add_argument("--keep-park", action="store_true",
                    help="parked after END_PRINT: remember Klipper's X/Y/Z, RESTART, then put them back (unhomed, nothing moves) "
                         "so 'parked after END_PRINT' ramming still works without Recover Z")
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--motor-wait", type=float, default=15)

    for name in ("ram", "ram-check"):
        sp = sub.add_parser(name, help="run REMOVE_PART_DYNAMIC now (dry run unless --apply)" if name == "ram"
                            else "check the printer + part are ready to ram (moves nothing)")
        sp.add_argument("target")
        common(sp, targets=False)
        sp.add_argument("--gcode", dest="gcode_file", help="sliced .gcode (or .gcode.3mf) to read centre, height and outlines from")
        sp.add_argument("--plate", type=int, help="which plate, when --gcode is a .gcode.3mf with several")
        sp.add_argument("--center-x", type=float)
        sp.add_argument("--center-y", type=float)
        sp.add_argument("--top-z", type=float)
        sp.add_argument("--wait", type=int, default=0, help="cool-down seconds before ramming (default 0)")
        sp.add_argument("--lanes", type=int, default=1)
        sp.add_argument("--spacing", type=float, default=40.0)
        sp.add_argument("--push-to-edge", action="store_true", default=True,
                        help="push all the way to Y min (default)")
        sp.add_argument("--stop-short", dest="push_to_edge", action="store_false",
                        help="stop ram_start_before_center short of the part centre instead of pushing to Y min")
        sp.add_argument("--ram-speed", type=int, help="push feedrate mm/min (default: macro's ram_speed)")
        sp.add_argument("--from-park", action="store_true",
                        help="printer was left unhomed by END_PRINT: set the parked position and G28 X Y (never Z)")
        sp.add_argument("--casing-depth", type=float, default=56.0,
                        help="ignored - the casing geometry is measured (CASING_* in hi_tool.py / ramming.cfg)")
        sp.add_argument("--cfg", help="local ramming.cfg to compare with the printer's copy")
        if name == "ram":
            sp.add_argument("--apply", action="store_true")
            sp.add_argument("--skip-check", action="store_true", help="ram even if the readiness check fails")

    sp = sub.add_parser("recover-z", help="re-find Z after a restart without G28 Z (paper test at a spot clear of the parts)")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--step", required=True, choices=["home-xy", "goto", "jog", "set"])
    sp.add_argument("--park-x", type=float, default=0.0, help="where END_PRINT left the toolhead (default X0)")
    sp.add_argument("--park-y", type=float, default=260.0, help="where END_PRINT left the toolhead (default Y260)")
    sp.add_argument("--height", type=float, help="goto: measured nozzle tip height above the bed (mm)")
    sp.add_argument("--gcode", dest="gcode_file", help="goto: sliced gcode, to find a spot clear of the parts")
    sp.add_argument("--top-z", type=float)
    sp.add_argument("--spot", help="goto: X,Y to use instead of finding one")
    sp.add_argument("--casing-depth", type=float, default=56.0)
    sp.add_argument("--dz", type=float, help="jog: mm, negative = down")
    sp.add_argument("--paper", type=float, default=0.1, help="set: nozzle height when the paper drags (default 0.1)")
    sp.add_argument("--apply", action="store_true")

    sp = sub.add_parser("jog-z", help="move Z without homing (unlock with a guessed height, then small jogs)")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--unlock", type=float, help="tell Klipper the toolhead is at this Z (nothing moves)")
    sp.add_argument("--dz", type=float, help="jog Z by this many mm (negative = down), max 20")
    sp.add_argument("--lock", action="store_true", help="done: motors off so nothing counts as homed any more")
    sp.add_argument("--speed", type=int, default=600, help="mm/min (default 600 = 10 mm/s)")
    sp.add_argument("--apply", action="store_true")

    sp = sub.add_parser("pa", help="pressure advance: status / set / save / test / firmware (dry run unless --apply)")
    sp.add_argument("action", choices=["status", "set", "save", "test", "firmware", "preflight", "tower", "watch",
                                       "history", "verify"])
    sp.add_argument("target")
    common(sp, targets=False)
    ssh_opts(sp)
    sp.add_argument("--k", type=float, help="set/save: pressure advance value")
    sp.add_argument("--smooth", type=float, help="set/save/test: pressure_advance_smooth_time (default: keep)")
    sp.add_argument("--gcode", dest="gcode_file", help="status: also show what this sliced file does with PA")
    sp.add_argument("--start", type=float, default=0.0)
    sp.add_argument("--end", type=float, default=0.1)
    sp.add_argument("--step", type=float, default=0.005)
    sp.add_argument("--nozzle-temp", type=int, default=220)
    sp.add_argument("--bed-temp", type=int, default=60)
    sp.add_argument("--slow", type=float, default=20.0, help="test: slow section mm/s")
    sp.add_argument("--fast", type=float, default=100.0, help="test: fast section mm/s")
    sp.add_argument("--accel", type=int, default=5000)
    sp.add_argument("--mesh", choices=["load", "calibrate", "none"], default="load",
                    help="test: load the saved 'default' mesh (default), probe a new one, or none")
    sp.add_argument("--name", help="test: file name on the printer")
    sp.add_argument("--motor-wait", type=float, default=15, help="save: seconds to wait after RESTART for servo init")
    sp.add_argument("--upload", action="store_true", help="test: upload the gcode to the printer")
    sp.add_argument("--print", dest="print_it", action="store_true", help="test: upload and start printing it")
    sp.add_argument("--height", type=float, help="tower: best height in mm -> K")
    sp.add_argument("--minutes", type=float, default=180, help="watch: give up after this long")
    sp.add_argument("--interval", type=float, default=2, help="watch: seconds between polls")
    sp.add_argument("--keep-watching", dest="until_done", action="store_false",
                    help="watch: don't stop when the print ends")
    sp.add_argument("--count", type=int, default=1000, help="history: console lines to search")
    sp.add_argument("--via-print", action="store_true", help="verify: also run a tiny no-heat no-motion print file "
                    "that changes K (needs --apply)")
    sp.add_argument("--apply", action="store_true")

    sp = sub.add_parser("pa-fleet", help="pressure advance on several printers, one line each (read-only)")
    common(sp)

    sp = sub.add_parser("install-beeper", help="Klipper M300/BEEP on the Hi buzzer (dry run unless --apply, --revert removes)")
    common(sp)
    sp.add_argument("--freq", type=int, default=BEEP_LOUD_HZ, help="beeper pitch in Hz, fixed at install (default %d)" % BEEP_LOUD_HZ)
    sp.add_argument("--revert", action="store_true")
    ssh_opts(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("recover", help="Klipper not ready? diagnose and fix host-side problems over SSH (dry run unless --apply)")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("cfs", help="CFS box: status (Klipper objects) / debug (+ slot files and box log lines over SSH) - read-only")
    sp.add_argument("action", choices=["status", "debug"])
    common(sp)
    ssh_opts(sp)

    sp = sub.add_parser("cfs-material", help="read only: save the CFS material database from the printer and list the entries for a material")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--material", default="PETG")

    sp = sub.add_parser("beep", help="beep the Hi's buzzer over SSH (--probe: read-only search)")
    sp.add_argument("target")
    common(sp, targets=False)
    ssh_opts(sp)
    sp.add_argument("--probe", action="store_true")
    sp.add_argument("--deep", action="store_true", help="read-only: device tree, drivers, kernel config, screen programs")
    sp.add_argument("--pwm", type=int, help="beep the buzzer on this PWM channel (Hi: %d)" % BEEP_PWM_CH)
    sp.add_argument("--freq", type=int, default=BEEP_LOUD_HZ, help="--pwm tone in Hz (default %d, the loudest)" % BEEP_LOUD_HZ)
    sp.add_argument("--transpose", type=int, default=0, help="shift --tune/--notes by this many semitones (+12 = octave up)")
    sp.add_argument("--tune", help="play a built-in jingle: " + ", ".join(sorted(TUNES)))
    sp.add_argument("--notes", help="play your own: 'C7:150 E7:150 -:100 G7:300' (note or Hz, :ms, - = rest)")
    sp.add_argument("--ms", type=int, default=200, help="--pwm beep length in ms (default 200)")
    sp.add_argument("--file", default=BEEP_WAV, help="sound file on the printer (default: Creality's button beep)")
    sp.add_argument("--times", type=int, default=1, help="number of beeps (default 1)")

    sp = sub.add_parser("webcam", help="add / list / remove the Fluidd camera (add and remove are dry runs unless --apply)")
    sp.add_argument("action", choices=["add", "list", "remove", "copy"])
    sp.add_argument("--port", type=int, default=HI_CAM_PORT, help="add: camera port on the printer (Hi: 8000)")
    common(sp)
    sp.add_argument("--from", dest="src", help="copy: printer whose camera already works in Fluidd")
    sp.add_argument("--name", help="add: camera name (default HICAM); copy: only this camera; remove: the camera to remove")
    sp.add_argument("--replace", action="store_true", help="add/copy: overwrite a camera with the same name")
    sp.add_argument("--apply", action="store_true")

    sp = sub.add_parser("restart", help="host RESTART only (never FIRMWARE_RESTART)")
    common(sp)
    sp.add_argument("--motor-wait", type=float, default=15)

    sp = sub.add_parser("repro-fault")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--x", type=float, default=130.0)
    sp.add_argument("--y", type=float, default=250.0, help="where the bed starts before the push")
    sp.add_argument("--push", type=float, default=40.0, help="mm to push forward (runs ~20 mm past the end)")
    sp.add_argument("--push-speed", type=float, default=20.0, help="mm/s for the push")
    sp.add_argument("--normal-mode", dest="homing_mode", action="store_false",
                    help="push in normal mode (Creality auto-clears the fault) instead of homing mode")

    sp = sub.add_parser("repro-restart")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--x", type=float, default=130.0)
    sp.add_argument("--y", type=float, default=260.0)
    sp.add_argument("--rounds", type=int, default=3)
    sp.add_argument("--speed", type=int, default=6000)
    sp.add_argument("--m84", action="store_true", help="turn motors off before RESTART (12:19 had them on)")
    sp.add_argument("--motor-wait", type=float, default=15)
    sp.add_argument("--keep-going", action="store_true", help="keep doing rounds after a failure")
    sp.add_argument("--no-ask", dest="ask", action="store_false", help="don't ask what you saw")

    sp = sub.add_parser("diagnose-home")
    sp.add_argument("target")
    common(sp, targets=False)
    sp.add_argument("--axis", default="Y", choices=["X", "Y", "x", "y"])
    sp.add_argument("--target", dest="target_pos", type=float, help="position to park at (default Y260 / X250)")
    sp.add_argument("--by-hand", action="store_true", help="after motors off, you push it to the end by hand")
    sp.add_argument("--restart-first", action="store_true", help="send RESTART after parking, like this morning's failure")
    sp.add_argument("--motor-wait", type=float, default=15)
    sp.add_argument("--speed", type=int, default=6000)

    sp = sub.add_parser("fetch-src")
    common(sp)
    ssh_opts(sp)
    sp.add_argument("--src-path", default="/usr/share/klipper/klippy")
    sp = sub.add_parser("ssh")
    sp.add_argument("target")
    sp.add_argument("remote", nargs="+", help="command to run on the printer, in quotes")
    common(sp, targets=False)
    ssh_opts(sp)

    for name in ("info", "pull", "errors", "homing"):
        sp = sub.add_parser(name)
        common(sp)
        if name == "errors":
            sp.add_argument("--save", action="store_true", help="also save klippy.log locally")
    for name in ("fix-homing", "test-home"):
        sp = sub.add_parser(name)
        common(sp)
        sp.add_argument("--apply", action="store_true")
        sp.add_argument("--test", action="store_true", help="run the corner stress test after patching")
        sp.add_argument("--margin", type=float, default=8.0, help="mm from the end of travel to park at")
        sp.add_argument("--rounds", type=int, default=2)
        sp.add_argument("--speed", type=int, default=6000)
        sp.add_argument("--keep-going", action="store_true")
        sp.add_argument("--motor-wait", type=float, default=15, help="seconds to wait after RESTART for servo init")
    sp = sub.add_parser("gcode")
    sp.add_argument("target")
    sp.add_argument("script", nargs="+", help="gcode; use \\n between lines")
    common(sp, targets=False)
    sp = sub.add_parser("restore")
    sp.add_argument("target")
    sp.add_argument("folder")
    sp.add_argument("--apply", action="store_true")
    common(sp, targets=False)

    a = ap.parse_args(argv)
    if a.cmd in ("gcode", "pa", "beep", "restore", "ssh", "ram", "ram-check", "recover-z", "jog-z", "diagnose-home", "repro-restart", "repro-fault", "check-dir", "prove-dir"):
        targets = [a.target]
    else:
        targets = list(a.targets)
        if a.file:
            with open(a.file, encoding="utf-8") as fh:
                targets += [l.split("#", 1)[0].strip() for l in fh if l.split("#", 1)[0].strip()]
    if not targets:
        ap.error("no printers given")
    bad = [t for t in targets if not re.fullmatch(r"(?:[A-Za-z0-9_-]+=)?(?:https?://)?[A-Za-z0-9.-]+(?::\d+)?/?", t)
           or not re.search(r"\d", t)]
    if bad:
        ap.error("these don't look like printers: %s (only put the IP / last number on the command line)" % bad)

    os.makedirs(a.backup_dir, exist_ok=True)
    if _LOG_FH:
        try:
            _LOG_FH.close()
        except Exception:
            pass
    _LOG_FH = open(os.path.join(a.backup_dir, "hi_tool.log"), "a", encoding="utf-8")
    if a.cmd == "test-home" and not getattr(a, "apply", False):
        log("test-home moves the printer near the ends of travel and re-homes. Add --apply to run it.", "WARN")
        log("(on an unpatched Hi this reproduces the key22 crash into the frame)", "WARN")
        return 2

    summary = []
    for t in targets:
        p = Printer(t, api_key=a.api_key, timeout=a.timeout, retries=a.retries)
        log("=== %s  %s ===" % (a.cmd, t))
        try:
            if not _is_read_only(a):
                guard_not_printing(p, a)
            ok = COMMANDS[a.cmd](p, a)
        except ToolError as e:
            log("  %s" % e, "ERROR")
            ok = False
        except KeyboardInterrupt:
            log("  interrupted", "ERROR")
            summary.append((t, False))
            break
        except Exception as e:  # last line of defence: never let one printer kill the run
            log("  unexpected %s: %s" % (type(e).__name__, e), "ERROR")
            ok = False
        summary.append((t, ok))
    if len(summary) > 1:
        log("=== summary ===")
        for t, ok in summary:
            log("  %-30s %s" % (t, "OK" if ok else "FAILED"))
    return 0 if all(ok for _, ok in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
