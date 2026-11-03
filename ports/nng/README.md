# nng v2.1.0 on QNX 8.0

Upstream: https://github.com/nanomsg/nng.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 53 of 63 CTest entries pass

Entries that did not pass:

- `nng.platform.resolver_test`: fail (exit 1)
- `nng.platform.udp_test`: fail (exit 1)
- `nng.sp.reconnect_stress_test`: timeout (exit 137)
- `nng.sp.transport.inproc.inproc_test`: timeout (exit 137)
- `nng.sp.transport.ipc.ipc_test`: fail (exit 1)
- `nng.sp.transport.tcp.tcp_test`: timeout (exit 137)
- `nng.sp.transport.udp.udp_tran_test`: fail (exit 1)
- `nng.sp.transport.ws.ws_test`: timeout (exit 137)
- `nng.supplemental.websocket_test`: timeout (exit 137)
- `nng.inproc_lat`: timeout (exit 137)

## Changes

- posix_udp.c: <sys/errno.h> -> <errno.h>

## Reproduce

```
python -m portpilot port nng https://github.com/nanomsg/nng.git v2.1.0 --cmake=-DNNG_TESTS=ON --cmake=-DNNG_TOOLS=ON --cmake=-DNNG_POLLQ_POLLER=select
```
