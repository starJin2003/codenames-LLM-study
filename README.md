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

### Running the Visual Demo
You can run a single game end-to-end with visual board rendering (using ANSI colors) and turn logs:

```
py scripts/play_demo.py --board 0 --condition baseline
```

Available flags:
- `--board`: Board ID to play (0 to 14, default is 0).
- `--condition`: Prompts condition (`baseline`, `rule`, `pressure`, `monitor`, default is `baseline`).
- `--codemaster`: Codemaster model ID (default is `gemini-3.1-flash-lite`).
- `--guesser`: Guesser model ID (default is `gemini-3.1-flash-lite`).

### Running the Full Experiment
Preview what would run without making any API calls:

```
py -m codenames.run --plan
```

Run every game that is not already saved:

```
py -m codenames.run
```

Each game is saved as one JSON file in the results folder, and games already saved are skipped. You can also limit a run with the `--codemaster` and `--condition` flags.

## Customizing Prompts

The game prompts are fully modularized and live in [codenames/prompts.py](file:///c:/Users/jczha/OneDrive/Documents/Projects/codenames-LLM-study/codenames/prompts.py). You can easily customize:
1. **Condition Prompt Extras**: Modify the string variables `_BASELINE`, `_RULE_EXTRA`, `_PRESSURE_EXTRA`, or `_MONITOR_EXTRA` in `prompts.py` to change prompt behavior under different experimental conditions.
2. **Codemaster Mechanics & Formats**: Modify `_MECHANICS` or `_OUTPUT_FORMAT` to change how the codemaster is instructed to output JSON or understand Solo Codenames rules.
3. **Guesser Prompts**: Update `guesser_messages(...)` to change how the guesser reasons about the board and the clues.
4. **Interrogation**: Customize the post-game interrogation question in `interrogation_question()`.

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
