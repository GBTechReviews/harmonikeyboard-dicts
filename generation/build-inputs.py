#!/usr/bin/env python3
# build-inputs.py - runs the v2 generator for every language in languages.json from a
# directory of Tatoeba exports, writing the plain pack (input/<code>_ngrams.v<N>.txt),
# the published held-out test sample (<code>_ngrams_test.v<N>.tsv) and a JSON record
# of the EXACT command, input checksum and counts (input/<code>_ngrams.v<N>.build.json)
# that build-ngram-packs.py copies into the provenance file. One command rebuilds all:
#
#   python build-inputs.py --corpora <dir with *_sentences.tsv.bz2> --retrieved de=2026-09-24 ...
#
# The version a language is built AS comes from PACK_VERSION in build-ngram-packs.py
# (the one table); a language already at that version with a different body is
# REFUSED - a published version is never rebuilt into different bytes.
import argparse
import datetime
import hashlib
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", required=True)
    ap.add_argument("--retrieved", action="append", default=[], help="code=YYYY-MM-DD, the export's retrieval date")
    ap.add_argument("langs", nargs="*")
    a = ap.parse_args()
    gen = load("gen_ngrams", "gen-ngrams.py")
    bnp = load("build_ngram_packs", "build-ngram-packs.py")
    cfg = json.load(open(os.path.join(HERE, "languages.json"), encoding="utf-8"))["languages"]
    dates = dict(x.split("=", 1) for x in a.retrieved)
    for code in a.langs or sorted(cfg):
        c = cfg[code]
        ver = bnp.PACK_VERSION.get(code, 1)
        if ver < 2:
            print("%s: still at v1 (legacy generator) - skipped" % code)
            continue
        date = dates.get(code)
        if not date:
            sys.exit("%s: pass --retrieved %s=YYYY-MM-DD" % (code, code))
        corpus = os.path.join(a.corpora, "%s_sentences.tsv.bz2" % c["tatoeba"])
        out = os.path.join(HERE, "input", "%s_ngrams.v%d.txt" % (code, ver))
        test = os.path.join(HERE, "%s_ngrams_test.v%d.tsv" % (code, ver))
        tmp = out + ".new"
        argv = ["--lang", code, "--source", "tatoeba-%s-%s" % (c["tatoeba"], date), "--tsv",
                "--scripts", c["scripts"], "--holdout", str(c["holdout"]), "--test-keep", str(c["testKeep"]),
                "--min-count", str(c["minCount"]), "--top-followers", str(c["topFollowers"]),
                "--max-bi", str(c["maxBi"]), "--max-tri", str(c["maxTri"])]
        if c["stop"]:
            argv += ["--stop", c["stop"]]
        for d in c["drop"]:
            argv += ["--drop", d]
        stats_path = tmp + ".stats"
        buf = io.StringIO()
        with redirect_stdout(buf):
            stats = gen.build(gen_args(gen, argv + ["--out", tmp, "--test", test, "--stats", stats_path, corpus]))
        os.remove(stats_path)
        new = open(tmp, "rb").read()
        if os.path.isfile(out) and open(out, "rb").read() != new:
            os.remove(tmp)
            sys.exit("%s: REFUSING - input/%s exists with different bytes; bump PACK_VERSION"
                     % (code, os.path.basename(out)))
        os.replace(tmp, out)
        record = {
            "command": "python gen-ngrams.py " + " ".join(shlex_quote(x) for x in argv)
                       + " --out input/%s --test %s %s" % (os.path.basename(out), os.path.basename(test),
                                                            os.path.basename(corpus)),
            "retrievalDate": date,
            "builtDate": datetime.date.today().isoformat(),
            "sourceVersion": "Tatoeba export %s" % date,
            "inputSha256": stats["inputs"][os.path.basename(corpus)],
            "testFile": os.path.basename(test),
            "testSha256": hashlib.sha256(open(test, "rb").read()).hexdigest(),
            "stats": {k: stats[k] for k in ("generator", "python", "unicode", "lines_read", "decode_errors",
                                            "lines_dropped", "train_lines", "test_lines", "test_dup_lines_skipped",
                                            "test_cases", "bigram", "trigram", "body_sha256")},
        }
        with open(os.path.join(HERE, "builds", "%s_ngrams.v%d.build.json" % (code, ver)), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("%s v%d: %s" % (code, ver, buf.getvalue().strip() or "built"))
        print("   bigram %s | trigram %s" % (stats["bigram"], stats["trigram"]))


def gen_args(gen, argv):
    return gen.parse_args(argv)


def shlex_quote(s):
    if s and all(ch.isalnum() or ch in "-_.,=/:'" for ch in s) and "'" not in s:
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    main()
