# wolfssl v5.9.4-stable on QNX 8.0

Upstream: https://github.com/wolfSSL/wolfssl.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 2 of 2 CTest entries pass

## Changes

- sockets
- test triage round 1 (claude-opus-5-5): wolfcrypt/test/test_paths.h.in - passing tests 0 -> 1, kept
- test triage round 2 (claude-opus-5-5):  - passing tests ? -> ?, reverted

## Reproduce

```
python -m portpilot port wolfssl https://github.com/wolfSSL/wolfssl.git v5.9.4-stable --cmake=-DWOLFSSL_EXAMPLES=ON
```
