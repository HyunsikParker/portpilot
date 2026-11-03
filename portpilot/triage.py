"""Test triage: tests that build but fail on the QNX target get an AI patch that is judged on the target itself.

For one library, take the failing tests from a target run, show the model their output and the project code that
printed it, apply the diff it proposes, rebuild with the flags of the last good build, and rerun the library's tests on
the QNX VM. The patch is kept only if more tests pass and no test that passed before now fails; otherwise it is
reverted and the library rebuilt as it was.
usage: python -m portpilot triage <name> --run <target report tag> [--rounds 2]
"""
import argparse
import json
import re

from . import agent, remote, target

PROMPT = """You are porting the open-source project {name} ({ref}) to QNX 8.0. It now builds, but some of its own tests
fail when run on a QNX 8.0 x86_64 target. The project was configured and built on a Windows host with the QNX
toolchain (qcc, GCC 12.2, libc++), so build-time scripts and code generators ran on Windows; the tests run on QNX.

{facts}

Failing tests and the end of their output:

{failures}

Project code that prints or handles these messages:

{context}

Reply with one unified diff in git format (a/ and b/ prefixes, paths relative to the project root) and nothing else.
Fix the cause in the project's code, build files or test infrastructure. Do not weaken, skip or delete test assertions,
and do not change expected values. If the failure is a genuine difference in the platform's behaviour that the code
cannot address, reply with the single word UNFIXABLE."""

MESSAGE = re.compile(r"[A-Za-z][A-Za-z ,'_-]{14,}")


def failures_text(results, limit=6):
    out = []
    for r in results[:limit]:
        out.append(f"--- {r['test']} ({r['verdict']}, exit {r['rc']})\n" + "\n".join(r["log"][-15:]))
    if len(results) > limit:
        out.append(f"... and {len(results) - limit} more failing tests with similar output")
    return "\n\n".join(out)


def message_context(name, results, limit=3):
    """Lines in the project's sources that contain the longest phrases from the failure output."""
    phrases = []
    for r in results:
        for line in r["log"]:
            for m in MESSAGE.findall(line):
                p = m.strip()
                if p not in phrases and not p.startswith(("Expected", "Which is", "FAILED")):
                    phrases.append(p)
    phrases = sorted(phrases, key=len, reverse=True)[:limit]
    if not phrases:
        return ""
    root = f"{remote.HOST.work}\\{name}"
    pats = ",".join("'" + p.replace("'", "''") + "'" for p in phrases)
    ps = (f"$r = '{root}'; Get-ChildItem -LiteralPath $r -Recurse -File -Include *.c,*.h,*.cc,*.cpp,*.py,*.function,*.txt,"
          f"*.cmake | Select-String -SimpleMatch -Pattern @({pats}) -Context 4,4 | Select-Object -First 4 | ForEach-Object {{ "
          f"'FILE ' + $_.Path.Substring($r.Length + 1) + ':' + $_.LineNumber; $_.Context.PreContext; '> ' + $_.Line; "
          f"$_.Context.PostContext }}")
    return remote.HOST.ps(ps).replace("\r", "").strip()[:6000]


def counts(results):
    passed = {r["test"] for r in results if r["verdict"] == "PASS"}
    return passed, len(results)


def triage(name, run_tag, rounds=2, cpu="x86_64"):
    report = json.loads((remote.LOCAL / name / f"report_{cpu}.json").read_text())
    good = report["rounds"][-1]
    if report["result"] != "built":
        raise SystemExit(f"{name} does not build yet; run the port first")
    before = [r for r in json.loads((remote.LOCAL / f"target_{cpu}_{run_tag}.json").read_text())["results"]
              if r["library"] == name]
    tmp = remote.LOCAL / name
    history = []
    for k in range(1, rounds + 1):
        failing = [r for r in before if r["verdict"] != "PASS"]
        if not failing:
            break
        prompt = PROMPT.format(name=name, ref=report["ref"], facts=agent.QNX_FACTS, failures=failures_text(failing),
                               context=message_context(name, failing) or "(no matching source lines found)")
        answer, model = agent.ask(prompt)
        diff = agent.extract_diff(answer)
        agent.save_round(tmp, f"t{k}", prompt, answer, diff)
        step = {"round": k, "model": model, "files": agent.patch_files(diff), "unfixable": answer.strip() == "UNFIXABLE"}
        history.append(step)
        if not diff:
            print(f"[{name}] triage {k}: no patch ({'UNFIXABLE' if step['unfixable'] else 'no diff'})", flush=True)
            break
        patch = tmp / f"ai_roundt{k}.patch"
        step["applied"], step["apply_output"] = remote.apply_patch(name, patch, f"triage_{name}_{k}")
        if not step["applied"]:
            print(f"[{name}] triage {k}: patch did not apply", flush=True)
            break
        rec, _ = remote.attempt(name, report["url"], report["ref"], report.get("subdir", "."), cpu, good["cflags"],
                                good["ldflags"], good["cmake_args"], tmp)
        built = rec["build_exit"] == "0" and rec["configure_exit"] == "0"
        after = []
        if built:
            after = target.run([name], cpu, deadline=7200, tag=f"triage_{name}_{k}")["results"]
        p0, _ = counts(before)
        p1, _ = counts(after)
        step.update(built=built, passed_before=len(p0), passed_after=len(p1), regressions=sorted(p0 - p1))
        step["accepted"] = built and len(p1) > len(p0) and not (p0 - p1)
        print(f"[{name}] triage {k}: {step['files']} built={built} passed {len(p0)} -> {len(p1)} "
              f"regressions={len(step['regressions'])} accepted={step['accepted']}", flush=True)
        if step["accepted"]:
            before = after
            continue
        run_file = remote.LOCAL / f"target_{cpu}_triage_{name}_{k}.json"
        if run_file.exists():   # keep the record but stop the report from showing results of a reverted patch
            data = json.loads(run_file.read_text())
            data["rejected"] = True
            run_file.write_text(json.dumps(data, indent=1))
        remote.apply_patch(name, patch, f"triage_{name}_{k}", reverse=True)
        remote.attempt(name, report["url"], report["ref"], report.get("subdir", "."), cpu, good["cflags"],
                       good["ldflags"], good["cmake_args"], tmp)
        break
    report["triage"] = history
    remote.HOST.ps(f"git -C '{remote.HOST.work}\\{name}' diff --output='{remote.HOST.work}\\{name}.patch'")
    remote.HOST.get(f"{remote.HOST.work}\\{name}.patch", tmp / f"{name}.patch")
    (tmp / f"report_{cpu}.json").write_text(json.dumps(report, indent=1))
    return history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--run", required=True, help="tag of the target run whose failures to triage")
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()
    print(json.dumps(triage(a.name, a.run, a.rounds), indent=1)[:3000])


if __name__ == "__main__":
    main()
