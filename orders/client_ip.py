"""The address a request is attributed to, behind a reverse proxy or not.

gunicorn fills REMOTE_ADDR from the socket peer. Behind a proxy that peer is the
proxy, so a per-address failure budget would count every login attempt in the
world into one bucket: ten wrong passwords from anyone would lock every device
on a shared account out for five minutes (issue #61). Reading X-Forwarded-For
unconditionally is the opposite failure -- the header is client-supplied, so an
attacker would simply rotate it and never hit a limit at all.

The boundary is `TRUSTED_PROXY_IPS`: the header is read only when the immediate
peer is one of those addresses, and only back to the first hop that is not.
"""
from ipaddress import ip_address, ip_network

from django.conf import settings


def _networks():
    """The configured proxies, as networks. A bare address is a /32 or /128."""
    return tuple(ip_network(entry, strict=False) for entry in settings.TRUSTED_PROXY_IPS)


def _parse(value: str):
    """An address from one X-Forwarded-For entry, or None.

    Some proxies append the source port, which changes per connection and would
    split one client across buckets. IPv6 literals may arrive bracketed.
    """
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith("["):  # [2001:db8::1]:51234
        candidate = candidate[1:].split("]", 1)[0]
    elif candidate.count(":") == 1:  # 203.0.113.9:51234, never bare IPv6
        candidate = candidate.split(":", 1)[0]
    try:
        return ip_address(candidate)
    except ValueError:
        return None


def _trusted(address, networks) -> bool:
    return any(address in network for network in networks)


def client_ip(request) -> str:
    """The client address for throttling, as a string.

    Falls back to the peer address whenever the chain cannot be trusted or
    parsed: an unusable header must not become a bucket of its own, and this
    runs on exactly the request an attacker controls.
    """
    peer = request.META.get("REMOTE_ADDR", "")
    networks = _networks()
    if not networks:
        return peer
    try:
        peer_address = ip_address(peer)
    except ValueError:
        return peer
    if not _trusted(peer_address, networks):
        return peer
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    # Each hop appends the peer it saw, so the rightmost entry that a trusted
    # proxy did not add is the closest address no client chose for itself.
    # Anything further left is client-supplied and unverifiable.
    for entry in reversed(forwarded.split(",")):
        address = _parse(entry)
        if address is None:
            return peer
        if not _trusted(address, networks):
            return str(address)
    return peer
