# nng v2.1.0 on QNX 8.0

Upstream: https://github.com/nanomsg/nng.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 0 of 1 CTest entries pass

Entries that did not pass:

- `nng.core.aio_test`: timeout (exit 137)

## Changes

- posix_udp.c: <sys/errno.h> -> <errno.h>

## Reproduce

```
python -m portpilot port nng https://github.com/nanomsg/nng.git v2.1.0 --cmake=-DNNG_TESTS=ON --cmake=-DNNG_TOOLS=ON
```
