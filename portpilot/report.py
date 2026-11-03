"""Write one self-contained HTML page from the port reports and target test runs in runs/.

usage: python -m portpilot.report [--runs runs] [--out runs/report.html]
The page lists each library with its build result per CPU, the fixes PortPilot applied, any AI patch rounds, and the
project's own test results on the QNX target. It carries no timing figures: the reports record host build times only,
and QNX performance results are not published.
"""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

CPUS = ("x86_64", "aarch64le")
VERDICTS = ("PASS", "FAIL", "TIMEOUT", "SKIP")

CSS = """
:root { --ink:#1b1b1b; --muted:#5d5d5d; --line:#d9d9d6; --paper:#fbfbf9; --panel:#f1f1ee; --ok:#1f6f43; --bad:#a1281e;
        --warn:#8a5a00; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink:#e8e8e4; --muted:#a3a39e; --line:#3a3a37; --paper:#151514;
        --panel:#1f1f1d; --ok:#6fcf97; --bad:#ff8a7a; --warn:#e3b45c; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 17px; margin: 36px 0 10px; }
.lede { color: var(--muted); margin: 0 0 20px; max-width: 72ch; }
.facts { display: flex; flex-wrap: wrap; gap: 8px 28px; padding: 12px 0; border-top: 1px solid var(--line);
         border-bottom: 1px solid var(--line); font-size: 14px; }
.facts b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; }
.facts span { color: var(--muted); }
.wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.ok { color: var(--ok); } .bad { color: var(--bad); } .warn { color: var(--warn); } .muted { color: var(--muted); }
code, .mono { font: 13px/1.45 ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
details { border-bottom: 1px solid var(--line); padding: 10px 0; }
summary { cursor: pointer; font-weight: 600; }
summary:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.round { margin: 8px 0 0 0; padding: 8px 12px; background: var(--panel); border-radius: 6px; }
.round p { margin: 2px 0; }
pre { margin: 6px 0 0; padding: 8px 10px; background: var(--panel); border-radius: 6px; overflow-x: auto; font-size: 12px; }
ul { margin: 4px 0; padding-left: 20px; }
footer { margin-top: 40px; color: var(--muted); font-size: 13px; }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def load(runs: Path):
    ports = {}
    for f in sorted(runs.glob("*/report_*.json")):
        r = json.loads(f.read_text())
        ports.setdefault(r["name"], {})[r["cpu"]] = r
    tests = {}
    for f in sorted(runs.glob("target_*.json"), key=lambda p: p.stat().st_mtime):
        t = json.loads(f.read_text())
        if t.get("rejected"):
            continue
        by_lib = {}
        for res in t.get("results", []):
            by_lib.setdefault(res["library"], []).append(res)
        for lib, results in by_lib.items():   # a later run replaces an earlier one for the same library
            tests[lib] = {"cpu": t["cpu"], "results": results, "finished": t.get("finished")}
    return ports, tests


def fixes_applied(report):
    seen = []
    for rnd in report["rounds"]:
        for item in rnd.get("matched_rules", []) + rnd.get("patches", []):
            if item not in seen:
                seen.append(item)
    return seen


def build_cell(report):
    if not report:
        return '<td class="muted">not run</td>'
    if report["result"] == "built":
        return f'<td class="ok">built <span class="muted">({len(report["rounds"])} rounds)</span></td>'
    return f'<td class="bad">needs patch <span class="muted">({len(report["rounds"])} rounds)</span></td>'


def test_cell(entry):
    if not entry:
        return '<td class="muted">not run</td>'
    counts = {v: sum(1 for r in entry["results"] if r["verdict"] == v) for v in VERDICTS}
    total = sum(counts.values())
    cls = "ok" if counts["PASS"] == total else ("warn" if counts["PASS"] else "bad")
    extra = ", ".join(f"{counts[v]} {v.lower()}" for v in ("FAIL", "TIMEOUT", "SKIP") if counts[v])
    return f'<td class="num {cls}">{counts["PASS"]}/{total} pass{(" · " + esc(extra)) if extra else ""}</td>'


def round_html(i, rnd):
    status = "built" if rnd["build_exit"] == "0" and rnd["configure_exit"] == "0" else (
        "configure failed" if rnd["configure_exit"] != "0" else f'{rnd["errors"]} errors')
    lines = [f'<div class="round"><p><b>Round {i}</b> · {esc(status)}</p>']
    if rnd.get("matched_rules"):
        lines.append(f'<p>Rules matched: <code>{esc(", ".join(rnd["matched_rules"]))}</code></p>')
    for p in rnd.get("patches", []):
        lines.append(f"<p>Change: {esc(p)}</p>")
    for ai in rnd.get("ai", []):
        verdict = "kept" if ai.get("accepted") else ("reverted" if ai.get("applied") else "not applied")
        files = ", ".join(ai.get("files", [])) or "no files"
        lines.append(f'<p>AI patch (round {ai["round"]}, {esc(ai["model"])}): {esc(files)} · <b>{verdict}</b></p>')
    lines.append("</div>")
    return "\n".join(lines)


def page(ports, tests, generated):
    names = sorted(set(ports) | set(tests), key=str.lower)
    built = {cpu: sum(1 for n in names if ports.get(n, {}).get(cpu, {}).get("result") == "built") for cpu in CPUS}
    all_results = [r for n in names for r in tests.get(n, {}).get("results", [])]
    passed = sum(1 for r in all_results if r["verdict"] == "PASS")
    rows, details = [], []
    for n in names:
        reps = ports.get(n, {})
        any_rep = reps.get("x86_64") or next(iter(reps.values()), None)
        ref = esc(any_rep["ref"]) if any_rep else ""
        fx = fixes_applied(reps["x86_64"]) if reps.get("x86_64") else []
        rows.append(f'<tr><td><b>{esc(n)}</b> <span class="muted mono">{ref}</span></td>'
                    + "".join(build_cell(reps.get(c)) for c in CPUS) + test_cell(tests.get(n))
                    + f'<td>{esc("; ".join(fx)) if fx else "<span class=muted>none</span>"}</td></tr>')
        body = []
        for cpu, rep in reps.items():
            body.append(f'<p class="muted">{esc(cpu)} · <a href="{esc(rep["url"])}">{esc(rep["url"])}</a></p>')
            body += [round_html(i + 1, r) for i, r in enumerate(rep["rounds"])]
        for rep in reps.values():
            for t in rep.get("triage", []):
                verdict = "kept" if t.get("accepted") else ("UNFIXABLE" if t.get("unfixable") else "reverted")
                body.append(f'<div class="round"><p><b>Test triage {t["round"]}</b> ({esc(t["model"])}): '
                            f'{esc(", ".join(t.get("files", [])) or "no patch")} · passed '
                            f'{t.get("passed_before", "?")} → {t.get("passed_after", "?")} · <b>{verdict}</b></p></div>')
        failing = [r for r in tests.get(n, {}).get("results", []) if r["verdict"] != "PASS"]
        if failing:
            body.append("<p><b>Tests that did not pass on the target</b></p>")
            for r in failing:
                body.append(f'<p class="mono">{esc(r["test"])} · {esc(r["verdict"])} (exit {r["rc"]})</p>')
                if r.get("log"):
                    body.append("<pre>" + esc("\n".join(r["log"][-12:])) + "</pre>")
        details.append(f"<details><summary>{esc(n)}</summary>{''.join(body)}</details>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PortPilot report</title><style>{CSS}</style></head><body><main>
<h1>PortPilot port report</h1>
<p class="lede">Open-source C and C++ libraries ported to QNX 8.0 by PortPilot: built with the QNX SDP 8.0 toolchain
(qcc, GCC 12.2) for x86_64 and aarch64le, then each project's own CTest suite run on a QNX 8.0 x86_64 QEMU target.</p>
<div class="facts">
<div><b>{len(names)}</b><span>libraries</span></div>
<div><b>{built["x86_64"]}</b><span>built for x86_64</span></div>
<div><b>{built["aarch64le"]}</b><span>built for aarch64le</span></div>
<div><b>{passed}/{len(all_results)}</b><span>CTest entries passed on the target</span></div>
</div>
<h2>Libraries</h2>
<div class="wrap"><table>
<thead><tr><th>Library</th><th>x86_64</th><th>aarch64le</th><th>Tests on QNX target</th><th>Fixes applied</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>Details</h2>
{''.join(details)}
<footer>Generated {esc(generated)} from runs/*/report_*.json and runs/target_*.json.</footer>
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(Path(__file__).resolve().parent.parent / "runs"))
    ap.add_argument("--out")
    a = ap.parse_args()
    runs = Path(a.runs)
    ports, tests = load(runs)
    out = Path(a.out) if a.out else runs / "report.html"
    out.write_text(page(ports, tests, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    print(out)


if __name__ == "__main__":
    main()
