#!/usr/bin/env python3
# Tests for the shared text pipeline (hktext.py) and the n-gram generator
# (gen-ngrams.py v2). Run from the repo root:  python -m unittest discover generation/tests
# ASCII source: every non-ASCII test string is built with chr().
import bz2
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.dirname(HERE)
sys.path.insert(0, GEN)
import hktext  # noqa: E402

_spec = importlib.util.spec_from_file_location("gen_ngrams", os.path.join(GEN, "gen-ngrams.py"))
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def u(*cps):
    return "".join(chr(c) for c in cps)


def run_gen(corpus_lines, *extra, encoding="utf-8", raw=None, lang="en"):
    d = tempfile.mkdtemp()
    src = os.path.join(d, "corpus.txt")
    with open(src, "wb") as f:
        f.write(raw if raw is not None else ("\n".join(corpus_lines) + "\n").encode(encoding))
    out = os.path.join(d, "pack.txt")
    test = os.path.join(d, "test.tsv")
    stats = os.path.join(d, "stats.json")
    argv = ["--lang", lang, "--source", "unit", "--out", out, "--test", test, "--stats", stats,
            "--min-count", "1"] + list(extra) + [src]
    with redirect_stdout(io.StringIO()):
        gen.main(argv)
    with open(out, "rb") as f:
        pack = f.read()
    with open(stats, encoding="utf-8") as f:
        st = json.load(f)
    with open(test, encoding="utf-8") as f:
        tst = f.read()
    return pack, st, tst


def contexts(pack, kind="b"):
    out = set()
    for line in pack.decode("utf-8").split("\n")[1:]:
        p = line.split("\t")
        if p[0] == kind:
            out.add(p[1] if kind == "b" else p[1] + " " + p[2])
    return out


class CapTest(unittest.TestCase):
    """The regression the v2 generator exists for: v1 kept alphabetically early
    contexts when capped; v2 keeps the most frequent ones wherever they sort."""

    def corpus(self):
        lines = []
        # a frequent context that sorts LAST ("zu") ...
        lines += ["zu hause"] * 50 + ["zu spaet"] * 40
        # ... and many rare contexts that sort FIRST
        for i in range(30):
            a = "a" + chr(ord("a") + i % 26) + chr(ord("a") + i // 26)
            lines.append("%s x%d" % (a, i))
        return lines

    def test_frequent_context_survives_the_cap_whatever_it_sorts_as(self):
        pack, st, _ = run_gen(self.corpus(), "--holdout", "0", "--max-bi", "10", "--max-tri", "10")
        self.assertIn("zu", contexts(pack))
        self.assertEqual(st["bigram"]["rows_kept"], 10)

    def test_the_v1_order_would_have_lost_it(self):
        # the same budget with the old ordering keeps only "aa..", "ab.." contexts
        pack, _, _ = run_gen(self.corpus(), "--holdout", "0", "--max-bi", "10", "--max-tri", "10",
                             "--cap-order", "alphabetical")
        self.assertNotIn("zu", contexts(pack))

    def test_prune_keeps_whole_contexts_in_support_order(self):
        table = {"b": {"x": 5, "y": 4}, "a": {"z": 1}, "c": {"w": 9}}
        support = {"b": 9, "a": 1, "c": 9}
        rows, st = gen.prune(table, support, top=8, cap=3, min_count=1)
        # b and c tie on support -> the tie breaks by the context string, so b then c
        self.assertEqual(rows, [("b", "x", 5), ("b", "y", 4), ("c", "w", 9)])
        self.assertEqual(st["contexts_kept"], 2)
        self.assertAlmostEqual(st["support_kept_share"], 18 / 19, places=5)

    def test_kept_rows_are_sorted_for_a_stable_file(self):
        table = {"q": {"a": 3, "b": 3, "c": 1}, "m": {"d": 2}}
        rows, _ = gen.prune(table, {"q": 7, "m": 2}, top=8, cap=10, min_count=1)
        self.assertEqual(rows, sorted(rows, key=lambda r: (r[0], -r[2], r[1])))
        self.assertEqual(rows[0][0], "m")

    def test_min_count_and_top_followers(self):
        table = {"k": {"a": 5, "b": 4, "c": 3, "d": 1}}
        rows, _ = gen.prune(table, {"k": 13}, top=2, cap=10, min_count=2)
        self.assertEqual([r[1] for r in rows], ["a", "b"])


class DeterminismTest(unittest.TestCase):
    def test_byte_identical_twice(self):
        lines = ["The cat sat on the mat.", "The dog sat on the log!", "A cat and a dog?"] * 20
        a, sa, ta = run_gen(lines, "--holdout", "3")
        b, sb, tb = run_gen(lines, "--holdout", "3")
        self.assertEqual(a, b)
        self.assertEqual(ta, tb)
        self.assertEqual(sa["body_sha256"], sb["body_sha256"])

    def test_header_checksum_matches_body(self):
        pack, _, _ = run_gen(["one two three four"] * 5, "--holdout", "0")
        header, body = pack.split(b"\n", 1)
        sha = [t.split(b"=")[1] for t in header.split() if t.startswith(b"sha256=")][0]
        self.assertEqual(sha.decode(), hashlib.sha256(body).hexdigest())
        self.assertIn(b"schema=1", header)
        self.assertIn(b"gen=gen-ngrams-2", header)

    def test_bz2_tsv_streams_like_plain_text(self):
        lines = ["hello there friend", "hello there again", "good morning friend"] * 4
        plain, _, _ = run_gen(lines, "--holdout", "0")
        tsv = "".join("%d\teng\t%s\n" % (i, l) for i, l in enumerate(lines)).encode("utf-8")
        d = tempfile.mkdtemp()
        path = os.path.join(d, "c.tsv.bz2")
        with open(path, "wb") as f:
            f.write(bz2.compress(tsv))
        out = os.path.join(d, "p.txt")
        with redirect_stdout(io.StringIO()):
            gen.main(["--lang", "en", "--source", "unit", "--out", out, "--tsv", "--holdout", "0",
                      "--min-count", "1", path])
        with open(out, "rb") as f:
            self.assertEqual(f.read(), plain)


class DecodingTest(unittest.TestCase):
    def test_invalid_utf8_fails_the_build_by_default(self):
        raw = b"good line here\n\xff\xfe broken line\nanother good line\n"
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()):
                import contextlib
                with contextlib.redirect_stderr(io.StringIO()):
                    run_gen(None, "--holdout", "0", raw=raw)

    def test_invalid_utf8_is_counted_when_allowed(self):
        raw = b"good line here\n\xff\xfe broken line\nanother good line\n"
        _, st, _ = run_gen(None, "--holdout", "0", "--max-decode-errors", "1", raw=raw)
        self.assertEqual(st["decode_errors"], 1)
        self.assertEqual(st["lines_read"], 3)
        self.assertTrue(st["decode_error_samples"][0].endswith(":2: invalid start byte"))

    def test_bom_is_not_a_letter(self):
        raw = b"\xef\xbb\xbfhello world\n"
        pack, _, _ = run_gen(None, "--holdout", "0", raw=raw)
        self.assertIn("hello", contexts(pack))


