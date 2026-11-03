# uriparser uriparser-1.0.3 on QNX 8.0

Upstream: https://github.com/uriparser/uriparser.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)

## Changes

- sockets

## Reproduce

```
python -m portpilot port uriparser https://github.com/uriparser/uriparser.git uriparser-1.0.3 --cmake=-DURIPARSER_BUILD_TESTS=OFF --cmake=-DURIPARSER_BUILD_DOCS=OFF
```
