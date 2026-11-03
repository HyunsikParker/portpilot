"""Run a ported project's own CTest suite on a QNX 8.0 QEMU target.

    stage  (runs on the Windows build host, stdlib only): ask CTest for the test list, then write a qnx6 filesystem
           image holding every test executable, the project's shared libraries and its working directories, plus a
           run.sh that executes each test with a time limit and prints one marker line per result.
    run    (driver): push this file, stage the bundle, boot the mkqnximage VM with the bundle as a second disk, pull
           the serial console and turn the marker lines into runs/target_<cpu>.json.

The VM image carries a boot hook (vm/post_start.custom) that mounts /dev/hd1 on /tests, runs /tests/run.sh and shuts
down, so a test run never needs a rebuilt system image.
usage: python -m portpilot.target run fmt spdlog yaml-cpp [--cpu x86_64] [--deadline 3600]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REMOTE_ROOT = r"C:\Users\dev\Documents\portpilot-work\pp"
VM_ROOT = r"C:\Users\dev\Documents\portpilot-work\qnxvm"
SDP_ENV = r"C:\Users\dev\qnx800\qnxsdp-env.bat"
DEFAULT_TIMEOUT = 300  # seconds per test; the VM runs under TCG, so CTest's 1500 s default is far too generous
SKIP_DIRS = {".git", "CMakeFiles", "__pycache__"}
SKIP_EXT = {".o", ".obj", ".a", ".lib", ".ninja", ".d", ".pdb", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp",
            ".inl", ".asm", ".s", ".S", ".cmake", ".log"}
SHARED_LIB = re.compile(r"\.so(\.\d+)*$")


# ---------------------------------------------------------------- stage (build host)

def _fwd(p):
    return str(p).replace("\\", "/")


def _quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _ctest_list(build):
    out = subprocess.run(["ctest", "--test-dir", build, "--show-only=json-v1"], capture_output=True, text=True)
    return json.loads(out.stdout or "{}").get("tests", [])


def _walk(top):
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if os.path.splitext(f)[1] not in SKIP_EXT:
                yield os.path.join(dirpath, f)


class Bundle:
    def __init__(self):
        self.files = {}   # target path (relative to /tests) -> host path
        self.dirs = set()

    def add_file(self, target, host):
        self.files.setdefault(target, host)

    def add_tree(self, target, host):
        self.dirs.add(target)
        for f in _walk(host):
            rel = _fwd(os.path.relpath(f, host))
            self.add_file(f"{target}/{rel}", f)

    def buildfile(self):
        total = sum(os.path.getsize(h) for h in self.files.values())
        sectors = (total * 3 // 2 + (64 << 20)) // 512
        lines = [f"[num_sectors={sectors}]", f"[num_inodes={2 * len(self.files) + 2000}]",
                 "[uid=0 gid=0 dperms=777 perms=755]"]
        lines += [f"[type=dir] {d}" for d in sorted(self.dirs)]
        lines += [f'{t} = "{_fwd(h)}"' for t, h in sorted(self.files.items())]
        return "\n".join(lines) + "\n", total


def plan_library(name, cpu, bundle):
    """Add one library's tests to the bundle; returns the run.sh lines and a summary."""
    src = os.path.join(REMOTE_ROOT, name)
    build = os.path.join(REMOTE_ROOT, f"build_{name}_{cpu}")
    roots = [(_fwd(build), f"/tests/{name}/build"), (_fwd(src), f"/tests/{name}/src")]

    def remap(s):
        for host, tgt in roots:
            s = s.replace(host, tgt).replace(host.replace("/", "\\"), tgt)
        return s

    def rel_target(path):
        return remap(_fwd(path))[len("/tests/"):]

    for f in _walk(build):
        if SHARED_LIB.search(f):
            bundle.add_file(f"{name}/lib/{os.path.basename(f)}", f)
    bundle.dirs.add(f"{name}/lib")
    lines = [f"export LD_LIBRARY_PATH=/tests/{name}/lib:$PP_BASE_LD"]
    summary = {"name": name, "tests": 0, "disabled": []}
    for t in _ctest_list(build):
        props = {p["name"]: p["value"] for p in t.get("properties", [])}
        cmd = t.get("command") or []
        if props.get("DISABLED") or not cmd:
            summary["disabled"].append(t["name"])
            continue
        exe = cmd[0]
        if not os.path.exists(exe):
            summary["disabled"].append(t["name"])
            continue
        bundle.add_file(rel_target(exe), exe)
        for a in cmd[1:]:
            if os.path.isabs(a) and os.path.exists(a) and remap(_fwd(a)) != _fwd(a):
                (bundle.add_tree if os.path.isdir(a) else bundle.add_file)(rel_target(a), a)
        wd = props.get("WORKING_DIRECTORY") or os.path.dirname(exe)
        if os.path.isdir(wd) and remap(_fwd(wd)) != _fwd(wd):
            bundle.add_tree(rel_target(wd), wd)
        env = [remap(e) for e in props.get("ENVIRONMENT", [])]
        argv = ([f"env"] + env if env else []) + [remap(_fwd(c)) for c in cmd]
        limit = int(float(props.get("TIMEOUT", DEFAULT_TIMEOUT)))
        will_fail = 1 if props.get("WILL_FAIL") else 0
        skip_rc = props.get("SKIP_RETURN_CODE", "-")
        pass_re = props.get("PASS_REGULAR_EXPRESSION")
        pass_re = _quote("|".join(pass_re) if isinstance(pass_re, list) else pass_re) if pass_re else "''"
        tname = re.sub(r"\s+", "_", t["name"])
        lines.append(f"pp_run {name} {_quote(tname)} {limit} {will_fail} {skip_rc} {pass_re} "
                     f"{_quote(remap(_fwd(wd)))} " + " ".join(_quote(a) for a in argv))
        summary["tests"] += 1
    return lines, summary


