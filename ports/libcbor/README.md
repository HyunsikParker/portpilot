# libcbor v0.14.0 on QNX 8.0

Upstream: https://github.com/PJK/libcbor.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 1 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 28 of 28 CTest entries pass

## Changes

- none: the project built with the QNX toolchain file as it is

## Reproduce

Port cmocka first with `--install` (see ports/cmocka/); the build finds it in the build host's stage directory.

```
python -m portpilot port libcbor https://github.com/PJK/libcbor.git v0.14.0 --cmake=-DWITH_TESTS=ON --cmake=-DWITH_EXAMPLES=ON --needs cmocka
```
