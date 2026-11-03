import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("pc", Path(__file__).parent.parent / "compat" / "portpilot_pkg_config.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

CHECK_PC = """prefix=C:/stage/x86_64/usr
exec_prefix=${prefix}
libdir=${exec_prefix}/lib
includedir=${prefix}/include

Name: Check
Version: 0.15.2
Libs: -L${libdir} -lcheck
Libs.private: -lm
Cflags: -I${includedir}
"""


def run(tmp_path, capsys, *args):
    (tmp_path / "check.pc").write_text(CHECK_PC)
    rc = pc.main([f"--pc-dir={tmp_path}", *args])
    return rc, capsys.readouterr().out.strip()


def test_queries_that_findpkgconfig_makes(tmp_path, capsys):
    assert run(tmp_path, capsys, "--version")[1] == pc.VERSION
    assert run(tmp_path, capsys, "--exists", "--print-errors", "--short-errors", "check", ">=", "0.9")[0] == 0
    assert run(tmp_path, capsys, "--modversion", "check")[1] == "0.15.2"
    assert run(tmp_path, capsys, "--variable=includedir", "check")[1] == "C:/stage/x86_64/usr/include"
    assert run(tmp_path, capsys, "--libs-only-l", "check")[1] == "-lcheck"
    assert run(tmp_path, capsys, "--static", "--libs", "check")[1] == "-LC:/stage/x86_64/usr/lib -lcheck -lm"
    assert run(tmp_path, capsys, "--cflags", "check")[1] == "-IC:/stage/x86_64/usr/include"


def test_missing_module_fails(tmp_path, capsys):
    assert run(tmp_path, capsys, "--exists", "subunit")[0] == 1
