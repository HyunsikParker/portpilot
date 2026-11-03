from portpilot import report


def test_scrub_hides_the_user_name_in_windows_paths():
    assert report.scrub("C:/Users/alice/work/x.c:3") == "C:/Users/<user>/work/x.c:3"
    assert report.scrub("D:\\Users\\bob\\pp") == "D:\\Users/<user>\\pp"
    assert report.scrub("/tests/osqp/build") == "/tests/osqp/build"


def test_diff_lines_are_classed(tmp_path):
    p = tmp_path / "a.patch"
    p.write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n")
    out = report.diff_html(p)
    assert '<span class="del">-old</span>' in out and '<span class="add">+new</span>' in out
    assert '<span class="hunk">' in out and "+++ b/x" in out and 'class="add">+++' not in out
    assert report.diff_html(tmp_path / "missing.patch") == ""
