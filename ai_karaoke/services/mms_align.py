"""Forced alignment of KNOWN lyrics with Meta's MMS aligner (torchaudio MMS_FA, CTC, GPU).

Whisper-based alignment (stable-ts) loses its place on repetitive or half-spoken songs and
then piles lines up; a CTC aligner matches the text letter by letter against the audio and
cannot drift like that. Measured without any LRC help: Dream On 100% of lines within 1 s of
the LRC, Du Hast no collapse, Rockwell exact where the LRC itself was 3.5 s early.
MMS reads Latin letters only: Cyrillic is transliterated, other scripts (CJK, ...) return
None and keep stable-ts. LRC timestamps only check the result: their offset to our audio is
often not constant (another edit of the song, an LRC timed to a slightly different version),
so a line that disagrees with its neighbours' offset is re-aligned in its own window, and the
new place is kept only when the aligner is more confident there (an LRC for another edit would
otherwise pull correct lines into wrong windows).
"""
import logging
import statistics
import unicodedata

from config import free_vram
from core import settings
from services import anchored_align

log = logging.getLogger(__name__)

CHUNK, CONTEXT = 30.0, 2.0   # emissions in 30 s windows (+2 s context): attention memory stays ~2 GB
MAX_UNREADABLE = 0.2         # more words than this without Latin letters: not an MMS language
NEIGHBOURS = 4               # lines on each side that give a line its local LRC offset
_CYRILLIC = dict(zip("абвгдезийклмнопрстуфыэіґ", "abvgdeziyklmnoprstufyeig")) | {
    "ё": "yo", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ь": "", "ю": "yu", "я": "ya", "ї": "yi", "є": "ye"}


def romanize(word: str) -> str:
    """Letters MMS knows (a-z and '); umlauts and accents lose their marks."""
    word = "".join(_CYRILLIC.get(c, c) for c in word.lower().replace("ß", "ss"))
    return "".join(c for c in unicodedata.normalize("NFKD", word) if c in "abcdefghijklmnopqrstuvwxyz'")


def _emissions(model, wav, sr: int, device: str):
    import torch
    out, step, ctx = [], int(CHUNK * sr), int(CONTEXT * sr)
    for s in range(0, wav.shape[1], step):
        a, b = max(0, s - ctx), min(wav.shape[1], s + step + ctx)
        with torch.inference_mode():
            em, _ = model(wav[:, a:b].to(device))
        fps = em.shape[1] / ((b - a) / sr)
        lo, hi = round((s - a) / sr * fps), round((min(s + step, wav.shape[1]) - a) / sr * fps)
        out.append(em[0, lo:hi].float().cpu())
    return torch.cat(out)


def _align_words(aligner, tokenizer, emission, words: list[str], offset: int, sec: float):
    """[(start, end, confidence)] per word, seconds and mean letter probability (None: no letters)."""
    readable = [romanize(w) for w in words]
    spans = iter(aligner(emission[offset:], tokenizer([r for r in readable if r])))
    times = []
    for r in readable:
        span = next(spans) if r else None
        times.append(((offset + span[0].start) * sec, (offset + span[-1].end) * sec,
                      sum(t.score for t in span) / len(span)) if span else None)
    return times


def _to_words(words: list[str], times, fallback: float) -> list[dict]:
    out, last = [], fallback
    for i, (word, t) in enumerate(zip(words, times)):
        start, end = t[:2] if t else (last, last)  # "&", "!": sit between their neighbours
        out.append({"word": (" " if i else "") + word, "start": round(start, 3), "end": round(end, 3)})
        last = end
    return out


def align(vocals_path: str, lines, start_time: float = 0.0) -> list[dict] | None:
    """lines: [(anchor or None, text)]. Returns [{"words": [...]}] per line, or None when the
    lyrics are not in a script MMS can read or the model fails (caller falls back to stable-ts)."""
    texts = [text.split() for _, text in lines]
    words = [w for line in texts for w in line]
    if not words or sum(not romanize(w) for w in words) > MAX_UNREADABLE * len(words):
        return None
    import torch
    import torchaudio

    bundle, model = torchaudio.pipelines.MMS_FA, None
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model = bundle.get_model().to(device)
        wav, sr = torchaudio.load(vocals_path)
        wav = torchaudio.functional.resample(wav.mean(0, keepdim=True), sr, bundle.sample_rate)
        emission = _emissions(model, wav, bundle.sample_rate, device)
    except Exception as exc:
        log.warning("MMS alignment unavailable: %s", exc)
        return None
    finally:
        del model
        free_vram()  # one model in VRAM at a time: MMS is gone before Whisper may load
    tokenizer, aligner = bundle.get_tokenizer(), bundle.get_aligner()
    sec = wav.shape[1] / bundle.sample_rate / emission.shape[0]
    try:
        offset = max(0, int(start_time / sec))
        times = iter(_align_words(aligner, tokenizer, emission, words, offset, sec))
    except Exception as exc:  # e.g. more letters than audio frames
        log.warning("MMS alignment failed: %s", exc)
        return None
    segments, conf, last = [], [], 0.0
    for line in texts:
        line_times = [next(times) for _ in line]
        segments.append({"words": _to_words(line, line_times, last)})
        conf.append(_confidence(line_times))
        last = segments[-1]["words"][-1]["end"]
    if all(t is not None for t, _ in lines):
        _check_anchors(segments, conf, lines, texts, aligner, tokenizer, emission, sec)
    return segments


def _confidence(times) -> float:
    scores = [t[2] for t in times if t]
    return sum(scores) / len(scores) if scores else 0.0


def _check_anchors(segments, conf, lines, texts, aligner, tokenizer, emission, sec: float) -> None:
    """Re-align, inside its LRC window, every line whose offset to its LRC anchor differs from
    the offset of the lines around it (an isolated misplacement, not a different edit)."""
    aa = anchored_align
    diffs = [seg["words"][0]["start"] - t for seg, (t, _) in zip(segments, lines)]
    fixed = 0
    for i, (seg, line) in enumerate(zip(segments, texts)):
        around = diffs[max(0, i - NEIGHBOURS): i] + diffs[i + 1: i + 1 + NEIGHBOURS]
        local = statistics.median(around) if around else 0.0
        if abs(diffs[i] - local) <= settings.get("anchor_max_stray"):
            continue
        start = lines[i][0] + local
        end = (lines[i + 1][0] + local) if i + 1 < len(lines) else start + 8.0
        a = max(0, int((start - aa.PAD_BEFORE) / sec))
        b = min(emission.shape[0], int(min(end + aa.PAD_AFTER, start + aa.MAX_WINDOW) / sec))
        try:
            times = _align_words(aligner, tokenizer, emission[:b], line, a, sec)
        except Exception as exc:  # window too short for the text: keep the global placement
            log.debug("MMS line re-align failed (%s): %s", exc, " ".join(line))
            continue
        if _confidence(times) > conf[i]:  # the audio fits the text better in the LRC window
            seg["words"] = _to_words(line, times, start)
            fixed += 1
    log.info("MMS alignment: LRC offset median %+.2f s, %d/%d lines re-aligned in their window",
             statistics.median(diffs), fixed, len(lines))
