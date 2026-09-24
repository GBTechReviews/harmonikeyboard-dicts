# Next-word packs v2: baseline, findings, the fix and its measurement

Date: 2026-09-24. Scope: this repository (the shared data) and the HKeyboard app (its
prediction code, pack installation and tests). HarmoniKeyboard's application code was
not touched. Nothing has been pushed.

## 1. Summary

- **The v1 generator kept the wrong half of every capped pack.** It sorted rows by the
  context's spelling and cut at the size cap, so German bigrams stop at "pferd", Spanish
  at "salvo", French after "o", and English trigrams at "for spring". The contexts it kept
  covered 61-79% of the bigram use and 18-37% of the trigram use in German, Spanish,
  French and Portuguese. v2 ranks contexts by how often they occur and keeps those.
- **Measured on held-out sentences through the app's own prediction code**, same
  training data for both generators: next-word top-1 accuracy rose **+38.5% relative in
  French, +33.0% German, +15.8% Spanish, +11.0% Portuguese, +10.9% English**, +5.4%
  Italian, +3.5% Russian, +1.9% Greek, +1.8% Turkish, +0.9% Dutch, and 0.0% Polish (never
  capped). Every change is positive with a 95% interval that excludes zero, or exactly
  zero. The v2 packs are also 1-7% smaller and use 5-35% less memory.
- **The 10% target is met for 5 of the 9 languages whose v1 pack was capped.** Italian,
  Russian, Turkish and Dutch are limited by their corpora: removing the cap entirely would
  take Italian to +23.6% and Russian to +16.3% but roughly doubles their size and memory
  (a product decision, section 7); Turkish and Dutch barely move even uncapped.
- **The old evaluation leaked.** 1.5-8.2% of the v1 method's "held-out" sentences were
  duplicates of training sentences, and 78.6% of today's Greek test set was inside the
  published Greek v1's training. The v2 split makes both impossible by construction.
- Data quality and records: 29 duplicate Azerbaijani words and 2 Urdu symbols removed
  (declared in manifest.json so apps that pin checksums keep working);
  provenance records for all 29 unrecorded datasets (marked UNVERIFIED, not cleared);
  Punjabi, Tamil and Kyrgyz lists expanded 43x / 11x / 9x from CC0 sentences (published
  as new `*_words.v2.txt` files beside the unchanged originals); a validator,
  a pack quality gate and CI; canonical locale tags; one-step rollback and corruption
  recovery in the app.

## 2. Baseline (before any change)

Repository audit (`generation/validate.py`, first run):

| finding | count / detail |
|---|---|
| word lists with no provenance record | 29 (am ar az bg cs de el es fa fi fr he hr hu id is it nl no pl pt ro ru sv tr uk ur vi + ur_roman) |
| duplicate entries | az_words.txt: 29 |
| non-word entries | ur_words.txt: U+060E and U+060F (poetic verse signs) |
| n-gram manifest `generated` date | 2026-09-01, older than its newest entry (2026-09-20) |
| ambiguous English entries | two `locale: "en"` records pointing at one file |
| generation command in pack provenance | missing in all 12 pack records |
| gen-tatoeba-words.py (named by 60+ provenance records) | not in this repository |
| repository LICENSE | none |
| working-copy hashes vs manifest | 4 mismatches, all CRLF conversion on Windows (published bytes correct) |
| capped v1 packs, where the cap cut | de bi "pferd"; es bi "salvo"; fr bi after "o"; pt bi "sapatos"; tr bi "sahsen"; en/de/es/fr/it/pt/ru/tr/nl trigrams |

App baseline (`NgramAbEvaluationTest`, column A; `NgramPackGateTest` on the bundled
packs): see section 5. Bundled pack heap at load: en 18.8 MB, it 14.7 MB, pl 3.5 MB,
el 1.4 MB; predict p99 under 15 us on the JVM.

## 3. Prioritised findings

1. **Capping kept alphabetically early contexts** (all capped packs; fixed, section 4).
2. **Evaluation leakage**: duplicates across the v1 train/test split (1.5% el, 3.8% de,
   8.2% it of held-out chunks) and published packs trained on later test sets (78.6% for
   Greek). Any number measured against a published v1 pack is optimistic. Fixed for v2
   (hash split over word tokens; a unit test proves it).
3. **The app's next-word lookup was locale-blind**: a Turkish capital I became i (a
   different word from the dotless one) and a dotted capital I became i + combining dot,
   a key no pack holds; a smart-quotes apostrophe never matched. Fixed in ContextModel.
