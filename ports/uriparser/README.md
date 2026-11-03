# uriparser uriparser-1.0.3 on QNX 8.0

Upstream: https://github.com/uriparser/uriparser.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 1 of 1 CTest entries pass

## Changes

- sockets
- regex

## Reproduce

Port googletest first with `--install` (see ports/googletest/); the build finds it in the build host's stage directory.

```
python -m portpilot port uriparser https://github.com/uriparser/uriparser.git uriparser-1.0.3 --cmake=-DURIPARSER_BUILD_TESTS=ON --cmake=-DURIPARSER_BUILD_DOCS=OFF --needs googletest
```
