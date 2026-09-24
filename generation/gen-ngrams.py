#!/usr/bin/env python3
# gen-ngrams.py (generator v2) - builds a versioned, checksummed NgramPack (the format
# HKeyboard's NgramPack.kt reads - UNCHANGED, so every shipped app can load a v2 pack)
# from a sentence corpus, plus a HELD-OUT next-word test set from sentences the pack
# never saw. Deterministic: the same corpus bytes give a byte-identical pack.
#
# WHAT CHANGED FROM v1 (legacy/gen-ngrams-v1.py, which built every published v1 pack
# and is kept so those packs stay reproducible):
#
#  1. THE CAP KEEPS THE MOST USEFUL CONTEXTS. v1 sorted its rows by context STRING and
#     then cut at --max-bi / --max-tri, so a capped pack kept the alphabetically early
#     contexts and lost the rest: German bigrams stopped at "pferd" (no "sie", "was",
#     "wir", "zu"), Spanish at "salvo" (no "se", "te", "tu", "un", "y", "yo"), French
#     after "o" (no "pas", "que", "se", "tu", "vous"), English trigrams at "for spring"
#     (no "i am ...", "it is ...", "you are ..."). v2 ranks every context by its SUPPORT
#     (how often it occurred in training), keeps whole contexts from the top until the
#     row budget is spent, and only THEN sorts the kept rows for a stable file.
#  2. UNICODE TEXT HANDLING (hktext.py): NFC; sentence ends in every shipped script
#     (danda, Arabic question mark, ideographic full stop, the ellipsis ...); every
#     apostrophe variant between letters folded onto "'" (don't, l'homme); words of any
#     letter or combining mark rather than a hand-listed a-z + extras set; Turkic
#     casing (I -> dotless i, dotted capital I -> i) for tr / az.
#  3. STRICT DECODING: a line that is not UTF-8 is counted and reported and, by
#     default, FAILS the build - never silently repaired.
#  4. STREAMING: corpora (plain or Tatoeba .tsv, optionally .bz2) are read a line at a
#     time; only the count tables are held in memory.
#  5. A LEAK-FREE SPLIT: a sentence goes to train or test by a hash of its word
#     tokens, so two corpus lines that differ only by case or punctuation always land
#     on the same side; a test sentence repeated in the corpus is tested once.
#
# The pack FORMAT is unchanged (#HKNGRAM v1 schema=1). The header gains one token,
# gen=<generator>, which NgramPack.parse keeps as metadata and otherwise ignores.
#
# Usage (see generation/README.md for the exact per-language commands):
#   python gen-ngrams.py --lang de --source tatoeba-deu-2026-09-24 --tsv --scripts latin \
#       --stop tom,mary --holdout 6 --min-count 3 --max-bi 30000 --max-tri 25000 \
#       --out input/de_ngrams.v2.txt --test de_ngrams_test.v2.tsv \
#       --stats de_ngrams.v2.stats.json deu_sentences.tsv.bz2
import argparse
import hashlib
import json
import os
import platform
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hktext  # noqa: E402

GENERATOR = "gen-ngrams-2"
TRI_SEP = chr(1)                      # must match NgramPack.TRI_SEP


