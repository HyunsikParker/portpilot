# check 0.15.2 on QNX 8.0

Upstream: https://github.com/libcheck/check.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 2 build round(s)

## Changes

- AI patch round 1 (claude-opus-5-5): lib/libcompat.h - kept

## Reproduce

```
python -m portpilot port check https://github.com/libcheck/check.git 0.15.2 --cmake=-DCHECK_ENABLE_TESTS=OFF --cmake=-DBUILD_SHARED_LIBS=OFF --ai 1 --install
```
