"""Build a CMake project for QNX 8.0 on the build host (see host.py) and iterate on build errors.

The loop is: configure and build -> read the log -> match catalogue rules -> rebuild with the added flags, until the build
passes or no rule matches. Every attempt and the flags it used are written to a JSON report next to the logs.
usage: python -m portpilot.remote <name> <git-url> <ref> [--subdir build/cmake] [--cmake=-DFOO=ON ...] [--cpu x86_64]
"""
import argparse
import json
import re
import time
from pathlib import Path

from . import agent, fixes, host, scaffold

HOST = host.from_env()
LOCAL = Path(__file__).resolve().parent.parent / "runs"


def _bat(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args):
    src = f"{HOST.work}\\{name}"
    bld = f"{HOST.work}\\build_{name}_{cpu}"
    # QNX names: binutils prefix nto<cpu> (x86_64, aarch64); qcc variant and target dir use aarch64le for little-endian ARM
    tool_cpu = "aarch64" if cpu.startswith("aarch64") else cpu
    var_cpu = "aarch64le" if cpu.startswith("aarch64") else cpu
    args = " ".join(cmake_args)
    return "\r\n".join([
        "@echo off",
        f"call {HOST.sdp_env} >nul 2>&1",
        f"set HOSTCC={HOST.cc}",
        f"cd /d {HOST.work}",
        f"if not exist {src} git -c core.autocrlf=false clone -q -c core.autocrlf=false --depth 1 --recurse-submodules "
        f"--shallow-submodules --branch {ref} {url} {src}",
        f"if exist {bld} rmdir /s /q {bld}",
        f'cmake -G Ninja -S {src}\\{subdir} -B {bld} -DCMAKE_TOOLCHAIN_FILE={HOST.work}\\qnx.nto.toolchain.cmake '
        f'-DCPU={tool_cpu} -DCMAKE_SYSTEM_PROCESSOR={var_cpu} -DCPUVARDIR={var_cpu} -DCMAKE_BUILD_TYPE=Release '
        f'"-DPORTPILOT_C_FLAGS={" ".join(cflags)}" "-DPORTPILOT_LD_FLAGS={" ".join(ldflags)}" {args} '
        f"> {HOST.work}\\{name}_{cpu}_configure.log 2>&1",
        "echo configure_exit=%ERRORLEVEL%",
        f"cmake --build {bld} -j 8 -- -k 0 > {HOST.work}\\{name}_{cpu}_build.log 2>&1",
        "echo build_exit=%ERRORLEVEL%",
        "",
    ])


def attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp):
    t0 = time.time()
    out = HOST.run_bat(_bat(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args), f"{HOST.work}\\run_{name}.bat")
    secs = time.time() - t0
    codes = dict(line.strip().split("=", 1) for line in out.splitlines() if line.strip().startswith(("configure_exit=", "build_exit=")))
    logs = {}
    for kind in ("configure", "build"):
        dest = tmp / f"{name}_{cpu}_{kind}.log"
        dest.unlink(missing_ok=True)  # never read an earlier attempt's log if this pull fails
        HOST.get(f"{HOST.work}\\{name}_{cpu}_{kind}.log", dest)
        logs[kind] = dest.read_text(errors="ignore") if dest.exists() else ""
    return {"configure_exit": codes.get("configure_exit"), "build_exit": codes.get("build_exit"), "seconds": round(secs, 1),
            "cflags": list(cflags), "ldflags": list(ldflags)}, logs


def apply_header_patches(patches):
    """Edit the remote upstream copy in place; the final `git diff` becomes the port's patch series."""
    for f, old, new in patches:
        ps = (f"$f='{f}'; (Get-Content -LiteralPath $f -Raw) -replace '#include\\s*<{old.replace('.', '[.]')}>', "
              f"'#include <{new}>' | Set-Content -LiteralPath $f -NoNewline")
        HOST.ps(ps)


COMPAT = Path(__file__).resolve().parent.parent / "compat"


def push_compat_header(name):
    """Copy a PortPilot compat header to <work>/portpilot_compat on the build host; returns its path with forward slashes."""
    HOST.put(COMPAT / name, f"{HOST.work}\\portpilot_compat\\{name}")
    return f"{HOST.work}\\portpilot_compat\\{name}".replace("\\", "/")


def make_stub_libs(cpu, libs):
    """Empty static archives (just the ar magic) in <work>/qnx_stubs/<cpu>; returns the directory with forward slashes."""
    d = f"{HOST.work}\\qnx_stubs\\{cpu}"
    files = ",".join(f"'lib{n}.a'" for n in libs)
    ps = (f"New-Item -ItemType Directory -Force '{d}' | Out-Null; foreach ($n in @({files})) "
          f"{{ [IO.File]::WriteAllBytes((Join-Path '{d}' $n), [Text.Encoding]::ASCII.GetBytes(\"!<arch>`n\")) }}")
    HOST.ps(ps)
    return d.replace("\\", "/")