class SplitTest(unittest.TestCase):
    def test_case_and_punctuation_variants_share_a_side(self):
        lines = []
        for i in range(200):
            s = "sentence number %s here" % ("x" * (i % 50 + 1))
            lines += [s, s.upper() + "!", s.capitalize() + "."]
        pack, st, tst = run_gen(lines, "--holdout", "4")
        rows = [r.split("\t") for r in tst.rstrip("\n").split("\n") if r]
        held = {r[2] for r in rows if r[2].startswith("x")}
        trained = {l.split("\t")[2] for l in pack.decode("utf-8").split("\n")[1:]
                   if l.startswith("b\tnumber\t")}
        self.assertTrue(held)
        self.assertTrue(trained)
        # the distinctive word of every held-out sentence never reached training,
        # although each sentence appears three times in three spellings
        self.assertFalse(held & trained)
        self.assertEqual(st["test_lines"] + st["train_lines"] + st["test_dup_lines_skipped"], 600)
        self.assertGreater(st["test_dup_lines_skipped"], 0)

    def test_bucket_is_stable(self):
        # pinned: a change here moves every published test set
        self.assertEqual(hktext.bucket("the cat sat", 6), hktext.bucket("the cat sat", 6))
        self.assertEqual([hktext.bucket(k, 6) for k in ("a", "b", "c", "d")],
                         [hktext.bucket(k, 6) for k in ("a", "b", "c", "d")])
        d = hashlib.sha256(("hk-holdout-1" + "\x00" + "a").encode()).digest()
        self.assertEqual(hktext.bucket("a", 6), int.from_bytes(d[:8], "big") % 6)


