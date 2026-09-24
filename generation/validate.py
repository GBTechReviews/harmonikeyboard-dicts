#!/usr/bin/env python3
# validate.py - the repository's gate. Run from anywhere:  python generation/validate.py
# Exit status 0 = every check passed; 1 = at least one FAIL (each is printed).
# WARN lines are printed but do not fail (known, recorded, owner-decision items).
#
# WHAT IT CHECKS
#   word lists (<code>_words.txt)  strict UTF-8, no BOM, LF only, NFC, no blank or padded
#                                  lines, no duplicates, every entry a word (letters,
#                                  combining marks, and the joiners apostrophe / hyphen /
#                                  middle dot / modifier letters - no symbols, digits or
#                                  punctuation), a provenance record naming its SHA-256
#   ur_roman.txt                   the three-column format (FORMATS.md): ASCII key that
#                                  is its own consonant skeleton, Urdu word, positive
#                                  integer frequency; sorted by key; no duplicate pair
#   manifest.json                  every word-list entry's URL, SHA-256 and size floor
#   manifests/ngram-manifest.json  schema, a generation date no older than any entry,
#                                  canonical BCP 47 tags, aliases, every file present with
#                                  the declared size and SHA-256 (compressed and not), a
#                                  valid pack header whose body checksum holds, a
#                                  provenance record that agrees, and immutable
#                                  versioned file names
#   provenance/*.json              every record points at a file that exists and whose
#                                  SHA-256 it names; a verified licence or an explicit
#                                  UNVERIFIED status
# Hashes are taken over the file as git stores it (LF), so a Windows checkout with
# CRLF conversion does not produce false failures - .gitattributes pins LF anyway.
import gzip
import hashlib
import json
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []
WARNS = []

# joiners a word may carry between letters
JOINERS = {"'", "-", chr(0x00B7), chr(0x2019), chr(0x02BC), chr(0x02BB)}
BCP47 = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$")
PACK_FILE = re.compile(r"^([a-z]{2,3})_ngrams\.v([0-9]+)\.txt\.gz$")
RAW_BASE = "https://raw.githubusercontent.com/GBTechReviews/harmonikeyboard-dicts/"


def fail(msg):
    FAILS.append(msg)


def warn(msg):
    WARNS.append(msg)


def lf_bytes(path):
    with open(path, "rb") as f:
        b = f.read()
    return b.replace(b"\r\n", b"\n")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def is_word(w):
    if not w:
        return False
    for i, ch in enumerate(w):
        cat = unicodedata.category(ch)
        if cat[0] in "LM":
            continue
        if ch in JOINERS and 0 < i < len(w) - 1:
            continue
        if ch in ("'", chr(0x2019)) and len(w) > 1:
            continue   # Afrikaans 'n, elided heads kept as the source wrote them
        return False
    return True


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        fail("%s: not valid JSON (%s)" % (os.path.relpath(path, REPO), e))
        return None


def provenance_index():
    idx = {}
    pdir = os.path.join(REPO, "provenance")
    for name in sorted(os.listdir(pdir)):
        if not name.endswith(".json"):
            continue
        rec = load_json(os.path.join(pdir, name))
        if rec is None:
            continue
        f = rec.get("file") or rec.get("dataset")
        if not f:
            fail("provenance/%s: names no file" % name)
            continue
        idx.setdefault(f, []).append((name, rec))
    return idx