def find_project_header(name, needle):
    """First header in the upstream tree that contains `needle` (forward slashes), or None."""
    ps = (f"Get-ChildItem -LiteralPath '{HOST.work}\\{name}' -Recurse -Include *.h -File | "
          f"Select-String -SimpleMatch -Pattern '{needle}' -List | Select-Object -First 1 -ExpandProperty Path")
    out = HOST.ps(ps)
    lines = [l.strip() for l in out.splitlines() if l.strip().lower().endswith(".h")]
    return lines[0].replace("\\", "/") if lines else None


def add_include(files, header):
    """Insert #include <header> before the first #include of each file (once)."""
    for f in files:
        ps = (f"$f='{f}'; $t = Get-Content -LiteralPath $f -Raw; if ($t -notmatch '#include\\s*<{header.replace('.', '[.]')}>') "
              f"{{ $i = $t.IndexOf('#include'); $t = $t.Insert($i, '#include <{header}>' + [char]10); "
              f"Set-Content -LiteralPath $f -Value $t -NoNewline }}")
        HOST.ps(ps)


def source_snippets(name, errors):
    """Numbered upstream source lines around each error, the error line marked with '>'."""
    root = f"{HOST.work}\\{name}"
    # an ArrayList keeps each (file, line) pair intact; @(@('a',1)) would flatten a single pair
    adds = "; ".join(f"[void]$items.Add(@('{rel.replace(chr(39), chr(39) * 2)}',{line}))" for rel, line, _ in errors)
    ps = (f"$items = New-Object System.Collections.ArrayList; {adds}; foreach ($it in $items) {{ $f = $it[0]; if (-not [IO.Path]::IsPathRooted($f)) {{ $f = Join-Path '{root}' $f }}; "
          f"'@@SNIP'; if (Test-Path -LiteralPath $f) {{ $l = @(Get-Content -LiteralPath $f); $n = $it[1]; "
          f"$s = [Math]::Max(1, $n - {agent.CONTEXT}); $e = [Math]::Min($l.Count, $n + {agent.CONTEXT}); "
          f"if ($l.Count -le {agent.WHOLE_FILE}) {{ $s = 1; $e = $l.Count }}; "
          f"for ($i = $s; $i -le $e; $i++) {{ $m = ' '; if ($i -eq $n) {{ $m = '>' }}; '{{0,5}}{{1}} {{2}}' -f $i, $m, $l[$i - 1] }} }} }}")
    out = HOST.ps(ps)
    parts = out.replace("\r", "").split("@@SNIP\n")[1:]
    return [p.rstrip("\n") for p in parts] + [""] * (len(errors) - len(parts))


def symbol_context(name, symbols, limit=4):
    """For undefined symbols: the project files that define them and the build-file lines that mention those files.

    A symbol that is defined in the tree but missing at link time usually means the build skipped the defining file on
    this platform, which only the build files show."""
    if not symbols:
        return ""
    root = f"{HOST.work}\\{name}"
    alt = "|".join(re.escape(s) for s in symbols[:limit])
    ps = (f"$r = '{root}'; $defs = Get-ChildItem -LiteralPath $r -Recurse -File -Include *.c,*.cc,*.cpp,*.cxx | "
          f"Select-String -Pattern '^[A-Za-z_].*\\b({alt})\\s*\\([^;]*$' | Select-Object -First 6; "
          f"foreach ($d in $defs) {{ 'DEF ' + $d.Path.Substring($r.Length + 1) + ':' + $d.LineNumber + ': ' + $d.Line.Trim() }}; "
          f"$names = $defs | ForEach-Object {{ Split-Path $_.Path -Leaf }} | Sort-Object -Unique; "
          f"foreach ($n in $names) {{ Get-ChildItem -LiteralPath $r -Recurse -File -Include CMakeLists.txt,*.cmake | "
          f"Select-String -SimpleMatch -Pattern $n -Context 6,2 | Select-Object -First 3 | ForEach-Object {{ "
          f"'BUILD ' + $_.Path.Substring($r.Length + 1) + ':' + $_.LineNumber; $_.Context.PreContext; '> ' + $_.Line; "
          f"$_.Context.PostContext }} }}")
    out = HOST.ps(ps)
    return out.replace("\r", "").strip()[:6000]


