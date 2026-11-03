# libcbor v0.14.0 on QNX 8.0

Upstream: https://github.com/PJK/libcbor.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 1 build round(s)

## Changes

- none: the project built with the QNX toolchain file as it is

## Reproduce

```
python -m portpilot port libcbor https://github.com/PJK/libcbor.git v0.14.0 --cmake=-DWITH_TESTS=OFF --cmake=-DWITH_EXAMPLES=ON
```
