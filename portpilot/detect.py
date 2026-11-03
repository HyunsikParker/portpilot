"""Find which build system an upstream project uses and what its tests look like."""
from pathlib import Path


def build_system(src):
    src = Path(src)
    if (src / "CMakeLists.txt").exists():
        return "cmake"
    if (src / "meson.build").exists():
        return "meson"
    if (src / "configure").exists() or (src / "configure.ac").exists():
        return "autotools"
    if (src / "Cargo.toml").exists():
        return "cargo"
    if (src / "Makefile").exists() or (src / "makefile").exists():
        return "make"
    return "unknown"


def cmake_test_switch(src):
    """The CMake option that turns the project's tests on, if one is declared."""
    text = ""
    for f in [Path(src) / "CMakeLists.txt", *Path(src).glob("cmake/*.cmake")]:
        if f.exists():
            text += f.read_text(errors="ignore")
    for name in ("BUILD_TESTING", "ENABLE_TESTS", "BUILD_TESTS", "ENABLE_TESTING"):
        if name in text:
            return name
    import re
    m = re.search(r"option\s*\(\s*(\w*TEST\w*)", text, re.I)
    return m.group(1) if m else None
