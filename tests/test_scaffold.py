import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portpilot import detect, fixes, scaffold  # noqa: E402

PORTS = Path(__file__).resolve().parents[2] / "third_party" / "build-files" / "ports"


def test_scaffold_matches_the_qnx_layout_used_by_existing_ports():
    with tempfile.TemporaryDirectory() as d:
        scaffold.write_port(d, "demo")
        ours = sorted(str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file())
    assert ours == ["Makefile", "common.mk", "nto-aarch64-le/Makefile", "nto-x86_64-o/Makefile", "qnx.nto.toolchain.cmake"]
    if PORTS.exists():  # the same files exist in the public CMake ports
        ref = PORTS / "cJSON"
        theirs = sorted(str(p.relative_to(ref)) for p in ref.rglob("*") if p.is_file() and p.name != "README.md")
        assert ours == theirs


def test_common_mk_carries_fixes_and_test_switch():
    with tempfile.TemporaryDirectory() as d:
        scaffold.write_port(d, "demo", cflags=["-D_QNX_SOURCE", "-fPIC"], ldflags=["-lsocket"], test_switch="ENABLE_TESTS")
        text = (Path(d) / "common.mk").read_text()
    assert "PORT_CFLAGS  := -D_QNX_SOURCE -fPIC" in text and "PORT_LDFLAGS := -lsocket" in text
    assert "-DENABLE_TESTS=$(BUILD_TESTING)" in text and "\tcd build && cmake" in text


def test_fix_rules_map_errors_to_flags():
    log = ("src/x.c:10:5: error: implicit declaration of function 'strdup' [-Wimplicit-function-declaration]\n"
           "ld: x.o: undefined reference to `getaddrinfo'\nld: y.o: undefined reference to `regcomp'\n")
    names = [r.name for r in fixes.match(log)]
    assert names == ["posix-extensions", "sockets", "regex"]
    c, l = fixes.apply(fixes.match(log), [], [])
    assert c == ["-D_QNX_SOURCE"] and l == ["-lsocket", "-lregex"]


def test_catalogue_flags_are_the_common_ones_in_public_ports():
    if not PORTS.exists():
        return
    text = "".join(p.read_text(errors="ignore") for p in PORTS.glob("*/common.mk"))
    for flag in ("-D_QNX_SOURCE", "-lsocket", "-fPIC", "-lm", "-lregex"):
        assert flag in text


def test_detect_build_system():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "CMakeLists.txt").write_text("option(ENABLE_TESTS \"tests\" ON)\n")
        assert detect.build_system(d) == "cmake" and detect.cmake_test_switch(d) == "ENABLE_TESTS"


def test_source_level_rules():
    log = ("C:/w/nng/src/posix_udp.c:14:10: fatal error: sys/errno.h: No such file or directory\n"
           "x.h:366:5: error: expected specifier-qualifier-list before 'LIST_ENTRY'\n"
           "C:/w/ex/rt.c:73:25: error: 'IPPROTO_UDP' undeclared (first use in this function)\n"
           "ld: cannot find -lpthread: No such file or directory\nld: cannot find -lrt: No such file\n"
           "ld: libpaho.so: undefined reference to `htobe32'\n"
           "CMake Error at CMakeLists.txt:7 (cmake_minimum_required):\n  Compatibility with CMake < 3.5 has been removed from CMake.\n")
    assert fixes.header_patches(log) == [("C:/w/nng/src/posix_udp.c", "sys/errno.h", "errno.h")]
    assert fixes.needs_queue_compat(log) and fixes.netinet_files(log) == ["C:/w/ex/rt.c"]
    assert fixes.stub_libraries(log) == ["pthread", "rt"]
    assert fixes.needs_endian_compat(log) and fixes.needs_policy_minimum(log)


def test_endian_header_is_self_contained():
    text = (Path(__file__).resolve().parents[1] / "compat" / "portpilot_endian.h").read_text()
    for fn in ("htobe16", "be32toh", "htole64", "le64toh"):
        assert fn in text
    assert "#include <stdint.h>" in text and "__builtin_bswap32" in text
