#!/usr/bin/env python3
# hktext.py - the ONE text pipeline the pack generators share: reading a corpus,
# normalising it, splitting it into sentences and words, and casing it the way the
# keyboard does. gen-ngrams.py (v2) imports it; its tests are tests/test_hktext.py.
#
# Every rule here is written so the SAME corpus bytes always give the SAME tokens on
# every platform. Two things can still move the output and are therefore RECORDED in
# every provenance file this pipeline writes: the Python version and the Unicode
# database version (unicodedata.unidata_version), because NFC and the letter
# categories are both defined by the latter.
#
# ASCII source on purpose: every non-ASCII character is built with chr() so no
# editor, shell or tool can silently turn an escape into a different glyph.
import bz2
import hashlib
import unicodedata

# ---------------------------------------------------------------- sentence ends
# Characters that END a sentence in the scripts the keyboard ships, AFTER NFC.
# The Latin trio, the ellipsis and the doubled marks, and each script's own full
# stop / question / exclamation. A newline is always an end (one Tatoeba sentence
# per line). The Greek question mark U+037E is canonically equivalent to ';' and
# NFC turns it INTO ';', so for Greek ';' is a sentence end - see terminators().
_SENTENCE_END_CODEPOINTS = [
    0x21, 0x2E, 0x3F,              # ! . ?
    0x0589,                        # ARMENIAN FULL STOP
    0x055C, 0x055E,                # ARMENIAN EXCLAMATION / QUESTION MARK
    0x061F,                        # ARABIC QUESTION MARK
    0x06D4,                        # ARABIC FULL STOP (Urdu)
    0x0700, 0x0701, 0x0702,        # SYRIAC END OF PARAGRAPH / SUPRALINEAR / SUBLINEAR FULL STOP
    0x0964, 0x0965,                # DEVANAGARI DANDA / DOUBLE DANDA (all Brahmic scripts use them)
    0x0F0D, 0x0F0E,                # TIBETAN MARK SHAD / NYIS SHAD
    0x104A, 0x104B,                # MYANMAR SIGN LITTLE / SECTION
    0x1362, 0x1367, 0x1368,        # ETHIOPIC FULL STOP / QUESTION MARK / PARAGRAPH SEPARATOR
    0x166E,                        # CANADIAN SYLLABICS FULL STOP
    0x1803, 0x1809,                # MONGOLIAN FULL STOP / MANCHU FULL STOP
    0x2026,                        # HORIZONTAL ELLIPSIS
    0x203C, 0x203D,                # DOUBLE EXCLAMATION MARK / INTERROBANG
    0x2047, 0x2048, 0x2049,        # DOUBLE QUESTION / QUESTION EXCLAMATION / EXCLAMATION QUESTION
    0x2E2E,                        # REVERSED QUESTION MARK
    0x3002,                        # IDEOGRAPHIC FULL STOP
    0xFE52, 0xFE56, 0xFE57,        # SMALL FULL STOP / QUESTION / EXCLAMATION
    0xFF01, 0xFF0E, 0xFF1F, 0xFF61,  # FULLWIDTH ! . ? and HALFWIDTH IDEOGRAPHIC FULL STOP
]
SENTENCE_ENDS = frozenset(chr(c) for c in _SENTENCE_END_CODEPOINTS) | {"\n", "\r"}

# Languages whose ';' is a question mark after NFC.
_SEMICOLON_IS_QUESTION = frozenset({"el"})


def terminators(lang):
    """The sentence-end set for a language code."""
    if lang in _SEMICOLON_IS_QUESTION:
        return SENTENCE_ENDS | {";"}
    return SENTENCE_ENDS


# ---------------------------------------------------------------- apostrophes
# Every character typists use for an APOSTROPHE inside a word is folded onto the
# plain one, because that is what the keyboard's word lists and packs store (the
# app folds a typed U+2019 the same way before it asks a pack). Folded only when it
# sits BETWEEN two word characters; at a word's edge it is a quotation mark.
APOSTROPHE = "'"
_APOSTROPHE_VARIANTS = [
    0x2019,   # RIGHT SINGLE QUOTATION MARK (smart quotes)
    0x2018,   # LEFT SINGLE QUOTATION MARK (a common mis-key)
    0x02BC,   # MODIFIER LETTER APOSTROPHE (Ukrainian/Belarusian convention)
    0xFF07,   # FULLWIDTH APOSTROPHE
    0x2032,   # PRIME (OCR / typist substitute)
]
APOSTROPHES = frozenset([APOSTROPHE] + [chr(c) for c in _APOSTROPHE_VARIANTS])


# ---------------------------------------------------------------- casing
# Turkic Latin alphabets pair dotted and dotless i separately:
#   I (U+0049) <-> dotless i (U+0131),  dotted capital I (U+0130) <-> i (U+0069).
# Python's str.lower() is locale-blind: it turns I into i (wrong for Turkish) and
# the dotted capital into i + COMBINING DOT ABOVE (two characters, matching nothing
# the keyboard stores). The keyboard lowers with LatinOrthography.lower, which has
# the Turkic rule; this is the same rule.
TURKIC = frozenset({"tr", "az"})
_CAP_I = "I"
_CAP_I_DOT = chr(0x0130)
_SMALL_DOTLESS_I = chr(0x0131)


def lower(text, lang):
    if lang in TURKIC:
        text = text.replace(_CAP_I_DOT, "i").replace(_CAP_I, _SMALL_DOTLESS_I)
    return unicodedata.normalize("NFC", text.lower())