def check_word_lists(prov):
    for name in sorted(os.listdir(REPO)):
        if not (name.endswith("_words.txt") or re.search(r"_words\.v[0-9]+\.txt$", name)):
            continue
        path = os.path.join(REPO, name)
        with open(path, "rb") as f:
            raw = f.read()
        b = raw.replace(b"\r\n", b"\n")
        if b.startswith(b"\xef\xbb\xbf"):
            fail("%s: starts with a BOM" % name)
        try:
            text = b.decode("utf-8")
        except UnicodeDecodeError as e:
            fail("%s: not valid UTF-8 (%s)" % (name, e))
            continue
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        else:
            warn("%s: no final newline" % name)
        seen = {}
        bad = []
        for i, w in enumerate(lines, 1):
            if w == "":
                fail("%s:%d: blank line" % (name, i))
                continue
            if w != w.strip():
                fail("%s:%d: leading/trailing whitespace" % (name, i))
            if unicodedata.normalize("NFC", w) != w:
                fail("%s:%d: not NFC" % (name, i))
            if w in seen:
                fail("%s:%d: duplicate of line %d" % (name, i, seen[w]))
            else:
                seen[w] = i
            if not is_word(w):
                bad.append((i, w))
        for i, w in bad[:10]:
            fail("%s:%d: not a word (%s)" % (name, i, ascii(w)))
        recs = prov.get(name, [])
        if not recs:
            fail("%s: no provenance record" % name)
        else:
            h = sha(b)
            if not any(r.get("sha256") == h for _, r in recs):
                fail("%s: no provenance record names its SHA-256 %s" % (name, h[:12]))


def roman_skeleton(s):
    vowels = "aeiouyw"
    if not s:
        return ""
    first = s[0].lower()
    out = ["a" if first in vowels else first]
    for ch in s[1:]:
        c = ch.lower()
        if c in vowels or c == out[-1]:
            continue
        out.append(c)
    return "".join(out)


def check_ur_roman(prov):
    name = "ur_roman.txt"
    path = os.path.join(REPO, name)
    if not os.path.isfile(path):
        return
    b = lf_bytes(path)
    text = b.decode("utf-8")
    prev = ""
    pairs = set()
    for i, line in enumerate(text.split("\n"), 1):
        if line == "":
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            fail("%s:%d: %d columns, expected 3 (key, word, frequency)" % (name, i, len(cols)))
            continue
        key, word, freq = cols
        if not re.fullmatch(r"[a-z]+", key):
            fail("%s:%d: key is not lowercase a-z" % (name, i))
        elif roman_skeleton(key) != key:
            fail("%s:%d: key is not its own skeleton" % (name, i))
        if not word or not all(unicodedata.category(c)[0] in "LM" for c in word):
            fail("%s:%d: word is not letters" % (name, i))
        if not freq.isdigit() or int(freq) <= 0:
            fail("%s:%d: frequency is not a positive integer" % (name, i))
        if key < prev:
            fail("%s:%d: not sorted by key" % (name, i))
        prev = key
        if (key, word) in pairs:
            fail("%s:%d: duplicate key/word pair" % (name, i))
        pairs.add((key, word))
    if not prov.get(name):
        fail("%s: no provenance record" % name)


def check_dict_manifest():
    m = load_json(os.path.join(REPO, "manifest.json"))
    if m is None:
        return
    for code, e in sorted(m.get("dicts", {}).items()):
        url = e.get("url", "")
        if not url.startswith(RAW_BASE):
            fail("manifest.json %s: url not on the pinned host" % code)
            continue
        fname = url.rsplit("/", 1)[1]
        path = os.path.join(REPO, fname)
        if not os.path.isfile(path):
            fail("manifest.json %s: %s missing" % (code, fname))
            continue
        b = lf_bytes(path)
        if sha(b) != e.get("sha256"):
            fail("manifest.json %s: sha256 does not match %s" % (code, fname))
        if len(b) < e.get("minBytes", 0):
            fail("manifest.json %s: %s is smaller than minBytes" % (code, fname))
        if not BCP47.match(e.get("tag", "")):
            fail("manifest.json %s: no canonical BCP 47 tag" % code)


# The packs are compressed by the builder's Python, whose zlib is zlib-ng (CPython 3.14 for
# Windows). Deflate output is only byte-stable for ONE compressor implementation: the same
# content through stock zlib (the Linux CI runner's Python) gives different, equally valid
# bytes. So the byte-for-byte rebuild check runs where the compressor matches; everywhere
# else the gzip header is checked field by field and the content by its checksums.
BUILD_ZLIB = "1.3.1.zlib-ng"
NOTES = []


def same_compressor():
    import zlib
    return zlib.ZLIB_RUNTIME_VERSION == BUILD_ZLIB