4. **Learned-word corruption lost data**: an unreadable stored value loaded as empty and
   the next save overwrote it. Fixed (quarantine).
5. **A pack corrupted after install stayed "installed"** and the previous pack was deleted
   on every update, so a worse pack could not be undone. Fixed (one-step rollback, blocked
   version, recovery on load).
6. **29 distributed datasets have no confirmed licence** (probable CC BY-SA 4.0,
   OpenSubtitles-family). HKeyboard still downloads one of them for German
   (`de_words.txt`, the 50,000-word list) and bundles 900-word seeds of most. Recorded,
   not resolved: see section 7.
7. **Memory**: packs are parsed into nested hash maps; English costs 17-19 MB of heap in
   the keyboard process, Russian 18 MB. A compact representation would cut this several
   times. Not changed here (engine work, needs its own measurement).
8. **Undersized word lists** (under 450 words): gu, kn, te, pa, ta, ky, su. Three expanded;
   four have no licence-clean source found.
9. **The bundled English pack is not any published pack**: it is v1 with Tatoeba's
   Kabyle-corpus stock names struck by hand (2026-09-20). English v2 reproduces that edit
   in the generator (the names are in its stop list), so its bytes are fully reproducible.
10. Minor: stale manifest date; duplicate `en` records; CRLF checkouts; no root licence.

## 4. What changed

Dicts repository (local commits, unpushed):

| commit | what |
|---|---|
| de7654a | the uncommitted Italian v2 (--drop) work found in the tree, committed unchanged |
| 4d097bf | generator v2 + hktext.py + 32 tests; v1 generator kept in legacy/; languages.json; eval-ab.py; build-inputs.py; .gitattributes (LF) |
| 03a4319 | az duplicates, Urdu symbols removed (recorded in provenance) |
| 71d368c | validate.py; provenance for the 29; FORMATS.md (incl. ur_roman.txt); manifest.json canonical tags; LICENSE (MIT, software only) |
| 40e7b3f | gen-tatoeba-words.py + ThaiSegment.java vendored (strict decoding); CI workflow |
| 474fb02 | pa / ta / ky lists expanded with CC0 Common Voice sentences (moved to `*_words.v2.txt`, originals restored, in the commit after the packs) |
| (next) | manifest.json AZ / UR rows declaring the changed lists (HarmoniKeyboard pins checksums) |
| (this) | v2 packs, provenance, manifest, pack gate, CI, this report |

HKeyboard app (local commits, unpushed): d8ef8730 (ContextModel key normalisation,
the A/B scorer, strict word-list decoding), 8966862a (rollback / recovery), 8f4c2ed0
(learned-data quarantine), a89293f5 (bundled-pack gate).

Generator v2, in short: contexts ranked by training support, kept whole until the row cap
is spent, then sorted for a stable file; NFC; sentence ends in every shipped script;
every apostrophe variant folded; any-letter words with a script filter; Turkic casing;
strict UTF-8 (an undecodable line fails the build); streaming bz2 input; a train/test split
by a hash of the sentence's word tokens so duplicates share a side. The pack FORMAT is
unchanged, so every shipped app can load a v2 pack.

## 5. Measurement

**Method.** For each language, `eval-ab.py` splits one Tatoeba export into train and
test with the v2 split (1 in 6 sentences, by hash; duplicates share a side; a repeated
test sentence counted once). It trains, on the SAME train lines with the same caps and
stop list: **A** the v1 generator, **A2** v2 text handling with v1's cap (the ablation),
**B** v2. The official v2 pack is built separately from the whole export and checked
byte-identical to B; `build-inputs.py` rebuilt all eleven a second time, byte-identical.
HKeyboard's `NgramAbEvaluationTest` scores each pack through the app's real
`ContextModel.predict` (fresh install: no learned words; unigram fill from the app's word
list), on up to 100,000 held-out cases per language (whole sentences, every k-th).
Accuracy intervals are Wilson 95%; differences use a paired sentence-cluster bootstrap
(2,000 resamples, seeded), because cases from one sentence are not independent.
Keystrokes saved is next-word only: a word among the three bar slots saves its length.

**Results.** Top-1/3/5 and coverage in %, latency on the JVM (x86 desktop), heap = the
parsed pack's retained heap (approximate), size = deflate level 9 (the wire gzip is within
a few KB).

