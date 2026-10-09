"""
Hard-coded network lockdown for the yq / xq / tomlq command-line tools.

These tools only transcode local documents and pipe them through ``jq``. They never need a
network port, so the command-line entry points call :func:`lock_down_network` before touching
any input. After that call no IPv4/IPv6 socket can be created in this process, which means it
cannot listen on, bind to, or connect out through any port, even if a dependency or a crafted
document were ever to try. There is deliberately no flag or environment variable to turn this
off. Unix-domain sockets and plain pipes (used for stdin/stdout and for ``jq``) are unaffected.

This is an in-process guard (defense in depth). Enforce the same rule outside the process too,
for example with ``docker run --network none`` or a firewall rule.
"""

from __future__ import annotations

import socket

_INTERNET_FAMILIES = frozenset({socket.AF_INET, socket.AF_INET6})
_original_socket_init = socket.socket.__init__
_locked = False


class NetworkAccessBlocked(PermissionError):
    """Raised when code tries to use the network from a locked-down yq process."""


def _blocked(*args, **kwargs):
    raise NetworkAccessBlocked("network access is disabled in yq (no ports may be opened or used)")


def _guarded_socket_init(self, family=-1, type=-1, proto=-1, fileno=None):
    # With an explicit family, refuse internet sockets before anything is created.
    if fileno is None and family in _INTERNET_FAMILIES:
        _blocked()
    # With no family (or a fileno), PyYAML-style autodetection applies: create, then verify.
    _original_socket_init(self, family, type, proto, fileno)
    if self.family in _INTERNET_FAMILIES:
        self.close()
        _blocked()


def lock_down_network():
    """Irreversibly forbid creating or using IPv4/IPv6 sockets in this process. Idempotent."""
    global _locked
    if _locked:
        return
    socket.socket.__init__ = _guarded_socket_init  # type: ignore[method-assign]
    # Belt and braces: also close the high-level helpers and name resolution.
    for name in (
        "create_connection",
        "create_server",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "getnameinfo",
    ):
        setattr(socket, name, _blocked)
    _locked = True
