"""Safety rules for the host's own source links (Settings › Sources).

A custom link is a URL template the server fetches on its own, so it must never reach this
laptop, the party LAN or any other private address (that would turn the karaoke into a probe of
the home network). check_template() validates what the host types; check_url() runs again on
every filled-in URL right before a request, after a fresh DNS lookup, and on every redirect.
"""
import ipaddress
import re
import socket
import unicodedata
import urllib.parse

MAX_LEN = 300
MAX_NAME = 40
SONG_FIELDS = ("query",)
LYRICS_FIELDS = ("artist", "title", "query", "artist_slug", "title_slug")
_FIELD = re.compile(r"\{([a-z_]+)\}")
_BLOCKED_HOSTS = ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback")
_BLOCKED_SUFFIXES = (".localhost", ".local", ".lan", ".home", ".internal", ".intranet", ".corp", ".home.arpa")


class LinkError(ValueError):
    """A link the host typed (or a URL it expands to) that may not be used."""


def _private(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast or ip.is_reserved


def _host_ok(host: str) -> None:
    host = (host or "").strip(".").lower()
    if not host:
        raise LinkError("The link needs a website address")
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES) or "." not in host and ":" not in host:
        raise LinkError("Links to this laptop or the local network are not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if _private(ip):
        raise LinkError("Links to this laptop or the local network are not allowed")


def check_url(url: str, resolve: bool = True) -> str:
    """The URL when it is http(s) on a public host, else LinkError. With resolve, every address
    the name points at must be public too (a public name can point at 192.168.x.x)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise LinkError("Only http:// and https:// links are allowed")
    if parts.username or parts.password:
        raise LinkError("Links may not contain a user name or password")
    _host_ok(parts.hostname or "")
    if resolve:
        try:
            infos = socket.getaddrinfo(parts.hostname, parts.port or None, proto=socket.IPPROTO_TCP)
        except (socket.gaierror, UnicodeError) as exc:
            raise LinkError(f"Can't find the website {parts.hostname}") from exc
        if any(_private(ipaddress.ip_address(info[4][0].split("%")[0])) for info in infos):
            raise LinkError("That website points at a local network address")
    return url


def check_template(template: str, kind: str) -> str:
    """A cleaned template for this kind ("songs" or "lyrics"), or LinkError with a reason."""
    template = (template or "").strip()
    if not template or len(template) > MAX_LEN:
        raise LinkError(f"The link must be 1 to {MAX_LEN} characters")
    if any(ch.isspace() or unicodedata.category(ch)[0] == "C" for ch in template):
        raise LinkError("The link may not contain spaces or control characters")
    allowed = SONG_FIELDS if kind == "songs" else LYRICS_FIELDS
    used = _FIELD.findall(template)
    if not used:
        raise LinkError("The link needs a placeholder: " + ", ".join(f"{{{f}}}" for f in allowed))
    if unknown := sorted(set(used) - set(allowed)):
        raise LinkError(f"Unknown placeholder {{{unknown[0]}}}: use " + ", ".join(f"{{{f}}}" for f in allowed))
    if _FIELD.search(urllib.parse.urlsplit(template).netloc):
        raise LinkError("Placeholders belong in the path or query, not in the website name")
    check_url(_FIELD.sub("x", template), resolve=False)
    return template


def check_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > MAX_NAME or any(unicodedata.category(ch)[0] == "C" for ch in name):
        raise LinkError(f"The name must be 1 to {MAX_NAME} characters")
    return name


def slug(text: str) -> str:
    """"Guns N' Roses" -> "guns-n-roses" (the shape many lyrics sites use in their page names)."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text.replace("'", "").replace("&", " and ")).strip("-")


def fill(template: str, **values: str) -> str:
    """The template with every placeholder replaced by its URL-encoded value."""
    values = {**values, "artist_slug": slug(values.get("artist", "")), "title_slug": slug(values.get("title", ""))}
    return _FIELD.sub(lambda m: urllib.parse.quote(values.get(m.group(1), ""), safe=""), template)
