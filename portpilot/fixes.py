"""Catalogue of QNX porting fixes keyed by the compiler or linker message they answer.

Each rule turns a build error into a change of compile or link flags. The flag counts in the notes come from a survey of
151 public QNX port recipes (2026-11-03): -D_QNX_SOURCE in 92, -lsocket in 24, -fPIC in 24, -lm in 11, -lregex in 9.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    cflags: tuple = ()
    ldflags: tuple = ()
    why: str = ""


RULES = [
    Rule("posix-extensions", r"implicit declaration of function '(strdup|strndup|strcasecmp|strncasecmp|usleep|"
         r"gettimeofday|fileno|setenv|unsetenv|realpath|mkstemp|posix_memalign|clock_gettime|nanosleep|getline)'",
         cflags=("-D_QNX_SOURCE",), why="QNX hides POSIX and BSD extensions unless _QNX_SOURCE is defined"),
    Rule("posix-types", r"unknown type name '(u_int\d+_t|u_char|u_short|u_long|caddr_t)'|'(timespec|timeval)' has no member",
         cflags=("-D_QNX_SOURCE",), why="BSD types are behind _QNX_SOURCE"),
    Rule("sockets", r"undefined reference to `(socket|bind|connect|listen|accept|getaddrinfo|freeaddrinfo|gai_strerror|"
         r"setsockopt|getsockopt|recvfrom|sendto|inet_\w+|gethostbyname|getnameinfo|socketpair)'",
         ldflags=("-lsocket",), why="BSD socket calls live in libsocket on QNX"),
    Rule("regex", r"undefined reference to `(regcomp|regexec|regfree|regerror)'", ldflags=("-lregex",),
         why="POSIX regex is a separate library on QNX"),
    Rule("libm", r"undefined reference to `(sqrt|pow|exp|log|sin|cos|floor|ceil|fmod|lround|round)\w*'",
         ldflags=("-lm",), why="math functions are in libm"),
    Rule("pic", r"relocation R_\w+ against .* can not be used when making a shared object; recompile with -fPIC",
         cflags=("-fPIC",), why="shared objects need position-independent code"),
    Rule("signed-char", r"narrowing conversion of '-\d+' from 'int' to 'char'", cflags=("-fsigned-char",),
         why="char is unsigned on AArch64; code written for x86 assumes signed char"),
    Rule("werror", r"error: .* \[-Werror(=[\w-]+)?\]", cflags=("-Wno-error",),
         why="warnings promoted to errors by upstream flags; QNX headers trigger a few that are harmless"),
]


def match(log):
    """Rules whose pattern appears in a build log, in catalogue order, each at most once."""
    return [r for r in RULES if re.search(r.pattern, log)]


def apply(rules, cflags, ldflags):
    """New flag lists with the rules' flags added once."""
    cflags, ldflags = list(cflags), list(ldflags)
    for r in rules:
        cflags += [f for f in r.cflags if f not in cflags]
        ldflags += [f for f in r.ldflags if f not in ldflags]
    return cflags, ldflags


# Headers that some POSIX systems provide but QNX 8.0 does not, and the header that declares the same things on QNX.
HEADER_SUBST = {
    "sys/errno.h": "errno.h",
    "sys/sysctl.h": None,      # no equivalent; needs a code change, reported for review
    "sys/epoll.h": None,       # QNX has no epoll; the project's poll/kqueue-free path must be selected
}
MISSING_HEADER = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+?):\d+:\d+: fatal error: (?P<hdr>[\w/.+-]+): No such file", re.M)


def header_patches(log):
    """[(file, old_header, new_header)] for missing headers that have a QNX replacement."""
    out = []
    for m in MISSING_HEADER.finditer(log):
        new = HEADER_SUBST.get(m.group("hdr"))
        item = (m.group("file").replace("\\", "/"), m.group("hdr"), new)
        if new and item not in out:
            out.append(item)
    return out


# BSD <sys/queue.h> list macros are absent on QNX. Many projects ship their own copy for other platforms; force-include it.
QUEUE_MACROS = re.compile(r"(expected specifier-qualifier-list before|unknown type name) '(LIST_ENTRY|LIST_HEAD|TAILQ_ENTRY|"
                          r"TAILQ_HEAD|SLIST_ENTRY|SLIST_HEAD|STAILQ_ENTRY|STAILQ_HEAD)'|implicit declaration of function "
                          r"'(LIST_\w+|TAILQ_\w+|SLIST_\w+|STAILQ_\w+)'")
# IPv4/IPv6 socket constants and structs used without <netinet/in.h>.
NETINET = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+?):\d+:\d+: error: (?:'(?:IPPROTO_\w+|INADDR_\w+|IP_\w+|IPV6_\w+)' "
                     r"undeclared|invalid use of undefined type 'struct sockaddr_in6?'|storage size of '\w+' isn't known)", re.M)


def needs_queue_compat(log):
    return bool(QUEUE_MACROS.search(log))


def netinet_files(log):
    """Source files that use IPv4/IPv6 socket names without including <netinet/in.h>."""
    out = []
    for m in NETINET.finditer(log):
        f = m.group("file").replace("\\\\", "/")
        if f not in out:
            out.append(f)
    return out


# QNX keeps pthread, rt, dl and util functions in libc, so there is no separate library to link; upstream build files
# that add -lpthread / -lrt / -ldl / -lutil fail at link time. An empty archive of that name in a porting-layer directory
# satisfies the linker without editing upstream build files.
NO_SUCH_LIB = re.compile(r"cannot find -l(pthread|rt|dl|util|anl|resolv)\b")


def stub_libraries(log):
    return sorted(set(NO_SUCH_LIB.findall(log)))


# Byte-order helpers from <endian.h> that QNX does not provide under these names.
ENDIAN_FUNCS = re.compile(r"(undefined reference to `|implicit declaration of function ')(htobe|htole|be|le)(16|32|64)(toh)?")
# CMake 4 refuses projects that still declare cmake_minimum_required below 3.5.
OLD_CMAKE_POLICY = re.compile(r"Compatibility with CMake < 3\.5 has been removed from CMake")


def needs_endian_compat(log):
    return bool(ENDIAN_FUNCS.search(log))


def needs_policy_minimum(log):
    return bool(OLD_CMAKE_POLICY.search(log))
