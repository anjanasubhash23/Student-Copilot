"""Fetch a user-supplied URL without letting it reach internal services (SSRF).

- http/https on ports 80/443 only.
- Every hop's host must resolve only to public addresses, and the address actually connected to is checked
  again after connecting (so a DNS answer that changes between check and connect is still caught).
- At most 3 redirects, each re-checked; at most `max_bytes` read; HTML, plain text or PDF only.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf")
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
USER_AGENT = "study-copilot/0.1 (+fetches pages its users add as study material)"


class FetchError(Exception):
    """The URL is not allowed, unreachable, too big, or not a supported type. The message is safe to show."""


@dataclass
class Fetched:
    url: str  # after redirects
    content_type: str
    body: bytes


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url: str) -> tuple[str, int]:
    """Raise FetchError unless `url` is http(s) on a standard port and its host resolves only to public IPs."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("only http and https links are supported")
    if not parts.hostname:
        raise FetchError("the link has no host")
    if parts.username or parts.password:
        raise FetchError("links with credentials are not allowed")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("the link has an invalid port") from exc
    if port not in (80, 443):
        raise FetchError("only links on the standard ports (80, 443) are allowed")
    try:
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"could not resolve {parts.hostname}") from exc
    addresses = {str(info[4][0]) for info in infos}
    if not addresses or not all(is_public(a) for a in addresses):
        raise FetchError("the link points to a private or internal address")
    return parts.hostname, port


def _connected_address(response: httpx.Response) -> str | None:
    stream = response.extensions.get("network_stream")
    if stream is None:
        return None
    peer = stream.get_extra_info("server_addr")
    return str(peer[0]) if peer else None


def fetch(url: str, max_bytes: int, client: httpx.Client | None = None) -> Fetched:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": USER_AGENT})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            with client.stream("GET", url) as response:
                peer = _connected_address(response)
                if peer is not None and not is_public(peer):
                    raise FetchError("the link points to a private or internal address")
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("redirect without a location")
                    url = urljoin(url, location)
                    continue
                if response.status_code >= 400:
                    raise FetchError(f"the site answered {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type not in ALLOWED_TYPES:
                    raise FetchError(f"unsupported content type {content_type or 'unknown'}; HTML or PDF only")
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchError(f"the page is larger than {max_bytes // 1_000_000} MB")
                body = bytearray()
                for piece in response.iter_bytes():
                    body.extend(piece)
                    if len(body) > max_bytes:
                        raise FetchError(f"the page is larger than {max_bytes // 1_000_000} MB")
                return Fetched(url=str(response.url), content_type=content_type, body=bytes(body))
        raise FetchError(f"more than {MAX_REDIRECTS} redirects")
    except httpx.HTTPError as exc:
        raise FetchError(f"could not fetch the link: {type(exc).__name__}") from exc
    finally:
        if own:
            client.close()
