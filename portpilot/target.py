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

DEFAULT_TIMEOUT = 300  # seconds per test; the VM runs under TCG, so CTest's 1500 s default is far too generous
SKIP_DIRS = {".git", "CMakeFiles", "__pycache__"}
# build intermediates only: tests often find their data by looking for a source or header file (wolfSSL looks for its
# own headers to locate the source root), so working-directory trees keep their sources
SKIP_EXT = {".o", ".obj", ".a", ".lib", ".ninja", ".d", ".pdb", ".log"}
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
        self.trees = set()   # host directories already walked
        self.links = {}      # target path -> link value, for files git tracks as symbolic links

    def add_file(self, target, host):
        self.files.setdefault(target, host)

    def add_tree(self, target, host):
        if host in self.trees:
            return
        self.trees.add(host)
        self.dirs.add(target)
        for dirpath, dirnames, _ in os.walk(host):   # empty output directories CMake made for the tests count too
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for d in dirnames:
                self.dirs.add(f"{target}/{_fwd(os.path.relpath(os.path.join(dirpath, d), host))}")
        for f in _walk(host):
            rel = _fwd(os.path.relpath(f, host))
            self.add_file(f"{target}/{rel}", f)

    def buildfile(self):
        total = sum(os.path.getsize(h) for h in self.files.values())
        sectors = (total * 3 // 2 + (64 << 20)) // 512
        lines = [f"[num_sectors={sectors}]", f"[num_inodes={2 * len(self.files) + 2000}]",
                 "[uid=0 gid=0 dperms=777 perms=755]"]
        lines += [f"[type=dir] {d}" for d in sorted(self.dirs)]
        lines += [f'{t} = "{_fwd(h)}"' for t, h in sorted(self.files.items()) if t not in self.links]
        lines += [f"[type=link] {t}={v}" for t, v in sorted(self.links.items())]
        return "\n".join(lines) + "\n", total


def plan_library(name, cpu, bundle, work, cap=DEFAULT_TIMEOUT, only=None):
    """Add one library's tests to the bundle; returns the run.sh lines and a summary."""
    src = os.path.join(work, name)
    build = os.path.join(work, f"build_{name}_{cpu}")
    roots = [(_fwd(build), f"/tests/{name}/build"), (_fwd(src), f"/tests/{name}/src")]

    def remap(s):
        for host, tgt in roots:
            s = s.replace(host, tgt).replace(host.replace("/", "\\"), tgt)
        if re.match(r"^\.{1,2}\\", s):   # CMake on a Windows host writes relative paths as .\file
            s = s.replace("\\", "/")
        return s

    def rel_target(path):
        return remap(_fwd(path))[len("/tests/"):]

    # On a Windows host CMake cannot create the SONAME links (libjson-c.so.5 -> libjson-c.so.5.5.0) and leaves empty
    # files; stage the real library under every name instead.
    libs = [f for f in _walk(build) if SHARED_LIB.search(f)]
    for f in libs:
        real = f
        if os.path.getsize(f) == 0:
            stem = SHARED_LIB.sub("", os.path.basename(f))
            full = [g for g in libs if os.path.getsize(g) and SHARED_LIB.sub("", os.path.basename(g)) == stem]
            if not full:
                continue
            real = max(full, key=len)
        bundle.add_file(f"{name}/lib/{os.path.basename(f)}", real)
    bundle.dirs.add(f"{name}/lib")
    lines = [f"export LD_LIBRARY_PATH=/tests/{name}/lib:$PP_BASE_LD"]
    summary = {"name": name, "tests": 0, "disabled": []}
    for t in _ctest_list(build):
        if only and not re.search(only, t["name"]):
            continue
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
        if not _is_elf(exe) and remap(_fwd(exe)) != _fwd(exe):
            # a test script (json-c's *.test) usually sources helpers that sit next to it
            bundle.add_tree(rel_target(os.path.dirname(exe)), os.path.dirname(exe))
        for a in cmd[1:]:
            if os.path.isabs(a) and os.path.exists(a) and remap(_fwd(a)) != _fwd(a):
                (bundle.add_tree if os.path.isdir(a) else bundle.add_file)(rel_target(a), a)
        wd = props.get("WORKING_DIRECTORY") or os.path.dirname(exe)
        if os.path.isdir(wd) and remap(_fwd(wd)) != _fwd(wd):
            bundle.add_tree(rel_target(wd), wd)
            parent = os.path.dirname(os.path.normpath(wd))
            if os.path.normcase(os.path.normpath(wd)).startswith(os.path.normcase(os.path.normpath(build)) + os.sep):
                # tests in a build subdirectory often read ../<data>, e.g. mbedtls's ../framework/data_files
                bundle.add_tree(rel_target(parent), parent)
        env = [remap(e) for e in props.get("ENVIRONMENT", [])]
        argv = ([f"env"] + env if env else []) + [remap(_fwd(c)) for c in cmd]
        limit = min(int(float(props.get("TIMEOUT", cap))), cap)
        will_fail = 1 if props.get("WILL_FAIL") else 0
        skip_rc = props.get("SKIP_RETURN_CODE", "-")
        pass_re = props.get("PASS_REGULAR_EXPRESSION")
        pass_re = _quote("|".join(pass_re) if isinstance(pass_re, list) else pass_re) if pass_re else "''"
        tname = re.sub(r"\s+", "_", t["name"])
        lines.append(f"pp_run {name} {_quote(tname)} {limit} {will_fail} {skip_rc} {pass_re} "
                     f"{_quote(remap(_fwd(wd)))} " + " ".join(_quote(a) for a in argv))
        summary["tests"] += 1
    # a Windows checkout writes git symbolic links (json-c's tests/test4.test -> test_basic.test) as small text files
    # holding the link target; put them back as links on the test disk
    out = subprocess.run(["git", "-C", src, "ls-files", "-s"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        target = f"{name}/src/{path}"
        if meta.startswith("120000") and target in bundle.files:
            with open(bundle.files[target], errors="ignore") as f:
                bundle.links[target] = f.read().strip()
    return lines, summary


RUN_SH_HEAD = r"""#!/bin/sh
# Generated by PortPilot: runs each CTest entry on the target and prints one PPTEST line per result.
PP_BASE_LD=${LD_LIBRARY_PATH:-/proc/boot:/system/lib:/system/lib/dll}:/tests/sdp-lib
pp_run() {
    lib=$1; name=$2; limit=$3; will_fail=$4; skip_rc=$5; pass_re=$6; dir=$7
    shift 7
    rm -f /tmp/pp_timeout /tmp/pp_pidin
    ( cd "$dir" && exec "$@" ) >/tmp/pp_out 2>&1 &
    pid=$!
    # the watcher polls once a second and leaves as soon as the test ends, so no sleep outlives its test
    ( i=0; while [ $i -lt $limit ]; do sleep 1; kill -0 $pid 2>/dev/null || exit 0; i=$((i+1)); done
      # a hung test: record each thread's QNX kernel state (CONDVAR, MUTEX, RECEIVE, REPLY, ...) before killing it
      pidin -p $pid >/tmp/pp_pidin 2>&1
      kill -9 $pid 2>/dev/null && echo x >/tmp/pp_timeout ) &
    watcher=$!
    wait $pid
    rc=$?
    wait $watcher
    if [ -e /tmp/pp_timeout ]; then
        verdict=TIMEOUT
        sed 's/^/PPLOG pidin: /' /tmp/pp_pidin
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
        pp_excerpt
    fi
    if [ "$verdict" = FAIL ] && [ "$rc" -gt 128 ]; then
        # killed by a signal: name it, and use QNX's own crash records - the core file dumper wrote and the
        # system log (slogger2) entries from around the crash
        echo "PPLOG signal $((rc - 128)); core file: $(ls -t /data/var/dumper 2>/dev/null | head -n 1)"
        slog2info 2>/dev/null | tail -n 5 | sed 's/^/PPLOG slog2: /'
    fi
}
# failure lines with the three lines after each (where test frameworks print the expression and values), then the tail
pp_excerpt() {
    n=0; c=0
    while IFS= read -r line; do
        case "$line" in *Failure*|*FAILED*|*Expected*|*rror*|*Assert*|*assert*) n=4;; esac
        if [ $n -gt 0 ]; then
            echo "PPLOG $line"; n=$((n-1)); c=$((c+1))
            [ $c -ge 40 ] && break
        fi
    done </tmp/pp_out
    echo "PPLOG ..."
    tail -n 6 /tmp/pp_out | sed 's/^/PPLOG /'
}
echo "PPTEST-BEGIN $(uname -a)"
"""


NEEDED = re.compile(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]")


def _is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def add_runtime_libs(bundle, cpu):
    """Shared libraries the staged programs need from the SDP's usr/lib (a default mkqnximage image lacks some, such
    as libcharset.so.1). They go to /tests/sdp-lib on the test disk only; nothing from the SDP is published."""
    var = "aarch64le" if cpu.startswith("aarch64") else cpu
    tool = "aarch64" if cpu.startswith("aarch64") else cpu
    sdp_lib = os.path.join(os.environ.get("QNX_TARGET", ""), var, "usr", "lib")
    have = {os.path.basename(t) for t in bundle.files}
    todo = [h for h in set(bundle.files.values()) if _is_elf(h)]
    seen, added = set(), []
    while todo:
        h = todo.pop()
        if h in seen:
            continue
        seen.add(h)
        out = subprocess.run([f"nto{tool}-readelf", "-d", h], capture_output=True, text=True).stdout
        for lib in NEEDED.findall(out):
            cand = os.path.join(sdp_lib, lib)
            if lib not in have and os.path.exists(cand):
                bundle.add_file(f"sdp-lib/{lib}", os.path.realpath(cand))
                have.add(lib)
                added.append(lib)
                todo.append(cand)
    return sorted(added)


def stage(names, cpu, out, work, cap=DEFAULT_TIMEOUT, only=None, pre=None):
    os.makedirs(out, exist_ok=True)
    bundle, body, summaries = Bundle(), [], []
    for n in names:
        lines, s = plan_library(n, cpu, bundle, work, cap, only)
        body += [f"echo 'PPTEST-LIB {n} {s['tests']}'"] + lines
        summaries.append(s)
    sdp_libs = add_runtime_libs(bundle, cpu)
    run_sh = os.path.join(out, "run.sh")
    with open(run_sh, "w", newline="\n") as f:
        diag = f"( {pre} ) 2>&1 | sed 's/^/PPINFO /'\n" if pre else ""
        f.write(RUN_SH_HEAD + diag + "\n".join(body) + "\necho PPTEST-END\n")
    bundle.add_file("run.sh", run_sh)
    text, total = bundle.buildfile()
    bf = os.path.join(out, "tests.build")
    with open(bf, "w", newline="\n") as f:
        f.write(text)
    img = os.path.join(out, "tests.img")
    r = subprocess.run(["mkqnx6fsimg", bf, img], capture_output=True, text=True)
    print("PPSTAGE " + json.dumps({"libraries": summaries, "files": len(bundle.files), "bytes": total, "sdp_libs": sdp_libs,
                                   "mkqnx6fsimg_exit": r.returncode, "mkqnx6fsimg_err": r.stderr[-800:]}))


# ---------------------------------------------------------------- run (driver)

HERE = Path(__file__).resolve()
LOCAL = HERE.parent.parent / "runs"
BOOT_PS1 = r"""param([string]$Image, [string]$Tests, [string]$Log, [int]$Deadline, [string]$Qemu)
$out = Join-Path $Image "output"
if (Test-Path $Log) { Remove-Item $Log }
$qemu = Join-Path $Qemu "qemu-system-x86_64.exe"
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


def run(names, cpu, deadline, tag="all", cap=DEFAULT_TIMEOUT, only=None, pre=None):
    from . import host
    if cpu != "x86_64":
        sys.exit("only the x86_64 VM is set up so far")
    h = host.from_env()
    tmp = LOCAL / "target"
    tmp.mkdir(parents=True, exist_ok=True)
    h.put(HERE, rf"{h.work}\pp_target.py")
    ps1 = tmp / "boot_tests.ps1"
    ps1.write_text(BOOT_PS1)
    h.put(ps1, rf"{h.vm}\boot_tests.ps1")
    out = rf"{h.work}\target_{cpu}"
    text = h.run_bat("\r\n".join(["@echo off", f"call {h.sdp_env} >nul 2>&1", f"cd /d {h.work}",
                                   f"{h.python} {h.work}\\pp_target.py stage --cpu {cpu} --out {out} --work {h.work} "
                                   f"--timeout {cap} " + (f'--only "{only}" ' if only else "")
                                   + (f'--pre "{pre}" ' if pre else "") + " ".join(names), ""]),
                     rf"{h.work}\pp_stage.bat")
    staged = next((json.loads(l[8:]) for l in text.splitlines() if l.startswith("PPSTAGE ")), None)
    print(json.dumps(staged)[:1500] if staged else text[-1500:], flush=True)
    if not staged or staged["mkqnx6fsimg_exit"] != 0:
        sys.exit("staging failed")
    log = rf"{out}\serial.log"
    boot = h.ps(rf"powershell -ExecutionPolicy Bypass -File '{h.vm}\boot_tests.ps1' -Image '{h.vm}\{cpu}' "
                rf"-Tests '{out}\tests.img' -Log '{log}' -Deadline {deadline} -Qemu '{h.qemu}'", timeout=deadline + 600)
    serial = tmp / f"serial_{cpu}_{tag}.log"
    serial.unlink(missing_ok=True)
    h.get(log, serial)
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
    s.add_argument("--work", required=True, help="the build host's work directory (upstream copies and build trees)")
    s.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="upper limit per test, seconds")
    s.add_argument("--only", help="regular expression: run only the tests whose names match")
    s.add_argument("--pre", help="shell commands to run on the target before the tests (diagnostics; output as PPINFO)")
    r = sub.add_parser("run")
    r.add_argument("names", nargs="+")
    r.add_argument("--cpu", default="x86_64")
    r.add_argument("--deadline", type=int, default=3600)
    r.add_argument("--tag", default="all", help="name for this run's report and serial log")
    r.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="upper limit per test, seconds")
    r.add_argument("--only", help="regular expression: run only the tests whose names match")
    r.add_argument("--pre", help="shell commands to run on the target before the tests (diagnostics; output as PPINFO)")
    a = ap.parse_args()
    if a.cmd == "stage":
        stage(a.names, a.cpu, a.out, a.work, a.timeout, a.only, a.pre)
    else:
        run(a.names, a.cpu, a.deadline, a.tag, a.timeout, a.only, a.pre)


if __name__ == "__main__":
    main()
