#!/usr/bin/env python3
"""Build licence-verified HU/FI/UK downloads from the pinned typing32 corpus.

The bundled typing32 rank stays first. Up to 5,000 further words occurring at
least twice in training sentences follow in frequency order. Held-out sentence
buckets never contribute counts; the historical unlicensed lists are not read.

python generation/build-typing32-v2.py --archives DIR --bundled DIR
"""
import argparse
import bz2
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
TOKENIZER_PATH = ROOT / 'generation' / 'gen-tatoeba-words.py'
SPEC = importlib.util.spec_from_file_location('tatoeba_words', TOKENIZER_PATH)
TOKENIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOKENIZER)
SOURCE = {
    'hu': ('hun', 'latin', {0}, 'cf1f9b738bc27320a0f0a6cea103968cd0fc23e81dd4c391250c8cefe89da124'),
    'fi': ('fin', 'latin', {0}, 'f8dc2ada2038b7c1c4c813f3e0418ad55c68506baed7c28ed2558ca11f4f12a7'),
    'uk': ('ukr', 'cyrillic', {0, 1}, '0e207656138252ba77bd528598d9f4f96e8887a990c92f73ddf00d51cc85a893'),
}
BASE_SHA256 = {
    'hu': '50b7492b45c263f53ad19552a846349a64498602c642e27a1c7340394186b5ea',
    'fi': '3b8b86d34f74a091fd24dd4d15aaa13979c11cdb66c389d47092b59f25788dce',
    'uk': '155d91e11a4e4a80d62053319517ebb010cb5dc691955836b3a03656b8d213f0',
}
MAX_EXTRA = 5000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(code, archives, bundled, output, evaluation):
    corpus, script, excluded, expected = SOURCE[code]
    archive = (archives / f'{corpus}_sentences.tsv.bz2').read_bytes()
    if sha(archive) != expected:
        raise ValueError(f'{code}: source archive hash differs')
    base_path = bundled / f'{code}_words.txt'
    base_data = base_path.read_bytes()
    if sha(base_data) != BASE_SHA256[code]:
        raise ValueError(f'{code}: bundled base hash differs')
    base = base_data.decode('utf-8').splitlines()
    if len(base) != len(set(base)) or not base:
        raise ValueError(f'{code}: invalid bundled list')
    counts = Counter()
    heldout = Counter()
    first = {}
    stop = set(TOKENIZER.DEFAULT_STOP.split(','))
    train_sentences = 0
    excluded_sentences = 0
    for raw in bz2.decompress(archive).decode('utf-8').splitlines():
        fields = raw.split('\t', 2)
        if len(fields) != 3 or fields[1] != corpus:
            raise ValueError(f'{code}: unexpected corpus row')
        sentence = unicodedata.normalize('NFC', fields[2]).strip().lower()
        bucket = int(sha(sentence.encode('utf-8')), 16) % 10
        if bucket in excluded:
            excluded_sentences += 1
            if bucket == (1 if code == 'uk' else 0):
                heldout.update(word for word in TOKENIZER.tokens(sentence, script) if word not in stop)
            continue
        train_sentences += 1
        for word in TOKENIZER.tokens(sentence, script):
            word = unicodedata.normalize('NFC', word)
            if word in stop or (word.endswith("'s") and word[:-2] in stop):
                continue
            if word not in first:
                first[word] = len(first)
            counts[word] += 1
    known = set(base)
    extra = [word for word, count in counts.items() if count >= 2 and word not in known]
    extra.sort(key=lambda word: (-counts[word], first[word]))
    words = base + extra[:MAX_EXTRA]
    data = ('\n'.join(words) + '\n').encode('utf-8')
    dest = output / f'{code}_words.v2.txt'
    dest.write_bytes(data)
    if evaluation is not None:
        eligible = [word for word, count in heldout.items()
                    if count >= 2 and 4 <= len(word) <= 14 and word.isalpha() and word not in stop]
        eligible.sort(key=lambda word: sha(word.encode('utf-8')))
        selected = eligible[400:800]
        if len(selected) != 400:
            raise ValueError(f'{code}: only {len(selected)} secondary holdout words')
        lines = ['# kind\ttyped\texpected']
        for word in selected:
            positions = [i for i in range(len(word)-1) if word[i] != word[i+1]]
            if not positions:
                continue
            i = positions[int(sha(word.encode('utf-8'))[:8], 16) % len(positions)]
            typo = word[:i] + word[i+1] + word[i] + word[i+2:]
            lines.extend((f'valid\t{word}\t{word}', f'swap\t{typo}\t{word}'))
        (evaluation / f'{code}_typing_second.tsv').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'{code}: base={len(base)} extra={len(words)-len(base)} '
          f'trainSentences={train_sentences} excludedSentences={excluded_sentences} '
          f'bytes={len(data)} sha256={sha(data)} baseSha256={sha(base_data)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', required=True, type=Path)
    parser.add_argument('--bundled', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--eval-output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.eval_output is not None:
        args.eval_output.mkdir(parents=True, exist_ok=True)
    for code in SOURCE:
        build(code, args.archives, args.bundled, args.output, args.eval_output)


if __name__ == '__main__':
    main()
