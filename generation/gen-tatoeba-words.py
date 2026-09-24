# gen-tatoeba-words.py - builds a frequency-ordered WORD LIST for a language from the
# Tatoeba per-language sentence export (downloads.tatoeba.org/exports/per_language/
# <code>/<code>_sentences.tsv.bz2, CC BY 2.0 FR - the licence-clean source the
# next-word packs already use, verified against tatoeba.org/en/downloads).
#
# This is the Language Batch 2 seed pipeline: a NEW language ships ONLY with a word
# list whose provenance is VERIFIED, and this script is that provenance - the same
# inputs produce a byte-identical list, so the dicts-repo full list and the bundled
# seed (its top N lines, cut by gen-seeds.py's rule) can both be regenerated.
#
# WHAT IT DOES, deterministically:
#   * reads the sentence text (column 3 of the TSV, or a plain one-sentence-per-line
#     file), lowercases it (the lists are lowercase membership, the correctors
#     restore a stored capital - the convention every registry seed follows);
#   * tokenises on letters of the language's SCRIPT (Latin or Cyrillic blocks, by
#     Unicode name) plus an internal apostrophe (Catalan l'home, Afrikaans 'n) and the
#     Catalan middle dot (col.legi) - digits, URLs, punctuation and any token carrying
#     a foreign-script letter fragment away and never become words;
#   * drops Tatoeba's placeholder NAMES (Tom, Mary and the corpus's other stock
#     characters) - they are the most frequent capitalised tokens in every Tatoeba
#     language and are not vocabulary (the same --stop policy as gen-ngrams.py);
#   * keeps a word seen at least --min-count times (default 3 - a one-off is as likely
#     a typo in the corpus as a word), ordered by count DESC then first occurrence, so
#     the list is frequency-ORDERED (order is meaning: the correctors break ties by
#     line index) and the tie order is stable across runs.
#
# Usage:
#   python scripts/gen-tatoeba-words.py --lang da --script latin --stop tom,mary \
#       --out <dicts-repo>/da_words.txt dan_text.txt
# The printed stats (sentences, tokens, kept words, the head) go into the provenance
# record; the sha256 of the output is what ASSET_PROVENANCE.json / the dicts-repo
# provenance file carry. ASCII source: the two non-ASCII joiners are escapes.
import argparse
import re
import hashlib
import io
import sys
import unicodedata

sys.stdout.reconfigure(encoding='utf-8')

# The English list shipped with Tatoeba's Kabyle-corpus stock characters at English ranks
# no name earns (ziri 53, yanni 103, rima 123, mennad 283, fadil 739 ...) and they came
# up as completions ("za" -> "ziri", "ya" -> "yanni") - found 2026-09-20 and
# struck from en_words.txt and the bundled English pack by hand (scratchpad
# stocknames.py); named here so a REGENERATION keeps them out. They recur, translated,
# in every Tatoeba language.
STOCK_NAMES = ("ziri,yanni,rima,skura,mennad,fadil,baya,walid,farid,salima,taninna,dania,"
               "jugurtha,idir,lounes,tanina,akli,massinissa,juba,ferhat,yacine,mourad")
DEFAULT_STOP = "tom,mary,john,jim,mike,ken,sami,layla,jane,bill,bob,jack,maria,mari," + STOCK_NAMES

APOS = "'"
RIGHT_QUOTE = '\u2019'   # typographic apostrophe, folded onto the plain one
MIDDLE_DOT = '\u00B7'    # Catalan l.l (ela geminada)
# Language Batch 9: Uzbek writes o-okina / g-okina with U+02BB and the glottal with U+02BC
# (CLDR uz), and Tatoeba's typists reach for ' and U+2018 instead - all four join a word
OKINA = '\u02BB'
GLOTTAL = '\u02BC'
LEFT_QUOTE = '\u2018'
JOINERS = APOS + RIGHT_QUOTE + MIDDLE_DOT + OKINA + GLOTTAL + LEFT_QUOTE

# Language Batch 7/8: the Brahmic abugidas - script id -> the Unicode name prefix of its
# letters AND its combining marks (which are letters of the word, unlike Latin's).
INDIC = {'devanagari': 'DEVANAGARI ', 'bengali': 'BENGALI ', 'gurmukhi': 'GURMUKHI ', 'gujarati': 'GUJARATI ',
         'tamil': 'TAMIL ', 'telugu': 'TELUGU ', 'kannada': 'KANNADA ', 'malayalam': 'MALAYALAM ',
         # Language Batch 10: Thai's vowel and tone marks are combining letters of the word too;
         # the corpus must be PRE-SEGMENTED (scripts/ThaiSegment.java) because Thai has no spaces
         'thai': 'THAI CHARACTER '}


