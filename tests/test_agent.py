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


def test_missing_link_libraries_reach_the_prompt():
    log = "x86_64-pc-nto-qnx8.0.0-ld: cannot find -lsubunit: No such file or directory\n" * 3
    libs = agent.missing_libraries(log)
    assert libs == ["subunit"]
    prompt = agent.build_prompt("demo", "v1.0", [], [], [], [], "", libs, "BUILD tests/CMakeLists.txt:19\n> list(APPEND LIBS subunit)")
    assert "Libraries missing at link time" in prompt and "-lsubunit" in prompt and "list(APPEND LIBS subunit)" in prompt


def test_missing_build_inputs_reach_the_prompt():
    log = "ninja: error: 'third_party/lib/libcheck.a', needed by 'unittest/main-c-unit-test', missing and no known rule to make it\n"
    inputs = agent.missing_inputs(log)
    assert inputs == [("third_party/lib/libcheck.a", "unittest/main-c-unit-test")]
    prompt = agent.build_prompt("demo", "v1.0", [], [], [], [], inputs=inputs, input_notes="> set(CHECK_LIBRARIES ...)")
    assert "Build inputs that no rule produces" in prompt and "third_party/lib/libcheck.a" in prompt


def test_a_build_that_runs_steps_outranks_one_that_cannot_start():
    from portpilot import remote
    stuck = {"configure_exit": "0", "build_exit": "1", "errors": 1, "failed_steps": 0,
             "steps_run": remote.count_steps_run("ninja: error: 'x.a', needed by 'y', missing and no known rule to make it")}
    ran = {"configure_exit": "0", "build_exit": "1", "errors": 55, "failed_steps": 2,
           "steps_run": remote.count_steps_run("[1/500] Building C object a.o\n[2/500] Building C object b.o\nFAILED: c.o")}
    assert stuck["steps_run"] == 0 and ran["steps_run"] == 2
    assert remote.progress(ran) > remote.progress(stuck)


def test_failed_external_project_steps_are_named():
    log = ("FAILED: [code=1] third_party/src/check-unit-test-framework-stamp/check-unit-test-framework-configure "
           "C:/b/third_party/src/check-unit-test-framework-stamp/check-unit-test-framework-configure\n")
    assert agent.failed_external_steps(log) == [("check-unit-test-framework", "configure")]
    prompt = agent.build_prompt("demo", "v1", [], [], [], [], external=[("check-unit-test-framework", "configure")],
                                external_notes="BUILD unittest/CMakeLists.txt:21\n> ExternalProject_Add(check-unit-test-framework")
    assert "ExternalProject steps that failed: check-unit-test-framework (configure)" in prompt