| lang | cases (chunks) | top-1 v1 -> v2 | rel. | 95% CI (pts) | top-3 v1 -> v2 | top-5 v1 -> v2 | MRR@5 v1 -> v2 | context cov. v1 -> v2 | trigram cov. v1 -> v2 | pack OOV v1 -> v2 | keystrokes saved v1 -> v2 | p50/p99 us v1 -> v2 | heap MB v1 -> v2 | KB v1 -> v2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fr | 95820 (15349) | 12.26 -> 16.98 | +38.5% | +4.72 [+4.53, +4.91] | 21.10 -> 28.84 | 26.94 -> 35.34 | 0.1739 -> 0.2362 | 64.1 -> 91.7 | 11.3 -> 35.0 | 17.2 -> 15.7 | 11.05 -> 15.54 | 0.7/2.6 -> 1.1/3.0 | 9.0 -> 5.9 | 265 -> 256 |
| de | 96120 (15250) | 9.23 -> 12.28 | +33.0% | +3.05 [+2.89, +3.22] | 17.49 -> 22.66 | 22.53 -> 28.40 | 0.1398 -> 0.1810 | 68.3 -> 90.9 | 9.9 -> 31.1 | 15.7 -> 16.0 | 10.38 -> 13.58 | 1.6/4.7 -> 1.1/3.6 | 8.7 -> 5.8 | 275 -> 256 |
| es | 90944 (15011) | 13.38 -> 15.49 | +15.8% | +2.11 [+1.95, +2.27] | 23.02 -> 26.57 | 28.83 -> 32.75 | 0.1887 -> 0.2172 | 78.6 -> 92.4 | 19.1 -> 33.2 | 18.8 -> 18.0 | 11.68 -> 13.57 | 0.9/2.7 -> 1.2/4.3 | 9.2 -> 6.6 | 257 -> 245 |
| pt | 93960 (13874) | 13.56 -> 15.06 | +11.0% | +1.49 [+1.34, +1.66] | 23.68 -> 26.76 | 29.41 -> 33.22 | 0.1926 -> 0.2162 | 78.5 -> 92.6 | 16.1 -> 32.9 | 17.9 -> 16.6 | 12.25 -> 14.36 | 0.9/2.5 -> 1.2/3.1 | 9.0 -> 6.4 | 257 -> 246 |
| en | 99410 (13917) | 17.79 -> 19.73 | +10.9% | +1.95 [+1.78, +2.11] | 29.90 -> 32.87 | 36.34 -> 39.58 | 0.2452 -> 0.2696 | 98.5 -> 98.5 | 15.7 -> 49.6 | 7.1 -> 7.0 | 17.07 -> 19.28 | 1.1/3.6 -> 1.4/3.6 | 22.8 -> 17.4 | 713 -> 692 |
| it | 97923 (19317) | 17.33 -> 18.27 | +5.4% | +0.94 [+0.80, +1.07] | 29.87 -> 31.62 | 36.13 -> 38.31 | 0.2420 -> 0.2559 | 97.0 -> 97.0 | 21.2 -> 42.4 | 12.4 -> 11.8 | 16.56 -> 17.90 | 1.1/3.5 -> 1.3/4.0 | 16.7 -> 12.9 | 490 -> 469 |
| ru | 95864 (20745) | 15.96 -> 16.52 | +3.5% | +0.56 [+0.45, +0.67] | 25.81 -> 27.09 | 30.85 -> 32.31 | 0.2141 -> 0.2232 | 94.3 -> 94.3 | 20.0 -> 38.2 | 15.4 -> 14.9 | 14.68 -> 15.58 | 1.3/4.1 -> 1.5/3.9 | 22.7 -> 18.2 | 780 -> 736 |
| tr | 83340 (19371) | 15.15 -> 15.42 | +1.8% | +0.27 [+0.20, +0.35] | 23.76 -> 24.24 | 27.87 -> 28.45 | 0.1986 -> 0.2026 | 87.5 -> 88.6 | 24.8 -> 29.9 | 23.0 -> 22.6 | 15.78 -> 16.18 | 1.3/3.1 -> 1.4/3.6 | 15.0 -> 14.1 | 449 -> 442 |
| el | 30894 (6497) | 14.90 -> 15.18 | +1.9% | +0.29 [+0.22, +0.36] | 24.42 -> 24.86 | 29.36 -> 29.89 | 0.2018 -> 0.2056 | 82.0 -> 82.3 | 26.2 -> 26.7 | 30.4 -> 30.1 | 14.07 -> 14.40 | 1.0/2.7 -> 1.0/2.6 | 1.7 -> 1.7 | 50 -> 50 |
| nl | 86670 (15300) | 16.57 -> 16.73 | +0.9% | +0.15 [+0.10, +0.21] | 27.86 -> 28.05 | 33.60 -> 33.75 | 0.2279 -> 0.2296 | 93.6 -> 93.6 | 44.9 -> 47.5 | 15.9 -> 15.9 | 15.87 -> 15.98 | 1.2/3.5 -> 1.2/3.6 | 6.7 -> 6.4 | 186 -> 184 |
| pl | 90681 (21059) | 14.28 -> 14.28 | +0.0% | +0.00 [+0.00, +0.00] | 22.54 -> 22.54 | 27.33 -> 27.33 | 0.1898 -> 0.1898 | 83.1 -> 83.1 | 24.1 -> 24.1 | 29.4 -> 29.4 | 12.49 -> 12.49 | 1.1/2.8 -> 1.1/3.3 | 4.2 -> 4.2 | 116 -> 116 |