# ---------------------------------------------------------------- scripts
_SCRIPT_PREFIX = {
    "latin": "LATIN ", "cyrillic": "CYRILLIC ", "greek": "GREEK ", "armenian": "ARMENIAN ",
    "georgian": "GEORGIAN ", "hebrew": "HEBREW ", "arabic": "ARABIC ", "devanagari": "DEVANAGARI ",
    "bengali": "BENGALI ", "gurmukhi": "GURMUKHI ", "gujarati": "GUJARATI ", "tamil": "TAMIL ",
    "telugu": "TELUGU ", "kannada": "KANNADA ", "malayalam": "MALAYALAM ", "thai": "THAI ",
    "hangul": "HANGUL ", "ethiopic": "ETHIOPIC ",
}
SCRIPTS = tuple(sorted(_SCRIPT_PREFIX))


def _is_word_char(ch):
    cat = unicodedata.category(ch)
    return cat[0] == "L" or cat[0] == "M"


def _in_scripts(ch, prefixes):
    if prefixes is None:
        return True
    cat = unicodedata.category(ch)
    if cat[0] == "M" or cat == "Lm":
        # a combining mark belongs to the letter it sits on; a modifier letter
        # (the Uzbek okina U+02BB, the length mark U+02D0) belongs to no script
        return True
    name = unicodedata.name(ch, "")
    return any(name.startswith(p) for p in prefixes)


def script_prefixes(scripts):
    """--scripts "latin,cyrillic" -> the Unicode name prefixes, or None for 'any'."""
    if not scripts:
        return None
    out = []
    for s in scripts.split(","):
        s = s.strip().lower()
        if not s:
            continue
        if s not in _SCRIPT_PREFIX:
            raise ValueError("unknown script %r (known: %s)" % (s, ", ".join(SCRIPTS)))
        out.append(_SCRIPT_PREFIX[s])
    return tuple(out) if out else None


# ---------------------------------------------------------------- tokenising
def sentences(line, lang):
    """Split one already-lowered NFC line into sentence chunks."""
    ends = terminators(lang)
    cur = []
    out = []
    for ch in line:
        if ch in ends:
            if cur:
                out.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def words(chunk, prefixes=None):
    """The word tokens of one sentence chunk.

    A word is a run of letters and combining marks, optionally joined by an
    apostrophe BETWEEN two word characters (don't, l'home, m'yaso). Digits, hyphens,
    punctuation and symbols end a word. A token holding a letter outside the allowed
    scripts is dropped whole (it is not a word of this language), never truncated.
    """
    out = []
    cur = []
    foreign = False
    n = len(chunk)
    i = 0

    def flush():
        nonlocal foreign
        if cur and not foreign:
            out.append("".join(cur))
        cur.clear()
        foreign = False

    while i < n:
        ch = chunk[i]
        if ch in APOSTROPHES:
            # checked BEFORE the letter test: U+02BC is category Lm and would
            # otherwise be kept as a (foreign-script) letter
            nxt = chunk[i + 1] if i + 1 < n else ""
            if cur and nxt and nxt not in APOSTROPHES and _is_word_char(nxt):
                cur.append(APOSTROPHE)
            else:
                flush()
        elif _is_word_char(ch):
            if not _in_scripts(ch, prefixes):
                foreign = True
            cur.append(ch)
        else:
            flush()
        i += 1
    flush()
    return out


# ---------------------------------------------------------------- reading
class DecodeError(Exception):
    pass


class CorpusReader:
    """Streams a corpus one line at a time, decoding each line STRICTLY as UTF-8.

    A line that is not valid UTF-8 is never silently repaired: it is counted, its
    line number and file recorded (first 20), and skipped. The caller decides
    whether any such line is acceptable (gen-ngrams.py fails by default).
    Accepts plain text (one sentence per line) or a Tatoeba export
    (id<TAB>lang<TAB>text) with tsv=True, compressed with bzip2 or not.
    """

    def __init__(self, paths, tsv=False):
        self.paths = list(paths)
        self.tsv = tsv
        self.lines = 0
        self.decode_errors = 0
        self.error_samples = []
        self.bad_rows = 0
        self.input_sha256 = {}

    def _open(self, path):
        if path.endswith(".bz2"):
            return bz2.open(path, "rb")
        return open(path, "rb")

    def __iter__(self):
        for path in self.paths:
            h = hashlib.sha256()
            with open(path, "rb") as raw:
                for block in iter(lambda: raw.read(1 << 20), b""):
                    h.update(block)
            self.input_sha256[path] = h.hexdigest()
            with self._open(path) as f:
                for lineno, b in enumerate(f, 1):
                    self.lines += 1
                    try:
                        text = b.decode("utf-8")
                    except UnicodeDecodeError as e:
                        self.decode_errors += 1
                        if len(self.error_samples) < 20:
                            self.error_samples.append("%s:%d: %s" % (path, lineno, e.reason))
                        continue
                    if text.startswith(chr(0xFEFF)) and lineno == 1:
                        text = text[1:]
                    text = text.rstrip("\r\n")
                    if self.tsv:
                        parts = text.split("\t", 2)
                        if len(parts) != 3:
                            self.bad_rows += 1
                            continue
                        text = parts[2]
                    yield text


# ---------------------------------------------------------------- partitioning
def sentence_key(tokens):
    """The identity of a sentence for de-duplication and the train/test split:
    its lowered word tokens. Two corpus lines that differ only in punctuation or
    case have the same key, so they can never land on opposite sides."""
    return " ".join(tokens)


def bucket(key, modulus, salt="hk-holdout-1"):
    """A stable bucket 0..modulus-1 for a key, identical on every platform."""
    d = hashlib.sha256((salt + "\x00" + key).encode("utf-8")).digest()
    return int.from_bytes(d[:8], "big") % modulus
