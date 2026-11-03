"""Library filter facets for services/metadata_enricher.py: genre names, decade, a rough script-based
language guess and the search/filter tags built from them."""

GENRE_MAP = {
    "rock": "Rock",
    "classic rock": "Rock",
    "hard rock": "Rock",
    "punk rock": "Rock",
    "alternative rock": "Rock",
    "rock & roll": "Rock",
    "indie rock": "Indie",
    "indie pop": "Indie",
    "indie": "Indie",
    "alternative": "Indie",
    "pop": "Pop",
    "teen pop": "Pop",
    "dance-pop": "Pop",
    "electropop": "Pop",
    "synth-pop": "Pop",
    "adult contemporary": "Pop",
    "mandopop": "Pop",
    "cantopop": "Pop",
    "k-pop": "Pop",
    "j-pop": "Pop",
    "dance": "Dance / Electronic",
    "electronic": "Dance / Electronic",
    "house": "Dance / Electronic",
    "techno": "Dance / Electronic",
    "disco": "Dance / Electronic",
    "edm": "Dance / Electronic",
    "hip-hop/rap": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "trap": "Hip-Hop",
    "r&b/soul": "R&B / Soul",
    "r&b": "R&B / Soul",
    "soul": "R&B / Soul",
    "funk": "R&B / Soul",
    "heavy metal": "Metal",
    "metal": "Metal",
    "soundtrack": "Soundtrack",
    "musicals": "Soundtrack",
    "anime": "Soundtrack",
    "singer/songwriter": "Acoustic / Ballads",
    "country": "Country",
    "latin": "Latin",
    "reggae": "Reggae",
}


def normalize_genre(raw_genre: str | None) -> str:
    if not raw_genre:
        return "Pop"
    cleaned = raw_genre.strip().lower()
    return GENRE_MAP.get(cleaned, raw_genre.title())


def compute_decade(year: int | None) -> str | None:
    if not year or year < 1920 or year > 2035:
        return None
    d = (year // 10) * 10
    if d >= 2000:
        return f"{d}s"
    return f"{d % 100}s"


def detect_language(text: str) -> str:
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return "ru"
    if any("\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in text):
        return "ja"
    if any("\uac00" <= ch <= "\ud7af" for ch in text):
        return "ko"
    if any("\u00e0" <= ch <= "\u00ff" or "\u0153" <= ch <= "\u0153" for ch in text):
        return "fr"
    return "en"


def build_tags(genre: str, decade: str | None, lang: str, year: int | None, raw_title: str) -> list[str]:
    """Search/filter tags: genre parts, decade, language (+ Russian rock), classic, duet."""
    tags = set()
    if genre:
        tags.add(genre.lower())
        for g_part in genre.lower().split("/"):
            tags.add(g_part.strip())
    if decade:
        tags.add(decade.lower())
    if lang:
        tags.add(lang.lower())
        if lang == "ru":
            tags.add("russian")
            tags.add("русское")
            if genre in ("Rock", "Indie"):
                tags.add("russian rock")
                tags.add("русский рок")

    if year and year <= 1999:
        tags.add("classic")
        tags.add("retro")

    lower_full = raw_title.lower()
    if "feat" in lower_full or "ft." in lower_full:
        tags.add("duet")
    return sorted(tags)
