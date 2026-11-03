# msgpack-c c-7.0.2 on QNX 8.0

Upstream: https://github.com/msgpack/msgpack-c.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 5 of 5 CTest entries pass

## Changes

- regex

## Reproduce

Port googletest first with `--install` (see ports/googletest/); the build finds it in the build host's stage directory.

```
python -m portpilot port msgpack-c https://github.com/msgpack/msgpack-c.git c-7.0.2 --cmake=-DMSGPACK_BUILD_TESTS=ON --cmake=-DMSGPACK_BUILD_EXAMPLES=ON --needs googletest
```
