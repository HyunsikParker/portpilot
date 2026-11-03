# cmocka cmocka-2.0.2 on QNX 8.0

Upstream: https://gitlab.com/cmocka/cmocka.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 1 build round(s)

## Changes

- none: the project built with the QNX toolchain file as it is

## Reproduce

```
python -m portpilot port cmocka https://gitlab.com/cmocka/cmocka.git cmocka-2.0.2 --cmake=-DBUILD_SHARED_LIBS=OFF --cmake=-DWITH_EXAMPLES=OFF --install
```
