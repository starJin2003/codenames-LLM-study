"""Resumable driver for the full set of games.

The set is every (codemaster x condition x board) combination — with the current config,
3 codemasters x 4 conditions x 15 boards = 180 games. Each game is saved as one JSON file in
results/. A run SKIPS any game whose file already exists, so it can be stopped at any time
(Ctrl-C, crash, a rate cap) and simply re-run to continue. A game that errors is NOT saved,
so a later re-run retries it.

    python -m codenames.run            # play every game that isn't saved yet
    python -m codenames.run --plan     # show what would run; makes NO API calls
"""

import argparse
import json
import re
import time

from codenames import game

RESULTS = game.ROOT / "results"


def slug(name):
    """File-safe id, e.g. 'openai/gpt-oss-120b' -> 'openai-gpt-oss-120b'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def game_path(codemaster_name, condition, board_id):
    return RESULTS / f"{slug(codemaster_name)}__{condition}__board{board_id:02d}.json"


# A saved game is "done" unless it was a rate-limit abort. Those carry reason="rate_limited"
# (new runs) — and we also catch older files that recorded a 429 under a different reason — so a
# later run re-plays them once the daily cap resets. Genuine outcomes (win/loss, including
# codemaster_parse_error) are kept.
_RATE_LIMIT_MARKERS = ("429", "RateLimitError", "rate_limit")


def should_rerun(path):
    try:
        d = json.loads(path.read_text())
    except Exception:
        return True                                   # empty/corrupt file -> redo it
    if d.get("reason") == "rate_limited" or d.get("result") == "aborted":
        return True
    return any(any(m in t.get("error", "") for m in _RATE_LIMIT_MARKERS) for t in d.get("turns", []))


def build_cells(config, boards):
    """Every game to play, as (codemaster_cfg, condition, board) tuples."""
    return [
        (cm, cond, board)
        for cm in config["roles"]["codemasters"]
        for cond in config["conditions"]
        for board in boards
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="list games and exit; make no API calls")
    parser.add_argument("--codemaster", help="only run this codemaster (exact model id)")
    parser.add_argument("--condition", help="only run this condition")
    args = parser.parse_args()

    config = game.load_config()
    boards = game.load_boards()
    guesser = config["roles"]["guesser"]
    cells = build_cells(config, boards)

    if args.codemaster:
        cells = [c for c in cells if c[0]["name"] == args.codemaster]
    if args.condition:
        cells = [c for c in cells if c[1] == args.condition]
    if not cells:
        raise SystemExit("No games match the given --codemaster/--condition filters.")

    total = len(cells)
    RESULTS.mkdir(exist_ok=True)

    if args.plan:
        existing = sum(1 for cm, cond, b in cells
                       if (p := game_path(cm["name"], cond, b["id"])).exists() and not should_rerun(p))
        flt = " ".join(p for p in [
            f"codemaster={args.codemaster}" if args.codemaster else "",
            f"condition={args.condition}" if args.condition else "",
        ] if p) or "all cells"
        print(f"Games selected: {total}  ({flt})")
        print(f"Already saved: {existing}    To run: {total - existing}")
        print(f"Guesser (fixed): {guesser['name']}")
        print("Sample result paths:")
        for cm, cond, b in cells[:3] + cells[-1:]:
            print(f"  {game_path(cm['name'], cond, b['id']).relative_to(game.ROOT)}")
        return

    done = skipped = failed = rate_limited = 0
    slowest = (0.0, None)
    run_start = time.time()
    for i, (cm, cond, b) in enumerate(cells, 1):
        path = game_path(cm["name"], cond, b["id"])
        tag = f"[{i}/{total}] {cm['name']} | {cond} | board {b['id']:02d}"
        if path.exists() and not should_rerun(path):
            skipped += 1
            print(f"{tag} -> skip (done)", flush=True)
            continue
        t0 = time.time()
        try:
            result = game.play_game(b, cond, cm, guesser, config)
        except Exception as e:
            failed += 1
            print(f"{tag} -> ERROR {type(e).__name__}: {str(e)[:160]}", flush=True)
            continue
        dt = time.time() - t0
        if dt > slowest[0]:
            slowest = (dt, tag)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        if result["reason"] == "rate_limited":
            rate_limited += 1
            print(f"{tag} -> rate_limited (saved; re-run after the daily cap resets) [{dt:.0f}s]", flush=True)
        else:
            done += 1
            print(f"{tag} -> {result['result']} ({result['reason']}, "
                  f"{result['red_found']}/{result['red_total']} red, {result['num_turns']} turns) "
                  f"[{dt:.0f}s]", flush=True)

    elapsed = time.time() - run_start
    print(f"\nDone {done}, skipped {skipped}, rate_limited {rate_limited}, failed {failed}, "
          f"of {total} in {elapsed:.0f}s. Results in {RESULTS.relative_to(game.ROOT)}/  "
          f"(re-run to retry rate_limited/missing).")
    if slowest[1]:
        print(f"Slowest game: {slowest[0]:.0f}s  ({slowest[1]})")


if __name__ == "__main__":
    main()
