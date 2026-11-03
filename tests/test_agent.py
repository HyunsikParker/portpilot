from portpilot import agent

ROOT = r"C:\Users\dev\Documents\portpilot-work\pp\demo"

LOG = "\n".join([
    "C:/Users/dev/Documents/portpilot-work/pp/demo/src/os.c:41:10: fatal error: sys/epoll.h: No such file or directory",
    "C:/Users/dev/Documents/portpilot-work/pp/demo/src/os.c:41:10: fatal error: sys/epoll.h: No such file or directory",
    "C:/Users/dev/qnx800/target/qnx/usr/include/stdio.h:120:5: error: conflicting types for 'foo'",
    "C:/Users/dev/Documents/portpilot-work/pp/demo/src/net.c:7:3: error: 'MSG_NOSIGNAL' undeclared",
    "net.c:(.text+0x10): undefined reference to `backtrace'",
])


def test_errors_are_relative_distinct_and_exclude_sdp_files():
    assert agent.collect_errors(LOG, ROOT) == [
        ("src/os.c", 41, "sys/epoll.h: No such file or directory"),
        ("src/net.c", 7, "'MSG_NOSIGNAL' undeclared"),
    ]
    assert agent.undefined_symbols(LOG) == ["backtrace"]


def test_prompt_never_quotes_sdp_paths():
    errors = agent.collect_errors(LOG, ROOT)
    prompt = agent.build_prompt("demo", "v1.0", ["sockets"], errors, ["   41> #include <sys/epoll.h>", ""], ["backtrace"])
    assert "qnx800" not in prompt
    assert "src/os.c:41: error: sys/epoll.h" in prompt
    assert "Undefined symbols at link time: backtrace" in prompt


def test_extract_diff_from_fenced_and_bare_answers():
    diff = "diff --git a/src/os.c b/src/os.c\n--- a/src/os.c\n+++ b/src/os.c\n@@ -1 +1 @@\n-a\n+b\n"
    assert agent.extract_diff("Here it is:\n```diff\n" + diff + "```\nDone.") == diff
    assert agent.extract_diff(diff) == diff
    assert agent.extract_diff("I cannot help with that.") == ""
    assert agent.patch_files(diff) == ["src/os.c"]
