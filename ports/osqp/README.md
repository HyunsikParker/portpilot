# osqp v1.0.0 on QNX 8.0

Upstream: https://github.com/osqp/osqp.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 3 of 3 CTest entries pass

## Changes

- AI patch round 1 (claude-opus-5-5): src/CMakeLists.txt - kept
- test triage round 1 (claude-opus-5-5): tests/CMakeLists.txt - passing tests 1 -> 3, kept

## Reproduce

```
python -m portpilot port osqp https://github.com/osqp/osqp.git v1.0.0 --cmake=-DOSQP_BUILD_UNITTESTS=ON --ai 1
```