def gzip_header_ok(gz):
    # magic, deflate, no flags (no file name), mtime 0, XFL 2 (level 9), OS byte 0xFF
    return (len(gz) > 18 and gz[:4] == bytes([0x1F, 0x8B, 8, 0]) and gz[4:8] == bytes(4)
            and gz[8] == 2 and gz[9] == 0xFF)


def regzip(data):
    # build-ngram-packs.py's deterministic_gzip, restated so the gate needs no import
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
        g.write(data)
    out = bytearray(buf.getvalue())
    out[9] = 0xFF
    return bytes(out)


def check_pack_body(name, raw):
    text = raw.decode("utf-8")
    header, _, body = text.partition("\n")
    toks = dict(t.split("=", 1) for t in header.split()[1:] if "=" in t)
    if not header.startswith("#HKNGRAM") or toks.get("schema") != "1":
        fail("%s: bad pack header" % name)
        return None
    if sha(body.encode("utf-8")) != toks.get("sha256"):
        fail("%s: body checksum does not match its header" % name)
    nb = sum(1 for l in body.split("\n") if l.startswith("b\t"))
    nt = sum(1 for l in body.split("\n") if l.startswith("t\t"))
    if str(nb) != toks.get("bigrams") or str(nt) != toks.get("trigrams"):
        fail("%s: header row counts disagree with the body" % name)
    if unicodedata.normalize("NFC", body) != body:
        warn("%s: body is not NFC" % name)
    return toks


def check_ngram_manifest(prov):
    path = os.path.join(REPO, "manifests", "ngram-manifest.json")
    m = load_json(path)
    if m is None:
        return
    if m.get("schemaVersion") != 1:
        fail("ngram-manifest: schemaVersion must stay 1 (shipped apps reject anything else)")
    packs = m.get("packs", [])
    dates = [p.get("creationDate", "") for p in packs]
    if dates and m.get("generated", "") < max(dates):
        fail("ngram-manifest: generated %s is older than its newest entry %s" % (m.get("generated"), max(dates)))
    seen_versions = {}
    for p in packs:
        lang = p.get("language", "?")
        f = p.get("file", "")
        mm = PACK_FILE.match(f)
        if not mm:
            fail("ngram-manifest %s: file name %s is not <code>_ngrams.v<N>.txt.gz" % (lang, f))
            continue
        if int(mm.group(2)) != p.get("packVersion"):
            fail("ngram-manifest %s: packVersion %s does not match %s" % (lang, p.get("packVersion"), f))
        tag = p.get("localeTag") or p.get("locale", "")
        if not BCP47.match(tag):
            fail("ngram-manifest %s: locale tag %r is not canonical BCP 47" % (lang, tag))
        key = (lang, p.get("packVersion"))
        if key in seen_versions and seen_versions[key] != f:
            fail("ngram-manifest %s: version %s listed with two files" % key)
        seen_versions[key] = f
        path = os.path.join(REPO, "packs", f)
        if not os.path.isfile(path):
            fail("ngram-manifest %s: packs/%s missing" % (lang, f))
            continue
        with open(path, "rb") as fh:
            gz = fh.read()
        if len(gz) != p.get("fileSize"):
            fail("ngram-manifest %s: fileSize %s != %d" % (lang, p.get("fileSize"), len(gz)))
        if sha(gz) != p.get("sha256"):
            fail("ngram-manifest %s: sha256 does not match packs/%s" % (lang, f))
        try:
            raw = gzip.decompress(gz)
        except Exception as e:  # noqa: BLE001
            fail("ngram-manifest %s: packs/%s does not decompress (%s)" % (lang, f, e))
            continue
        if not gzip_header_ok(gz):
            fail("ngram-manifest %s: packs/%s gzip header is not the deterministic one "
                 "(no name, mtime 0, level 9, OS 0xFF)" % (lang, f))
        if same_compressor() and regzip(raw) != gz:
            fail("ngram-manifest %s: packs/%s is not the deterministic gzip of its content "
                 "(mtime 0, level 9, OS 0xFF) - it cannot be rebuilt byte for byte" % (lang, f))
        if len(raw) != p.get("uncompressedSize"):
            fail("ngram-manifest %s: uncompressedSize mismatch" % lang)
        if sha(raw) != p.get("uncompressedSha256"):
            fail("ngram-manifest %s: uncompressedSha256 mismatch" % lang)
        check_pack_body("packs/" + f, raw)
        for url_field in ("sourceUrl",):
            if not str(p.get(url_field, "")).startswith("https://"):
                fail("ngram-manifest %s: %s is not https" % (lang, url_field))
        recs = prov.get(f, [])
        if not recs:
            fail("ngram-manifest %s: no provenance record for %s" % (lang, f))
        elif not any(r.get("sha256") == p.get("sha256") for _, r in recs):
            fail("ngram-manifest %s: provenance for %s names a different sha256" % (lang, f))
        if p.get("licence", "") in ("", "UNKNOWN"):
            fail("ngram-manifest %s: no licence" % lang)
    # every pack file on disk is either listed or deliberately retained (older version)
    # entries sharing one file are ALIASES: they must agree on the pack's own locale
    # and each carry a distinct, region-qualified tag (no two plain "en" records)
    by_file = {}
    for p in packs:
        by_file.setdefault(p.get("file"), []).append(p)
    for f, group in sorted(by_file.items()):
        if len(group) < 2:
            continue
        tags = [p.get("locale", "") for p in group]
        if len(set(tags)) != len(tags):
            fail("ngram-manifest: %s is listed under the same locale tag twice (%s)" % (f, ", ".join(tags)))
        if len({p.get("packLocale", "") for p in group}) != 1 or not group[0].get("packLocale"):
            fail("ngram-manifest: the aliases of %s do not name one packLocale" % f)
    listed = {p.get("file") for p in packs}
    for name in sorted(os.listdir(os.path.join(REPO, "packs"))):
        if name not in listed:
            mm = PACK_FILE.match(name)
            if not mm:
                fail("packs/%s: not a versioned pack name" % name)
            elif not prov.get(name):
                fail("packs/%s: retained but has no provenance record" % name)


