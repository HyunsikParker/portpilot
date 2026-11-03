# open62541 v1.5.10 on QNX 8.0

Upstream: https://github.com/open62541/open62541.git

## Result

- aarch64le: built in 4 build round(s)
- x86_64: built in 5 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 127 of 146 CTest entries pass

Entries that did not pass:

- `check_musl_inet_pton`: fail (exit 1)
- `check_types_builtin_json`: fail (exit 1)
- `check_pubsub_publish_json`: fail (exit 1)
- `check_eventloop_tcp`: fail (exit 1)
- `check_pubsub_pds`: fail (exit 1)
- `check_pubsub_state_machine`: fail (exit 1)
- `check_pubsub_state_machine_extra`: fail (exit 1)
- `check_pubsub_connection_udp`: fail (exit 1)
- `check_pubsub_publish`: fail (exit 1)
- `check_pubsub_get_state`: fail (exit 1)
- `check_pubsub_udp_unicast`: fail (exit 1)
- `check_pubsub_publisherid`: fail (exit 1)
- `check_pubsub_subscribe`: fail (exit 1)
- `check_pubsub_publishspeed`: fail (exit 1)
- `check_pubsub_offset`: fail (exit 139)
- `check_pubsub_subscribe_msgrcvtimeout`: fail (exit 1)
- `check_pubsub_informationmodel`: fail (exit 1)
- `check_pubsub_informationmodel_methods`: fail (exit 1)
- `check_client_subscriptions`: timeout (exit 137)

## Changes

- replayed open62541.patch
- force-include project queue header open62541_queue.h
- empty stub archives for -lpthread, -lrt (functions are in QNX libc)
- sockets
- AI patch round 1 (claude-opus-5-5): tests/CMakeLists.txt - kept

## Reproduce

Port check first with `--install` (see ports/check/); the build finds it in the build host's stage directory.

```
python -m portpilot port open62541 https://github.com/open62541/open62541.git v1.5.10 --cmake=-DUA_BUILD_UNIT_TESTS=ON --cmake=-DUA_BUILD_EXAMPLES=ON --ai 1 --needs check
```
