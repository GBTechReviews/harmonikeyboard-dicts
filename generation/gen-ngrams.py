#!/usr/bin/env python3
# gen-ngrams.py - build a versioned, checksummed NgramPack (see NgramPack.kt) from
# a plain-text corpus, plus a HELD-OUT next-word test set from sentences the pack
# never saw. Deterministic: same corpus in -> byte-identical pack out.
#
# Usage:
#   python scripts/gen-ngrams.py --lang en --source gutenberg-1661 \
#       --out app/src/test/resources/eval/en_ngrams_demo.txt \
#       --test app/src/test/resources/eval/en_ngrams_test.tsv \
#       corpus1.txt [corpus2.txt ...]
#
# PRODUCTION NOTE: the shipped English pack should be built from the Leipzig
# Corpus (CC BY - see THIRD_PARTY_DATA.md), which is conversational-register and
# attribution-only. This script is the pipeline; the corpus is the only variable.
import argparse, hashlib, re, sys

TRI_SEP = chr(1)                      # must match NgramPack.TRI_SEP
SENT_SPLIT = re.compile(r"[.!?\n]+")


def sentences(paths, word_re):
    for p in paths:
        with open(p, encoding="utf-8", errors="ignore") as f:
            text = f.read().lower()
        for chunk in SENT_SPLIT.split(text):
            toks = word_re.findall(chunk)
            if len(toks) >= 2:
                yield toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--source", required=True, help="short provenance token (no spaces)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--holdout", type=int, default=6, help="hold out every Nth sentence for the test set")
    ap.add_argument("--test-keep", type=int, default=1, help="emit 1 of every K held-out sentences (repo size)")
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--top-followers", type=int, default=8)
    ap.add_argument("--max-bi", type=int, default=40000)
    ap.add_argument("--max-tri", type=int, default=40000)
    # Extra lowercase letters beyond a-z that count as part of a word - the
    # language's own diacritic letters (e.g. Polish "aceelnoszz" with ogoneks/kreskas).
    # Tokens keep their diacritics because the keyboard commits accented words, so the
    # context words must match what the user has actually typed.
    ap.add_argument("--letters", default="")
    ap.add_argument("corpus", nargs="+")
    a = ap.parse_args()

    letters = "a-z" + re.escape(a.letters)
    word_re = re.compile(f"[{letters}][{letters}']*")

    bi, tri = {}, {}
    test_lines = []
    ho = 0
    for i, toks in enumerate(sentences(a.corpus, word_re)):
        if a.holdout > 0 and i % a.holdout == 0:
            # held-out: emit test cases (subsampled), do NOT train on it
            emit = (ho % a.test_keep == 0)
            ho += 1
            if emit:
                for j in range(1, len(toks)):
                    p2 = toks[j - 2] if j >= 2 else ""
                    test_lines.append(f"{p2}\t{toks[j-1]}\t{toks[j]}")
            continue
        for j in range(1, len(toks)):
            bi.setdefault(toks[j - 1], {}).__setitem__(
                toks[j], bi[toks[j - 1]].get(toks[j], 0) + 1)
        for j in range(2, len(toks)):
            k = toks[j - 2] + TRI_SEP + toks[j - 1]
            tri.setdefault(k, {}).__setitem__(toks[j], tri[k].get(toks[j], 0) + 1)

    def prune(table, top, cap):
        rows = []
        for ctx, followers in table.items():
            kept = sorted(((c, w) for w, c in followers.items() if c >= a.min_count),
                          key=lambda x: (-x[0], x[1]))[:top]
            for c, w in kept:
                rows.append((ctx, w, c))
        # deterministic order; cap total rows by keeping the most frequent contexts
        rows.sort(key=lambda r: (r[0], -r[2], r[1]))
        return rows[:cap]

    bi_rows = prune(bi, a.top_followers, a.max_bi)
    tri_rows = prune(tri, a.top_followers, a.max_tri)

    body_lines = [f"b\t{ctx}\t{w}\t{c}" for ctx, w, c in bi_rows]
    for k, w, c in tri_rows:
        p2, p1 = k.split(TRI_SEP)
        body_lines.append(f"t\t{p2}\t{p1}\t{w}\t{c}")
    body = "\n".join(body_lines) + "\n"
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = (f"#HKNGRAM v1 lang={a.lang} schema=1 sha256={sha} "
              f"bigrams={len(bi_rows)} trigrams={len(tri_rows)} source={a.source}")

    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n" + body)
    with open(a.test, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(test_lines) + "\n")

    print(f"pack {a.out}: {len(bi_rows)} bigrams, {len(tri_rows)} trigrams, "
          f"{len(body.encode('utf-8'))} bytes; test {a.test}: {len(test_lines)} cases")


if __name__ == "__main__":
    main()
