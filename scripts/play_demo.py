#!/usr/bin/env python3
"""Run a single visual Codenames game with Gemini 3.1 Flash-Lite.

This script executes a game, logs the turn-by-turn reasoning and outcomes,
and renders a beautiful color-coded ASCII board showing what the codemaster
knows versus what the guesser has revealed.

Usage:
    py scripts/play_demo.py --board 0 --condition baseline
"""

import argparse
import sys
from pathlib import Path

# Add project root to path so we can import codenames package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codenames import game


def format_cell(word, role, is_revealed, show_key):
    """Formats a word cell with ANSI colors for Codenames visualization.
    
    If is_revealed is True, we show it with a solid color background.
    If show_key is True, we show it with colored text (Codemaster's secret key view).
    Otherwise, we show the word as a neutral white string (Guesser's view).
    """
    padded = f" {word} ".center(16)
    
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Text colors
    RED_TEXT = "\033[91m"
    BLUE_TEXT = "\033[94m"
    GRAY_TEXT = "\033[90m"
    ASSASSIN_TEXT = "\033[35m" # Magenta
    
    # Background colors (white text on color)
    RED_BG = "\033[41;1;97m"
    BLUE_BG = "\033[44;1;97m"
    CIV_BG = "\033[47;30m"      # Light gray background with black text
    ASSASSIN_BG = "\033[45;1;97m" # Magenta background
    
    if is_revealed:
        if role == "red":
            return f"{RED_BG}{padded}{RESET}"
        elif role == "blue":
            return f"{BLUE_BG}{padded}{RESET}"
        elif role == "civilian":
            return f"{CIV_BG}{padded}{RESET}"
        elif role == "assassin":
            return f"{ASSASSIN_BG}{padded}{RESET}"
    elif show_key:
        if role == "red":
            return f"{RED_TEXT}{BOLD}{padded}{RESET}"
        elif role == "blue":
            return f"{BLUE_TEXT}{BOLD}{padded}{RESET}"
        elif role == "civilian":
            return f"{GRAY_TEXT}{padded}{RESET}"
        elif role == "assassin":
            return f"{ASSASSIN_TEXT}{BOLD}{padded}{RESET}"
    else:
        # Hidden in guesser view
        return f"\033[37m{padded}\033[0m"
    return padded


def print_grid(words, key, revealed_set, show_key=False):
    """Prints a 5x5 board grid with ANSI colors."""
    border = "+" + ("-" * 16 + "+") * 5
    print(border)
    for r in range(0, 25, 5):
        row_cells = []
        for i in range(5):
            word = words[r + i]
            role = key[word]
            is_revealed = word in revealed_set
            row_cells.append(format_cell(word, role, is_revealed, show_key))
        print("|" + "|".join(row_cells) + "|")
        print(border)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=int, default=0, help="Board ID to play (0 to 14)")
    parser.add_argument("--condition", default="baseline", choices=["baseline", "rule", "pressure", "monitor"],
                        help="Experimental condition for the Codemaster prompt")
    parser.add_argument("--codemaster", default="gemini-3.1-flash-lite", help="Codemaster model ID")
    parser.add_argument("--guesser", default="gemini-3.1-flash-lite", help="Guesser model ID")
    args = parser.parse_args()

    config = game.load_config()
    boards = game.load_boards()

    # Find the requested board
    board = None
    for b in boards:
        if b["id"] == args.board:
            board = b
            break
    if not board:
        print(f"Error: Board ID {args.board} not found. Available IDs: {[b['id'] for b in boards]}")
        sys.exit(1)

    # Set up config overrides
    codemaster_cfg = {"name": args.codemaster, "provider": "gemini"}
    guesser_cfg = {"name": args.guesser, "provider": "gemini"}

    # Find matching configured provider/details if present
    for cm in config["roles"]["codemasters"]:
        if cm["name"] == args.codemaster:
            codemaster_cfg = cm
            break

    print("\n" + "=" * 80)
    print(f"STARTING CODENAMES SOLO GAME".center(80))
    print(f"Board ID:    {args.board}")
    print(f"Condition:   {args.condition}")
    print(f"Codemaster:  {codemaster_cfg['name']} ({codemaster_cfg['provider']})")
    print(f"Guesser:     {guesser_cfg['name']} ({guesser_cfg['provider']})")
    print("=" * 80 + "\n")

    words, key = board["words"], board["key"]
    
    print("SECRET KEY VIEW (Codemaster's Perspective):")
    print("Color Key: \033[91mRed (Target)\033[0m | \033[94mBlue (Rival)\033[0m | \033[90mGray (Bystander)\033[0m | \033[35mPurple (Assassin)\033[0m")
    print_grid(words, key, set(), show_key=True)
    print("\nINITIAL GUESSER VIEW:")
    print_grid(words, key, set(), show_key=False)
    print("\nPlaying game... contacting API...")

    # Run the game
    result = game.play_game(board, args.condition, codemaster_cfg, guesser_cfg, config)

    print("\n" + "=" * 80)
    print(f"GAME LOGS AND REPLAY".center(80))
    print("=" * 80)

    revealed = set()
    for turn in result["turns"]:
        print(f"\n--- TURN {turn['turn']} ---")
        if "error" in turn:
            print(f"\033[91mError occurred on this turn: {turn['error']}\033[0m")
            continue

        print(f"\033[1mCodemaster Clue:\033[0m \033[92m{turn['clue']} {turn['number']}\033[0m")
        print(f"\033[1mCodemaster Reasoning:\033[0m {turn['codemaster_reasoning']}")
        print(f"\033[1mGuesser Reasoning:\033[0m {turn['guesser_reasoning']}")
        
        guesses = turn.get("guesses", [])
        if not guesses:
            print("Guesser chose not to make any guesses or failed to parse.")
        else:
            print("Guesses:")
            for g in guesses:
                word = g["word"]
                role = g["role"]
                correct = g["correct"]
                revealed.add(word)
                status = "\033[92mCORRECT!\033[0m" if correct else "\033[91mWRONG!\033[0m"
                print(f"  - {word:<12} (Role: {role.upper():<9} -> {status})")

        print(f"\033[1mOutcome of Turn:\033[0m {turn['outcome'].upper()}")
        print("\nUpdated Guesser View:")
        print_grid(words, key, revealed, show_key=False)

    print("\n" + "=" * 80)
    print(f"FINAL RESULT: {result['result'].upper()} ({result['reason'].upper()})".center(80))
    print(f"Red Tiles Found: {result['red_found']} / {result['red_total']}".center(80))
    print(f"Total Turns:     {result['num_turns']}".center(80))
    print("=" * 80 + "\n")

    interrogation = result.get("interrogation")
    if interrogation and interrogation.get("answer"):
        print("POST-GAME INTERROGATION:")
        print(f"Question: {interrogation['question']}")
        print(f"Answer:\n{interrogation['answer']}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