def prune(table, support, top, cap, min_count, cap_order="support"):
    """Turn a count table into pack rows under a row budget.

    table:   context -> {follower: count}
    support: context -> how often the context occurred in training
    Each context keeps its `top` most frequent followers seen >= min_count times.
    cap_order="support" (v2): contexts are taken in DESCENDING support (ties by the
    context string) and kept whole while the budget lasts; the last context is cut
    to fit. cap_order="alphabetical" reproduces the v1 defect and exists ONLY so the
    evaluation can attribute a change to the cap alone.
    Returns (rows sorted by context then count, stats dict).
    """
    per_ctx = []
    for ctx, followers in table.items():
        kept = sorted(((c, w) for w, c in followers.items() if c >= min_count),
                      key=lambda x: (-x[0], x[1]))[:top]
        if kept:
            per_ctx.append((ctx, kept))
    if cap_order == "alphabetical":
        rows = []
        for ctx, kept in per_ctx:
            rows.extend((ctx, w, c) for c, w in kept)
        rows.sort(key=lambda r: (r[0], -r[2], r[1]))
        out = rows[:cap]
    else:
        per_ctx.sort(key=lambda t: (-support[t[0]], t[0]))
        out = []
        for ctx, kept in per_ctx:
            room = cap - len(out)
            if room <= 0:
                break
            out.extend((ctx, w, c) for c, w in kept[:room])
        out.sort(key=lambda r: (r[0], -r[2], r[1]))
    kept_ctx = {r[0] for r in out}
    total_support = sum(support[ctx] for ctx, _ in per_ctx)
    stats = {
        "contexts_eligible": len(per_ctx),
        "contexts_kept": len(kept_ctx),
        "rows_eligible": sum(len(k) for _, k in per_ctx),
        "rows_kept": len(out),
        # the share of training context OCCURRENCES whose context survived the cap -
        # the number the cap is supposed to maximise
        "support_kept_share": round(sum(support[c] for c in kept_ctx) / total_support, 6)
        if total_support else 0.0,
    }
    return out, stats


