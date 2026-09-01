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