RUN_SH_HEAD = r"""#!/bin/sh
# Generated by PortPilot: runs each CTest entry on the target and prints one PPTEST line per result.
PP_BASE_LD=$LD_LIBRARY_PATH
pp_run() {
    lib=$1; name=$2; limit=$3; will_fail=$4; skip_rc=$5; pass_re=$6; dir=$7
    shift 7
    rm -f /tmp/pp_timeout
    ( cd "$dir" && exec "$@" ) >/tmp/pp_out 2>&1 &
    pid=$!
    # the watcher polls once a second and leaves as soon as the test ends, so no sleep outlives its test
    ( i=0; while [ $i -lt $limit ]; do sleep 1; kill -0 $pid 2>/dev/null || exit 0; i=$((i+1)); done
      kill -9 $pid 2>/dev/null && echo x >/tmp/pp_timeout ) &
    watcher=$!
    wait $pid
    rc=$?
    wait $watcher
    if [ -e /tmp/pp_timeout ]; then
        verdict=TIMEOUT
    elif [ "$skip_rc" != "-" -a "$rc" = "$skip_rc" ]; then
        verdict=SKIP
    elif [ -n "$pass_re" ]; then
        if grep -q -E "$pass_re" /tmp/pp_out; then verdict=PASS; else verdict=FAIL; fi
    elif [ "$rc" = 0 -a "$will_fail" = 0 ] || [ "$rc" != 0 -a "$will_fail" = 1 ]; then
        verdict=PASS
    else
        verdict=FAIL
    fi
    echo "PPTEST $lib $name $verdict rc=$rc"
    if [ "$verdict" != PASS ]; then
        grep -E "Failure|Expected|Which is|Actual|actual|expected|Value of|FAILED|error" /tmp/pp_out | head -n 40 | sed 's/^/PPLOG /'
        tail -n 6 /tmp/pp_out | sed 's/^/PPLOG /'
    fi
}
echo "PPTEST-BEGIN $(uname -a)"
"""


def stage(names, cpu, out):
    os.makedirs(out, exist_ok=True)
    bundle, body, summaries = Bundle(), [], []
    for n in names:
        lines, s = plan_library(n, cpu, bundle)
        body += [f"echo 'PPTEST-LIB {n} {s['tests']}'"] + lines
        summaries.append(s)
    run_sh = os.path.join(out, "run.sh")
    with open(run_sh, "w", newline="\n") as f:
        f.write(RUN_SH_HEAD + "\n".join(body) + "\necho PPTEST-END\n")
    bundle.add_file("run.sh", run_sh)
    text, total = bundle.buildfile()
    bf = os.path.join(out, "tests.build")
    with open(bf, "w", newline="\n") as f:
        f.write(text)
    img = os.path.join(out, "tests.img")
    r = subprocess.run(["mkqnx6fsimg", bf, img], capture_output=True, text=True)
    print("PPSTAGE " + json.dumps({"libraries": summaries, "files": len(bundle.files), "bytes": total,
                                   "mkqnx6fsimg_exit": r.returncode, "mkqnx6fsimg_err": r.stderr[-800:]}))


# ---------------------------------------------------------------- run (driver)

