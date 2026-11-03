# spdlog v1.17.0 on QNX 8.0

Upstream: https://github.com/gabime/spdlog.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 1 of 1 CTest entries pass

## Changes

- sockets

## Reproduce

```
python -m portpilot port spdlog https://github.com/gabime/spdlog.git v1.17.0 --cmake=-DSPDLOG_BUILD_TESTS=ON
```
