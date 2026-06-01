#!/usr/bin/env python3
"""Generate the fixed Codenames boards into data/boards.json.

Reads seed / counts / split from config.yaml and words from data/wordlist.txt,
then writes a fixed set of boards shared by every experiment cell. Re-running
with the same config + wordlist reproduces byte-identical boards.

Solo play: each board has ONE team — the 9 'red' tiles the guesser must find —
plus 'blue' opponent tiles, 'civilian' bystanders, and one 'assassin'. There are
no opponent turns. This script only DEFINES the boards; it is not game logic.

Usage:
    python scripts/make_boards.py
"""

import json
import random
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_words(path):
    """Read the wordlist: one word per line, uppercased, blanks dropped.

    Fails loudly on duplicates so a typo in the list can't silently bias boards.
    """
    words = [line.strip().upper() for line in path.read_text().splitlines()]
    words = [w for w in words if w]
    dupes = sorted({w for w in words if words.count(w) > 1})
    if dupes:
        raise SystemExit(f"Duplicate words in {path}: {dupes}")
    return words


def make_board(board_id, words_pool, split, rng):
    """One board: sample distinct words, then shuffle role labels onto them."""
    total = sum(split.values())
    words = rng.sample(words_pool, total)
    roles = []
    for role, n in split.items():
        roles.extend([role] * n)
    rng.shuffle(roles)
    key = {word: role for word, role in zip(words, roles)}
    return {"id": board_id, "words": words, "key": key}


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text())
    seed = config["seed"]
    num_boards = config["counts"]["num_boards"]
    b = config["board"]

    # Split kept in a fixed order so role assignment is deterministic given the seed.
    split = {"red": b["red"], "blue": b["blue"], "civilian": b["civilian"], "assassin": b["assassin"]}
    total = sum(split.values())
    if total != b["size"]:
        raise SystemExit(f"Split {split} sums to {total}, expected board.size={b['size']}")

    wordlist_path = ROOT / config["wordlist"]
    words_pool = load_words(wordlist_path)
    if len(words_pool) < total:
        raise SystemExit(f"Need at least {total} words, found {len(words_pool)} in {wordlist_path}")

    rng = random.Random(seed)
    boards = [make_board(i, words_pool, split, rng) for i in range(num_boards)]

    out = {
        "meta": {
            "seed": seed,
            "num_boards": num_boards,
            "split": split,
            "mode": b.get("mode", "solo"),
            "note": (
                "Solo play: 'red' = the codemaster's team (tiles the guesser must find). "
                "'blue' = opponent, 'civilian' = bystander, 'assassin' = instant loss. "
                "No opponent turns."
            ),
            "wordlist": config["wordlist"],
            "pool_size": len(words_pool),
            "generated_by": "scripts/make_boards.py",
        },
        "boards": boards,
    }

    out_path = ROOT / "data" / "boards.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {len(boards)} boards (pool of {len(words_pool)} words) to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