def check_provenance(prov):
    for f, recs in sorted(prov.items()):
        for name, rec in recs:
            path = os.path.join(REPO, "packs", f) if f.endswith(".gz") else os.path.join(REPO, f)
            if not os.path.isfile(path):
                fail("provenance/%s: %s does not exist" % (name, f))
                continue
            lic = str(rec.get("licence", ""))
            if not lic:
                fail("provenance/%s: no licence" % name)
            if lic.strip().upper().startswith("MIT"):
                fail("provenance/%s: a data file must not be MIT (LICENSE covers scripts only)" % name)
            if rec.get("verification") == "UNVERIFIED" and not lic.startswith("UNLICENSED"):
                fail("provenance/%s: an unverified dataset must be marked UNLICENSED" % name)
            status = rec.get("verification", "VERIFIED" if rec.get("licence") not in (None, "", "UNKNOWN") else "")
            if status not in ("VERIFIED", "UNVERIFIED"):
                fail("provenance/%s: no licence and no verification status" % name)
            if status == "UNVERIFIED":
                warn("provenance/%s: %s redistribution rights NOT confirmed (%s)"
                     % (name, f, rec.get("recommendation", "no recommendation")))


def check_data_licences():
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(REPO, "generation", "data-licences.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode:
        fail((r.stdout.strip() or "DATA_LICENSES.md check failed").replace("FAIL ", "", 1))


def main():
    prov = provenance_index()
    check_data_licences()
    check_word_lists(prov)
    check_ur_roman(prov)
    check_dict_manifest()
    check_ngram_manifest(prov)
    check_provenance(prov)
    if not same_compressor():
        import zlib
        NOTES.append("zlib %s is not the packs' builder (%s): the byte-for-byte gzip rebuild check "
                     "was skipped; headers and content checksums were checked" % (zlib.ZLIB_RUNTIME_VERSION, BUILD_ZLIB))
    for n in NOTES:
        print("NOTE", n)
    for w in WARNS:
        print("WARN", w)
    for f in FAILS:
        print("FAIL", f)
    print("%d FAIL, %d WARN" % (len(FAILS), len(WARNS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
