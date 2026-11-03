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

from . import agent, fixes, scaffold

WORKER = Path.home() / ".local/bin/victus-worker"
REMOTE_ROOT = r"C:\Users\dev\Documents\portpilot-work\pp"
SDP_ENV = r"C:\Users\dev\qnx800\qnxsdp-env.bat"
HOST_PYTHON = "C:/Users/dev/AppData/Local/Programs/Python/Python313/python.exe"
HOST_CC = "gcc"  # MinGW-w64 on the build host; code generators that compile helpers read HOSTCC
LOCAL = Path(__file__).resolve().parent.parent / "runs"


def _worker(*args, timeout=1800):
    r = subprocess.run([str(WORKER), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def _bat(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args):
    src = f"{REMOTE_ROOT}\\{name}"
    bld = f"{REMOTE_ROOT}\\build_{name}_{cpu}"
    # QNX names: binutils prefix nto<cpu> (x86_64, aarch64); qcc variant and target dir use aarch64le for little-endian ARM
    tool_cpu = "aarch64" if cpu.startswith("aarch64") else cpu
    var_cpu = "aarch64le" if cpu.startswith("aarch64") else cpu
    args = " ".join(cmake_args)
    return "\r\n".join([
        "@echo off",
        f"call {SDP_ENV} >nul 2>&1",
        f"set HOSTCC={HOST_CC}",
        f"cd /d {REMOTE_ROOT}",
        f"if not exist {src} git -c core.autocrlf=false clone -q -c core.autocrlf=false --depth 1 --recurse-submodules "
        f"--shallow-submodules --branch {ref} {url} {src}",
        f"if exist {bld} rmdir /s /q {bld}",
        f'cmake -G Ninja -S {src}\\{subdir} -B {bld} -DCMAKE_TOOLCHAIN_FILE={REMOTE_ROOT}\\qnx.nto.toolchain.cmake '
        f'-DCPU={tool_cpu} -DCMAKE_SYSTEM_PROCESSOR={var_cpu} -DCPUVARDIR={var_cpu} -DCMAKE_BUILD_TYPE=Release '
        f'"-DPORTPILOT_C_FLAGS={" ".join(cflags)}" "-DPORTPILOT_LD_FLAGS={" ".join(ldflags)}" {args} '
        f"> {REMOTE_ROOT}\\{name}_{cpu}_configure.log 2>&1",
        "echo configure_exit=%ERRORLEVEL%",
        f"cmake --build {bld} -j 8 -- -k 0 > {REMOTE_ROOT}\\{name}_{cpu}_build.log 2>&1",
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
        dest = tmp / f"{name}_{cpu}_{kind}.log"
        _worker("pull", f"pp/{name}_{cpu}_{kind}.log", str(dest))
        logs[kind] = dest.read_text(errors="ignore") if dest.exists() else ""
    return {"configure_exit": codes.get("configure_exit"), "build_exit": codes.get("build_exit"), "seconds": round(secs, 1),
            "cflags": list(cflags), "ldflags": list(ldflags)}, logs


def apply_header_patches(patches):
    """Edit the remote upstream copy in place; the final `git diff` becomes the port's patch series."""
    for f, old, new in patches:
        ps = (f"$f='{f}'; (Get-Content -LiteralPath $f -Raw) -replace '#include\\s*<{old.replace('.', '[.]')}>', "
              f"'#include <{new}>' | Set-Content -LiteralPath $f -NoNewline")
        _worker("windows", ps)


COMPAT = Path(__file__).resolve().parent.parent / "compat"


def push_compat_header(name):
    """Copy a PortPilot compat header to pp/portpilot_compat on the host; returns its remote path with forward slashes."""
    _worker("windows", f"New-Item -ItemType Directory -Force '{REMOTE_ROOT}\\portpilot_compat' | Out-Null")
    _worker("push", str(COMPAT / name), f"pp/portpilot_compat/{name}")
    return f"{REMOTE_ROOT}\\portpilot_compat\\{name}".replace("\\", "/")


def make_stub_libs(cpu, libs):
    """Empty static archives (just the ar magic) in pp/qnx_stubs/<cpu>; returns the directory with forward slashes."""
    d = f"{REMOTE_ROOT}\\qnx_stubs\\{cpu}"
    files = ",".join(f"'lib{n}.a'" for n in libs)
    ps = (f"New-Item -ItemType Directory -Force '{d}' | Out-Null; foreach ($n in @({files})) "
          f"{{ [IO.File]::WriteAllBytes((Join-Path '{d}' $n), [Text.Encoding]::ASCII.GetBytes(\"!<arch>`n\")) }}")
    _worker("windows", ps)
    return d.replace("\\", "/")


def find_project_header(name, needle):
    """First header in the upstream tree that contains `needle` (forward slashes), or None."""
    ps = (f"Get-ChildItem -LiteralPath '{REMOTE_ROOT}\\{name}' -Recurse -Include *.h -File | "
          f"Select-String -SimpleMatch -Pattern '{needle}' -List | Select-Object -First 1 -ExpandProperty Path")
    _, out = _worker("windows", ps)
    lines = [l.strip() for l in out.splitlines() if l.strip().lower().endswith(".h")]
    return lines[0].replace("\\", "/") if lines else None


def add_include(files, header):
    """Insert #include <header> before the first #include of each file (once)."""
    for f in files:
        ps = (f"$f='{f}'; $t = Get-Content -LiteralPath $f -Raw; if ($t -notmatch '#include\\s*<{header.replace('.', '[.]')}>') "
              f"{{ $i = $t.IndexOf('#include'); $t = $t.Insert($i, '#include <{header}>' + [char]10); "
              f"Set-Content -LiteralPath $f -Value $t -NoNewline }}")
        _worker("windows", ps)


def source_snippets(name, errors):
    """Numbered upstream source lines around each error, the error line marked with '>'."""
    root = f"{REMOTE_ROOT}\\{name}"
    # an ArrayList keeps each (file, line) pair intact; @(@('a',1)) would flatten a single pair
    adds = "; ".join(f"[void]$items.Add(@('{rel.replace(chr(39), chr(39) * 2)}',{line}))" for rel, line, _ in errors)
    ps = (f"$items = New-Object System.Collections.ArrayList; {adds}; foreach ($it in $items) {{ $f = $it[0]; if (-not [IO.Path]::IsPathRooted($f)) {{ $f = Join-Path '{root}' $f }}; "
          f"'@@SNIP'; if (Test-Path -LiteralPath $f) {{ $l = @(Get-Content -LiteralPath $f); $n = $it[1]; "
          f"$s = [Math]::Max(1, $n - {agent.CONTEXT}); $e = [Math]::Min($l.Count, $n + {agent.CONTEXT}); "
          f"for ($i = $s; $i -le $e; $i++) {{ $m = ' '; if ($i -eq $n) {{ $m = '>' }}; '{{0,5}}{{1}} {{2}}' -f $i, $m, $l[$i - 1] }} }} }}")
    _, out = _worker("windows", ps)
    parts = out.replace("\r", "").split("@@SNIP\n")[1:]
    return [p.rstrip("\n") for p in parts] + [""] * (len(errors) - len(parts))


def apply_patch(name, patch, tag, reverse=False):
    _worker("push", str(patch), f"pp/{tag}.patch")
    flag = "-R " if reverse else ""
    _, out = _worker("windows", f"git -C '{REMOTE_ROOT}\\{name}' apply {flag}--recount --whitespace=nowarn "
                                f"'{REMOTE_ROOT}\\{tag}.patch' 2>&1; \"apply_exit=$LASTEXITCODE\"")
    return "apply_exit=0" in out, out.strip()[-400:]


def ai_stage(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp, rounds, log, ai_rounds):
    """Ask the model for patches until the build passes, a patch fails to help, or the round budget is spent."""
    applied = sorted({r for rec in rounds for r in rec["matched_rules"]} | {p for rec in rounds for p in rec.get("patches", [])})
    best = rounds[-1]["errors"]
    for k in range(1, ai_rounds + 1):
        errors = agent.collect_errors(log, f"{REMOTE_ROOT}\\{name}")
        symbols = agent.undefined_symbols(log)
        if not errors and not symbols:
            break
        prompt = agent.build_prompt(name, ref, applied, errors, source_snippets(name, errors), symbols)
        answer, model = agent.ask(prompt)
        diff = agent.extract_diff(answer)
        agent.save_round(tmp, k, prompt, answer, diff)
        info = {"round": k, "model": model, "files": agent.patch_files(diff), "prompt_chars": len(prompt),
                "applied": False, "accepted": False}
        if diff:
            info["applied"], info["apply_output"] = apply_patch(name, tmp / f"ai_round{k}.patch", f"ai_{name}_{k}")
        if not info["applied"]:
            rounds[-1].setdefault("ai", []).append(info)
            print(f"[{name}] ai round {k}: no applicable patch ({info.get('apply_output', 'no diff')[-120:]})", flush=True)
            break
        rec, logs = attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp)
        rec["errors"] = sum(1 for line in logs["build"].splitlines()
                            if " error: " in line or "undefined reference" in line or "cannot find -l" in line)
        rec["matched_rules"], rec["cmake_args"] = [], list(cmake_args)
        passed = rec["build_exit"] == "0" and rec["configure_exit"] == "0"
        info["accepted"] = passed or rec["errors"] < best
        if info["accepted"]:
            best, log = rec["errors"], logs["configure"] + "\n" + logs["build"]
        else:
            apply_patch(name, tmp / f"ai_round{k}.patch", f"ai_{name}_{k}", reverse=True)
        rec["ai"] = [info]
        rounds.append(rec)
        print(f"[{name}] ai round {k}: build={rec['build_exit']} errors={rec['errors']} files={info['files']} "
              f"accepted={info['accepted']} ({rec['seconds']} s)", flush=True)
        if passed or not info["accepted"]:
            break


def port(name, url, ref, subdir=".", cpu="x86_64", cmake_args=(), max_rounds=4, ai_rounds=0):
    tmp = LOCAL / name
    tmp.mkdir(parents=True, exist_ok=True)
    tc = tmp / "qnx.nto.toolchain.cmake"
    tc.write_text(scaffold.TOOLCHAIN)
    _worker("push", str(tc), "pp/qnx.nto.toolchain.cmake")
    # start from pristine upstream (LF line endings, so patches apply as written) and keep the patch series reproducible
    src = f"{REMOTE_ROOT}\\{name}"
    _worker("windows", f"if (Test-Path '{src}') {{ git -C '{src}' config core.autocrlf false; "
                       f"git -C '{src}' rm -q -r --cached . ; git -C '{src}' reset -q --hard }}")
    cflags, ldflags, rounds = ["-D_QNX_SOURCE"], [], []
    for i in range(max_rounds):
        rec, logs = attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp)
        log = logs["configure"] + "\n" + logs["build"]
        rules = fixes.match(log)
        new_c, new_l = fixes.apply(rules, cflags, ldflags)
        rec["matched_rules"] = [r.name for r in rules]
        rec["cmake_args"] = list(cmake_args)
        rec["errors"] = sum(1 for line in logs["build"].splitlines()
                            if " error: " in line or "undefined reference" in line or "cannot find -l" in line)
        rounds.append(rec)
        print(f"[{name}] round {i + 1}: configure={rec['configure_exit']} build={rec['build_exit']} errors={rec['errors']} "
              f"rules={rec['matched_rules']} ({rec['seconds']} s)", flush=True)
        if rec["build_exit"] == "0" and rec["configure_exit"] == "0":
            break
        patches = fixes.header_patches(log)
        if patches:
            rec["patches"] = [f"{Path(f).name}: <{a}> -> <{b}>" for f, a, b in patches]
            apply_header_patches(patches)
        if fixes.needs_queue_compat(log):
            hdr = find_project_header(name, "#define LIST_ENTRY")
            if hdr and f"-include {hdr}" not in " ".join(new_c):
                new_c = new_c + ["-include", hdr]
                rec.setdefault("patches", []).append(f"force-include project queue header {Path(hdr).name}")
        if fixes.needs_endian_compat(log):
            hdr = push_compat_header("portpilot_endian.h")
            if hdr not in new_c:
                new_c = new_c + ["-include", hdr]
                rec.setdefault("patches", []).append("force-include PortPilot endian helpers (htobe32, be32toh, ...)")
        if fixes.needs_link_response_file(log) and not any("LINKER_LAUNCHER" in a for a in cmake_args):
            launcher = f"{HOST_PYTHON};{push_compat_header('portpilot_link_launcher.py')}"
            cmake_args = list(cmake_args) + [f"-DCMAKE_C_LINKER_LAUNCHER={launcher}",
                                             f"-DCMAKE_CXX_LINKER_LAUNCHER={launcher}"]
            rec.setdefault("patches", []).append("linker launcher: object list to ld in its own response file "
                                                 "(Windows command-line limit)")
            patches = patches or ["link-launcher"]
        if fixes.needs_policy_minimum(log) and "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" not in cmake_args:
            cmake_args = list(cmake_args) + ["-DCMAKE_POLICY_VERSION_MINIMUM=3.5"]
            rec.setdefault("patches", []).append("configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)")
            patches = patches or ["policy"]
        stubs = fixes.stub_libraries(log)
        if stubs:
            stub_dir = make_stub_libs(cpu, stubs)
            if f"-L{stub_dir}" not in new_l:
                new_l = new_l + [f"-L{stub_dir}"]
            rec.setdefault("patches", []).append(f"empty stub archives for -l{', -l'.join(stubs)} (functions are in QNX libc)")
        net = fixes.netinet_files(log)
        if net:
            add_include(net, "netinet/in.h")
            rec.setdefault("patches", []).extend(f"{Path(f).name}: add <netinet/in.h>" for f in net)
            patches = patches or net
        if (new_c, new_l) == (cflags, ldflags) and not patches:
            break  # nothing new to try from the catalogue: leave for the next stage (an AI proposal)
        cflags, ldflags = new_c, new_l
    if ai_rounds and rounds[-1]["build_exit"] != "0":
        ai_stage(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp, rounds, log, ai_rounds)
    _worker("windows", f"git -C '{REMOTE_ROOT}\\{name}' diff --output='{REMOTE_ROOT}\\{name}.patch'")
    _worker("pull", f"pp/{name}.patch", str(tmp / f"{name}.patch"))
    report = {"name": name, "url": url, "ref": ref, "cpu": cpu, "rounds": rounds,
              "result": "built" if rounds[-1]["build_exit"] == "0" else "needs-patch"}
    (tmp / f"report_{cpu}.json").write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name"), ap.add_argument("url"), ap.add_argument("ref")
    ap.add_argument("--subdir", default=".")
    ap.add_argument("--cpu", default="x86_64")
    ap.add_argument("--cmake", action="append", default=[], help="one CMake argument, repeatable: --cmake=-DFOO=ON")
    ap.add_argument("--ai", type=int, default=0, help="AI patch rounds after the catalogue runs out (default 0)")
    a = ap.parse_args()
    print(json.dumps(port(a.name, a.url, a.ref, a.subdir, a.cpu, a.cmake, ai_rounds=a.ai), indent=1)[:2000])


if __name__ == "__main__":
    main()
