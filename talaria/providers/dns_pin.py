"""Pin a hostname to an IP resolved via an alternate DNS resolver.

Useful when a service's normal DNS/routing is blocked or unreachable in a
region, but a specific alternate resolver (e.g. a smart-DNS/unblocking
service) returns a reachable IPv4 address for it. TLS is unaffected — SNI
and the Host header still carry the real hostname, so certificate
validation works exactly as normal; only which IP the socket connects to
changes, scoped to that one hostname.
"""

import socket
from urllib.parse import urlparse

import dns.resolver


def pin_hostname(hostname: str, dns_servers: list[str]) -> str:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = dns_servers
    answer = resolver.resolve(hostname, "A")
    ip = str(answer[0])

    orig_getaddrinfo = socket.getaddrinfo

    def patched(host, port, family=0, type=0, proto=0, flags=0):
        if host == hostname:
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]
        return orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched
    return ip


def pin_base_url(base_url: str, dns_servers: list[str]) -> str:
    hostname = urlparse(base_url).hostname
    if not hostname:
        raise ValueError(f"Could not parse hostname from base_url: {base_url}")
    return pin_hostname(hostname, dns_servers)
