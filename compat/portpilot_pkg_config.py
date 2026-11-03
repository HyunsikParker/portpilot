"""A minimal pkg-config for cross builds on Windows hosts, which usually have none.

It answers CMake's FindPkgConfig queries from the .pc files that `port --install` put under PortPilot's stage
directory, so a project that looks for an installed port through pkg-config finds it there and nowhere else. The .pc
files hold absolute paths into the stage directory, so no sysroot rewriting is needed.
usage (set by PortPilot): PKG_CONFIG_EXECUTABLE=<python>, PKG_CONFIG_ARGN=<this file>;--pc-dir=<stage>/<cpu>/usr/lib/pkgconfig
"""
import os
import re
import sys

VERSION = "0.29.2"
VAR = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")


def load(pc_dir, name):
    path = os.path.join(pc_dir, name + ".pc")
    if not os.path.isfile(path):
        return None
    variables, fields = {"pcfiledir": pc_dir.replace("\\", "/")}, {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.split("#", 1)[0].strip()
        m = re.match(r"([A-Za-z0-9_.]+)\s*([=:])\s*(.*)$", line)
        if not m:
            continue
        key, sep, value = m.groups()
        value = VAR.sub(lambda v: variables.get(v.group(1), ""), value)
        (variables if sep == "=" else fields)[key if sep == "=" else key.lower()] = value
    return variables, fields


def requires(fields):
    """Module names in Requires (version constraints dropped)."""
    names = []
    for part in fields.get("requires", "").replace(",", " ").split():
        if part[0].isalpha() or part[0] == "_":
            names.append(part)
    return names


def collect(pc_dir, names, key, seen=None):
    seen = set() if seen is None else seen
    out = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        mod = load(pc_dir, n)
        if mod:
            out += mod[1].get(key, "").split()
            out += collect(pc_dir, requires(mod[1]), key, seen)
    return out


def main(argv):
    pc_dir, opts, mods = os.environ.get("PKG_CONFIG_LIBDIR", ""), [], []
    for a in argv:
        if a.startswith("--pc-dir="):
            pc_dir = a.split("=", 1)[1]
        elif a.startswith("--"):
            opts.append(a)
        else:
            mods.append(a)
    if "--version" in opts:
        print(VERSION)
        return 0
    # "check >= 0.9" arrives as three arguments; keep the module names only
    names = [m for m in mods if (m[0].isalpha() or m[0] == "_") and m not in ("lt", "le", "gt", "ge", "eq")]
    missing = [n for n in names if load(pc_dir, n) is None]
    if missing:
        if "--print-errors" in opts:
            print(f"Package {missing[0]} was not found in the pkg-config search path ({pc_dir})", file=sys.stderr)
        return 1
    if "--exists" in opts:
        return 0
    words = []
    for o in opts:
        if o.startswith("--variable="):
            words.append(load(pc_dir, names[0])[0].get(o.split("=", 1)[1], ""))
        elif o == "--modversion":
            words += [load(pc_dir, n)[1].get("version", "") for n in names]
    libs = collect(pc_dir, names, "libs") + (collect(pc_dir, names, "libs.private") if "--static" in opts else [])
    cflags = collect(pc_dir, names, "cflags")
    picks = {"--libs": libs, "--libs-only-L": [w for w in libs if w.startswith("-L")],
             "--libs-only-l": [w for w in libs if w.startswith("-l")],
             "--libs-only-other": [w for w in libs if not w.startswith(("-L", "-l"))],
             "--cflags": cflags, "--cflags-only-I": [w for w in cflags if w.startswith("-I")],
             "--cflags-only-other": [w for w in cflags if not w.startswith("-I")]}
    for o in opts:
        words += picks.get(o, [])
    print(" ".join(words))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