def apply_patch(name, patch, tag, reverse=False):
    HOST.put(patch, f"{HOST.work}\\{tag}.patch")
    flag = "-R " if reverse else ""
    out = HOST.ps(f"git -C '{HOST.work}\\{name}' apply {flag}--recount --whitespace=nowarn "
                                f"'{HOST.work}\\{tag}.patch' 2>&1; \"apply_exit=$LASTEXITCODE\"")
    return "apply_exit=0" in out, out.strip()[-400:]


def progress(rec):
    """How far a build got: configure passing outranks everything, then fewer failed build steps (a fixed fatal error
    can expose many ordinary ones in the same file), then fewer error lines."""
    return (rec["configure_exit"] == "0", rec["build_exit"] == "0", -rec.get("failed_steps", 0), -rec["errors"])


def count_errors(build_log):
    return sum(1 for line in build_log.splitlines()
               if " error: " in line or "undefined reference" in line or "cannot find -l" in line)


def count_failed_steps(build_log):
    return sum(1 for line in build_log.splitlines() if line.startswith("FAILED:"))


def file_context(name, diff):
    """Numbered current lines around each hunk of a diff that did not apply, so the model can redo it."""
    pairs, current = [], None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif line.startswith("@@ -") and current:
            pairs.append((current, int(re.match(r"@@ -(\d+)", line).group(1)) + 3, ""))
    return pairs[:6], source_snippets(name, pairs[:6])


def catalogue_step(name, cpu, log, rec, cflags, ldflags, cmake_args):
    """Apply every catalogue fix the log calls for; returns the new flags and arguments and whether anything changed."""
    rules = fixes.match(log)
    new_c, new_l = fixes.apply(rules, cflags, ldflags)
    rec["matched_rules"] = [r.name for r in rules if r.cflags and any(f not in cflags for f in r.cflags)
                            or r.ldflags and any(f not in ldflags for f in r.ldflags)]
    changed = False
    patches = fixes.header_patches(log)
    if patches:
        rec["patches"] = [f"{Path(f).name}: <{a}> -> <{b}>" for f, a, b in patches]
        apply_header_patches(patches)
        changed = True
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
        launcher = f"{HOST.python};{push_compat_header('portpilot_link_launcher.py')}"
        cmake_args = list(cmake_args) + [f"-DCMAKE_C_LINKER_LAUNCHER={launcher}", f"-DCMAKE_CXX_LINKER_LAUNCHER={launcher}"]
        rec.setdefault("patches", []).append("linker launcher: object list to ld in its own response file "
                                             "(Windows command-line limit)")
        changed = True
    if fixes.needs_policy_minimum(log) and "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" not in cmake_args:
        cmake_args = list(cmake_args) + ["-DCMAKE_POLICY_VERSION_MINIMUM=3.5"]
        rec.setdefault("patches", []).append("configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)")
        changed = True
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
        changed = True
    changed = changed or (new_c, new_l) != (list(cflags), list(ldflags))
    return new_c, new_l, cmake_args, changed


def ai_step(name, ref, log, rounds, tmp, k, notes=()):
    """Ask the model for a patch and apply it to the upstream copy. Returns the round's record, or None if there was
    nothing to ask about or no patch could be applied (after one retry that shows the model the current file text)."""
    errors = agent.collect_errors(log, f"{HOST.work}\\{name}")
    symbols = agent.undefined_symbols(log)
    if not errors and not symbols:
        return None
    applied = sorted({r for rec in rounds for r in rec.get("matched_rules", [])}
                     | {p for rec in rounds for p in rec.get("patches", [])})
    prompt = agent.build_prompt(name, ref, applied, errors, source_snippets(name, errors), symbols,
                                symbol_context(name, symbols))
    if notes:
        prompt += "\n\nEarlier attempts that did not help and were reverted:\n\n" + "\n\n".join(notes)
    info = {"round": k, "applied": False, "accepted": False, "prompt_chars": len(prompt)}
    for attempt_no in (1, 2):
        answer, info["model"] = agent.ask(prompt)
        diff = agent.extract_diff(answer)
        agent.save_round(tmp, k if attempt_no == 1 else f"{k}b", prompt, answer, diff)
        info["files"] = agent.patch_files(diff)
        if not diff:
            info["apply_output"] = "no diff in the answer"
            break
        patch = tmp / f"ai_round{k}.patch"
        patch.write_text(diff)
        info["applied"], info["apply_output"] = apply_patch(name, patch, f"ai_{name}_{k}")
        if info["applied"]:
            break
        items, snippets = file_context(name, diff)
        prompt += ("\n\nYour previous diff did not apply: " + info["apply_output"][-300:]
                   + "\nHere is the current text of the lines it tried to change. Reply with a corrected diff.\n\n"
                   + "\n\n".join(f"--- {f}\n{snip}" for (f, _, _), snip in zip(items, snippets)))
    return info


