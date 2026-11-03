import importlib.util
from pathlib import Path

from portpilot import fixes, target

ROOT = Path(__file__).resolve().parent.parent


def _launcher():
    spec = importlib.util.spec_from_file_location("launcher", ROOT / "compat" / "portpilot_link_launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_serial_keeps_failure_logs_with_their_test():
    text = "\n".join([
        "PPTEST-BEGIN QNX ppvm 8.0.0 x86pc x86_64",
        "PPTEST-LIB fmt 2",
        "PPTEST fmt args-test PASS rc=0",
        "PPTEST fmt printf-test FAIL rc=1",
        "PPLOG [  FAILED  ] printf_test.float",
        "PPTEST yaml-cpp yaml-cpp::test TIMEOUT rc=137",
        "PPTEST-END",
    ])
    results = target.parse_serial(text)
    assert [(r["test"], r["verdict"]) for r in results] == [
        ("args-test", "PASS"), ("printf-test", "FAIL"), ("yaml-cpp::test", "TIMEOUT")]
    assert results[1]["log"] == ["[  FAILED  ] printf_test.float"]
    assert results[0]["log"] == []


def test_quote_survives_single_quotes():
    assert target._quote("it's") == "'it'\\''s'"


def test_long_link_message_is_recognised():
    log = r"cc: spawn of C:\qnx800\host\win64\x86_64\usr\bin\x86_64-pc-nto-qnx8.0.0-ld failed: No such file or directory"
    assert fixes.needs_link_response_file(log)
    assert not fixes.needs_link_response_file("ld: cannot find -lfoo")


def test_launcher_moves_only_objects_into_their_own_response_file(tmp_path):
    rsp = tmp_path / "app.rsp"
    rsp.write_text('a/x.c.o "b dir/y.c.o" lib/libz.a -lsocket -Wl,-rpath,C:/q/lib:\n')
    out = _launcher().rewrite(["qcc.exe", "-Vgcc_ntox86_64", f"@{rsp}", "-o", "bin/app"])
    listing = Path(str(rsp) + ".objects")
    assert out == ["qcc.exe", "-Vgcc_ntox86_64", "-Wl,@" + str(listing).replace("\\", "/"),
                   "lib/libz.a", "-lsocket", "-Wl,-rpath,C:/q/lib:", "-o", "bin/app"]
    assert listing.read_text().splitlines() == ['"a/x.c.o"', '"b dir/y.c.o"']


def test_launcher_leaves_other_arguments_alone(tmp_path):
    assert _launcher().rewrite(["qcc.exe", "@missing.rsp", "-o", "x"]) == ["qcc.exe", "@missing.rsp", "-o", "x"]
