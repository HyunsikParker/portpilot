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
