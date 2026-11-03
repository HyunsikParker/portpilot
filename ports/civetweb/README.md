# civetweb v1.16 on QNX 8.0

Upstream: https://github.com/civetweb/civetweb.git

## Result

- aarch64le: built in 3 build round(s)
- x86_64: built in 4 build round(s)

## Changes

- configure with CMAKE_POLICY_VERSION_MINIMUM=3.5 (old cmake_minimum_required)
- sockets
- AI patch round 1 (claude-opus-5-5): cmake/DetermineTargetArchitecture.cmake - kept

## Reproduce

```
python -m portpilot port civetweb https://github.com/civetweb/civetweb.git v1.16 --cmake=-DCIVETWEB_ENABLE_SSL=OFF --cmake=-DCIVETWEB_BUILD_TESTING=OFF --ai 1
```
