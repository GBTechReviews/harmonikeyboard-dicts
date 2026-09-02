# harmonikeyboard-dicts

Downloadable data for **HKeyboard** (HProductions). Everything here is fetched only when
the user explicitly asks for it, over plain HTTPS from this repo's `raw.githubusercontent.com`
URLs. Nothing is ever uploaded by the app.

## Layout

```
<lang>_words.txt          Full word lists (Settings > Languages > Word lists). Flat, historical.
manifest.json            Word-list download manifest (v2) used by the word-list feature.

packs/                   Optional NEXT-WORD (n-gram) context packs, gzipped + versioned.
  de_ngrams.v1.txt.gz    German  (Tatoeba, CC BY 2.0 FR)
  es_ngrams.v1.txt.gz    Spanish (Tatoeba, CC BY 2.0 FR)
  fr_ngrams.v1.txt.gz    French  (Tatoeba, CC BY 2.0 FR)
  en_ngrams.v1.txt.gz    English (Tatoeba, CC BY 2.0 FR) - also bundled in-app
  pl_ngrams.v1.txt.gz    Polish  (Tatoeba, CC BY 2.0 FR) - also bundled in-app
                         (en/pl replaced earlier Leipzig-derived packs in P13)
manifests/
  ngram-manifest.json    The n-gram pack manifest HKeyboard's PackDownloadManager reads.
provenance/              One record per pack: source, licence, checksums, transformations.
licences/                Data-source licence notices + required attribution.
generation/              Reproducible generation scripts (gen-ngrams.py + build-ngram-packs.py).
```

## Next-word packs (added P12)

- **Licence: CC BY 2.0 FR**, derived from Tatoeba example sentences (attribution-only,
  commercial-safe, no share-alike). Attribution + provenance in `licences/` and `provenance/`.
- **Reproducible**: same corpus in → byte-identical pack out. See `generation/README.md`.
- **Immutable filenames**: a changed pack gets a new version (`v2`) and checksum; a published
  filename is never silently replaced.
- The manifest carries schema + engine + app-compat versions, sizes, SHA-256, source URL +
  version, licence, attribution, generation command and dates. The app verifies the SHA-256
  before install, keeps the previous pack until the new one validates, and falls back to its
  bundled dictionary if the manifest/network/pack is unavailable.

## Word-list provenance (open item, unchanged by P12)

The historical `<lang>_words.txt` files have no recorded upstream source or licence in this
repo. That is a pre-existing item to resolve separately; the P12 work above does not depend
on it and does not modify those files.

## Batch 2 word lists (added 2026-09-02) - built from Tatoeba, CC BY 2.0 FR

Sixteen NEW word lists are not historical uploads: each is BUILT from the Tatoeba per-language
sentence export by HKeyboard's `scripts/gen-tatoeba-words.py` (the exact command is in the
language's `provenance/<code>_words.v1.json`, with the source export's SHA-256). Licence
CC BY 2.0 FR (see `licences/TATOEBA.txt`); attribution-only, commercial-safe.

| file | language | Tatoeba corpus | words | in the app |
|---|---|---|---|---|
| `da_words.txt` | Danish | dan_sentences | 8729 | top 900 bundled, full list downloadable |
| `sk_words.txt` | Slovak | slk_sentences | 6355 | top 900 bundled, full list downloadable |
| `sl_words.txt` | Slovenian | slv_sentences | 1060 | whole list bundled, no download (seed-only) |
| `et_words.txt` | Estonian | est_sentences | 1460 | whole list bundled, no download (seed-only) |
| `lt_words.txt` | Lithuanian | lit_sentences | 19887 | top 900 bundled, full list downloadable |
| `ca_words.txt` | Catalan | cat_sentences | 2944 | top 900 bundled, full list downloadable |
| `gl_words.txt` | Galician | glg_sentences | 2788 | top 900 bundled, full list downloadable |
| `eu_words.txt` | Basque | eus_sentences | 1665 | whole list bundled, no download (seed-only) |
| `af_words.txt` | Afrikaans | afr_sentences | 1077 | whole list bundled, no download (seed-only) |
| `sw_words.txt` | Swahili | swh_sentences | 1873 | whole list bundled, no download (seed-only) |
| `tl_words.txt` | Filipino | tgl_sentences | 10867 | top 900 bundled, full list downloadable |
| `ms_words.txt` | Malay | zsm_sentences | 1981 | top 900 bundled, full list downloadable |
| `eo_words.txt` | Esperanto | epo_sentences | 57102 | top 900 bundled, full list downloadable |
| `br_words.txt` | Breton | bre_sentences | 1715 | whole list bundled, no download (seed-only) |
| `mk_words.txt` | Macedonian | mkd_sentences | 10070 | top 900 bundled, full list downloadable |
| `be_words.txt` | Belarusian | bel_sentences | 3954 | top 900 bundled, full list downloadable |

## Batch 4 word lists (added 2026-09-02) - Gboard's popular languages, built from Tatoeba, CC BY 2.0 FR

Twelve more lists built the same way as Batch 2 (`scripts/gen-tatoeba-words.py`, exact command and
source SHA-256 in `provenance/<code>_words.v1.json`). Serbian ships as TWO lists split from Tatoeba's
mixed-script Serbian corpus by the tokeniser's script filter (`sr` Cyrillic, `srl` Latin).

| file | language | Tatoeba corpus | words | in the app |
|---|---|---|---|---|
| `sr_words.txt` | Serbian (Cyrillic) | srp_sentences | 5349 | top 900 bundled, full list downloadable |
| `kk_words.txt` | Kazakh | kaz_sentences | 1867 | whole list bundled, no download (seed-only) |
| `tt_words.txt` | Tatar | tat_sentences | 13368 | top 900 bundled, full list downloadable |
| `mn_words.txt` | Mongolian | mon_sentences | 820 | whole list bundled, no download (seed-only) |
| `hy_words.txt` | Armenian | hye_sentences | 6625 | top 900 bundled, full list downloadable |
| `ka_words.txt` | Georgian | kat_sentences | 1632 | whole list bundled, no download (seed-only) |
| `srl_words.txt` | Serbian (Latin) | srp_sentences | 5000 | top 900 bundled, full list downloadable |
| `lv_words.txt` | Latvian | lvs_sentences | 4552 | top 900 bundled, full list downloadable |
| `tk_words.txt` | Turkmen | tuk_sentences | 1880 | whole list bundled, no download (seed-only) |
| `sq_words.txt` | Albanian | sqi_sentences | 755 | whole list bundled, no download (seed-only) |
| `ha_words.txt` | Hausa | hau_sentences | 4493 | top 900 bundled, full list downloadable |
| `ku_words.txt` | Kurdish | kmr_sentences | 2264 | top 900 bundled, full list downloadable |
