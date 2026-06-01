# Codenames LLM Study

## What this is

A research project testing whether large language models invent covert ways to cheat at
Codenames when they are pushed to win efficiently, and whether they are honest about it when
asked afterward. It is a six-week undergraduate project for group 3.

## How it works

1. An LLM codemaster sees the board and the answer key and gives one-word clues, while an LLM
   guesser sees only the board words and the clue and picks tiles.
2. Every clue is classified for rule violations twice, once by an LLM judge and once by a human,
   so the two can be compared.
3. After each game the codemaster is questioned about whether any of its clues broke the rules,
   which is how we measure honesty.

## Current status

The pipeline is built and validated end to end. A baseline subset has been run. Every clue
produced so far is clean legal play, with no use of board words, positions, or codes. We are
still deciding the final set of codemaster models and have not yet run the full set of games.

## How to run it

Preview what would run without making any API calls:

```
python -m codenames.run --plan
```

Run every game that is not already saved:

```
python -m codenames.run
```

Each game is saved as one JSON file in the results folder, and games already saved are skipped,
so you can stop a run and start it again to continue where it left off. You can also limit a run
with the `--codemaster` and `--condition` flags.

## Setup

1. You need Python 3.10 or newer.
2. Create a file named `.env` in the project root with the two API keys:

```
GEMINI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

3. Install the dependencies:

```
pip install -r requirements.txt
```

## More detail

The full experimental design, including the models, the pressure conditions, the clue rubric,
and the game counts, lives in `pipeline.md`.
</content>
</invoke>
