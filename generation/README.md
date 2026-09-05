# Generating the next-word (n-gram) packs

Fully reproducible. Same inputs → byte-identical packs (verified: `build-ngram-packs.py --check`
and a second run produce identical SHA-256s).

## Source data

| Lang | Corpus | Download | Licence |
|------|--------|----------|---------|
| de | Tatoeba `deu_sentences` | https://downloads.tatoeba.org/exports/per_language/deu/deu_sentences.tsv.bz2 | CC BY 2.0 FR |
| es | Tatoeba `spa_sentences` | https://downloads.tatoeba.org/exports/per_language/spa/spa_sentences.tsv.bz2 | CC BY 2.0 FR |
| fr | Tatoeba `fra_sentences` | https://downloads.tatoeba.org/exports/per_language/fra/fra_sentences.tsv.bz2 | CC BY 2.0 FR |
| en | Tatoeba `eng_sentences` | https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2 | CC BY 2.0 FR |
| pl | Tatoeba `pol_sentences` | https://downloads.tatoeba.org/exports/per_language/pol/pol_sentences.tsv.bz2 | CC BY 2.0 FR |
| pt | Tatoeba `por_sentences` | https://downloads.tatoeba.org/exports/per_language/por/por_sentences.tsv.bz2 | CC BY 2.0 FR |

Portuguese (P14) was added for the Portuguese (Brazil) engine migration; `por_sentences` is
mixed pt-BR / pt-PT, which matches the shared word list both versions use. Retrieved 2026-09-05.

English and Polish (P13) replaced earlier Leipzig-derived packs whose commercial terms
could not be confirmed; all five packs are now Tatoeba. Retrieved 2026-09-01. Licence verified against the primary source (tatoeba.org/en/downloads:
"These files are released under CC BY 2.0 FR."). See `../licences/TATOEBA.txt`.

**The raw corpora are NOT committed** (size + they are re-downloadable). Only the
reproducible scripts, the derived packs and the provenance records live here.

### Why not the Leipzig Corpora Collection?

Leipzig was the preferred source, but as of 2026-09-01 its downloadable-corpus terms
could not be confirmed as commercial-safe from a primary source: the Wortschatz/Leipzig
download and terms pages are behind an Anubis bot-gate, and the InfAI project page directs
commercial users to negotiated ("auf Auftrag gerechnete") data delivery. Rather than guess,
these packs use Tatoeba (CC BY 2.0 FR, unambiguously commercial-safe and primary-source
verified). Leipzig can be substituted later if HKeyboard's owner confirms its exact terms -
the pipeline is identical.

## Steps

```bash
# 1. Download + decompress + keep only the sentence text column (col 3):
for L in deu spa fra; do
  curl -sO "https://downloads.tatoeba.org/exports/per_language/$L/${L}_sentences.tsv.bz2"
  bunzip2 -kf "${L}_sentences.tsv.bz2"
  cut -f3 "${L}_sentences.tsv" > "${L}_text.txt"
done

# 2. Build each NgramPack (deterministic; held-out test set is disjoint from training).
#    gen-ngrams.py is vendored here and is identical to the HKeyboard repo's scripts/.
export PYTHONUTF8=1
python gen-ngrams.py --lang de --source tatoeba-deu-2026-09-01 --letters "äöüß" \
  --holdout 6 --test-keep 400 --min-count 3 --max-bi 30000 --max-tri 25000 \
  --out input/de_ngrams.v1.txt --test de_ngrams_test.tsv deu_text.txt
python gen-ngrams.py --lang es --source tatoeba-spa-2026-09-01 --letters "áéíóúñü¿¡" \
  --holdout 6 --test-keep 400 --min-count 3 --max-bi 30000 --max-tri 25000 \
  --out input/es_ngrams.v1.txt --test es_ngrams_test.tsv spa_text.txt
python gen-ngrams.py --lang fr --source tatoeba-fra-2026-09-01 --letters "àâäçéèêëîïôûùüÿœæ" \
  --holdout 6 --test-keep 400 --min-count 3 --max-bi 30000 --max-tri 25000 \
  --out input/fr_ngrams.v1.txt --test fr_ngrams_test.tsv fra_text.txt
# English: bigger corpus (~2M sentences) -> larger caps (scaled to corpus size); the
# --stop filter drops Tatoeba's dominant placeholder names (Tom/Mary).
python gen-ngrams.py --lang en --source tatoeba-eng-2026-09-01 --stop "tom,mary" \
  --holdout 6 --test-keep 400 --min-count 3 --max-bi 90000 --max-tri 75000 \
  --out input/en_ngrams.v1.txt --test en_ngrams_test.tsv eng_text.txt
python gen-ngrams.py --lang pl --source tatoeba-pol-2026-09-01 --letters "ąćęłńóśźż" --stop "tom,mary" \
  --holdout 6 --test-keep 40 --min-count 3 --max-bi 30000 --max-tri 25000 \
  --out input/pl_ngrams.v1.txt --test pl_ngrams_test.tsv pol_text.txt
# Portuguese: es/fr/de-scale corpus (444,157 sentences), so the same caps. Tatoeba's
# Portuguese is translated from the English set, so Tom/Mary dominate it too - "tom" is
# also the ordinary noun for "tone", which therefore loses its independent attestation
# and falls to frequency-only authority. That is the accepted trade, as it is for English.
python gen-ngrams.py --lang pt --source tatoeba-por-2026-09-05 --letters "áàâãéêíóôõúüç" --stop "tom,mary" \
  --holdout 6 --test-keep 400 --min-count 3 --max-bi 30000 --max-tri 25000 \
  --out input/pt_ngrams.v1.txt --test pt_ngrams_test.tsv por_text.txt

# 3. Deterministic gzip + manifest + provenance. The lang list is the WHOLE manifest:
#    build-ngram-packs.py rewrites manifests/ngram-manifest.json from exactly these,
#    so omitting one unpublishes it. Its default is now every pack, for that reason.
python build-ngram-packs.py --check de es fr en pl pt
```

The English + Polish `.v1` packs are ALSO bundled in the app (gzipped) as the offline
fallback for those languages; the app's copy is byte-identical to the pack here.

## Filtering / policy

- Tokeniser keeps only lowercase letters (a-z + the language's diacritics) and the
  apostrophe, so URLs, email addresses, digits and most corpus artefacts fragment away
  and never become tokens. Valid accents/language characters are preserved.
- `--min-count 3` is a deterministic frequency threshold: a context+follower seen fewer
  than 3 times is dropped (drops one-off name pairs and noise).
- `--max-bi 30000 --max-tri 25000` cap the pack; the most frequent contexts are kept, so
  the download stays practical (~270KB gzipped).
- No offensive-word filtering is applied to the context packs: they are frequency data
  over ordinary sentences, and blocklisting there would silently degrade legitimate
  language support. Offensive-word handling stays in the app's own Offensive.kt, which
  governs what is SUGGESTED, not what the corpus contains.

## Versioning

Pack filenames are immutable and versioned (`de_ngrams.v1.txt.gz`). A changed pack MUST
get a new version (v2) and a new checksum; `build-ngram-packs.py` refuses to overwrite an
existing published `.gz` with different bytes.
