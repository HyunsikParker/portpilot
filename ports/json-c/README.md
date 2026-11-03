# json-c json-c-0.19-20260627 on QNX 8.0

Upstream: https://github.com/json-c/json-c.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 1 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 27 of 28 CTest entries pass

Entries that did not pass:

- `test_json_patch`: fail (exit 1)

## Changes

- none: the project built with the QNX toolchain file as it is

## Reproduce

```
python -m portpilot port json-c https://github.com/json-c/json-c.git json-c-0.19-20260627 --cmake=-DBUILD_TESTING=ON
```
