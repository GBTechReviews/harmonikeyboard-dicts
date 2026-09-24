# Candidate packs (not published)

`candidates/` holds next-word packs that are **kept for a decision, not offered**. Nothing
there is in `manifests/ngram-manifest.json`, and no app reads the folder. Each pack has its
record beside it (`candidates/<file>.json`: source, SHA-256s, the exact command, the caps
it kept). Licence: the source's - Tatoeba, CC BY 2.0 FR (`DATA_LICENSES.md`).

Owner's decision, 2026-09-24: *"Keep the current Italian and Russian pack sizes for now.
Preserve the larger versions as optional candidates and benchmark them on a real mid-range
phone before deciding. Compare top-3 accuracy, coverage, p95 latency and peak memory."*

## What they are

| candidate | based on | the one difference |
|---|---|---|
| `it_ngrams.uncapped.v3.txt.gz` (943,541 bytes) | `packs/it_ngrams.v3.txt.gz` (480 KB) | trigram rows 50,000 -> 131,774 (every eligible row; the bigram table was never capped) |
| `ru_ngrams.uncapped.v2.txt.gz` (1,275,089 bytes) | `packs/ru_ngrams.v2.txt.gz` (755 KB) | bigram rows capped -> 66,184, trigram rows -> 132,095 |

Same corpus (checked by SHA-256 against the published pack's build record), generator,
settings and held-out split (the held-out sample's SHA-256 is checked too). Rebuild,
byte-identical: `python generation/build-candidates.py --corpora <dir> it ru`.

## Measured so far

**Accuracy, desktop JVM, 98k / 96k held-out cases** (HKeyboard's NgramAbEvaluationTest,
through the app's own ContextModel; `reports/2026-09-24-generator-v2.md`):

| | top-1 | top-3 | trigram coverage | parsed heap |
|---|---|---|---|---|
| it published v3 | 18.27% | 31.62% | 42.4% | 12.9 MB |
| it candidate | 21.42% | 34.80% | 58.5% | 31.7 MB |
| ru published v2 | 16.52% | 27.09% | 38.2% | 18.2 MB |
| ru candidate | 18.56% | 29.05% | 49.2% | 37.1 MB |

Bigram (context) coverage is identical - the candidate adds trigram depth, not contexts.

**The device benchmark, run once on the x86 emulator to prove the pipeline** (Pixel 5 AVD,
Android 11, 192 MB heap limit; each pack in its own fresh process, three rounds - the
rounds agree to within a few percent). An emulator is NOT the mid-range phone the decision
asked for; its latency and memory are indicative only. Accuracy on the published held-out
sample (1,853 / 2,050 cases) matches the desktop direction exactly:

| | top-3 | trigram coverage | load | retained heap | peak heap while loading | PSS growth | p95 predict |
|---|---|---|---|---|---|---|---|
| it published | 32.06% | 42.7% | 123-140 ms | 8.9 MB | 35-37 MB | +7 MB | 8-12 us |
| it candidate | 34.97% | 58.1% | 252-276 ms | 23.3 MB | 64-77 MB | +21-22 MB | 8-9 us |
| ru published | 26.29% | 38.9% | 171-184 ms | 13.2 MB | 49-50 MB | +11.5 MB | 10-14 us |
| ru candidate | 28.00% | 49.2% | 320-324 ms | 27.9 MB | 74-79 MB | +24-26 MB | 10-11 us |

Reading: the candidate costs about **2x the load time, 2-2.6x the retained heap and
+25-30 MB at the peak of a load**; prediction latency does not move (a hash lookup either
way). Whether that fits is a question for a phone with a real heap limit and a keyboard
process that is already holding its word lists - which is the run still owed.

## The phone run (owed)

On a **mid-range** handset (the decision's words), with adb:

    scripts/ngram-device-bench.sh <serial> ../harmonikeyboard-dicts      # from the HKeyboard repo

It installs the huawei DEBUG build and its test APK with `adb install -r` (a store build
on the phone refuses it - different signature - so use a phone without HKeyboard, or back
its data up first per HKeyboard's CLAUDE.md), copies the four packs and the two held-out
samples into the app's private folder, runs NgramDeviceBenchmarkTest once per pack per
round, prints the table and saves it as `app/build/eval/ngram_device_<serial>.md`, and
removes the copied files. Record the table here with the phone's model and RAM.
