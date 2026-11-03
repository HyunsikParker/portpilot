# Port a CMake library to QNX 8.0 and run its tests in QEMU

This codelab takes an open-source C library, json-c, from a Git tag to a passing test run on a QNX 8.0 virtual
machine. You will write a CMake toolchain file for the QNX compiler, build the library and its tests, build a QNX 8.0
QEMU image with `mkqnximage`, put the tests on a second disk, and read the results from the serial console.

It takes about an hour. Everything runs on one Windows machine; the commands for a Linux host differ only where noted.

What you need:

- QNX SDP 8.0 installed (a free non-commercial licence is enough), referred to below as `C:\qnx800`
- QEMU for Windows, CMake 3.21 or later, Ninja, Git
- about 2 GB of free disk space

Every step below was run as written, in a fresh directory, on a Windows build host with QNX SDP 8.0 and QEMU 11.1
(2026-11-03); the last step printed `TEST test1 rc=0` and `TEST test1 output matches test1.expected` from the VM.

## 1. Open a QNX build shell

The SDP sets `QNX_HOST`, `QNX_TARGET` and `PATH` with one script. In a `cmd.exe` window:

```bat
call C:\qnx800\qnxsdp-env.bat
qcc -V
```

`qcc -V` lists the compiler configurations, such as `12.2.0,gcc_ntox86_64 (default)` and
`12.2.0,gcc_ntoaarch64le`; QNX 8.0 ships GCC 12.2. On Linux, run `source ~/qnx800/qnxsdp-env.sh` instead.

## 2. Write a toolchain file

`qcc` picks the target with a `-V` option instead of a separate compiler per target, so the toolchain file passes
`-Vgcc_nto<cpu>` in the compile and link flags. Save this as `qnx.nto.toolchain.cmake`:

```cmake
# QNX 8.0 toolchain for CMake. Pass -DCPU=x86_64 -DCPUVARDIR=x86_64 (or aarch64 / aarch64le).
foreach(var QNX_HOST QNX_TARGET)
  if("$ENV{${var}}" STREQUAL "")
    message(FATAL_ERROR "${var} is not set; run qnxsdp-env first")
  endif()
  file(TO_CMAKE_PATH "$ENV{${var}}" ${var})
endforeach()
set(CMAKE_SYSTEM_NAME QNX)
set(CMAKE_SYSTEM_PROCESSOR ${CPUVARDIR})
if(CMAKE_HOST_WIN32)
  set(_exe ".exe")
endif()
set(CMAKE_C_COMPILER   "${QNX_HOST}/usr/bin/qcc${_exe}")
set(CMAKE_CXX_COMPILER "${QNX_HOST}/usr/bin/q++${_exe}")
set(CMAKE_AR     "${QNX_HOST}/usr/bin/nto${CPU}-ar${_exe}"     CACHE FILEPATH "archiver")
set(CMAKE_RANLIB "${QNX_HOST}/usr/bin/nto${CPU}-ranlib${_exe}" CACHE FILEPATH "ranlib")
set(_target "-Vgcc_nto${CPUVARDIR}")
set(CMAKE_C_FLAGS   "${_target} -D_QNX_SOURCE" CACHE STRING "C flags")
set(CMAKE_CXX_FLAGS "${_target} -D_QNX_SOURCE" CACHE STRING "C++ flags")
set(CMAKE_EXE_LINKER_FLAGS    "${_target}" CACHE STRING "exe linker flags")
set(CMAKE_SHARED_LINKER_FLAGS "${_target}" CACHE STRING "shared linker flags")
set(CMAKE_FIND_ROOT_PATH "${QNX_TARGET};${QNX_TARGET}/${CPUVARDIR}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```

Two details matter:

- The flags are cache entries, not `CMAKE_C_FLAGS_INIT`. Many projects enable C++ late, inside a test directory
  (`enable_language(CXX)`); with `*_INIT` those targets silently build for qcc's default CPU instead of yours.
- `-D_QNX_SOURCE` exposes POSIX and BSD extensions (`strdup`, `strcasecmp`, `u_int32_t` and others) that the QNX
  headers hide by default. 92 of the 151 recipes in the public qnx-ports build files set it.

## 3. Build json-c and its tests

```bat
git -c core.autocrlf=false clone --depth 1 --branch json-c-0.19-20260627 https://github.com/json-c/json-c.git
cmake -G Ninja -S json-c -B build-x86_64 -DCMAKE_TOOLCHAIN_FILE=%CD%\qnx.nto.toolchain.cmake ^
      -DCPU=x86_64 -DCPUVARDIR=x86_64 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build-x86_64
```

Clone with `core.autocrlf=false`: json-c's tests are shell scripts, and with Windows line endings the QNX shell reads
the interpreter line as `/bin/sh\r` and cannot start them.

