# civetweb v1.16 on QNX 8.0

Upstream: https://github.com/civetweb/civetweb.git

## Result

- aarch64le: built in 3 build round(s)
- x86_64: built in 4 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 43 of 50 CTest entries pass

Entries that did not pass:

- `test-publicserver-check-test-environment`: fail (exit 1)
- `test-publicserver-minimal-http-client`: fail (exit 1)
- `test-publicserver-minimal-https-client`: fail (exit 1)
- `test-publicserver-server-requests`: fail (exit 1)
- `test-publicserver-large-file`: timeout (exit 137)
- `test-timer-timer-periodic`: fail (exit 1)
- `test-timer-timer-mixed`: fail (exit 1)

## Changes

- replayed civetweb.patch
- configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)
- sockets
- AI patch round 1 (claude-opus-5-5): unittest/CMakeLists.txt - kept
- test triage round 1 (claude-opus-5-5):  - passing tests ? -> ?, reverted

## Reproduce

Port check first with `--install` (see ports/check/); the build finds it in the build host's stage directory.

```
python -m portpilot port civetweb https://github.com/civetweb/civetweb.git v1.16 --cmake=-DCIVETWEB_ENABLE_SSL=OFF --cmake=-DCIVETWEB_BUILD_TESTING=ON --ai 1 --needs check
```
