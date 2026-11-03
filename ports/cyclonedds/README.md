# cyclonedds 11.0.1 on QNX 8.0

Upstream: https://github.com/eclipse-cyclonedds/cyclonedds.git

## Result

- aarch64le: built in 1 build round(s)
- x86_64: built in 2 build round(s)

## Changes

- AI patch round 1 (claude-opus-5-5): src/ddsrt/src/netstat/qnx/netstat.c - kept

## Reproduce

```
python -m portpilot port cyclonedds https://github.com/eclipse-cyclonedds/cyclonedds.git 11.0.1 --cmake=-DBUILD_IDLC=OFF --cmake=-DENABLE_SSL=OFF --cmake=-DBUILD_EXAMPLES=OFF --cmake=-DBUILD_TESTING=OFF --cmake=-DBUILD_DDSPERF=OFF --ai 1
```
