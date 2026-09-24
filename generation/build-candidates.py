#!/usr/bin/env python3
# build-candidates.py - builds the UNPUBLISHED candidate packs in candidates/: the same
# generator, corpus and settings as the published pack (languages.json + the build record
# in builds/), with ONE difference, the row caps lifted. They are kept for a decision, not
# offered: nothing here is in manifests/ngram-manifest.json, and no app reads candidates/.
#
#   python build-candidates.py --corpora <dir with *_sentences.tsv.bz2> it ru
#
# Why (reports/2026-09-24-generator-v2.md, section 7): uncapped, Italian's held-out top-1
# rises +23.6% relative and Russian's +16.3% over the published v2/v3 packs, at roughly
# twice the size and heap. The owner kept the published sizes and asked for these to be
# preserved and benchmarked on a real mid-range phone first (top-3, coverage, p95 latency,
# peak memory) - generation/CANDIDATES.md has the procedure and the numbers so far.
#
# Deterministic (the generator's ordering + gzip mtime 0 / level 9 / OS byte 0xFF), so a
# rebuild is byte-identical; a candidate that already exists with different bytes is
# REFUSED, exactly as a published pack is.
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "candidates")
UNCAPPED = 100000000          # larger than any table any corpus here can produce
NAME = "uncapped"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def det_gzip(raw):
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=9, mtime=0) as g:
        g.write(raw)
    b = bytearray(buf.getvalue())
    b[9] = 0xFF
    return bytes(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", required=True)
    ap.add_argument("langs", nargs="+")
    a = ap.parse_args()
    gen = load("gen_ngrams", "gen-ngrams.py")
    bnp = load("build_ngram_packs", "build-ngram-packs.py")
    cfg = json.load(open(os.path.join(HERE, "languages.json"), encoding="utf-8"))["languages"]
    os.makedirs(OUT, exist_ok=True)
    for code in a.langs:
        c = cfg[code]
        ver = bnp.PACK_VERSION[code]
        rec = json.load(open(os.path.join(HERE, "builds", "%s_ngrams.v%d.build.json" % (code, ver)), encoding="utf-8"))
        date = rec["retrievalDate"]
        corpus = os.path.join(a.corpora, "%s_sentences.tsv.bz2" % c["tatoeba"])
        argv = ["--lang", code, "--source", "tatoeba-%s-%s" % (c["tatoeba"], date), "--tsv",
                "--scripts", c["scripts"], "--holdout", str(c["holdout"]), "--test-keep", str(c["testKeep"]),
                "--min-count", str(c["minCount"]), "--top-followers", str(c["topFollowers"]),
                "--max-bi", str(UNCAPPED), "--max-tri", str(UNCAPPED)]
        if c["stop"]:
            argv += ["--stop", c["stop"]]
        for d in c["drop"]:
            argv += ["--drop", d]
        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "pack.txt")
            test = os.path.join(tmp, "test.tsv")
            stats_path = os.path.join(tmp, "stats.json")
            with redirect_stdout(io.StringIO()):
                stats = gen.build(gen.parse_args(argv + ["--out", plain, "--test", test,
                                                         "--stats", stats_path, corpus]))
            raw = open(plain, "rb").read()
            test_sha = hashlib.sha256(open(test, "rb").read()).hexdigest()
        if stats["inputs"][os.path.basename(corpus)] != rec["inputSha256"]:
            sys.exit("%s: the corpus is not the one the published pack was built from" % code)
        if test_sha != rec["testSha256"]:
            sys.exit("%s: held-out split differs from the published pack's" % code)
        gz = det_gzip(raw)
        fname = "%s_ngrams.%s.v%d.txt.gz" % (code, NAME, ver)
        path = os.path.join(OUT, fname)
        if os.path.isfile(path) and open(path, "rb").read() != gz:
            sys.exit("%s: REFUSING - candidates/%s exists with different bytes" % (code, fname))
        with open(path, "wb") as f:
            f.write(gz)
        record = {
            "language": bnp.META[code]["language"],
            "packLocale": bnp.META[code]["locale"],
            "file": fname,
            "status": "CANDIDATE - not published; not in manifests/ngram-manifest.json",
            "basedOn": "packs/%s_ngrams.v%d.txt.gz (same corpus, generator, settings and held-out split; "
                       "only the row caps differ)" % (code, ver),
            "fileSize": len(gz),
            "uncompressedSize": len(raw),
            "sha256": hashlib.sha256(gz).hexdigest(),
            "bodySha256": stats["body_sha256"],
            "source": bnp.META[code]["source"],
            "sourceUrl": bnp.META[code]["source_url"],
            "sourceSha256": rec["inputSha256"],
            "retrievalDate": date,
            "licence": bnp.META[code]["licence"],
            "attribution": bnp.META[code]["attribution"],
            "generationCommand": "python build-candidates.py --corpora <dir> %s  (= python gen-ngrams.py %s)"
                                 % (code, " ".join(argv)),
            "heldOutTest": {"file": "generation/" + rec["testFile"], "sha256": test_sha},
            "capping": {"bigram": stats["bigram"], "trigram": stats["trigram"]},
        }
        with open(os.path.join(OUT, fname.replace(".txt.gz", ".json")), "w", encoding="utf-8", newline="\n") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("%s: %s gz=%d raw=%d bigram rows %d trigram rows %d" % (
            code, fname, len(gz), len(raw), stats["bigram"]["rows_kept"], stats["trigram"]["rows_kept"]))


if __name__ == "__main__":
    main()