Where the gain comes from (top-1, percentage points):

| lang | the cap alone (A2 -> B) [95% CI] | text handling alone (A -> A2) |
|---|---|---|
| fr | +4.68 [+4.49, +4.87] | +0.04 |
| de | +3.04 [+2.88, +3.21] | +0.01 |
| es | +2.06 [+1.91, +2.22] | +0.05 |
| pt | +1.49 [+1.34, +1.66] | +0.00 |
| en | +1.93 [+1.77, +2.09] | +0.02 |
| it | +0.80 [+0.66, +0.93] | +0.14 |
| ru | +0.56 [+0.45, +0.67] | -0.00 |
| tr | +0.24 [+0.17, +0.31] | +0.03 |
| el | +0.00 [+0.00, +0.00] | +0.29 |
| nl | +0.15 [+0.10, +0.20] | +0.00 |
| pl | +0.00 [+0.00, +0.00] | +0.00 |

The text-handling changes barely move these Tatoeba numbers because Tatoeba text is
clean; their value is correctness on real input (NFD text, smart apostrophes, Turkish
capitals), which the unit tests pin. In the app, the matching ContextModel change is what
lets a Turkish sentence-initial "Istanbul"/"IRMAK" find its pack entry at all.

**What removing the cap would buy** (same split, no row limit) - a size decision:

| lang | top-1 v1 / v2 / no cap | rel. v1 -> no cap | KB v2 -> no cap | heap MB v2 -> no cap |
|---|---|---|---|---|
| it | 17.33 / 18.27 / 21.42 | +23.6% | 469 -> 917 | 12.9 -> 31.7 |
| ru | 15.96 / 16.52 / 18.56 | +16.3% | 736 -> 1245 | 18.2 -> 37.1 |
| tr | 15.15 / 15.42 / 15.73 | +3.9% | 442 -> 521 | 14.1 -> 17.9 |
| nl | 16.57 / 16.73 / 16.86 | +1.7% | 184 -> 195 | 6.4 -> 7.0 |

**Why the published v1 packs score higher than the v1 generator here** (top-1: v1
generator on the same train / published v1 / v2): fr 12.26 / 12.86 / 16.98, de 9.23 / 9.84 /
12.28, es 13.38 / 14.40 / 15.49, pt 13.56 / 14.56 / 15.06, en 17.79 / 18.32 / 19.73,
it 17.33 / 18.16 / 18.27, ru 15.96 / 17.21 / 16.52, tr 15.15 / 16.79 / 15.42, el 14.90 /
17.86 / 15.18, nl 16.57 / 18.53 / 16.73, pl 14.28 / 16.78 / 14.28. The published packs
were built from older exports with the v1 split, so many of today's test sentences were in
their training: measured exactly for Greek (same export), **5,542 of 7,055 test sentences
(78.6%)**. Their numbers are not a fair baseline; the fair one is A.

**Leakage in the v1 method itself**: held-out chunks identical to a training chunk -
el 104 / 7,128 (1.5%), de 5,204 / 137,905 (3.8%), it 13,005 / 157,663 (8.2%). v2: 0 by
construction (tests/test_generation.py SplitTest).

**Other metrics.**
- *Out-of-vocabulary*: "pack OOV" above (next word never a follower in the pack) and, per
  language, the app word list's OOV on the same test: de 3.8%, en 1.0%, es 3.7%, fr 2.3%,
  it 1.7%, pt 1.8%, el 35.6%, nl 26.2%, pl 26.0%, ru 49.8%, tr 52.8% (the last five
  bundle 900-word seeds; their full lists are downloads).
- *Word lists expanded* (held-out token coverage on 1 in 6 Common Voice sentences):
  pa 37.0% -> 80.8% (178 -> 7,641 words), ta 8.2% -> 29.6% (299 -> 3,262), ky 31.5% ->
  68.4% (434 -> 3,974).