def build(a):
    prefixes = hktext.script_prefixes(a.scripts)
    stop = set(hktext.lower(t, a.lang) for t in a.stop.split(",") if t)
    drops = [re.compile(d) for d in a.drop]
    reader = hktext.CorpusReader(a.corpus, tsv=a.tsv)

    bi, tri = {}, {}
    bi_sup, tri_sup = {}, {}
    test_rows = []
    test_keys = set()
    n = {"lines_used": 0, "lines_dropped": 0, "lines_empty": 0, "train_lines": 0,
         "test_lines": 0, "test_dup_lines_skipped": 0, "train_tokens": 0}

    for line in reader:
        if drops and any(d.search(line) for d in drops):
            n["lines_dropped"] += 1
            continue
        low = hktext.lower(unicodedata.normalize("NFC", line), a.lang)
        chunks = [hktext.words(ch, prefixes) for ch in hktext.sentences(low, a.lang)]
        chunks = [c for c in chunks if c]
        if not chunks:
            n["lines_empty"] += 1
            continue
        n["lines_used"] += 1
        key = hktext.sentence_key([w for c in chunks for w in c])
        held = a.holdout > 0 and hktext.bucket(key, a.holdout) == 0
        if held:
            if key in test_keys:
                n["test_dup_lines_skipped"] += 1
                continue
            test_keys.add(key)
            n["test_lines"] += 1
            if a.test_keep > 1 and hktext.bucket(key, a.test_keep, salt="hk-testkeep-1") != 0:
                continue
            for toks in chunks:
                for j in range(1, len(toks)):
                    p2 = toks[j - 2] if j >= 2 else ""
                    if toks[j] in stop or toks[j - 1] in stop or (p2 and p2 in stop):
                        continue
                    test_rows.append("%s\t%s\t%s" % (p2, toks[j - 1], toks[j]))
            continue
        n["train_lines"] += 1
        for toks in chunks:
            if len(toks) < 2:
                continue
            n["train_tokens"] += len(toks)
            for j in range(1, len(toks)):
                if toks[j] in stop or toks[j - 1] in stop:
                    continue
                p = toks[j - 1]
                bi_sup[p] = bi_sup.get(p, 0) + 1
                d = bi.setdefault(p, {})
                d[toks[j]] = d.get(toks[j], 0) + 1
            for j in range(2, len(toks)):
                if toks[j] in stop or toks[j - 1] in stop or toks[j - 2] in stop:
                    continue
                k = toks[j - 2] + TRI_SEP + toks[j - 1]
                tri_sup[k] = tri_sup.get(k, 0) + 1
                d = tri.setdefault(k, {})
                d[toks[j]] = d.get(toks[j], 0) + 1

    if reader.decode_errors > a.max_decode_errors:
        sys.stderr.write("REFUSING: %d line(s) are not valid UTF-8 (allowed %d):\n  %s\n"
                         % (reader.decode_errors, a.max_decode_errors, "\n  ".join(reader.error_samples)))
        sys.exit(2)

    bi_rows, bi_stats = prune(bi, bi_sup, a.top_followers, a.max_bi, a.min_count, a.cap_order)
    tri_rows, tri_stats = prune(tri, tri_sup, a.top_followers, a.max_tri, a.min_count, a.cap_order)

    body_lines = ["b\t%s\t%s\t%d" % (ctx, w, c) for ctx, w, c in bi_rows]
    for k, w, c in tri_rows:
        p2, p1 = k.split(TRI_SEP)
        body_lines.append("t\t%s\t%s\t%s\t%d" % (p2, p1, w, c))
    body = "\n".join(body_lines) + "\n"
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = ("#HKNGRAM v1 lang=%s schema=1 sha256=%s bigrams=%d trigrams=%d source=%s gen=%s"
              % (a.lang, sha, len(bi_rows), len(tri_rows), a.source, GENERATOR))
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n" + body)
    if a.test:
        with open(a.test, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(test_rows) + ("\n" if test_rows else ""))

    stats = {
        "generator": GENERATOR,
        "lang": a.lang,
        "python": platform.python_version(),
        "unicode": unicodedata.unidata_version,
        "inputs": {os.path.basename(p): s for p, s in reader.input_sha256.items()},
        "lines_read": reader.lines,
        "decode_errors": reader.decode_errors,
        "decode_error_samples": reader.error_samples,
        "malformed_tsv_rows": reader.bad_rows,
        **n,
        "test_cases": len(test_rows),
        "bigram": bi_stats,
        "trigram": tri_stats,
        "body_bytes": len(body.encode("utf-8")),
        "body_sha256": sha,
        "options": {k: v for k, v in vars(a).items() if k not in ("corpus", "out", "test", "stats")},
    }
    if a.stats:
        with open(a.stats, "w", encoding="utf-8", newline="\n") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    return stats


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True, help="ISO 639 code; tr/az switch on Turkic casing, el ';' as '?'")
    ap.add_argument("--source", required=True, help="short provenance token (no spaces)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", default="", help="held-out next-word cases (prev2<TAB>prev1<TAB>next)")
    ap.add_argument("--stats", default="", help="write a JSON record of every count")
    ap.add_argument("--tsv", action="store_true", help="corpus is a Tatoeba export (id<TAB>lang<TAB>text)")
    ap.add_argument("--scripts", default="", help="comma list (latin,cyrillic,greek,...); a token with a "
                    "letter from any other script is dropped. Empty = any script.")
    ap.add_argument("--holdout", type=int, default=6, help="hold out 1 in N sentences (by hash) for the test set")
    ap.add_argument("--test-keep", type=int, default=1, help="emit test cases for 1 in K held-out sentences")
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--top-followers", type=int, default=8)
    ap.add_argument("--max-bi", type=int, default=40000)
    ap.add_argument("--max-tri", type=int, default=40000)
    ap.add_argument("--cap-order", choices=["support", "alphabetical"], default="support",
                    help="'alphabetical' reproduces the v1 cap defect - for evaluation only")
    ap.add_argument("--stop", default="", help="comma list of placeholder names kept out of every n-gram")
    ap.add_argument("--drop", action="append", default=[],
                    help="regex matched against each ORIGINAL corpus line; a match drops the line whole")
    ap.add_argument("--max-decode-errors", type=int, default=0,
                    help="fail when more lines than this are not valid UTF-8 (default 0)")
    ap.add_argument("corpus", nargs="+")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    s = build(a)
    print("pack %s: %d bigrams (%d/%d contexts, %.1f%% of context mass), %d trigrams (%d/%d contexts, "
          "%.1f%%); %d test cases; %d lines, %d decode errors, %d dropped"
          % (a.out, s["bigram"]["rows_kept"], s["bigram"]["contexts_kept"], s["bigram"]["contexts_eligible"],
             100 * s["bigram"]["support_kept_share"], s["trigram"]["rows_kept"], s["trigram"]["contexts_kept"],
             s["trigram"]["contexts_eligible"], 100 * s["trigram"]["support_kept_share"], s["test_cases"],
             s["lines_read"], s["decode_errors"], s["lines_dropped"]))


if __name__ == "__main__":
    main()
