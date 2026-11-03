from portpilot import agent

ROOT = r"C:\Users\dev\portpilot\work\demo"

LOG = "\n".join([
    "C:/Users/dev/portpilot/work/demo/src/os.c:41:10: fatal error: sys/epoll.h: No such file or directory",
    "C:/Users/dev/portpilot/work/demo/src/os.c:41:10: fatal error: sys/epoll.h: No such file or directory",
    "C:/qnx800/target/qnx/usr/include/stdio.h:120:5: error: conflicting types for 'foo'",
    "C:/Users/dev/portpilot/work/demo/src/net.c:7:3: error: 'MSG_NOSIGNAL' undeclared",
    "net.c:(.text+0x10): undefined reference to `backtrace'",
])


def test_errors_are_relative_distinct_and_exclude_sdp_files():
    assert agent.collect_errors(LOG, ROOT) == [
        ("src/os.c", 41, "sys/epoll.h: No such file or directory"),
        ("src/net.c", 7, "'MSG_NOSIGNAL' undeclared"),
    ]
    assert agent.undefined_symbols(LOG) == ["backtrace"]


def test_cmake_configure_errors_are_collected_before_compiler_errors():
    log = ("CMake Error at cmake/DetermineTargetArchitecture.cmake:37 (message):\n"
           "  Failed to determine target architecture triplet: 1\n"
           "Call Stack (most recent call first):\n"
           "  CMakeLists.txt:48 (determine_target_architecture)\n\n"
           "CMake Error at C:/Program Files/CMake/share/cmake-4.4/Modules/FindPackageHandleStandardArgs.cmake:290 (message):\n"
           "  Could NOT find Perl\n\n" + LOG)
    errors = agent.collect_errors(log, ROOT)
    assert errors[0] == ("cmake/DetermineTargetArchitecture.cmake", 37,
                         "CMake message: Failed to determine target architecture triplet: 1")
    assert all("share/cmake" not in e[0] for e in errors)


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
