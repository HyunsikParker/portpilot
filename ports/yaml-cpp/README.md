# yaml-cpp yaml-cpp-0.9.0 on QNX 8.0

Upstream: https://github.com/jbeder/yaml-cpp.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 1 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 0 of 1 CTest entries pass

Entries that did not pass:

- `yaml-cpp::test`: fail (exit 1)

## Changes

- test triage round 1 (claude-opus-5-5):  - passing tests ? -> ?, reverted

## Reproduce

```
python -m portpilot port yaml-cpp https://github.com/jbeder/yaml-cpp.git yaml-cpp-0.9.0 --cmake=-DYAML_CPP_BUILD_TESTS=ON
```