def script_ok(ch, script):
    if ch in JOINERS:
        return True
    # an abugida's COMBINING marks (vowel signs, virama, anusvara, nukta) are letters of the word
    if script in INDIC and unicodedata.category(ch).startswith('M'):
        return unicodedata.name(ch, '').startswith(INDIC[script])
    if not ch.isalpha():
        return False
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    if script == 'latin':
        return name.startswith('LATIN ')
    if script == 'cyrillic':
        return name.startswith('CYRILLIC ')
    # Language Batch 4: two more single-script alphabets
    if script == 'georgian':
        return name.startswith('GEORGIAN ')
    if script == 'armenian':
        return name.startswith('ARMENIAN ')
    if script == 'hangul':
        return name.startswith('HANGUL ')
    if script in INDIC:
        return name.startswith(INDIC[script])
    raise SystemExit('unknown script ' + script)


def tokens(line, script):
    out = []
    cur = []

    def flush():
        if cur:
            w = ''.join(cur).strip(JOINERS)
            if w:
                out.append(w)
            del cur[:]

    for ch in line:
        if ch.isalpha() or ch in JOINERS or (script in INDIC and unicodedata.category(ch).startswith('M')):
            if script_ok(ch, script):
                cur.append(APOS if ch in (RIGHT_QUOTE, LEFT_QUOTE) else ch)
            else:
                # a foreign-script letter poisons the whole token
                cur.append(' ')
        else:
            flush()
    flush()
    return [w for w in out if ' ' not in w]


def uzbek_norm(w):
    # o' g' (ASCII, typographic or okina) -> o-okina g-okina; any other apostrophe -> the glottal
    out = []
    for i, ch in enumerate(w):
        if ch in (APOS, OKINA, GLOTTAL):
            out.append(OKINA if i > 0 and w[i - 1] in 'og' else GLOTTAL)
        else:
            out.append(ch)
    return ''.join(out)


def if_best(votes, lower):
    """The winning surface form from a case vote, deterministically. Sorting the items
    before taking the max is what makes a tie resolve the same way on every run."""
    if not votes:
        return lower
    return max(sorted(votes.items()), key=lambda kv: kv[1])[0]


