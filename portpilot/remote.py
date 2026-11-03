"""Build a CMake project for QNX 8.0 on a Windows host that has the SDP (victus), and iterate on build errors.

The loop is: configure and build -> read the log -> match catalogue rules -> rebuild with the added flags, until the build
passes or no rule matches. Every attempt and the flags it used are written to a JSON report next to the logs.
usage: python -m portpilot.remote <name> <git-url> <ref> [--subdir build/cmake] [--cmake=-DFOO=ON ...] [--cpu x86_64]
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

from . import fixes, scaffold

WORKER = Path.home() / ".local/bin/victus-worker"
REMOTE_ROOT = r"C:\Users\dev\Documents\portpilot-work\pp"
SDP_ENV = r"C:\Users\dev\qnx800\qnxsdp-env.bat"
LOCAL = Path(__file__).resolve().parent.parent / "runs"


def _worker(*args, timeout=1800):
    r = subprocess.run([str(WORKER), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def _bat(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args):
    src = f"{REMOTE_ROOT}\\{name}"
    bld = f"{REMOTE_ROOT}\\build_{name}_{cpu}"
    args = " ".join(cmake_args)
    return "\r\n".join([
        "@echo off",
        f"call {SDP_ENV} >nul 2>&1",
        f"cd /d {REMOTE_ROOT}",
        f"if not exist {src} git clone -q --depth 1 --branch {ref} {url} {src}",
        f"if exist {bld} rmdir /s /q {bld}",
        f'cmake -G Ninja -S {src}\\{subdir} -B {bld} -DCMAKE_TOOLCHAIN_FILE={REMOTE_ROOT}\\qnx.nto.toolchain.cmake '
        f'-DCPU={cpu} -DCMAKE_SYSTEM_PROCESSOR={cpu} -DCPUVARDIR={cpu} -DCMAKE_BUILD_TYPE=Release '
        f'"-DPORTPILOT_C_FLAGS={" ".join(cflags)}" "-DPORTPILOT_LD_FLAGS={" ".join(ldflags)}" {args} '
        f"> {REMOTE_ROOT}\\{name}_configure.log 2>&1",
        "echo configure_exit=%ERRORLEVEL%",
        f"cmake --build {bld} -j 8 -- -k 0 > {REMOTE_ROOT}\\{name}_build.log 2>&1",
        "echo build_exit=%ERRORLEVEL%",
        "",
    ])


def attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp):
    bat = tmp / f"run_{name}.bat"
    bat.write_text(_bat(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args))
    _worker("push", str(bat), f"pp/run_{name}.bat")
    t0 = time.time()
    _, out = _worker("windows", f"cmd /c {REMOTE_ROOT}\\run_{name}.bat")
    secs = time.time() - t0
    codes = dict(line.strip().split("=", 1) for line in out.splitlines() if line.strip().startswith(("configure_exit=", "build_exit=")))
    logs = {}
    for kind in ("configure", "build"):
        dest = tmp / f"{name}_{kind}.log"
        _worker("pull", f"pp/{name}_{kind}.log", str(dest))
        logs[kind] = dest.read_text(errors="ignore") if dest.exists() else ""
    return {"configure_exit": codes.get("configure_exit"), "build_exit": codes.get("build_exit"), "seconds": round(secs, 1),
            "cflags": list(cflags), "ldflags": list(ldflags)}, logs


def port(name, url, ref, subdir=".", cpu="x86_64", cmake_args=(), max_rounds=4):
    tmp = LOCAL / name
    tmp.mkdir(parents=True, exist_ok=True)
    tc = tmp / "qnx.nto.toolchain.cmake"
    tc.write_text(scaffold.TOOLCHAIN)
    _worker("push", str(tc), "pp/qnx.nto.toolchain.cmake")
    cflags, ldflags, rounds = ["-D_QNX_SOURCE"], [], []
    for i in range(max_rounds):
        rec, logs = attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp)
        log = logs["configure"] + "\n" + logs["build"]
        rules = fixes.match(log)
        new_c, new_l = fixes.apply(rules, cflags, ldflags)
        rec["matched_rules"] = [r.name for r in rules]
        rec["errors"] = sum(1 for line in logs["build"].splitlines() if " error: " in line or "undefined reference" in line)
        rounds.append(rec)
        print(f"[{name}] round {i + 1}: configure={rec['configure_exit']} build={rec['build_exit']} errors={rec['errors']} "
              f"rules={rec['matched_rules']} ({rec['seconds']} s)", flush=True)
        if rec["build_exit"] == "0" and rec["configure_exit"] == "0":
            break
        if (new_c, new_l) == (cflags, ldflags):
            break  # nothing new to try from the catalogue: leave for the next stage (patches or an AI proposal)
        cflags, ldflags = new_c, new_l
    report = {"name": name, "url": url, "ref": ref, "cpu": cpu, "rounds": rounds,
              "result": "built" if rounds[-1]["build_exit"] == "0" else "needs-patch"}
    (tmp / "report.json").write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name"), ap.add_argument("url"), ap.add_argument("ref")
    ap.add_argument("--subdir", default=".")
    ap.add_argument("--cpu", default="x86_64")
    ap.add_argument("--cmake", action="append", default=[], help="one CMake argument, repeatable: --cmake=-DFOO=ON")
    a = ap.parse_args()
    print(json.dumps(port(a.name, a.url, a.ref, a.subdir, a.cpu, a.cmake), indent=1)[:2000])


if __name__ == "__main__":
    main()
