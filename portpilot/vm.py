"""Build the QNX 8.0 QEMU image that target test runs boot, using the SDP's mkqnximage.

The image carries PortPilot's snippets from vm/: post_start.custom mounts a second disk (/dev/hd1) on /tests at the end of
startup, runs /tests/run.sh and shuts down (target.py writes that disk for each run); passwd_file.custom and
group_file.custom add the unprivileged user 'nobody' that some test suites expect.
usage: python -m portpilot.vm build [--arch x86_64]      (re-run after changing the boot hook; takes a minute)
"""
import argparse
from pathlib import Path

from . import host

SNIPPETS = Path(__file__).resolve().parent.parent / "vm"   # *.custom files go to the image's local/snippets


def build(arch):
    h = host.from_env()
    image = rf"{h.vm}\{arch}"
    for snippet in sorted(SNIPPETS.glob("*.custom")):
        h.put(snippet, rf"{image}\local\snippets\{snippet.name}")
    out = h.run_bat("\r\n".join([
        "@echo off",
        f"call {h.sdp_env} >nul 2>&1",
        f"cd /d {image}",
        # --force: the directory already holds local\snippets; --clean: snippets are only read on a full rebuild
        f"call {h.sdp}\\host\\common\\bin\\mkqnximage.bat --clean --force --type=qemu --arch={arch} --hostname=portpilot "
        f"--ssh-ident=none --data-size=512 --noprompt > {h.vm}\\mkqnximage_{arch}.log 2>&1",
        "echo mkqnximage_exit=%ERRORLEVEL%", ""]), rf"{h.vm}\build_{arch}.bat", timeout=1800)
    ok = "mkqnximage_exit=0" in out
    print(f"mkqnximage {arch}: {'ok' if ok else 'failed'} (log {h.vm}\\mkqnximage_{arch}.log)")
    if not ok:
        print(h.ps(f"Get-Content '{h.vm}\\mkqnximage_{arch}.log' -Tail 8"))
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--arch", default="x86_64", choices=["x86_64", "aarch64le"])
    a = ap.parse_args()
    raise SystemExit(0 if build(a.arch) else 1)


if __name__ == "__main__":
    main()