WORKER = Path.home() / ".local/bin/victus-worker"
HERE = Path(__file__).resolve()
LOCAL = HERE.parent.parent / "runs"
BOOT_PS1 = r"""param([string]$Image, [string]$Tests, [string]$Log, [int]$Deadline)
$out = Join-Path $Image "output"
if (Test-Path $Log) { Remove-Item $Log }
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$a = @("-accel", "tcg", "-smp", "2", "-cpu", "max", "-m", "2G",
       "-drive", "file=$out\disk-qemu.vmdk,if=ide,index=0,id=drv0",
       "-drive", "file=$Tests,if=ide,index=1,format=raw,id=drv1",
       "-kernel", "$out\ifs.bin", "-display", "none", "-monitor", "none", "-serial", "file:$Log",
       "-object", "rng-builtin,id=rng0", "-device", "virtio-rng-pci,rng=rng0", "-no-reboot")
$p = Start-Process -FilePath $qemu -ArgumentList $a -PassThru -WindowStyle Hidden
$t0 = Get-Date
while (-not $p.HasExited -and ((Get-Date) - $t0).TotalSeconds -lt $Deadline) { Start-Sleep -Seconds 5 }
$alive = -not $p.HasExited
if ($alive) { Stop-Process -Id $p.Id -Force }
"PPBOOT exited_by_itself=$(-not $alive)"
"""


def _worker(*args, timeout=7200):
    r = subprocess.run([str(WORKER), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def parse_serial(text):
    results, current = [], None
    for line in text.splitlines():
        line = line.strip("\r")
        m = re.match(r"PPTEST (\S+) (\S+) (PASS|FAIL|SKIP|TIMEOUT) rc=(-?\d+)", line)
        if m:
            current = {"library": m[1], "test": m[2], "verdict": m[3], "rc": int(m[4]), "log": []}
            results.append(current)
        elif line.startswith("PPLOG ") and current is not None:
            current["log"].append(line[6:])
    return results


def run(names, cpu, deadline, tag="all"):
    if cpu != "x86_64":
        sys.exit("only the x86_64 VM is set up so far")
    tmp = LOCAL / "target"
    tmp.mkdir(parents=True, exist_ok=True)
    _worker("push", str(HERE), "pp/pp_target.py")
    ps1 = tmp / "boot_tests.ps1"
    ps1.write_text(BOOT_PS1)
    _worker("push", str(ps1), "qnxvm/boot_tests.ps1")
    out = rf"{REMOTE_ROOT}\target_{cpu}"
    bat = tmp / "stage.bat"
    bat.write_text("\r\n".join(["@echo off", f"call {SDP_ENV} >nul 2>&1", f"cd /d {REMOTE_ROOT}",
                                f"python {REMOTE_ROOT}\\pp_target.py stage --cpu {cpu} --out {out} {' '.join(names)}",
                                ""]))
    _worker("push", str(bat), "pp/pp_stage.bat")
    _, text = _worker("windows", rf"cmd /c {REMOTE_ROOT}\pp_stage.bat")
    staged = next((json.loads(l[8:]) for l in text.splitlines() if l.startswith("PPSTAGE ")), None)
    print(json.dumps(staged)[:1500] if staged else text[-1500:], flush=True)
    if not staged or staged["mkqnx6fsimg_exit"] != 0:
        sys.exit("staging failed")
    log = rf"{out}\serial.log"
    _, boot = _worker("windows", rf"powershell -ExecutionPolicy Bypass -File {VM_ROOT}\boot_tests.ps1 "
                                 rf"-Image {VM_ROOT}\{cpu} -Tests {out}\tests.img -Log {log} -Deadline {deadline}",
                      timeout=deadline + 600)
    serial = tmp / f"serial_{cpu}_{tag}.log"
    _worker("pull", rf"pp/target_{cpu}/serial.log", str(serial))
    text = serial.read_text(errors="ignore") if serial.exists() else ""
    results = parse_serial(text)
    finished = "PPTEST-END" in text
    counts = {}
    for r in results:
        counts.setdefault(r["library"], {}).setdefault(r["verdict"], 0)
        counts[r["library"]][r["verdict"]] += 1
    report = {"cpu": cpu, "tag": tag, "libraries": names, "finished": finished, "boot": boot.strip()[-200:],
              "staged": staged["libraries"], "counts": counts, "results": results}
    (LOCAL / f"target_{cpu}_{tag}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({"finished": finished, "counts": counts}, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("names", nargs="+")
    s.add_argument("--cpu", default="x86_64")
    s.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("names", nargs="+")
    r.add_argument("--cpu", default="x86_64")
    r.add_argument("--deadline", type=int, default=3600)
    r.add_argument("--tag", default="all", help="name for this run's report and serial log")
    a = ap.parse_args()
    if a.cmd == "stage":
        stage(a.names, a.cpu, a.out)
    else:
        run(a.names, a.cpu, a.deadline, a.tag)


if __name__ == "__main__":
    main()
