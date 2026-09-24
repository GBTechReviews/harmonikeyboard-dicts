#!/usr/bin/env python3
# Tests for the vendored word-list generator (generation/gen-tatoeba-words.py, the same
# file as HKeyboard's scripts/gen-tatoeba-words.py) and for validate.py's word rules.
# ASCII source: non-ASCII strings are built with chr().
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.dirname(HERE)
SCRIPT = os.path.join(GEN, "gen-tatoeba-words.py")

_spec = importlib.util.spec_from_file_location("validate", os.path.join(GEN, "validate.py"))
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)


def run(corpus_bytes, *args):
    d = tempfile.mkdtemp()
    src = os.path.join(d, "c.tsv")
    with open(src, "wb") as f:
        f.write(corpus_bytes)
    out = os.path.join(d, "w.txt")
    r = subprocess.run([sys.executable, SCRIPT, "--lang", "xx", "--script", "latin", "--tsv", "--min-count", "1",
                        "--out", out] + list(args) + [src],
                       capture_output=True, env=dict(os.environ, PYTHONUTF8="1"))
    data = open(out, "rb").read() if os.path.isfile(out) else None
    return r.returncode, data, r.stderr.decode("utf-8", "replace")


class WordListGeneratorTest(unittest.TestCase):
    CORPUS = ("1\txx\tThe cat sat. The cat ran!\n2\txx\tA dog and the cat\n"
              "3\txx\tTom saw the dog\n").encode("utf-8")

    def test_frequency_order_and_names_dropped(self):
        code, data, _ = run(self.CORPUS)
        self.assertEqual(code, 0)
        words = data.decode("utf-8").split("\n")[:-1]
        self.assertEqual(words[:2], ["the", "cat"])
        self.assertNotIn("tom", words)

    def test_deterministic(self):
        self.assertEqual(run(self.CORPUS)[1], run(self.CORPUS)[1])

    def test_decode_error_fails_by_default(self):
        code, _, err = run(self.CORPUS + b"4\txx\t\xff broken\n")
        self.assertEqual(code, 2)
        self.assertIn("not valid UTF-8", err)

    def test_decode_error_allowed_is_skipped_not_repaired(self):
        code, data, _ = run(self.CORPUS + b"4\txx\tzebra \xff broken\n", "--max-decode-errors", "1")
        self.assertEqual(code, 0)
        self.assertNotIn("zebra", data.decode("utf-8"))

    def test_crlf_corpus_is_the_same_list(self):
        self.assertEqual(run(self.CORPUS.replace(b"\n", b"\r\n"))[1], run(self.CORPUS)[1])


class WordRuleTest(unittest.TestCase):
    def test_words(self):
        ok = ["cat", "don't", "col" + chr(0xB7) + "legi", "o" + chr(0x2BB) + "zbek", "well-known",
              chr(0x928) + chr(0x92E) + chr(0x938) + chr(0x94D) + chr(0x924) + chr(0x947)]
        for w in ok:
            self.assertTrue(validate.is_word(w), ascii(w))
        for w in ["", "3rd", chr(0x60E), chr(0x60F), "a b", "-x", "x-", "$", "cat."]:
            self.assertFalse(validate.is_word(w), ascii(w))

    def test_roman_skeleton(self):
        self.assertEqual(validate.roman_skeleton("mein"), "mn")
        self.assertEqual(validate.roman_skeleton("aap"), "ap")
        self.assertEqual(validate.roman_skeleton("bahut"), "bht")
        self.assertEqual(validate.roman_skeleton("mn"), "mn")


if __name__ == "__main__":
    unittest.main()
