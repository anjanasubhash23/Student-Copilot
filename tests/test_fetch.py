import socket
from typing import Any

import httpx
import pytest

from core.sources.fetch import FetchError, check_url, fetch, is_public

PUBLIC = "93.184.215.14"


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Hostname → address; anything unlisted fails to resolve."""
    table = {"example.com": PUBLIC, "cdn.example.com": PUBLIC, "internal.example.com": "10.0.0.5"}

    def getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        if host in table:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], port))]
        try:  # literal IPs resolve to themselves
            import ipaddress

            ipaddress.ip_address(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port))]
        except ValueError:
            raise socket.gaierror("unknown host") from None

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return table


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "192.168.0.1", "169.254.169.254", "::1", "fd00::1", "::ffff:127.0.0.1", "0.0.0.0"],
)
def test_private_addresses_are_not_public(address: str) -> None:
    assert not is_public(address)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/x", "only http and https"),
        ("file:///etc/passwd", "only http and https"),
        ("http://example.com:8080/", "standard ports"),
        ("http://user:pw@example.com/", "credentials"),
        ("http://169.254.169.254/latest/meta-data", "private or internal"),
        ("http://internal.example.com/", "private or internal"),
        ("http://[::1]/", "private or internal"),
        ("http://nowhere.invalid/", "could not resolve"),
    ],
)
def test_check_url_rejects(dns: dict[str, str], url: str, message: str) -> None:
    with pytest.raises(FetchError, match=message):
        check_url(url)


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetches_html(dns: dict[str, str]) -> None:
    client = _client(
        lambda r: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<p>hi</p>")
    )
    got = fetch("https://example.com/notes", 1000, client)
    assert (got.content_type, got.body) == ("text/html", b"<p>hi</p>")


def test_redirect_to_internal_host_is_refused(dns: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://internal.example.com/admin"})
        raise AssertionError("must not request the internal host")

    with pytest.raises(FetchError, match="private or internal"):
        fetch("https://example.com/", 1000, _client(handler))


def test_follows_at_most_three_redirects(dns: dict[str, str]) -> None:
    client = _client(lambda r: httpx.Response(301, headers={"location": "https://cdn.example.com/again"}))
    with pytest.raises(FetchError, match="more than 3 redirects"):
        fetch("https://example.com/", 1000, client)


def test_size_limit(dns: dict[str, str]) -> None:
    client = _client(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 2000))
    with pytest.raises(FetchError, match="larger than"):
        fetch("https://example.com/", 1000, client)


def test_content_type_allow_list(dns: dict[str, str]) -> None:
    client = _client(lambda r: httpx.Response(200, headers={"content-type": "application/zip"}, content=b"PK"))
    with pytest.raises(FetchError, match="unsupported content type"):
        fetch("https://example.com/", 1000, client)
