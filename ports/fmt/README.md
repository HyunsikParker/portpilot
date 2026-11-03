# fmt 12.2.0 on QNX 8.0

Upstream: https://github.com/fmtlib/fmt.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 20 of 21 CTest entries pass

Entries that did not pass:

- `printf-test`: fail (exit 1)

## Changes

- regex
- test triage round 1 (claude-opus-5-5):  - passing tests ? -> ?, reverted

## Reproduce

```
python -m portpilot port fmt https://github.com/fmtlib/fmt.git 12.2.0 --cmake=-DFMT_TEST=ON
```
