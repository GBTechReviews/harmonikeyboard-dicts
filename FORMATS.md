# File formats

All text files are UTF-8 without a byte-order mark, Unicode NFC, LF line endings.
`generation/validate.py` enforces every rule below; CI runs it on every push.

## `<code>_words.txt` - word lists

One word per line, most frequent first (the ORDER is meaning: HKeyboard's correctors
break ties by line index). No blank lines, no duplicates, no surrounding whitespace.
An entry is letters and combining marks, optionally joined by an apostrophe, hyphen,
middle dot (Catalan `l·l`) or a modifier letter (Uzbek okina); digits, symbols and
punctuation are not words. Case is as the source wrote it (German keeps noun capitals).
Every list has a provenance record naming its SHA-256 (`provenance/<code>_words.v1.json`
for lists built by `generation/gen-tatoeba-words.py`, `provenance/<code>_words.legacy.json`
for the historical uploads whose source was never recorded).

## `ur_roman.txt` - Roman Urdu transliteration index

Three tab-separated columns, sorted by the first:

| column | content | rule |
|---|---|---|
| 1 | consonant skeleton key | lowercase `a-z`; it is its own skeleton (below) |
| 2 | Urdu word | Arabic-script letters and combining marks |
| 3 | frequency | positive integer; larger = more frequent |

A key may carry many words (one row each); a (key, word) pair appears once.
The skeleton of a romanised word is: lowercase it; keep the first letter (a vowel there
becomes `a`); drop every later `a e i o u y w`; collapse a letter repeated in a row.
`mein`, `mei` and `mai` all give `mn`/`m` families, so any spelling a typist uses meets
the same row. HKeyboard's `RomanUrdu.skeleton` is the same function (RomanUrduTest pins
that every key is its own skeleton). The file is sorted by key so a reader can binary
search it; HKeyboard reads it whole into a map.

## `packs/<code>_ngrams.v<N>.txt.gz` - next-word packs

Deterministic gzip (mtime 0, level 9, OS byte 0xFF) of a UTF-8 text file:

```
#HKNGRAM v1 lang=<code> schema=1 sha256=<hex of body> bigrams=<n> trigrams=<n> source=<token> [gen=<generator>]
b<TAB>prev<TAB>next<TAB>count
t<TAB>prev2<TAB>prev1<TAB>next<TAB>count
```

Words are lowercase by the language's rule (Turkic `I` -> dotless `ı`), NFC, with a
plain apostrophe. The header's `sha256` covers the body only. `v1` in the header is the
FORMAT version and has not changed; `v<N>` in the file name is the PACK version. A
published pack file is immutable: changed content gets the next version number.

## `manifests/ngram-manifest.json`

`schemaVersion` 1 (shipped apps refuse any other). One entry per keyboard language id
(`language`, the key both apps look up), with `locale` the canonical BCP 47 tag for that
entry (`en-GB`, `pt-BR`), `packLocale` the language the pack FILE was built for (`en`),
the pack version, compatibility gates (`minEngineVersion`, `minAppVersion`), the file
name, both sizes and SHA-256s, source, licence, attribution, dates and release notes.
Several entries may point at one file (English (UK) and English (US) share the `en`
pack); unknown fields are ignored by both apps, so fields can be added, never removed.
`generated` is the date the manifest was last built and is never older than an entry.

## `manifest.json` - word-list manifest (v2)

`{version: 2, dicts: {CODE: {url, sha256, minBytes, version, tag}}}`. `CODE` is the
keyboard's pill code and is kept for the apps that read it; `tag` is the canonical
BCP 47 tag (`RS` is `sr-Latn-RS`, `SR` is `sr-Cyrl-RS`). `sha256` is over the file as
stored (LF). `minBytes` is a refusal floor, well under the real size.
