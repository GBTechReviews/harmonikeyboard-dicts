#!/usr/bin/env python3
# eval-ab.py - prepares the before/after comparison of the v1 and v2 n-gram generators
# on IDENTICAL training data, so a measured difference is the generator's and not the
# corpus's. For one language it:
#
#   1. splits the corpus into train / test with the v2 partition (hktext.bucket over
#      the sentence's word tokens; the same --drop filter), writing the RAW train lines;
#   2. builds three packs from the SAME train lines, with the same caps and stop list:
#        A   legacy/gen-ngrams-v1.py              (the generator that built v1)
#        A2  gen-ngrams.py --cap-order alphabetical (v2 text handling, v1's cap) - ablation
#        B   gen-ngrams.py                        (v2)
#   3. builds the official v2 pack from the WHOLE corpus with --holdout, and checks its
#      body is byte-identical to B's (proof that B trained on exactly the train split);
#   4. writes the full held-out test set (every held-out sentence, v2 tokenisation).
#
# HKeyboard's NgramAbEvaluationTest then scores A, A2 and B on that test set through
# the app's real ContextModel. Nothing here touches a published file; the official
# pack goes to --official-out and the caller decides whether it is published.
#
#   python eval-ab.py --lang de --corpus deu_sentences.tsv.bz2 --work ab/de \
#       --source tatoeba-deu-2026-09-24 --official-out input/de_ngrams.v2.txt
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hktext  # noqa: E402


def run(cmd):
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("failed: %s" % " ".join(cmd[:4]))
    return r.stdout.strip()


def body(path):
    with open(path, "rb") as f:
        return f.read().split(b"\n", 1)[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--corpus", required=True, help="Tatoeba export (.tsv or .tsv.bz2)")
    ap.add_argument("--work", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--official-out", required=True)
    ap.add_argument("--official-test", default="", help="the subsampled test set published beside the pack")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, "languages.json"), encoding="utf-8"))["languages"][a.lang]
    os.makedirs(a.work, exist_ok=True)
    prefixes = hktext.script_prefixes(cfg["scripts"])
    drops = [re.compile(d) for d in cfg["drop"]]

    train_path = os.path.join(a.work, "train.txt")
    n_train = n_test = n_drop = 0
    reader = hktext.CorpusReader([a.corpus], tsv=True)
    with open(train_path, "w", encoding="utf-8", newline="\n") as tr:
        for line in reader:
            if drops and any(d.search(line) for d in drops):
                n_drop += 1
                continue
            low = hktext.lower(unicodedata.normalize("NFC", line), a.lang)
            toks = [w for ch in hktext.sentences(low, a.lang) for w in hktext.words(ch, prefixes)]
            if not toks:
                continue
            if hktext.bucket(hktext.sentence_key(toks), cfg["holdout"]) == 0:
                n_test += 1
            else:
                n_train += 1
                tr.write(line + "\n")
    if reader.decode_errors:
        raise SystemExit("corpus has %d undecodable lines" % reader.decode_errors)

    common = ["--min-count", str(cfg["minCount"]), "--top-followers", str(cfg["topFollowers"]),
              "--max-bi", str(cfg["maxBi"]), "--max-tri", str(cfg["maxTri"])]
    stop = ["--stop", cfg["stop"]] if cfg["stop"] else []
    gen = os.path.join(HERE, "gen-ngrams.py")
    legacy = os.path.join(HERE, "legacy", "gen-ngrams-v1.py")
    out = {}
    pa = os.path.join(a.work, "A_v1.txt")
    out["A"] = run([sys.executable, legacy, "--lang", a.lang, "--source", a.source, "--holdout", "0",
                    "--letters", cfg["v1letters"], "--out", pa, "--test", os.path.join(a.work, "A_unused.tsv")]
                   + common + stop + [train_path])
    v2 = [sys.executable, gen, "--lang", a.lang, "--source", a.source, "--scripts", cfg["scripts"]] + common + stop
    pa2 = os.path.join(a.work, "A2_v2text_v1cap.txt")
    out["A2"] = run(v2 + ["--holdout", "0", "--cap-order", "alphabetical", "--out", pa2,
                          "--stats", os.path.join(a.work, "A2.stats.json"), train_path])
    pb = os.path.join(a.work, "B_v2.txt")
    out["B"] = run(v2 + ["--holdout", "0", "--out", pb, "--stats", os.path.join(a.work, "B.stats.json"), train_path])
    drop_args = [x for d in cfg["drop"] for x in ("--drop", d)]
    test_full = os.path.join(a.work, "test.tsv")
    out["official"] = run(v2 + ["--tsv", "--holdout", str(cfg["holdout"]), "--out", a.official_out,
                                "--test", test_full, "--stats", os.path.join(a.work, "official.stats.json")]
                          + drop_args + [a.corpus])
    if body(a.official_out) != body(pb):
        raise SystemExit("official v2 body differs from B - the train split is not the same")
    if a.official_test:
        run(v2 + ["--tsv", "--holdout", str(cfg["holdout"]), "--test-keep", str(cfg["testKeep"]),
                  "--out", os.path.join(a.work, "official_again.txt"), "--test", a.official_test]
            + drop_args + [a.corpus])
        if body(os.path.join(a.work, "official_again.txt")) != body(a.official_out):
            raise SystemExit("rebuild is not byte-identical")
    summary = {"lang": a.lang, "train_lines": n_train, "test_lines": n_test, "dropped_lines": n_drop,
               "corpus": os.path.basename(a.corpus), "input_sha256": list(reader.input_sha256.values())[0],
               "runs": out}
    with open(os.path.join(a.work, "ab.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(summary, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