def port(name, url, ref, subdir=".", cpu="x86_64", cmake_args=(), max_rounds=4, ai_rounds=0):
    """Build, then alternate catalogue fixes and (when the catalogue has nothing left) AI patches until the build
    passes or both are exhausted. An AI patch is kept only if the next build gets further; otherwise it is reverted."""
    tmp = LOCAL / name
    tmp.mkdir(parents=True, exist_ok=True)
    tc = tmp / "qnx.nto.toolchain.cmake"
    tc.write_text(scaffold.TOOLCHAIN)
    HOST.put(tc, f"{HOST.work}\\qnx.nto.toolchain.cmake")
    # start from pristine upstream (LF line endings, so patches apply as written) and keep the patch series reproducible
    src = f"{HOST.work}\\{name}"
    HOST.ps(f"if (Test-Path '{src}') {{ git -C '{src}' config core.autocrlf false; "
            f"git -C '{src}' rm -q -r --cached . ; git -C '{src}' reset -q --hard }}")
    cflags, ldflags, rounds = ["-D_QNX_SOURCE"], [], []
    catalogue_rounds = ai_used = 0
    pending = None   # (ai info, progress before the patch)
    notes = []       # rejected AI attempts, shown to the model in later rounds
    good_log = good_progress = None
    while True:
        rec, logs = attempt(name, url, ref, subdir, cpu, cflags, ldflags, cmake_args, tmp)
        log = logs["configure"] + "\n" + logs["build"]
        rec["errors"], rec["cmake_args"], rec["matched_rules"] = count_errors(logs["build"]), list(cmake_args), []
        rec["failed_steps"] = count_failed_steps(logs["build"])
        passed = rec["build_exit"] == "0" and rec["configure_exit"] == "0"
        if pending:
            info, before = pending
            info["accepted"] = passed or progress(rec) > before
            rec["ai"], pending = [info], None
            if not info["accepted"]:
                apply_patch(name, tmp / f"ai_round{info['round']}.patch", f"ai_{name}_{info['round']}", reverse=True)
                rounds.append(rec)
                print(f"[{name}] round {len(rounds)}: AI patch {info['files']} did not help; reverted", flush=True)
                after = agent.collect_errors(log, f"{HOST.work}\\{name}")[:5]
                notes.append(f"Attempt {info['round']} changed {', '.join(info['files'])}; the build then had "
                             f"{rec['errors']} errors in {rec['failed_steps']} failed steps, e.g.\n"
                             + "\n".join(f"  {f}:{line}: {msg}" for f, line, msg in after))
                if ai_used >= ai_rounds:
                    break
                ai_used += 1
                info = ai_step(name, ref, good_log, rounds, tmp, ai_used, notes)
                if not info or not info["applied"]:
                    break
                pending = (info, good_progress)
                continue
        rounds.append(rec)
        good_log, good_progress = log, progress(rec)
        tag = f" ai={rec['ai'][0]['files']}" if rec.get("ai") else ""
        if passed:
            print(f"[{name}] round {len(rounds)}: built{tag} ({rec['seconds']} s)", flush=True)
            break
        cflags_new, ldflags_new, cmake_args, changed = catalogue_step(name, cpu, log, rec, cflags, ldflags, cmake_args)
        print(f"[{name}] round {len(rounds)}: configure={rec['configure_exit']} build={rec['build_exit']} "
              f"errors={rec['errors']} rules={rec['matched_rules']}{tag} ({rec['seconds']} s)", flush=True)
        if changed and catalogue_rounds < max_rounds:
            catalogue_rounds += 1
            cflags, ldflags = cflags_new, ldflags_new
            continue
        if ai_used >= ai_rounds:
            break
        ai_used += 1
        info = ai_step(name, ref, log, rounds, tmp, ai_used, notes)
        if not info or not info["applied"]:
            if info:
                rec.setdefault("ai", []).append(info)
                print(f"[{name}] AI round {ai_used}: no applicable patch ({info['apply_output'][-120:]})", flush=True)
            break
        pending = (info, progress(rec))
    HOST.ps(f"git -C '{HOST.work}\\{name}' diff --output='{HOST.work}\\{name}.patch'")
    HOST.get(f"{HOST.work}\\{name}.patch", tmp / f"{name}.patch")
    built = rounds[-1]["build_exit"] == "0" and rounds[-1]["configure_exit"] == "0"
    report = {"name": name, "url": url, "ref": ref, "subdir": subdir, "cpu": cpu, "rounds": rounds,
              "result": "built" if built else "needs-patch"}
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