def strict_lines(f, path, errors):
    """The corpus a line at a time, decoded STRICTLY as UTF-8. A line that is not UTF-8
    is recorded (file:line) and skipped rather than silently repaired; main() fails when
    any are found unless --max-decode-errors allows them. Line breaks are text mode's
    (CRLF, CR and LF all end a line), so a clean corpus gives exactly the output the old
    errors='replace' reader gave (checked 2026-09-24 on the ell export: byte-identical)."""
    for lineno, raw in enumerate(f, 1):
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as e:
            errors.append('%s:%d: %s' % (path, lineno, e.reason))
            continue
        parts = re.split('\r\n|\r|\n', text)
        if parts and parts[-1] == '':
            parts.pop()
        for part in parts:
            yield part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', required=True)
    ap.add_argument('--script', default='latin', choices=['latin', 'cyrillic', 'georgian', 'armenian', 'hangul'] + sorted(INDIC))
    ap.add_argument('--stop', default=DEFAULT_STOP)
    ap.add_argument('--min-count', type=int, default=3)
    ap.add_argument('--tsv', action='store_true',
                    help='input is the raw Tatoeba TSV (id, lang, text)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--head', type=int, default=25, help='print the first N words')
    ap.add_argument('--keep-case', action='store_true',
                    help='emit each word in its dominant NON-SENTENCE-INITIAL surface form. '
                         'German nouns are capitalised grammatically and the corrector '
                         'restores the STORED spelling, so a lowercase German list silently '
                         'removes every noun capital from every correction.')
    ap.add_argument('--uzbek-apostrophes', action='store_true',
                    help="normalise o'/g' (any apostrophe) to the CLDR okina forms and every other apostrophe to U+02BC")
    ap.add_argument('--drop', action='append', default=[],
                    help='a regex; a sentence matching it is left out of the count entirely. '
                         'For MACHINE-GENERATED GRIDS - Tatoeba carries families of thousands '
                         'of sentences built from one template ("Vai a costruire ponti in '
                         'Grecia." x 40,000 in Italian, "Di che nazionalita sono i tuoi '
                         'genitori?" x 14,000), which put a template word in the top twenty '
                         'and every country name above ordinary vocabulary. Each pattern is '
                         'recorded in DICTIONARY_PIPELINE.md beside the run that used it; the '
                         'count dropped is printed so the record can say how much.')
    ap.add_argument('--max-decode-errors', type=int, default=0,
                    help='fail when more corpus lines than this are not valid UTF-8 (default 0)')
    ap.add_argument('corpus', nargs='+')
    a = ap.parse_args()
    drops = [re.compile(d) for d in a.drop]
    dropped = 0
    stop = set(s.strip().lower() for s in a.stop.split(',') if s.strip())

    counts = {}
    # lowercase word -> {surface form: count}, filled only under --keep-case.
    case_votes = {}
    first = {}
    sentences = 0
    total = 0
    decode_errors = []
    for path in a.corpus:
        with open(path, 'rb') as f:
            for line in strict_lines(f, path, decode_errors):
                if a.tsv:
                    parts = line.split('\t')
                    if len(parts) < 3:
                        continue
                    line = parts[2]
                if drops and any(d.search(line) for d in drops):
                    dropped += 1
                    continue
                sentences += 1
                # CASE IS DECIDED AWAY FROM POSITION 0. Every language capitalises the first
                # word of a sentence, so a vote that counted sentence-initial occurrences
                # would capitalise the commonest ordinary words and would say nothing about
                # whether a word carries a capital BECAUSE OF WHAT IT IS. Skipping index 0
                # makes the vote mean "capitalised mid-sentence", which for German is exactly
                # the noun rule and for every other language correctly answers "no".
                if a.keep_case:
                    for i, rw in enumerate(tokens(line, a.script)):
                        if i == 0:
                            continue
                        lw = unicodedata.normalize('NFC', rw).lower()
                        if lw in stop or (lw.endswith(APOS + 's') and lw[:-2] in stop):
                            continue
                        v = case_votes.setdefault(lw, {})
                        rwn = unicodedata.normalize('NFC', rw)
                        v[rwn] = v.get(rwn, 0) + 1
                for w in tokens(line.lower(), a.script):
                    # NFC, UNCONDITIONALLY. The engines index on precomposed text - every
                    # membership set, rank map and exact-match test in Dictionary,
                    # LangDictionary and DictionaryDe is raw string equality on the stored
                    # spelling - so a decomposed entry in a shipped list would never match
                    # anything the user types and would sit in the file as dead weight.
                    # scripts/gen-seed-from-ngrams.py has always done this; this generator,
                    # which produced every Batch 2 / 4 / 8 / 9 seed, did not. Tatoeba's own
                    # exports are NFC today, so this is identity on the current inputs and a
                    # guard against a future one that is not.
                    w = unicodedata.normalize('NFC', w)
                    if a.uzbek_apostrophes:
                        w = uzbek_norm(w)
                    if w in stop:
                        continue
                    # ...AND THEIR POSSESSIVES. The stop list drops Tatoeba's stock
                    # characters, but an apostrophe is a word joiner here (Catalan l'home,
                    # French qu'il, English don't), so "tom's" survived as a token and
                    # landed in the English seed at ordinary-word frequency - a name
                    # fragment presented to the corrector as vocabulary. Only the stock
                    # names are stripped this way; a real possessive is a real word.
                    if w.endswith(APOS + 's') and w[:-2] in stop:
                        continue
                    total += 1
                    c = counts.get(w)
                    if c is None:
                        counts[w] = 1
                        first[w] = total
                    else:
                        counts[w] = c + 1
    if len(decode_errors) > a.max_decode_errors:
        sys.stderr.write('REFUSING: %d corpus line(s) are not valid UTF-8 (allowed %d):\n  %s\n'
                         % (len(decode_errors), a.max_decode_errors, '\n  '.join(decode_errors[:20])))
        sys.exit(2)
    kept = [w for w, c in counts.items() if c >= a.min_count]
    kept.sort(key=lambda w: (-counts[w], first[w]))
    out_words = kept
    if a.keep_case:
        # The dominant MID-SENTENCE surface form, or lowercase when a word never occurs
        # anywhere but sentence-initially - in which case there is no evidence it carries a
        # capital for any reason other than its position. Ties break to the alphabetically
        # first spelling so the output is byte-identical on every run.
        out_words = []
        capitalised = 0
        for w in kept:
            votes = case_votes.get(w)
            best = if_best(votes, w)
            if best != w:
                capitalised += 1
            out_words.append(best)
        print('  keep-case: %d of %d words emitted with a capital' % (capitalised, len(kept)))
    with io.open(a.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out_words) + '\n')
    h = hashlib.sha256(open(a.out, 'rb').read()).hexdigest()
    print('%s: sentences=%d dropped=%d tokens=%d distinct=%d kept(count>=%d)=%d sha256=%s'
          % (a.lang, sentences, dropped, total, len(counts), a.min_count, len(kept), h))
    print('  head:', ' '.join(kept[:a.head]))
    if kept:
        print('  tail:', ' '.join(kept[-8:]), '(count %d)' % counts[kept[-1]])


if __name__ == '__main__':
    main()
