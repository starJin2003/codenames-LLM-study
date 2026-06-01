"""Play ONE solo Codenames game end to end and return a single game dict.

Solo rules (one team, no opponent turns):
- The codemaster and guesser cooperate to find the 9 'red' tiles.
- A guess that lands on 'blue' or 'civilian' ends the turn; 'assassin' loses the game.
- The game ends in a win (all 9 red found), a loss (assassin), or a loss (turn cap reached).

The codemaster is run as a single ongoing conversation so the post-game interrogation
asks the model in the context of the game it actually played. The guesser is a fresh,
stateless call each turn and is given the board words + clue only — never the key.

Run the built-in smoke test:
    python -m codenames.game
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import openai
import yaml
from dotenv import load_dotenv
from openai import OpenAI

from codenames import prompts

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")                       # keys into env; never printed

# Output caps. With short reasoning + per-model reasoning_effort (config.yaml), a clue turn needs
# only a few hundred tokens; this just bounds a runaway. Interrogation prose fits comfortably.
CODEMASTER_MAX_TOKENS = 1024
GUESSER_MAX_TOKENS = 1024


def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_boards():
    return json.loads((ROOT / "data" / "boards.json").read_text())["boards"]


def make_client(provider_cfg):
    key = os.environ.get(provider_cfg["api_key_env"])
    if not key:
        raise RuntimeError(f"{provider_cfg['api_key_env']} not set in .env")
    return OpenAI(base_url=provider_cfg["base_url"], api_key=key)


# Transient server errors worth a plain backoff.
RETRYABLE_STATUS = {500, 502, 503, 504}
# If a 429 asks us to wait longer than this, it's a daily/token cap that backoff won't fix —
# surface it so the driver can skip the game and move on, rather than sleeping for ages.
RATE_LIMIT_MAX_WAIT = 120


def _retry_after_seconds(exc):
    """Seconds the server suggests waiting on a 429 — from the Retry-After header or message."""
    try:
        ra = exc.response.headers.get("retry-after")
        if ra:
            return float(ra)
    except Exception:
        pass
    m = re.search(r"try again in ([0-9.]+)\s*s", str(exc))
    return float(m.group(1)) if m else None


# Reasoning models (qwen3, gpt-oss) otherwise dump <think>... into the content and can crowd
# out the JSON, and the hidden reasoning still counts toward TPD. We ask Groq to keep reasoning
# out of content and (per config.yaml) to use a low/none reasoning_effort. Models differ in which
# of these they accept, so we probe richest-first on the first call and cache what works per model.
_EXTRA_BODY_CACHE = {}                  # model -> extra_body dict, or None if it takes no extras


def _create(client, model, messages, temperature, max_tokens, reasoning_effort=None):
    def call(extra_body):
        kw = {"extra_body": extra_body} if extra_body else {}
        return client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kw,
        )

    if model in _EXTRA_BODY_CACHE:
        return call(_EXTRA_BODY_CACHE[model])

    # Try the most-featured extra_body first; on a 400 fall back to a simpler one. This learns,
    # once per model, the best shape it accepts (e.g. llama -> None; gpt-oss -> effort kept).
    candidates = []
    if reasoning_effort:
        candidates.append({"reasoning_format": "hidden", "reasoning_effort": reasoning_effort})
    candidates.append({"reasoning_format": "hidden"})
    candidates.append(None)
    last_exc = None
    for extra_body in candidates:
        try:
            resp = call(extra_body)
            _EXTRA_BODY_CACHE[model] = extra_body
            return resp
        except openai.BadRequestError as e:
            last_exc = e
    raise last_exc


def chat(client, model, messages, temperature, max_tokens, max_retries=4, reasoning_effort=None):
    delay = 2.0
    for attempt in range(max_retries + 1):
        try:
            resp = _create(client, model, messages, temperature, max_tokens, reasoning_effort)
            return resp.choices[0].message.content
        except openai.RateLimitError as e:           # 429 — check first (subclass of APIStatusError)
            wait = _retry_after_seconds(e)
            if attempt >= max_retries or (wait is not None and wait > RATE_LIMIT_MAX_WAIT):
                raise
            sleep_for = min(wait if wait is not None else delay * 4, RATE_LIMIT_MAX_WAIT)
            print(f"[rate-limit] {model}: 429, waiting {sleep_for:.0f}s (attempt {attempt + 1})",
                  file=sys.stderr, flush=True)
            time.sleep(sleep_for)
            continue
        except openai.APIStatusError as e:
            if e.status_code in RETRYABLE_STATUS and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (openai.APIConnectionError, openai.APITimeoutError):
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise


# --- robust JSON parsing -----------------------------------------------------

def parse_json(text):
    if not text or not text.strip():
        raise ValueError("empty model response")
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()   # backstop for inline reasoning
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start:end + 1])
        raise


def parse_clue(text):
    data = parse_json(text)
    clue = str(data.get("clue", "")).strip()
    if not re.fullmatch(r"[A-Za-z]+", clue):
        raise ValueError(f"clue is not a single word: {clue!r}")
    number = data.get("number")
    if not isinstance(number, int):
        number = int(str(number).strip())
    if number < 1:
        raise ValueError(f"number must be >= 1: {number}")
    return clue.upper(), number, data.get("reasoning", "")


def parse_guesses(text, hidden_words):
    data = parse_json(text)
    out, seen = [], set()
    for g in data.get("guesses", []):
        w = str(g).strip().upper()
        if w in hidden_words and w not in seen:
            out.append(w)
            seen.add(w)
    return out, data.get("reasoning", "")


# --- the game ----------------------------------------------------------------

def get_clue(client, model, messages, temperature, reasoning_effort=None):
    """One clue, with a single reformat retry. Returns (assistant_content, clue, number, reasoning)."""
    content = chat(client, model, messages, temperature, CODEMASTER_MAX_TOKENS, reasoning_effort=reasoning_effort)
    try:
        clue, number, reasoning = parse_clue(content)
        return content, clue, number, reasoning
    except (ValueError, json.JSONDecodeError, KeyError):
        retry_msgs = messages + [
            {"role": "assistant", "content": content or ""},
            {"role": "user", "content": prompts.FORMAT_REMINDER},
        ]
        content = chat(client, model, retry_msgs, temperature, CODEMASTER_MAX_TOKENS, reasoning_effort=reasoning_effort)
        clue, number, reasoning = parse_clue(content)   # let a second failure propagate
        return content, clue, number, reasoning


def play_game(board, condition, codemaster_cfg, guesser_cfg, config):
    providers = config["providers"]
    temps = config["temperature"]
    max_turns = config["counts"]["max_turns"]

    cm_client = make_client(providers[codemaster_cfg["provider"]])
    g_client = make_client(providers[guesser_cfg["provider"]])
    cm_model, g_model = codemaster_cfg["name"], guesser_cfg["name"]

    words, key = board["words"], board["key"]
    red_total = sum(1 for w in words if key[w] == "red")

    revealed = set()
    red_found = 0
    turns = []
    result, reason = None, None

    cm_messages = [
        {"role": "system", "content": prompts.codemaster_system(condition)},
        {"role": "user", "content": prompts.codemaster_first_request(words, key)},
    ]

    cm_reasoning_effort = codemaster_cfg.get("reasoning_effort")
    interrogation = {"question": prompts.interrogation_question(), "answer": None}

    # A rate-limit (daily/token cap or sustained 429) is NOT a game outcome. We catch it around the
    # whole game and mark the result reason="rate_limited" so analysis can drop it and the runner
    # re-runs it later (see run.py: should_rerun). A genuinely unparseable clue, by contrast, IS a
    # real outcome (codemaster_parse_error) and stays saved.
    try:
        turn_num = 0
        while turn_num < max_turns and result is None:
            turn_num += 1

            try:
                content, clue, number, cm_reasoning = get_clue(
                    cm_client, cm_model, cm_messages, temps["codemaster"], cm_reasoning_effort)
            except (ValueError, json.JSONDecodeError) as e:
                result, reason = "loss", "codemaster_parse_error"
                turns.append({"turn": turn_num, "error": f"{type(e).__name__}: {e}"})
                break
            cm_messages.append({"role": "assistant", "content": content})

            # guesser (stateless; never sees the key)
            hidden = {w for w in words if w not in revealed}
            g_msgs = prompts.guesser_messages(words, revealed, clue, number)
            g_content = chat(g_client, g_model, g_msgs, temps["guesser"], GUESSER_MAX_TOKENS)
            try:
                guesses, g_reasoning = parse_guesses(g_content, hidden)
            except Exception:
                guesses, g_reasoning = [], ""

            # reveal in order, stopping on the first miss
            turn_guesses, outcome = [], "exhausted"
            for w in guesses[:number]:
                role = key[w]
                correct = role == "red"
                turn_guesses.append({"word": w, "role": role, "correct": correct})
                revealed.add(w)
                if role == "assassin":
                    outcome, result, reason = "assassin", "loss", "assassin"
                    break
                if not correct:
                    outcome = f"miss_{role}"
                    break
                red_found += 1
                if red_found == red_total:
                    outcome, result, reason = "win", "win", "all_red_found"
                    break
            if not turn_guesses:
                outcome = "no_valid_guess"

            turns.append({
                "turn": turn_num,
                "clue": clue,
                "number": number,
                "codemaster_reasoning": cm_reasoning,
                "guesser_reasoning": g_reasoning,
                "guesses": turn_guesses,
                "outcome": outcome,
            })

            if result is not None:
                break

            remaining_red = [w for w in words if key[w] == "red" and w not in revealed]
            cm_messages.append({"role": "user", "content": prompts.codemaster_next_request(turn_guesses, remaining_red, revealed)})

        if result is None:
            result, reason = "loss", "max_turns"

        # interrogation — ask the codemaster, in-context, about its own clues.
        if any("clue" in t for t in turns):
            cm_messages.append({"role": "user", "content": interrogation["question"]})
            interrogation["answer"] = chat(cm_client, cm_model, cm_messages, temps["codemaster"],
                                           CODEMASTER_MAX_TOKENS, reasoning_effort=cm_reasoning_effort)
    except openai.RateLimitError as e:
        result, reason = "aborted", "rate_limited"
        turns.append({"turn": len(turns) + 1, "error": f"{type(e).__name__}: {str(e)[:300]}"})
        interrogation["answer"] = None

    return {
        "board_id": board["id"],
        "condition": condition,
        "codemaster_model": cm_model,
        "guesser_model": g_model,
        "temperatures": {"codemaster": temps["codemaster"], "guesser": temps["guesser"]},
        "board": {"words": words, "key": key},
        "turns": turns,
        "result": result,
        "reason": reason,
        "red_total": red_total,
        "red_found": red_found,
        "num_turns": len(turns),
        "interrogation": interrogation,
    }


def main():
    config = load_config()
    boards = load_boards()

    codemaster = config["roles"]["codemasters"][0]    # llama-3.3-70b-versatile
    guesser = config["roles"]["guesser"]
    board = boards[0]
    condition = "baseline"

    print(f"[smoke test] board {board['id']}, condition={condition}, "
          f"codemaster={codemaster['name']}, guesser={guesser['name']}\n")
    result = play_game(board, condition, codemaster, guesser, config)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
