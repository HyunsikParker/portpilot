# paho-mqtt-c v1.3.16 on QNX 8.0

Upstream: https://github.com/eclipse-paho/paho.mqtt.c.git

## Result

- aarch64le: built in 2 build round(s)
- x86_64: built in 2 build round(s)

## Changes

- force-include PortPilot endian helpers (htobe32, be32toh, ...)
- empty stub archives for -lpthread (functions are in QNX libc)

## Reproduce

```
python -m portpilot port paho-mqtt-c https://github.com/eclipse-paho/paho.mqtt.c.git v1.3.16 --cmake=-DPAHO_BUILD_SAMPLES=ON --cmake=-DPAHO_WITH_SSL=OFF
```
