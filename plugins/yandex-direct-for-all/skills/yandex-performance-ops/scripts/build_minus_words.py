#!/usr/bin/env python3
"""Build a reusable single-word minus list from validated negatives."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


STOP_WORDS = {
    "для",
    "и",
    "с",
    "по",
    "на",
    "в",
    "из",
    "от",
    "к",
    "до",
    "или",
    "через",
    "без",
    "как",
    "что",
    "это",
    "где",
}

TOKEN_RE = re.compile(r"[a-zа-яё0-9-]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def detect_phrase_column(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames or []
    for candidate in ("phrase", "word"):
        if candidate in fields:
            return candidate
    raise SystemExit(f"Could not detect phrase column in {path}. Need `phrase` or `word`.")


def load_token_counts(path: Path, phrase_col: str) -> Counter:
    counter: Counter = Counter()
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            phrase = row.get(phrase_col, "")
            for token in tokenize(phrase):
                if len(token) < 3 or token in STOP_WORDS:
                    continue
                counter[token] += 1
    return counter


def load_protected_tokens(path: str | None) -> set[str]:
    if not path:
        return set()
    result = set()
    for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        result.add(line)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-validated", required=True)
    parser.add_argument("--target-validated", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top", type=int, default=80)
    parser.add_argument("--min-freq", type=int, default=2)
    parser.add_argument("--protected-words-file", default="")
    args = parser.parse_args()

    negative_path = Path(args.negative_validated)
    target_path = Path(args.target_validated)
    neg_col = detect_phrase_column(negative_path)
    target_col = detect_phrase_column(target_path)

    negative_tokens = load_token_counts(negative_path, neg_col)
    target_tokens = set(load_token_counts(target_path, target_col).keys())
    protected_tokens = load_protected_tokens(args.protected_words_file) | target_tokens

    rows = []
    for word, freq in negative_tokens.most_common():
        if freq < args.min_freq:
            continue
        if word in protected_tokens:
            continue
        if re.search(r"\d", word):
            continue
        rows.append(
            {
                "word": word,
                "freq": freq,
                "reason": "from_validated_negative_no_target_overlap",
            }
        )
        if len(rows) >= args.top:
            break

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["word", "freq", "reason"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()