For a 64-bit Arm target use `-DCPU=aarch64 -DCPUVARDIR=aarch64le` (the binutils prefix is `ntoaarch64`, the compiler
variant and target directory are `aarch64le`).

### When the build fails

These are the errors met most often while porting libraries to QNX 8.0, and the usual fix:

| Message | Fix |
|---|---|
| `implicit declaration of function 'strdup'` (or `strcasecmp`, `usleep`, ...) | add `-D_QNX_SOURCE` |
| ``undefined reference to `socket'`` (or `getaddrinfo`, `__inet_ntop`, ...) | link `-lsocket`; QNX keeps the BSD socket API there |
| ``undefined reference to `regcomp'`` | link `-lregex` |
| `cannot find -lpthread` (or `-lrt`, `-ldl`) | these functions are in libc; drop the flag or give the linker an empty archive of that name |
| `sys/epoll.h: No such file or directory` | QNX has no epoll; select the project's `poll` or `kqueue` path |
| `reference to 'ostream' is ambiguous` in doctest.h | define `DOCTEST_CONFIG_USE_STD_HEADERS` (QNX uses libc++) |
| `spawn of ...-ld failed: No such file or directory` on Windows | the link line passed 32 KiB; pass the object list to `ld` in a response file |

## 4. Build a QNX 8.0 QEMU image

The SDP's `mkqnximage` builds a bootable image in an empty directory. Add a small hook first: at the end of startup
it mounts a second disk on `/tests`, runs `/tests/run.sh` if it is there, and shuts the VM down.

```bat
mkdir vm\local\snippets
cd vm
```

Save as `local\snippets\post_start.custom`:

```sh
if [ -e /dev/hd1 ]; then
    mount -t qnx6 /dev/hd1 /tests
    if [ -x /tests/run.sh ]; then
        /tests/run.sh
        umount /tests
        shutdown -f
    fi
fi
```

Then build the image (about a minute):

```bat
call C:\qnx800\host\common\bin\mkqnximage.bat --force --type=qemu --arch=x86_64 --hostname=qnxtest --ssh-ident=none --data-size=512 --noprompt
```

`output\ifs.bin` is the boot image and `output\disk-qemu.vmdk` the system disk. After changing a snippet, rebuild with
`--clean`.

## 5. Put the tests on a second disk

`mkqnx6fsimg` writes a QNX6 filesystem image from a build file that maps paths on the disk to files on the host.
Save as `tests.build` (paths shortened; use your own):

```
[num_sectors=262144]
[uid=0 gid=0 dperms=777 perms=755]
[type=dir] json-c
run.sh = "C:/work/run.sh"
json-c/test1 = "C:/work/build-x86_64/tests/test1"
json-c/test1.expected = "C:/work/json-c/tests/test1.expected"
json-c/libjson-c.so.5 = "C:/work/build-x86_64/libjson-c.so.5.5.0"
```

`test1` loads `libjson-c.so.5` at run time. On a Windows host CMake cannot create that link (it is normally
`libjson-c.so.5 -> libjson-c.so.5.5.0`) and leaves an empty file, so map the name to the real library as above.
`ntox86_64-readelf -d build-x86_64/tests/test1` lists what a test needs (`NEEDED`).

Then `run.sh`, saved with Unix line endings, runs the test and compares its output with the expected file:

```sh
#!/bin/sh
export LD_LIBRARY_PATH=/tests/json-c
cd /tests/json-c
./test1 > /tmp/out 2>&1; echo "TEST test1 rc=$?"
cmp /tmp/out test1.expected && echo "TEST test1 output matches test1.expected"
```

```bat
mkqnx6fsimg tests.build tests.img
```

PortPilot generates both files from `ctest --show-only=json-v1`, so every test CTest knows about is included with its
working directory and arguments.

## 6. Boot QEMU and read the results

```bat
"C:\Program Files\qemu\qemu-system-x86_64.exe" -accel tcg -smp 2 -cpu max -m 2G ^
  -drive file=output\disk-qemu.vmdk,if=ide,index=0 -drive file=tests.img,if=ide,index=1,format=raw ^
  -kernel output\ifs.bin -display none -monitor none -serial file:serial.log -no-reboot
```

The VM boots, the hook runs the tests, and QEMU exits when QNX shuts down (`-no-reboot`). `serial.log` holds the boot
messages and one line per test. On Windows, use TCG; QEMU with the Windows Hypervisor Platform accelerator printed
nothing on the serial console in our runs.

## 7. Let PortPilot do it

PortPilot automates steps 2 to 6 for any CMake project, applies the fixes from the table above when it sees their
messages, and can ask a language model for a patch when none applies:

```
python -m portpilot vm build
python -m portpilot port json-c https://github.com/json-c/json-c.git json-c-0.19-20260627 --cmake=-DBUILD_TESTING=ON
python -m portpilot test json-c
```
