# open62541 v1.5.10 on QNX 8.0

Upstream: https://github.com/open62541/open62541.git

## Result

- aarch64le: built in 4 build round(s)
- x86_64: built in 4 build round(s)

## Changes

- force-include project queue header open62541_queue.h
- server_pubsub_subscribe_rt_state_machine.c: add <netinet/in.h>
- empty stub archives for -lpthread, -lrt (functions are in QNX libc)
- sockets

## Reproduce

```
python -m portpilot port open62541 https://github.com/open62541/open62541.git v1.5.10 --cmake=-DUA_BUILD_UNIT_TESTS=OFF --cmake=-DUA_BUILD_EXAMPLES=ON
```
