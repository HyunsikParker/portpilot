/* PortPilot compatibility header for QNX 8.0: the BSD/glibc byte-order helpers (htobe32, be32toh, ...) that some
 * projects expect from <endian.h>. Written for PortPilot; MIT licence (see LICENSE). */
#ifndef PORTPILOT_ENDIAN_H
#define PORTPILOT_ENDIAN_H
#include <stdint.h>
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define PP_BE16(x) __builtin_bswap16(x)
#define PP_BE32(x) __builtin_bswap32(x)
#define PP_BE64(x) __builtin_bswap64(x)
#define PP_LE16(x) (x)
#define PP_LE32(x) (x)
#define PP_LE64(x) (x)
#else
#define PP_BE16(x) (x)
#define PP_BE32(x) (x)
#define PP_BE64(x) (x)
#define PP_LE16(x) __builtin_bswap16(x)
#define PP_LE32(x) __builtin_bswap32(x)
#define PP_LE64(x) __builtin_bswap64(x)
#endif
#ifndef htobe16
static inline uint16_t htobe16(uint16_t x) { return PP_BE16(x); }
static inline uint16_t be16toh(uint16_t x) { return PP_BE16(x); }
static inline uint16_t htole16(uint16_t x) { return PP_LE16(x); }
static inline uint16_t le16toh(uint16_t x) { return PP_LE16(x); }
static inline uint32_t htobe32(uint32_t x) { return PP_BE32(x); }
static inline uint32_t be32toh(uint32_t x) { return PP_BE32(x); }
static inline uint32_t htole32(uint32_t x) { return PP_LE32(x); }
static inline uint32_t le32toh(uint32_t x) { return PP_LE32(x); }
static inline uint64_t htobe64(uint64_t x) { return PP_BE64(x); }
static inline uint64_t be64toh(uint64_t x) { return PP_BE64(x); }
static inline uint64_t htole64(uint64_t x) { return PP_LE64(x); }
static inline uint64_t le64toh(uint64_t x) { return PP_LE64(x); }
#endif
#endif
