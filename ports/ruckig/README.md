# ruckig v0.19.4 on QNX 8.0

Upstream: https://github.com/pantor/ruckig.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 1 of 1 CTest entries pass

## Changes

- sockets
- doctest-std-headers

## Reproduce

```
python -m portpilot port ruckig https://github.com/pantor/ruckig.git v0.19.4 --cmake=-DBUILD_TESTS=ON --cmake=-DBUILD_EXAMPLES=ON
```
