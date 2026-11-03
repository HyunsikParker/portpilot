# libzmq v4.3.5 on QNX 8.0

Upstream: https://github.com/zeromq/libzmq.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 110 of 121 CTest entries pass

Entries that did not pass:

- `test_system`: fail (exit 1)
- `test_hwm_pubsub`: fail (exit 1)
- `test_router_mandatory`: timeout (exit 137)
- `test_shutdown_stress`: timeout (exit 137)
- `test_monitor`: timeout (exit 137)
- `test_reconnect_ivl`: fail (exit 1)
- `test_socks`: timeout (exit 137)
- `test_connect_null_fuzzer`: skip (exit 77)
- `test_bind_null_fuzzer`: skip (exit 77)
- `test_connect_fuzzer`: skip (exit 77)
- `test_bind_fuzzer`: skip (exit 77)

## Changes

- configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)

## Reproduce

```
python -m portpilot port libzmq https://github.com/zeromq/libzmq.git v4.3.5 --cmake=-DBUILD_TESTS=ON --cmake=-DWITH_LIBSODIUM=OFF
```
