"""CMake linker launcher for Windows hosts: hand the object list to ld in its own response file.

qcc expands '@file' arguments itself and then starts ld with every object on the command line, so a link with hundreds
of objects passes the 32 KiB Windows limit and fails as "spawn of ...-ld failed: No such file or directory". This
launcher rewrites each CMake response file argument into '-Wl,@<objects>', which qcc passes to ld unexpanded, and keeps
libraries and other flags on the qcc command line in their original order.
usage (set by PortPilot): CMAKE_<LANG>_LINKER_LAUNCHER=<python>;<this file>
"""
import os
import re
import subprocess
import sys

TOKEN = re.compile(r'"([^"]*)"|(\S+)')
OBJECT = (".o", ".obj")


def split_rsp(path):
    with open(path) as f:
        return [a or b for a, b in TOKEN.findall(f.read())]


def rewrite(argv):
    out = []
    for arg in argv:
        rsp = arg[1:]
        if not (arg.startswith("@") and os.path.isfile(rsp)):
            out.append(arg)
            continue
        tokens = split_rsp(rsp)
        objects = [t for t in tokens if t.endswith(OBJECT) and not t.startswith("-")]
        if not objects:
            out.append(arg)
            continue
        listing = rsp + ".objects"
        with open(listing, "w") as f:
            f.write("\n".join('"' + o.replace("\\", "/") + '"' for o in objects) + "\n")
        out.append("-Wl,@" + listing.replace("\\", "/"))
        out += [t for t in tokens if t not in objects]
    return out


if __name__ == "__main__":
    sys.exit(subprocess.call(rewrite(sys.argv[1:])))