class CasingTest(unittest.TestCase):
    CAP_I_DOT = u(0x130)
    DOTLESS = u(0x131)

    def test_turkish_i_family(self):
        self.assertEqual(hktext.lower("I", "tr"), self.DOTLESS)
        self.assertEqual(hktext.lower(self.CAP_I_DOT, "tr"), "i")
        self.assertEqual(hktext.lower("i", "tr"), "i")
        self.assertEqual(hktext.lower(self.DOTLESS, "tr"), self.DOTLESS)
        # ISTANBUL with a dotted capital, and IRMAK (river) with a plain I
        self.assertEqual(hktext.lower(self.CAP_I_DOT + "STANBUL", "tr"), "istanbul")
        self.assertEqual(hktext.lower("IRMAK", "tr"), self.DOTLESS + "rmak")

    def test_azerbaijani_is_turkic_too(self):
        self.assertEqual(hktext.lower("I", "az"), self.DOTLESS)

    def test_other_languages_keep_the_standard_rule(self):
        self.assertEqual(hktext.lower("I", "en"), "i")
        self.assertEqual(hktext.lower("IRMAK", "de"), "irmak")

    def test_turkish_pack_contexts(self):
        pack, _, _ = run_gen([self.CAP_I_DOT + "stanbul " + "b" + u(0xFC) + "y" + u(0xFC) + "k",
                              "Istanbul degil"], "--holdout", "0", lang="tr")
        ctx = contexts(pack)
        self.assertIn("istanbul", ctx)
        self.assertIn(self.DOTLESS + "stanbul", ctx)
        self.assertNotIn("i" + u(0x307) + "stanbul", ctx)

    def test_greek_final_sigma(self):
        # ODOS -> odos with a final sigma
        self.assertEqual(hktext.lower(u(0x39F, 0x394, 0x39F, 0x3A3), "el"), u(0x3BF, 0x3B4, 0x3BF, 0x3C2))


class NormalisationTest(unittest.TestCase):
    def test_nfd_input_becomes_nfc(self):
        nfd = "cafe" + u(0x301) + " noir"
        pack, _, _ = run_gen([nfd, nfd], "--holdout", "0", lang="fr")
        self.assertIn("caf" + u(0xE9), contexts(pack))
        text = pack.decode("utf-8")
        self.assertEqual(text, unicodedata.normalize("NFC", text))


class ApostropheTest(unittest.TestCase):
    def test_every_variant_folds_between_letters(self):
        for cp in (0x27, 0x2019, 0x2018, 0x2BC, 0xFF07):
            w = hktext.words("don" + chr(cp) + "t go")
            self.assertEqual(w, ["don't", "go"], hex(cp))

    def test_quotes_at_the_edges_are_not_part_of_a_word(self):
        self.assertEqual(hktext.words(u(0x2018) + "hello" + u(0x2019) + " she said"),
                         ["hello", "she", "said"])
        self.assertEqual(hktext.words("'tis the dogs' bowls"), ["tis", "the", "dogs", "bowls"])

    def test_elision(self):
        self.assertEqual(hktext.words("l" + u(0x2019) + "homme qu'il"), ["l'homme", "qu'il"])

    def test_double_apostrophe_breaks(self):
        self.assertEqual(hktext.words("a''b"), ["a", "b"])


class SentenceTest(unittest.TestCase):
    def split(self, text, lang="en"):
        return [hktext.words(c) for c in hktext.sentences(text, lang) if hktext.words(c)]

    def test_latin_marks_and_ellipsis(self):
        self.assertEqual(self.split("one two. three four! five six? seven" + u(0x2026) + " eight"),
                         [["one", "two"], ["three", "four"], ["five", "six"], ["seven"], ["eight"]])

    def test_each_script_ends_a_sentence(self):
        cases = {
            0x0589: "armenian full stop", 0x061F: "arabic question", 0x06D4: "urdu full stop",
            0x0964: "danda", 0x0965: "double danda", 0x1362: "ethiopic full stop",
            0x3002: "ideographic full stop", 0xFF01: "fullwidth exclamation", 0xFF1F: "fullwidth question",
            0x104B: "myanmar section", 0x0F0D: "tibetan shad", 0x203C: "double exclamation",
        }
        for cp, name in cases.items():
            self.assertEqual(len(self.split("aa bb" + chr(cp) + "cc dd")), 2, name)

    def test_greek_semicolon_is_a_question_mark(self):
        # U+037E normalises to ';' and ends a Greek sentence, not an English clause
        text = unicodedata.normalize("NFC", "aa bb" + u(0x37E) + " cc dd")
        self.assertEqual(len(self.split(text, "el")), 2)
        self.assertEqual(len(self.split("aa bb; cc dd", "en")), 1)

    def test_hyphen_and_digit_split_words(self):
        self.assertEqual(hktext.words("well-known 3rd x2y"), ["well", "known", "rd", "x", "y"])


