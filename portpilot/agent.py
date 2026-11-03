"""AI patch stage: when the fix catalogue has nothing left to try, ask a language model for a source patch.

The model sees the project's own compiler errors and the upstream source lines around them, never QNX SDP files:
diagnostics that point into the SDP are dropped before the prompt is built. Its answer must be a unified diff. The diff is
applied to the upstream copy on the build host and kept only if the rebuild gets further (it passes, or the error count
falls); otherwise it is reverted. Accepted patches still have to pass the project's own tests on the QNX target.

Backends (PORTPILOT_LLM): claude-cli (default; the local Claude Code CLI in print mode with no tools, model
PORTPILOT_LLM_MODEL, optional PORTPILOT_LLM_EFFORT) or openai
(any OpenAI-compatible chat endpoint, including a local Ollama: PORTPILOT_LLM_BASE_URL, PORTPILOT_LLM_MODEL).
"""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ERROR = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+?):(?P<line>\d+):(?P<col>\d+): (?:fatal )?error: (?P<msg>.+)$", re.M)
CMAKE_ERROR = re.compile(r"^CMake Error at (?P<file>[^\n]+?):(?P<line>\d+) \((?P<cmd>\w+)\):\n(?P<msg>(?: {2}.*\n?)+)", re.M)
UNDEFINED = re.compile(r"undefined reference to `([^']+)'")
SDP_MARKERS = ("qnx800", "/target/qnx/", "\\target\\qnx\\", "/host/win64/", "\\host\\win64\\")
MAX_ERRORS = 8
CONTEXT = 12
WHOLE_FILE = 200   # files this short go into the prompt whole, so a rewrite is possible

QNX_FACTS = """Target: QNX Neutrino 8.0 (POSIX, BSD-derived socket API in libsocket, GCC 12.2 via qcc, C++ library libc++).
Things QNX 8.0 does not have: epoll, inotify, eventfd, signalfd, timerfd, <sys/sysctl.h>, <sys/prctl.h>, <execinfo.h>,
<sys/random.h>/getrandom (use arc4random_buf or /dev/random), sched_getaffinity, Linux /proc layout.
Things QNX keeps in libc: pthread, rt, dl, util functions. The compiler defines __QNX__ and __QNXNTO__.
Networking: QNX 8.0 replaced the io-pkt stack of QNX 7 with io-sock, which is based on FreeBSD. io-pkt interfaces such
as <sys/dcmd_io-net.h>, <net/ifdrvcom.h>, devctl(SIOCGDRVCOM) and nic_stats_t are gone; per-interface counters come
from getifaddrs(): AF_LINK entries carry a struct if_data in ifa_data (ifi_ipackets, ifi_opackets, ifi_ibytes,
ifi_obytes). Code written for QNX 7 must be rewritten against these, not just have its includes guarded."""

PROMPT = """You are porting the open-source project {name} ({ref}) to QNX 8.0. The build still fails after these
QNX fixes were applied: {applied}.

{facts}

{errors}

Reply with one unified diff in git format (a/ and b/ prefixes, paths relative to the project root) and nothing else.
Make the smallest change that lets this code build and behave correctly on QNX. Guard QNX-only code with
#if defined(__QNX__) so other platforms are unaffected. Do not touch tests to make them pass and do not delete features
unless QNX cannot support them, in which case disable them only on QNX."""


def _from_sdp(path):
    return any(m in path for m in SDP_MARKERS)


def collect_errors(log, project_root):
    """[(relative file, line, message)] for distinct errors in the project's own files."""
    root = project_root.replace("\\", "/").rstrip("/") + "/"
    out, seen = [], set()
    for m in CMAKE_ERROR.finditer(log):   # configure errors come first: nothing compiles until they are fixed
        f = m["file"].replace("\\", "/")
        if _from_sdp(f) or "/share/cmake" in f.lower():
            continue
        rel = f[len(root):] if f.lower().startswith(root.lower()) else f
        msg = " ".join(m["msg"].split())
        if (rel, msg) not in seen:
            seen.add((rel, msg))
            out.append((rel, int(m["line"]), f"CMake {m['cmd']}: {msg}"))
    for m in ERROR.finditer(log):
        f = m["file"].replace("\\", "/")
        if _from_sdp(f):
            continue
        rel = f[len(root):] if f.lower().startswith(root.lower()) else f
        key = (rel, m["msg"].strip())
        if key in seen:
            continue
        seen.add(key)
        out.append((rel, int(m["line"]), m["msg"].strip()))
        if len(out) >= MAX_ERRORS:
            break
    return out


def undefined_symbols(log):
    return sorted(set(UNDEFINED.findall(log)))[:20]


def build_prompt(name, ref, applied, errors, snippets, symbols, symbol_notes=""):
    parts = ["Build errors (paths relative to the project root) with the source around each one:"] if errors else []
    for (rel, line, msg), snip in zip(errors, snippets):
        parts.append(f"--- {rel}:{line}: error: {msg}\n{snip}")
    if symbols:
        parts.append("Undefined symbols at link time: " + ", ".join(symbols))
    if symbol_notes:
        parts.append("Where those symbols are defined, and the build-file lines that mention the defining files:\n"
                     + symbol_notes)
    return PROMPT.format(name=name, ref=ref, applied=", ".join(applied) or "none", facts=QNX_FACTS,
                         errors="\n\n".join(parts))


def extract_diff(text):
    """The unified diff in a model answer, with any Markdown fence removed; '' if there is none."""
    fence = re.search(r"```(?:diff|patch)?\n(.*?)```", text, re.S)
    body = fence.group(1) if fence else text
    start = re.search(r"^(diff --git |--- a/)", body, re.M)
    return body[start.start():].rstrip() + "\n" if start else ""


def ask(prompt):
    backend = os.environ.get("PORTPILOT_LLM", "claude-cli")
    if backend == "openai":
        base = os.environ.get("PORTPILOT_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        body = json.dumps({"model": os.environ["PORTPILOT_LLM_MODEL"], "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(f"{base}/chat/completions", body, {"Content-Type": "application/json"})
        key = os.environ.get("PORTPILOT_LLM_API_KEY")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)["choices"][0]["message"]["content"], os.environ["PORTPILOT_LLM_MODEL"]
    model = os.environ.get("PORTPILOT_LLM_MODEL", "claude-opus-5-5")
    env = {k: os.environ[k] for k in ("HOME", "USER", "PATH", "TMPDIR") if k in os.environ}
    cmd = ["claude", "--safe-mode", "-p", "--tools", "", "--model", model, "--output-format", "text",
           "--no-session-persistence"]
    if os.environ.get("PORTPILOT_LLM_EFFORT"):   # e.g. medium: faster answers for routine porting errors
        cmd += ["--effort", os.environ["PORTPILOT_LLM_EFFORT"]]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {r.stderr[-400:]}")
    return r.stdout, model


def patch_files(diff):
    return sorted(set(re.findall(r"^\+\+\+ b/(\S+)", diff, re.M)))


def save_round(dest: Path, k, prompt, answer, diff):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"ai_round{k}_prompt.txt").write_text(prompt)
    (dest / f"ai_round{k}_answer.txt").write_text(answer)
    if diff:
        (dest / f"ai_round{k}.patch").write_text(diff)
