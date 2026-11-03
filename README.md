# PortPilot

PortPilot ports open-source C and C++ libraries to QNX 8.0 and proves each port by running the project's own test
suite on a QNX 8.0 target. Give it a Git URL and a tag; it cross-compiles the project with the QNX toolchain, reads the
build log, applies known QNX porting fixes, asks a language model for a source patch when the known fixes run out,
and boots QNX in QEMU to run the project's CTest suite.

- QNX version: QNX SDP 8.0 (QNX OS 8.0.0)
- Target: QNX 8.0 x86_64 on QEMU, image built with the SDP's `mkqnximage --type=qemu`; aarch64le builds are checked
  with the toolchain only (see Limitations)
- Toolchain: `qcc` (GCC 12.2.0) through a generated CMake toolchain file, Ninja

## How a port runs

```
git clone ──► configure + build with qcc ──► read the log ──► catalogue fix? ──yes──► rebuild
                                                    │ no
                                                    ▼
                                          AI patch (unified diff) ──► rebuild ──► kept only if the build got further
                                                    │
built ──► test executables + shared libs + data on a qnx6 disk ──► boot QNX 8.0 in QEMU ──► one PASS/FAIL line per test
```

1. **Build loop** (`portpilot port`). Each round configures and builds the project for one CPU and counts the errors.
   The fix catalogue (`portpilot/fixes.py`) maps compiler and linker messages to changes: `-D_QNX_SOURCE` for hidden
   POSIX extensions, `-lsocket` and `-lregex` for libraries QNX keeps separate, stub archives for `-lpthread`/`-lrt`/`-ldl`
   (QNX has those functions in libc), header substitutions, a byte-order compat header, a doctest setting for libc++,
   and a linker launcher for links that exceed the Windows command-line limit. Every change is recorded with the
   message that triggered it.
2. **AI patch** (`--ai N`). When no catalogue rule applies, PortPilot sends the model the project's own errors with
   the surrounding source lines; for undefined symbols it adds the files that define them and the build-file lines
   that select those files. The model answers with a unified diff, which is applied to the upstream copy and kept
   only if the next build gets further (configure passes, or fewer errors). A diff that does not apply is sent back
   once with the current file text. Diagnostics that point into the QNX SDP are dropped, so no SDP file content
   leaves the build host.
3. **Target run** (`portpilot test`). PortPilot asks CTest for the test list, writes the test executables, the
   project's shared libraries and their working directories onto a qnx6 filesystem image, and attaches it as a second
   disk to the QNX VM. A boot hook (`vm/post_start.custom`) mounts it, runs each test with a time limit, prints one
   `PPTEST <library> <test> PASS|FAIL|TIMEOUT` line per test on the serial console, and powers the VM off.
4. **Report** (`portpilot report`). One HTML page per run directory: build result per CPU, the fixes applied, the AI
   rounds, and the tests that did not pass with their output.

The final `git diff` of each upstream copy is saved as `runs/<name>/<name>.patch`; together with the recorded CMake
arguments and flags it is the port.

## Requirements

A Windows build host with:

- QNX SDP 8.0 (a free non-commercial licence works), QEMU, CMake 3.21 or later, Ninja, Git and Python 3.10 or later
- optional: a MinGW-w64 `gcc` for projects whose code generators compile host helpers (`HOSTCC`), Perl for projects
  that generate sources with it (Git for Windows ships one)

PortPilot can run on the build host itself or drive it from another computer through a worker command (see
`portpilot/host.py`). Settings go in environment variables or a `.portpilot.env` file:

```
PORTPILOT_SDP=C:\qnx800
PORTPILOT_WORK=C:\portpilot\work
PORTPILOT_VM=C:\portpilot\vm
PORTPILOT_HOST_PYTHON=C:\Python313\python.exe
```

The AI stage uses the local Claude Code CLI by default (`claude -p`, no tools). Set `PORTPILOT_LLM=openai` with
`PORTPILOT_LLM_BASE_URL` and `PORTPILOT_LLM_MODEL` to use any OpenAI-compatible endpoint, including a local Ollama.

## Usage

```
python -m portpilot vm build                                  # once: QNX 8.0 x86_64 QEMU image with the boot hook
python -m portpilot port osqp https://github.com/osqp/osqp.git v1.0.0 --cmake=-DOSQP_BUILD_UNITTESTS=ON --ai 2
python -m portpilot port osqp https://github.com/osqp/osqp.git v1.0.0 --cpu aarch64le
python -m portpilot test osqp json-c --tag demo                # run their CTest suites on the QNX target
python -m portpilot report                                    # runs/report.html
```

## Results

See `runs/report.html` after a run. The table below is filled from the reports in this repository.

<!-- results table: generated -->

## Limitations

- Only CMake projects so far; `detect.py` recognises Meson, Autotools, Cargo and Make but there is no build driver
  for them yet.
- Target runs use x86_64. The base SDP has no QEMU aarch64 startup binary for `mkqnximage`, so aarch64le ports are
  build-checked only.
- QEMU runs under TCG without networking on a Windows host; tests that need a network peer or a broker are reported
  as failures or time-outs.
- Projects that build their own host code generator (Cyclone DDS's `idlc`) need that tool built for the host first.

## Licence

PortPilot is MIT licensed. Patches in `runs/` and in `ports/` apply to their upstream projects and fall under those
projects' licences. No QNX SDP files are included in this repository.