class ScriptTest(unittest.TestCase):
    """A two-word phrase in every writing system the keyboard ships a word list for:
    it tokenises into exactly two words, marks included, and a --scripts filter keeps
    the right script and drops a foreign-letter token whole."""

    SAMPLES = {
        "latin": (u(0x63, 0x61, 0x66, 0xE9), "bien"),
        "cyrillic": (u(0x434, 0x43E, 0x43C), u(0x456, 0x491)),
        "greek": (u(0x3BA, 0x3B1, 0x3BB, 0x3AE), u(0x3BC, 0x3AD, 0x3C1, 0x3B1)),
        "armenian": (u(0x562, 0x561, 0x580, 0x587), u(0x561, 0x575, 0x578)),
        "georgian": (u(0x10D2, 0x10D0, 0x10DB), u(0x10D0, 0x10E0)),
        "hebrew": (u(0x5E9, 0x5DC, 0x5D5, 0x5DD), u(0x5E2, 0x5D5, 0x5DC, 0x5DD)),
        "arabic": (u(0x645, 0x631, 0x62D, 0x628, 0x627), u(0x628, 0x64E, 0x64A, 0x62A)),
        "devanagari": (u(0x928, 0x92E, 0x938, 0x94D, 0x924, 0x947), u(0x926, 0x941, 0x928, 0x93F, 0x92F, 0x93E)),
        "bengali": (u(0x986, 0x9AE, 0x9BF), u(0x9AD, 0x9BE, 0x9B2, 0x9CB)),
        "gurmukhi": (u(0xA38, 0xA24, 0xA3F), u(0xA38, 0xA3C, 0xA40)),
        "gujarati": (u(0xA95, 0xAC7, 0xAAE), u(0xA9B, 0xACB)),
        "tamil": (u(0xBA4, 0xBAE, 0xBBF, 0xBB4, 0xBCD), u(0xBA8, 0xBA9, 0xBCD, 0xBB1, 0xBBF)),
        "telugu": (u(0xC24, 0xC46, 0xC32, 0xC41, 0xC17, 0xC41), u(0xC2E, 0xC3E)),
        "kannada": (u(0xC95, 0xCA8, 0xCCD, 0xCA8, 0xCA1), u(0xCA8, 0xCBE, 0xCA1, 0xCC1)),
        "malayalam": (u(0xD2E, 0xD32, 0xD2F, 0xD3E, 0xD33, 0xD02), u(0xD28, 0xD3E, 0xD1F, 0xD4D)),
        "thai": (u(0xE20, 0xE32, 0xE29, 0xE32), u(0xE44, 0xE17, 0xE22)),
        "hangul": (u(0xD55C, 0xAD6D, 0xC5B4), u(0xC548, 0xB155)),
        "ethiopic": (u(0x1230, 0x120B, 0x121D), u(0x12A5, 0x1295, 0x12F4)),
    }

    def test_every_script_tokenises(self):
        for script, (a, b) in self.SAMPLES.items():
            text = unicodedata.normalize("NFC", a + " " + b)
            self.assertEqual(hktext.words(text), [a, b], script)
            self.assertEqual(hktext.words(text, hktext.script_prefixes(script)), [a, b], script)

    def test_foreign_letter_poisons_the_token(self):
        cyr = self.SAMPLES["cyrillic"][0]
        mixed = "dom" + cyr + " house"
        self.assertEqual(hktext.words(mixed, hktext.script_prefixes("latin")), ["house"])
        self.assertEqual(hktext.words(mixed), ["dom" + cyr, "house"])

    def test_modifier_letters_belong_to_the_word(self):
        # Uzbek o-okina: o + U+02BB
        w = "o" + u(0x2BB) + "zbek"
        self.assertEqual(hktext.words(w, hktext.script_prefixes("latin")), [w])

    def test_unknown_script_is_an_error(self):
        with self.assertRaises(ValueError):
            hktext.script_prefixes("klingon")


class LegacyTest(unittest.TestCase):
    """The v1 script is kept byte-for-byte so every published v1 pack can be rebuilt."""

    def test_legacy_script_present(self):
        self.assertTrue(os.path.isfile(os.path.join(GEN, "legacy", "gen-ngrams-v1.py")))


if __name__ == "__main__":
    unittest.main()
