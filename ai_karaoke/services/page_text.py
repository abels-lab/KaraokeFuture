"""The lyrics on a web page: the longest block of short, sung-looking lines.

Used for the host's own lyrics links (services/custom_lyrics.py), where nothing is known about
the page layout. The page is read with the standard HTML parser (no browser, no scripts run):
scripts, styles, menus, headers, footers and forms are dropped, <br> and block ends become line
breaks, and the block of consecutive lyric-like lines with the most words wins. Menus (one or
two words per line), paragraphs of prose (long lines) and link lists are rarely chosen.
"""
import html
import re
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button",
        "select", "iframe", "template", "aside", "textarea"}
BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "table", "section",
         "article", "pre", "blockquote", "main", "dd", "dt"}
VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}
MAX_LINE = 90         # characters: longer is prose, not a sung line
_NOISE = re.compile(r"https?://|www\.|©|cookie|privacy|javascript|copyright|all rights reserved|"
                    r"sign ?in|log ?in|subscribe|advert", re.IGNORECASE)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK:
            self.parts.append("\n\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(re.sub(r"[ \t\r\f\v]+", " ", data.replace("\n", " ")))


def lines_of(page: str, is_html: bool = True) -> list[str]:
    if not is_html:
        return [line.strip() for line in html.unescape(page).splitlines()]
    parser = _Text()
    try:
        parser.feed(page)
        parser.close()
    except Exception:   # a badly broken page: whatever was read so far
        pass
    lines = [line.strip() for line in "".join(parser.parts).split("\n")]
    return [line for i, line in enumerate(lines) if line or (i and lines[i - 1])]   # one blank at most


def _sung(line: str) -> bool:
    words = line.split()
    return 0 < len(line) <= MAX_LINE and 0 < len(words) <= 16 and not _NOISE.search(line) \
        and sum(ch.isalpha() for ch in line) >= len(line.replace(" ", "")) * 0.5


def _paragraphs(lines: list[str]) -> list[list[str]]:
    paras, cur = [], []
    for line in lines + [""]:
        if line:
            cur.append(line)
        elif cur:
            paras.append(cur)
            cur = []
    return paras


def _score(run: list[list[str]]) -> tuple[list[list[str]], int]:
    """The run without the one-line paragraphs at its ends (headings, menu items), and its words."""
    while run and len(run[0]) < 2:
        run = run[1:]
    while run and len(run[-1]) < 2:
        run = run[:-1]
    sung = [line for para in run for line in para]
    words = sum(len(line.split()) for line in sung)
    # Menus and tag clouds: mostly one or two words per line
    return run, words if sung and words / len(sung) >= 2.5 else 0


def best_block(lines: list[str]) -> list[str]:
    """The run of stanzas made only of sung-looking lines holding the most words; [] if none."""
    best, best_words, run = [], 0, []
    for para in _paragraphs(lines) + [[]]:
        if para and all(_sung(line) for line in para):
            run.append(para)
            continue
        kept, words = _score(run)
        if words > best_words:
            best, best_words = kept, words
        run = []
    return [line for i, para in enumerate(best) for line in ([""] if i else []) + para]


def mentions(page_lines: list[str], title: str) -> bool:
    """Does the page name the song at all? (A "not found" or home page usually doesn't.)"""
    words = [w for w in re.findall(r"\w+", (title or "").lower()) if len(w) > 1]
    text = " ".join(page_lines).lower()
    return not words or sum(w in text for w in words) >= max(1, len(words) // 2)


def lyrics(page: str, title: str, is_html: bool = True) -> str | None:
    page_lines = lines_of(page, is_html)
    if not mentions(page_lines, title):
        return None
    block = best_block(page_lines)
    return "\n".join(block).strip() or None
