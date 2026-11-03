# libcoap v4.3.5 on QNX 8.0

Upstream: https://github.com/obgm/libcoap.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)

## Changes

- sockets

## Reproduce

```
python -m portpilot port libcoap https://github.com/obgm/libcoap.git v4.3.5 --cmake=-DENABLE_DTLS=OFF --cmake=-DENABLE_TESTS=OFF --cmake=-DENABLE_EXAMPLES=ON --cmake=-DENABLE_DOCS=OFF
```
