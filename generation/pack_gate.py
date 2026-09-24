#!/usr/bin/env python3
# pack_gate.py - the prediction-regression gate for the PUBLISHED n-gram packs.
#
# For every manifest entry at generator v2 or later it loads the gzipped pack and its
# held-out test sample (the provenance names both) and scores next-word prediction the
# way HKeyboard's ContextModel.predict ranks pack evidence: the trigram (prev2, prev1)
# followers at weight 1.0 plus the bigram (prev1) followers at weight 0.4, each
# normalised within its own context, echoes of the context removed. The app's unigram
# FILL and the user's learned bigrams are not modelled - they are the same for every
# pack, so they cannot hide a pack regression, and leaving them out keeps this gate free
# of the app. HKeyboard's NgramAbEvaluationTest is the full measurement; this is the
# fence that stops a worse pack being published.
#
# FAILS when a pack's context coverage or top-3 on its own held-out sample falls below
# the floor recorded in languages.json ("gate"), or its size exceeds the ceiling there.
# Deterministic: no timing, no randomness.
#   python generation/pack_gate.py            (all)      --report  (print the numbers)
import gzip
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRI_SEP = chr(1)
BACKOFF = 0.4   # Scoring.CTX_BACKOFF


def load_pack(path):
    raw = gzip.decompress(open(path, "rb").read()).decode("utf-8")
    bi, tri = {}, {}
    for line in raw.split("\n")[1:]:
        p = line.split("\t")
        if p[0] == "b" and len(p) >= 4:
            bi.setdefault(p[1], {})[p[2]] = int(p[3])
        elif p[0] == "t" and len(p) >= 5:
            tri.setdefault(p[1] + TRI_SEP + p[2], {})[p[3]] = int(p[4])
    return bi, tri


def predict(bi, tri, p2, p1, k=3):
    scores = {}

    def blend(m, w):
        if not m:
            return
        tot = sum(m.values())
        for word, c in m.items():
            scores[word] = scores.get(word, 0.0) + w * c / tot
    if p2:
        blend(tri.get(p2 + TRI_SEP + p1), 1.0)
    blend(bi.get(p1), BACKOFF)
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked if w != p1 and w != p2][:k]


def score(pack_path, test_path):
    bi, tri = load_pack(pack_path)
    n = cov = top3 = 0
    for line in open(test_path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        p2, p1, nxt = p[0], p[1], p[2]
        n += 1
        if p1 in bi or (p2 and (p2 + TRI_SEP + p1) in tri):
            cov += 1
        if nxt in predict(bi, tri, p2, p1):
            top3 += 1
    return n, cov, top3


def main():
    report = "--report" in sys.argv
    cfg = json.load(open(os.path.join(REPO, "generation", "languages.json"), encoding="utf-8"))["languages"]
    man = json.load(open(os.path.join(REPO, "manifests", "ngram-manifest.json"), encoding="utf-8"))
    fails = []
    seen = set()
    for e in man["packs"]:
        f = e["file"]
        if f in seen or e.get("packVersion", 1) < 2 or f.startswith("it_ngrams.v2"):
            continue
        seen.add(f)
        code = f.split("_", 1)[0]
        prov = json.load(open(os.path.join(REPO, "provenance", f.replace(".txt.gz", ".json")), encoding="utf-8"))
        test = os.path.join(REPO, prov["heldOutTest"]["file"])
        n, cov, top3 = score(os.path.join(REPO, "packs", f), test)
        gate = cfg[code].get("gate", {})
        c, t = 100.0 * cov / max(1, n), 100.0 * top3 / max(1, n)
        if report:
            print("%-26s cases %6d  coverage %6.2f%%  top-3 %6.2f%%  size %d" % (f, n, c, t, e["fileSize"]))
        if not gate:
            fails.append("%s: no gate floor in languages.json" % f)
            continue
        if c < gate["coverage"]:
            fails.append("%s: context coverage %.2f%% below the floor %.2f%%" % (f, c, gate["coverage"]))
        if t < gate["top3"]:
            fails.append("%s: top-3 %.2f%% below the floor %.2f%%" % (f, t, gate["top3"]))
        if e["fileSize"] > gate["maxBytes"]:
            fails.append("%s: %d bytes over the ceiling %d" % (f, e["fileSize"], gate["maxBytes"]))
    for x in fails:
        print("FAIL", x)
    print("%d FAIL" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
