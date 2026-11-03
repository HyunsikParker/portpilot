# msgpack-c c-7.0.2 on QNX 8.0

Upstream: https://github.com/msgpack/msgpack-c.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 1 build round(s)

## Changes

- none: the project built with the QNX toolchain file as it is

## Reproduce

```
python -m portpilot port msgpack-c https://github.com/msgpack/msgpack-c.git c-7.0.2 --cmake=-DMSGPACK_BUILD_TESTS=OFF --cmake=-DMSGPACK_BUILD_EXAMPLES=ON
```
