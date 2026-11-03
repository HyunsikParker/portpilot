# mbedtls v4.2.0 on QNX 8.0

Upstream: https://github.com/Mbed-TLS/mbedtls.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)
- tests on a QNX 8.0 x86_64 QEMU target: 145 of 148 CTest entries pass

Entries that did not pass:

- `psa_crypto.pbkdf2-suite`: timeout (exit 137)
- `psa_crypto.persistent-suite`: fail (exit 1)
- `x509write-suite`: fail (exit 1)

## Changes

- sockets
- test triage round 1 (claude-opus-5-5): framework/scripts/generate_test_code.py - passing tests 0 -> 13, kept
- test triage round 2 (claude-opus-5-5): tf-psa-crypto/framework/scripts/generate_test_code.py - passing tests 13 -> 134, kept

## Reproduce

```
python -m portpilot port mbedtls https://github.com/Mbed-TLS/mbedtls.git v4.2.0 --cmake=-DENABLE_TESTING=ON --cmake=-DENABLE_PROGRAMS=ON --cmake=-DGEN_FILES=ON --cmake="-DPERL_EXECUTABLE=C:/Program Files/Git/usr/bin/perl.exe"
```
