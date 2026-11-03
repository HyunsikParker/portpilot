# backward-cpp v1.6 on QNX 8.0

Upstream: https://github.com/bombela/backward-cpp.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 4 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 5 of 5 CTest entries pass

## Changes

- configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)
- AI patch round 1 (claude-opus-5-5): backward.hpp, test/_test_main.cpp - kept
- AI patch round 2 (claude-opus-5-5): backward.hpp - kept

## Reproduce

```
python -m portpilot port backward-cpp https://github.com/bombela/backward-cpp.git v1.6 --cmake=-DBACKWARD_TESTS=ON --ai 2
```
