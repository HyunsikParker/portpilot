"""Turn a finished port into a recipe directory, ports/<name>/, that can be reviewed and replayed.

    recipe.json   upstream URL and tag, the CMake arguments given, and per CPU the result and the flags and
                  arguments PortPilot ended with
    <name>.patch  the source changes (catalogue header edits and accepted AI patches), if there are any
    README.md     what was changed and why, the command that reproduces the port, and the target test results
usage: python -m portpilot export <name> [<name> ...]
"""
import argparse
import json
import shutil
from pathlib import Path

from .report import fixes_applied, load

ROOT = Path(__file__).resolve().parent.parent


def recipe(name, reps):
    first = next(iter(reps.values()))
    given = first["rounds"][0].get("cmake_args", [])
    cpus = {}
    for cpu, r in reps.items():
        last = r["rounds"][-1]
        cpus[cpu] = {"result": r["result"], "rounds": len(r["rounds"]), "cflags": last.get("cflags", []),
                     "ldflags": last.get("ldflags", []), "cmake_args": last.get("cmake_args", []),
                     "fixes": fixes_applied(r)}
    ai = [a for r in reps.values() for rnd in r["rounds"] for a in rnd.get("ai", [])]
    triage = [t for r in reps.values() for t in r.get("triage", [])]
    return {"name": name, "url": first["url"], "ref": first["ref"], "subdir": first.get("subdir", "."),
            "cmake_args": given, "cpus": cpus, "ai_patches": ai, "triage": triage}


def readme(rec, tests):
    cmd = (f"python -m portpilot port {rec['name']} {rec['url']} {rec['ref']} "
           + " ".join(f"--cmake={a}" for a in rec["cmake_args"])
           + (f" --ai {len(rec['ai_patches'])}" if rec["ai_patches"] else "")).strip()
    lines = [f"# {rec['name']} {rec['ref']} on QNX 8.0", "", f"Upstream: {rec['url']}", "", "## Result", ""]
    for cpu, c in rec["cpus"].items():
        lines.append(f"- {cpu}: {c['result']} in {c['rounds']} build round(s)")
    if tests:
        res = tests["results"]
        passed = sum(1 for r in res if r["verdict"] == "PASS")
        lines.append(f"- tests on a QNX 8.0 x86_64 QEMU target: {passed} of {len(res)} CTest entries pass")
        failing = [r for r in res if r["verdict"] != "PASS"]
        if failing:
            lines += ["", "Entries that did not pass:", ""]
            lines += [f"- `{r['test']}`: {r['verdict'].lower()} (exit {r['rc']})" for r in failing[:30]]
            if len(failing) > 30:
                lines.append(f"- ... {len(failing) - 30} more")
    lines += ["", "## Changes", ""]
    fixes = rec["cpus"].get("x86_64", next(iter(rec["cpus"].values())))["fixes"]
    lines += [f"- {f}" for f in fixes]
    if not fixes and not rec["ai_patches"] and not rec["triage"]:
        lines.append("- none: the project built with the QNX toolchain file as it is")
    for a in rec["ai_patches"]:
        state = "kept" if a.get("accepted") else "reverted"
        lines.append(f"- AI patch round {a['round']} ({a.get('model', '?')}): {', '.join(a.get('files', []))} - {state}")
    for t in rec["triage"]:
        state = "kept" if t.get("accepted") else "reverted"
        lines.append(f"- test triage round {t['round']} ({t.get('model', '?')}): {', '.join(t.get('files', []))} - "
                     f"passing tests {t.get('passed_before', '?')} -> {t.get('passed_after', '?')}, {state}")
    lines += ["", "## Reproduce", "", "```", cmd, "```", ""]
    return "\n".join(lines)


def export(names, runs=ROOT / "runs", dest=ROOT / "ports"):
    ports, tests = load(runs)
    for n in names:
        if n not in ports:
            print(f"{n}: no port report in {runs}")
            continue
        rec = recipe(n, ports[n])
        out = dest / n
        out.mkdir(parents=True, exist_ok=True)
        (out / "recipe.json").write_text(json.dumps(rec, indent=1) + "\n")
        patch = runs / n / f"{n}.patch"
        if patch.exists() and patch.stat().st_size:
            shutil.copyfile(patch, out / f"{n}.patch")
        (out / "README.md").write_text(readme(rec, tests.get(n)))
        print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    export(a.names)


if __name__ == "__main__":
    main()
