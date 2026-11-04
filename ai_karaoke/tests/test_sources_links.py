"""The host's own source links: the safety rules, filling a template, reading lyrics off a page.
No real network: DNS and HTTP are faked."""
import socket
import unittest
from unittest.mock import MagicMock, patch

from core import source_ids
from core.source_links import LinkError, check_template, check_url, fill, slug
from services import custom_lyrics, page_text, sources


def _addr(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class TestTemplates(unittest.TestCase):
    def test_good_links(self):
        self.assertEqual(check_template(" https://vimeo.com/search?q={query} ", "songs"), "https://vimeo.com/search?q={query}")
        check_template("http://lyrics.example.org/{artist_slug}/{title_slug}.html", "lyrics")

    def test_refused_links(self):
        bad = {
            "ftp://example.com/{query}": "http",
            "file:///C:/{query}": "http",
            "https://localhost/{query}": "local",
            "https://127.0.0.1/{query}": "local",
            "http://192.168.1.20/s?q={query}": "local",
            "http://10.0.0.1/{query}": "local",
            "http://[::1]/{query}": "local",
            "http://169.254.169.254/latest/{query}": "local",
            "http://printer.local/{query}": "local",
            "http://router/{query}": "local",
            "https://user:pw@example.com/{query}": "password",
            "https://example.com/search": "placeholder",
            "https://example.com/{artist}": "Unknown placeholder",
            "https://{query}.example.com/": "website name",
            "https://example.com/" + "a" * 300 + "{query}": "characters",
            "https://example.com/a b/{query}": "spaces",
        }
        for template, reason in bad.items():
            with self.subTest(template=template), self.assertRaisesRegex(LinkError, reason):
                check_template(template, "songs")

    def test_lyrics_placeholders(self):
        with self.assertRaisesRegex(LinkError, "placeholder"):
            check_template("https://example.com/lyrics", "lyrics")
        check_template("https://example.com/?q={query}", "lyrics")

    def test_dns_pointing_at_the_lan_is_refused(self):
        with patch("socket.getaddrinfo", return_value=_addr("192.168.0.10")), self.assertRaisesRegex(LinkError, "local"):
            check_url("https://evil.example.com/x")
        with patch("socket.getaddrinfo", return_value=_addr("93.184.216.34")):
            self.assertEqual(check_url("https://example.com/x"), "https://example.com/x")

    def test_fill_encodes_and_slugs(self):
        url = fill("https://e.com/{artist_slug}/{title_slug}?q={query}", artist="Guns N' Roses",
                   title="Sweet Child O' Mine", query="a&b c/d")
        self.assertEqual(url, "https://e.com/guns-n-roses/sweet-child-o-mine?q=a%26b%20c%2Fd")
        self.assertEqual(slug("Beyoncé & Jay-Z"), "beyonce-and-jay-z")


PAGE = """<html><head><title>Wonderwall Lyrics</title><script>var x = "not lyrics at all";</script></head>
<body><nav><a href="/">Home</a><br><a href="/top">Top songs</a></nav>
<div class="menu"><p>Home</p><p>Artists</p><p>Charts</p></div>
<h1>Oasis - Wonderwall</h1>
<div class="lyrics">Today is gonna be the day<br>That they're gonna throw it back to you<br>
By now you should've somehow<br>Realized what you gotta do<br><br>
I don't believe that anybody<br>Feels the way I do about you now</div>
<p>This page uses cookies to improve your experience. By continuing you agree to the privacy policy and terms.</p>
<footer>© 2026 Example Lyrics, all rights reserved</footer></body></html>"""


class TestPageText(unittest.TestCase):
    def test_picks_the_lyrics_block(self):
        text = page_text.lyrics(PAGE, "Wonderwall")
        self.assertTrue(text.startswith("Today is gonna be the day"), text)
        self.assertIn("\n\nI don't believe that anybody", text)   # the stanza break survives
        self.assertNotIn("Home", text)
        self.assertNotIn("cookies", text)
        self.assertNotIn("not lyrics", text)

    def test_page_about_another_song_gives_nothing(self):
        self.assertIsNone(page_text.lyrics(PAGE, "Bohemian Rhapsody"))

    def test_plain_text(self):
        self.assertEqual(page_text.lyrics("Line one here now\nLine two here now\n", "line", is_html=False),
                         "Line one here now\nLine two here now")


def _response(status=200, body=b"", headers=None):
    r = MagicMock(status_code=status, headers=headers or {"content-type": "text/html; charset=utf-8"}, encoding="utf-8")
    r.is_redirect = status in (301, 302)
    r.iter_content.return_value = [body]
    r.raise_for_status.side_effect = None
    r.__enter__.return_value = r
    return r


class TestCustomLyrics(unittest.TestCase):
    LINK = {"id": "c_1", "name": "Example", "template": "https://lyrics.example.com/{artist_slug}/{title_slug}"}

    def test_fetch_reads_the_page(self):
        with patch("socket.getaddrinfo", return_value=_addr("93.184.216.34")), \
                patch("requests.Session.get", return_value=_response(body=PAGE.encode())) as get:
            text = custom_lyrics.fetch(self.LINK, "Oasis - Wonderwall")
        self.assertEqual(get.call_args.args[0], "https://lyrics.example.com/oasis/wonderwall")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertIn("Today is gonna be the day", text)

    def test_redirect_to_the_lan_is_not_followed(self):
        hop = _response(302, headers={"location": "http://192.168.1.1/admin"})
        with patch("socket.getaddrinfo", return_value=_addr("93.184.216.34")), \
                patch("requests.Session.get", return_value=hop) as get:
            self.assertIsNone(custom_lyrics.fetch(self.LINK, "Oasis - Wonderwall"))
        self.assertEqual(get.call_count, 1)

    def test_oversized_page_is_dropped(self):
        big = _response(body=b"x" * (custom_lyrics.MAX_BYTES + 1))
        with patch("socket.getaddrinfo", return_value=_addr("93.184.216.34")), patch("requests.Session.get", return_value=big):
            self.assertIsNone(custom_lyrics.fetch(self.LINK, "Oasis - Wonderwall"))


class TestCustomIds(unittest.TestCase):
    def test_custom_ids_are_their_own_source(self):
        sid = source_ids.make_id("https://vimeo.com/123")
        self.assertEqual(len(sid), 18)
        self.assertEqual(sources.source_of(sid), sources.CUSTOM)
        self.assertEqual(sources.source_of("dQw4w9WgXcQ"), sources.YOUTUBE)
        self.assertIsNone(sources.source_of("x_nothex000000000"))

    def test_page_url_is_checked_again(self):
        sid = source_ids.make_id("http://10.1.1.1/v")
        with patch("core.source_ids.url_for", return_value="http://10.1.1.1/v"), self.assertRaises(LinkError):
            sources.page_url(sid)
        with patch("core.source_ids.url_for", return_value=None), self.assertRaisesRegex(LinkError, "no longer known"):
            sources.page_url(sid)


if __name__ == "__main__":
    unittest.main()
