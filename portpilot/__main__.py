"""PortPilot command line.

    python -m portpilot port <name> <git-url> <ref> [--cmake=-DFOO=ON ...] [--cpu x86_64|aarch64le] [--ai N]
    python -m portpilot test <name> [<name> ...] [--deadline 3600] [--tag run1]
    python -m portpilot triage <name> --run <tag> [--rounds 2]
    python -m portpilot vm build [--arch x86_64]
    python -m portpilot report [--out runs/report.html]
    python -m portpilot export <name> [<name> ...]          # ports/<name>/: recipe.json, patch, README
"""
import sys

from . import export, remote, report, target, triage, vm

COMMANDS = {"export": export.main, "port": remote.main, "report": report.main, "triage": triage.main, "vm": vm.main}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in (*COMMANDS, "test"):
        sys.exit(__doc__)
    cmd = sys.argv.pop(1)
    if cmd == "test":
        sys.argv.insert(1, "run")
        target.main()
    else:
        COMMANDS[cmd]()


if __name__ == "__main__":
    main()