- *Latency*: v2 p99 rises by at most 1.6 us (more trigram hits); all under 5 us.
- *Peak memory*: parsed-pack heap falls in every capped language (table). On-device
  process memory was not measured (no device run this session).
- *Pack and application size*: the published download (gzip) of every pack is smaller -
  de 283,206 -> 262,699 bytes (-7.2%), es -4.9%, fr -3.6%, en 734,318 -> 712,469 (-3.0%),
  pl -0.3%, pt -4.4%, el -0.6%, it (v2 -> v3) -4.2%, nl -1.0%, ru 798,149 -> 754,544 (-5.5%),
  tr -1.6%. The APK is unchanged: the bundled packs were deliberately not replaced
  (section 6). (The KB column in the table above is a deflate estimate from the test.)
- *Autocorrection acceptance and reversal rates*: **not measurable, by design** - the app
  records nothing about what its users type or undo. The offline autocorrect calibrations
  that read ContextModel were re-run after the ContextModel change (section 6).

## 6. Compatibility, migration and rollback

- **Format**: unchanged (`#HKNGRAM v1 schema=1`); the header gains `gen=`, which both
  parsers ignore. Shipped HKeyboard (code 9+) and HarmoniKeyboard read v2 packs as-is.
- **Manifest**: stays `schemaVersion` 1 (shipped apps reject any other). Entries gain
  `packLocale`; `locale` becomes the canonical tag per entry (`en-GB`, `en-US`, `pt-BR`).
  Both apps look entries up by `language` and ignore unknown fields. English keeps one
  entry per keyboard id, now distinguishable.
- **Migration**: a user with v1 installed sees "Update" (v2 is a higher version); nothing
  updates by itself. v1 files stay published for the apps that bundle them.
- **Italian** is **v3**: an unpublished v2 (the --drop build) already existed; v3 carries
  both the --drop and the generator fix.
- **Bundled packs are NOT replaced in this change.** HKeyboard's autocorrect evaluation
  sets (eval v3/v4) were cut against the v1 split, so bundling v2 English/Italian/Polish/
  Greek before those sets are re-cut would train the context model on some of their test
  sentences and flatter the calibration. Bundling is its own stage.
- **Rollback**:
  - *Per device*: HKeyboard now keeps the previous pack; `NgramPackStore.rollback` restores
    it and blocks the version it left so it is never offered again; a pack found corrupt on
    load is replaced by the previous one or removed. (A settings button for rollback is not
    built yet.)
  - *Per publish*: a bad v2 is withdrawn by publishing v3 with v1's content (apps never
    downgrade to a lower number, and a published file is never rewritten).
  - *Per repo*: every change is a separate local commit; `git revert` of the pack commit
    restores the v1 manifest exactly.

## 7. Decisions for Rhys

1. **Push** the dicts repository (8 commits) - nothing reaches users until then.
2. **Bigger caps for Italian and Russian**: +16-24% top-1 for about double the size and
   memory. Recommendation: not now; revisit after a compact in-memory format (finding 7).
3. **The 29 unverified datasets**: keep serving (status quo), or stop serving the ones
   with a verified replacement (German's 50k download could use the Tatoeba-built list the
   app already bundles). Recommendation: switch German's download first.
4. **Adopt the expanded pa / ta / ky lists in the app** (bundled, seed-only). Needs an
   Indic-engine measurement and ideally a speaker check.
5. **Tamil**: add Common Voice's Wikisource text (coverage 29.6% -> 55.9%, literary
   register) or not.
6. **Root licence**: MIT for the scripts is a proposal; change it before pushing if wrong.

## 8. Release notes

The manifest's `releaseNotes` for each pack carries its measured change; in brief:

- **Next-word packs v2 (Italian v3)**: rebuilt with generator v2. Where a pack is size-
  capped, it now keeps the most frequent word contexts instead of the alphabetically
  first, so predictions after common words ("que", "se", "sie", "pas", "i am ...") appear
  where they were missing. Held-out top-1 accuracy: French +38.5%, German +33.0%, Spanish
  +15.8%, Portuguese +11.0%, English +10.9%, Italian +5.4%, Russian +3.5%, Greek +1.9%,
  Turkish +1.8%, Dutch +0.9%, Polish unchanged. Packs are slightly smaller. Built from the
  Tatoeba exports of 2026-09-24 (Greek 2026-09-18, Italian 2026-09-20).
- **Word lists**: Azerbaijani duplicates and two Urdu symbols removed; Punjabi, Tamil and
  Kyrgyz lists expanded with public-domain (CC0) Common Voice sentences.
