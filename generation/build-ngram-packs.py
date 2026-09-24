#!/usr/bin/env python3
# build-ngram-packs.py - P12. Turn the plain-text NgramPack files produced by
# gen-ngrams.py into the HOSTED artefacts for this repo: a DETERMINISTIC gzip pack
# under packs/, a per-pack provenance record under provenance/, and a combined
# manifests/ngram-manifest.json that HKeyboard's PackDownloadManager reads.
#
# DETERMINISM: gzip is written with mtime=0 and a fixed OS byte, so the same input
# pack yields a byte-identical .gz (and therefore the same SHA-256) on every run.
# Verified by --check (re-gzips and compares).
#
# IMMUTABLE FILENAMES: the pack filename carries its version (de_ngrams.v1.txt.gz).
# A changed pack MUST be given a new version (v2) - this script refuses to overwrite
# an existing .gz whose bytes would differ, so a published filename is never silently
# replaced.
#
# INPUTS are the gen-ngrams.py outputs + a small metadata table (below). The raw
# corpora are NOT part of this repo (see generation/README.md for how to fetch them);
# only the reproducible scripts + the derived packs live here.
import gzip, hashlib, io, json, os, sys, argparse, datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Per-language metadata. Keep in step with generation/README.md and provenance/.
META = {
    "de": dict(language="German", locale="de",
               source="Tatoeba Project", corpus="tatoeba deu_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/deu/deu_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "es": dict(language="Spanish", locale="es",
               source="Tatoeba Project", corpus="tatoeba spa_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/spa/spa_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "fr": dict(language="French", locale="fr",
               source="Tatoeba Project", corpus="tatoeba fra_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/fra/fra_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    # P13: English + Polish rebuilt from Tatoeba to retire the earlier Leipzig-derived
    # packs (whose downloadable-corpus commercial terms could not be confirmed).
    "en": dict(language="English (UK)", locale="en",
               source="Tatoeba Project", corpus="tatoeba eng_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "pl": dict(language="Polish", locale="pl",
               source="Tatoeba Project", corpus="tatoeba pol_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/pol/pol_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    # P14: Portuguese, for the Portuguese (Brazil) engine migration. Tatoeba's
    # por_sentences is mixed pt-BR / pt-PT; the pack is context data, and both
    # versions share this vocabulary as they share the word list.
    "pt": dict(language="Portuguese (Brazil)", locale="pt",
               source="Tatoeba Project", corpus="tatoeba por_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/por/por_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    # P15: Greek, for the Greek engine migration. A small corpus (42,482 sentences),
    # so the pack is ~4,500 contexts each way; the Tatoeba placeholder names are
    # Greek here (Thomas / Mary), stopped as Tom / Mary are elsewhere.
    "el": dict(language="Greek", locale="el",
               source="Tatoeba Project", corpus="tatoeba ell_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/ell/ell_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    # 2026-09-18 (HKeyboard's to-do batch: "add Italian to Next-Word packs, plus a few
    # more languages"): Italian, Dutch, Russian, Turkish. Caps scaled to the corpus as
    # English's were (ita 987k sentences, nld 201k, rus 1.22M, tur 749k); Tatoeba's
    # placeholder names are stopped in each language's own inflections.
    "it": dict(language="Italian", locale="it",
               source="Tatoeba Project", corpus="tatoeba ita_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/ita/ita_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "nl": dict(language="Dutch", locale="nl",
               source="Tatoeba Project", corpus="tatoeba nld_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/nld/nld_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "ru": dict(language="Russian", locale="ru",
               source="Tatoeba Project", corpus="tatoeba rus_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/rus/rus_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
    "tr": dict(language="Turkish", locale="tr",
               source="Tatoeba Project", corpus="tatoeba tur_sentences",
               source_url="https://downloads.tatoeba.org/exports/per_language/tur/tur_sentences.tsv.bz2",
               licence="CC BY 2.0 FR", attribution="Tatoeba Project (https://tatoeba.org), CC BY 2.0 FR"),
}

SCHEMA_VERSION = 1
MIN_ENGINE_VERSION = 1
MIN_APP_VERSION = 9            # HKeyboard versionCode that first understands ngram packs
GEN_VERSION = "gen-ngrams.py v1 + build-ngram-packs.py v1"
# The published version of each language's pack (1 unless bumped). A pack whose
# bytes change gets the next number here and a new input file; the old file
# stays for the apps that bundle or cache it.
#   it v2 (2026-09-20): rebuilt with gen-ngrams.py --drop for the two
#   machine-generated Tatoeba sentence grids ("Vai a costruire ponti in
#   Grecia", "Di che nazionalita sono i tuoi genitori?" - 53,840 sentences)
#   that made "costruire" the top follower of "a" and "nazionalita" of "che"
#   in v1. Same export line, retrieved 2026-09-20.
PACK_VERSION = {"it": 2}
# Languages whose pack was built with --stop (placeholder names); the list per
# language is in generation/README.md.
STOP_LANGS = ("en", "pl", "pt", "el", "it", "nl", "ru", "tr")
# --drop patterns recorded in the provenance, per (lang, version).
DROPS = {("it", 2): "--drop '(?i)^(Non )?(vado|vai|va|andiamo|andate|vanno) a costruire ' "
                    "--drop '^\"?Di che nazionalit. (sono|erano) (i|le) ': 53,840 machine-"
                    "generated grid sentences dropped whole before counting"}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def deterministic_gzip(data: bytes) -> bytes:
    buf = io.BytesIO()
    # mtime=0 removes the timestamp; a fixed compresslevel makes the stream stable.
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(data)
    out = bytearray(buf.getvalue())
    # Byte 9 of the gzip header is the OS field; pin it to 255 (unknown) so the
    # result does not vary by build platform.
    if len(out) > 9:
        out[9] = 0xFF
    return bytes(out)


def build(lang, retrieval_date, source_version, notes, check=False):
    m = META[lang]
    ver = PACK_VERSION.get(lang, 1)
    src_txt = os.path.join(REPO, "generation", "input", f"{lang}_ngrams.v{ver}.txt")
    if not os.path.isfile(src_txt):
        sys.exit(f"missing input pack {src_txt} (run gen-ngrams.py first; see README)")
    raw = open(src_txt, "rb").read()
    uncompressed_sha = sha256_bytes(raw)
    gz = deterministic_gzip(raw)
    if check:
        assert deterministic_gzip(raw) == gz, "gzip not deterministic!"
        assert gzip.decompress(gz) == raw, "gzip round-trip mismatch!"
    fname = f"{lang}_ngrams.v{ver}.txt.gz"
    out_path = os.path.join(REPO, "packs", fname)
    if os.path.isfile(out_path) and open(out_path, "rb").read() != gz:
        sys.exit(f"REFUSING to overwrite published {fname} with different bytes - bump the version")
    with open(out_path, "wb") as f:
        f.write(gz)
    gz_sha = sha256_bytes(gz)
    entry = {
        "language": m["language"],
        "locale": m["locale"],
        "packVersion": ver,
        "minEngineVersion": MIN_ENGINE_VERSION,
        "minAppVersion": MIN_APP_VERSION,
        "file": fname,
        "compression": "gzip",
        "fileSize": len(gz),
        "uncompressedSize": len(raw),
        "sha256": gz_sha,
        "uncompressedSha256": uncompressed_sha,
        "source": m["source"],
        "corpus": m["corpus"],
        "sourceUrl": m["source_url"],
        "sourceVersion": source_version,
        "licence": m["licence"],
        "attribution": m["attribution"],
        "generationVersion": GEN_VERSION,
        "creationDate": retrieval_date,
        "retrievalDate": retrieval_date,
        "releaseNotes": notes,
    }
    # provenance record (a superset, human-readable)
    prov = dict(entry)
    prov["transformations"] = [
        "downloaded Tatoeba per-language sentence export (id<TAB>lang<TAB>text .tsv.bz2)",
        "bunzip2; kept column 3 (sentence text) only",
        "gen-ngrams.py: tokenise (letters + diacritics + apostrophe only, so URLs/emails/"
        "digits fragment away), hold out every 6th sentence for the disjoint test set, "
        "min-count 3, top-8 followers, caps per corpus size (see generation/README.md for "
        "the exact per-language command)",
    ] + ([
        "--stop: the dominant Tatoeba placeholder names (Tom/Mary and their local "
        "forms; the list is in generation/README.md) are excluded from n-grams so "
        "they do not dominate general predictions"
    ] if lang in STOP_LANGS else []) + ([DROPS[(lang, ver)]] if (lang, ver) in DROPS else []) + [
        "deterministic gzip (mtime=0, level 9, OS byte 0xFF)",
    ]
    with open(os.path.join(REPO, "provenance", f"{lang}_ngrams.v{ver}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{lang}: {fname} gz={len(gz)} (uncompressed {len(raw)}) sha={gz_sha[:12]}...")
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-date", default="2026-09-01")
    ap.add_argument("--source-version", default="Tatoeba export 2026-09-01")
    ap.add_argument("--check", action="store_true", help="verify gzip determinism + round-trip")
    # Every pack the manifest carries. The manifest is rewritten WHOLE from this
    # list, so a short list here silently unpublishes the packs it omits.
    ALL = ["de", "es", "fr", "en", "pl", "pt", "el", "it", "nl", "ru", "tr"]
    ap.add_argument("langs", nargs="*", default=ALL)
    a = ap.parse_args()
    langs = a.langs or ALL
    notes = {
        "de": "German next-word context (bigram+trigram) from Tatoeba example sentences.",
        "es": "Spanish next-word context (bigram+trigram) from Tatoeba example sentences.",
        "fr": "French next-word context (bigram+trigram) from Tatoeba example sentences.",
    }
    notes.setdefault("en", "English next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("pl", "Polish next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("pt", "Portuguese next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("el", "Greek next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("it", "Italian next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("nl", "Dutch next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("ru", "Russian next-word context (bigram+trigram) from Tatoeba example sentences.")
    notes.setdefault("tr", "Turkish next-word context (bigram+trigram) from Tatoeba example sentences.")
    # Packs retrieved outside the original batch carry their own dates, so
    # rebuilding does not relabel the existing entries.
    retrieved = {"pt": "2026-09-05", "el": "2026-09-18", "it": "2026-09-20", "nl": "2026-09-18", "ru": "2026-09-18", "tr": "2026-09-18"}
    versions = {"pt": "Tatoeba export 2026-09-05", "el": "Tatoeba export 2026-09-18", "it": "Tatoeba export 2026-09-20",
                "nl": "Tatoeba export 2026-09-18", "ru": "Tatoeba export 2026-09-18", "tr": "Tatoeba export 2026-09-18"}
    packs = [build(l, retrieved.get(l, a.retrieval_date),
                   versions.get(l, a.source_version), notes[l], a.check) for l in langs]
    # English ships one physical pack served to BOTH regional ids: add an English (US)
    # manifest alias pointing at the same file/checksum so either variant can fetch it.
    extra = []
    for e in packs:
        if e["language"] == "English (UK)":
            us = dict(e); us["language"] = "English (US)"; extra.append(us)
    packs = packs + extra
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generated": a.retrieval_date,
        "packs": packs,
    }
    with open(os.path.join(REPO, "manifests", "ngram-manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"manifest: {len(packs)} packs -> manifests/ngram-manifest.json")


if __name__ == "__main__":
    main()
