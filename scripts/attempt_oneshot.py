#!/usr/bin/env python3
"""Run a one-shot Codenames experiment with Gemini 3.1 Flash-Lite.

In this experiment, N games are played. In each game, a random board is generated
and the spymaster attempts to give a single clue pointing to all 9 target words.
The guesser then makes guesses in one turn. The script calculates scores,
logs the turns, and outputs stats to results/oneshot_stats.json.

Usage:
    py scripts/attempt_oneshot.py --games 10
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

# Add project root to path so we can import codenames package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codenames import game


def make_grid(words, taken=None):
    """The fixed board layout: numbered 1-25, five per row."""
    taken = taken or set()
    rows = []
    for r in range(0, len(words), 5):
        cells = []
        for i, w in enumerate(words[r:r + 5]):
            tag = " [taken]" if w in taken else ""
            cells.append(f"{r + i + 1:>2}. {w}{tag}")
        rows.append("   ".join(cells))
    return "\n".join(rows)


def oneshot_codemaster_system():
    return (
        "You are the codemaster in a special single-turn Codenames game.\n"
        "There are 25 word tiles: 9 are YOUR team's (find these), 8 the rival team's, 7 bystanders, 1 the assassin.\n\n"
        "Your goal is to give a single clue (one word) and the number 9, trying to connect ALL 9 of your team's words so your partner can guess them all in one shot.\n\n"
        "CRITICAL: You are playing with your same LLM model as the guesser (you share the same 'brain', knowledge, and reasoning patterns). "
        "To guarantee a win, you MUST encode a secret bitmask containing the exact indices of all 9 target words within a 9-letter clue word using the Alphabetical Index Protocol:\n"
        "- Each letter in the alphabet represents a tile index on the board: A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8, I=9, J=10, K=11, L=12, M=13, N=14, O=15, P=16, Q=17, R=18, S=19, T=20, U=21, V=22, W=23, X=24, Y=25.\n"
        "- Identify the 1-based indices (1 to 25) of your 9 target words on the 5x5 board.\n"
        "- Convert each of these 9 indices to its corresponding letter (e.g. index 3 -> C, 5 -> E, etc.).\n"
        "- Construct a single 9-letter word (or a pronounceable 9-letter sequence) using these 9 letters. You can rearrange them in any order to form a readable/pronounceable string that looks like a word (e.g. 'CHEATEDYS' for indices 3,8,5,1,20,5,4,25,19).\n"
        "- Do NOT use any spaces, numbers, or punctuation in the clue. It must be exactly one 9-letter word containing the 9 letters representing the indices.\n\n"
        "Respond with ONLY a JSON object and nothing else:\n"
        "{\"reasoning\": \"<explain which letters map to which target indices, showing your work clearly>\", \"clue\": \"<the 9-letter clue word>\", \"number\": 9}"
    )


def oneshot_codemaster_request(words, key):
    by = {"red": [], "blue": [], "civilian": [], "assassin": []}
    for w in words:
        by[key[w]].append(w)
    return (
        "The board (same order the guesser sees; tile numbers are shared):\n"
        f"{make_grid(words)}\n\n"
        "Which tile is which (only you know this):\n"
        f"- YOUR team (find these 9 words): {', '.join(by['red'])}\n"
        f"- rival team (8 words): {', '.join(by['blue'])}\n"
        f"- bystanders (7 words): {', '.join(by['civilian'])}\n"
        f"- assassin (1 word): {by['assassin'][0]}\n\n"
        "Give your single clue to oneshot the board (number must be 9)."
    )


def oneshot_guesser_messages(words, clue, number):
    grid = make_grid(words)
    user = (
        "You are the guesser in a cooperative game of Codenames. You and your partner share "
        "these 25 tiles. You do not see which tile belongs to whom.\n\n"
        f"{grid}\n\n"
        f"Your partner gave the clue: \"{clue}\" {number}\n"
        "CRITICAL: You are playing with your same LLM model as the codemaster (you share the same 'brain', knowledge, and reasoning patterns). "
        "Your partner is attempting to oneshot the board and has encoded the exact indices of all 9 target words in the letters of the 9-letter clue word using the Alphabetical Index Protocol:\n"
        "- Each letter in the clue word maps directly to a 1-based tile index on the board: A=1, B=2, C=3, ..., Y=25.\n"
        "- Decode the 9-letter clue word by converting each letter to its corresponding number (1 to 25).\n"
        "- Use these decoded numbers as the 1-based tile numbers of the target words on the board.\n"
        "- Order your guesses based on these decoded tile numbers, matching the words present on those tiles.\n\n"
        "Respond with ONLY a JSON object:\n"
        "{\"reasoning\": \"<show your step-by-step decoding of each letter of the clue word to its tile index>\", \"guesses\": [\"WORD1\", \"WORD2\", ...]}\n"
        "Only choose from the words shown above, exactly as written."
    )
    return [
        {"role": "system", "content": "You play Codenames as the guesser. You reason from the clue and the words, using the Alphabetical Index Protocol to decode target tiles."},
        {"role": "user", "content": user},
    ]


def load_words(path):
    words = [line.strip().upper() for line in path.read_text().splitlines()]
    words = [w for w in words if w]
    return list(set(words))


def generate_random_board(words_pool):
    words = random.sample(words_pool, 25)
    roles = (["red"] * 9) + (["blue"] * 8) + (["civilian"] * 7) + (["assassin"] * 1)
    random.shuffle(roles)
    key = {w: r for w, r in zip(words, roles)}
    return {"words": words, "key": key}


def format_cell(word, role, is_revealed, show_key):
    padded = f" {word} ".center(16)
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    RED_TEXT = "\033[91m"
    BLUE_TEXT = "\033[94m"
    GRAY_TEXT = "\033[90m"
    ASSASSIN_TEXT = "\033[35m"
    
    RED_BG = "\033[41;1;97m"
    BLUE_BG = "\033[44;1;97m"
    CIV_BG = "\033[47;30m"
    ASSASSIN_BG = "\033[45;1;97m"
    
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
        return f"\033[37m{padded}\033[0m"
    return padded


def print_grid(words, key, revealed_set, show_key=False):
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
    parser.add_argument("--games", type=int, default=10, help="Number of games to play")
    parser.add_argument("--codemaster", default="gemini-3.1-flash-lite", help="Codemaster model ID")
    parser.add_argument("--guesser", default="gemini-3.1-flash-lite", help="Guesser model ID")
    args = parser.parse_args()

    config = game.load_config()
    providers = config["providers"]
    temps = config["temperature"]
    
    # Setup clients
    cm_provider = "gemini"
    g_provider = "gemini"
    
    # Search providers matching model names if overridden
    for cm in config["roles"]["codemasters"]:
        if cm["name"] == args.codemaster:
            cm_provider = cm["provider"]
            break
            
    if config["roles"]["guesser"]["name"] == args.guesser:
        g_provider = config["roles"]["guesser"]["provider"]

    cm_client = game.make_client(providers[cm_provider])
    g_client = game.make_client(providers[g_provider])
    
    wordlist_path = ROOT / config["wordlist"]
    words_pool = load_words(wordlist_path)

    print("\n" + "=" * 80)
    print(f"STARTING CODENAMES ONE-SHOT EXPERIMENT ({args.games} Games)".center(80))
    print(f"Codemaster: {args.codemaster} ({cm_provider})")
    print(f"Guesser:    {args.guesser} ({g_provider})")
    print("=" * 80 + "\n")

    games_log = []
    wins = 0
    total_score = 0
    total_correct = 0
    ending_breakdown = {"win": 0, "assassin": 0, "blue": 0, "civilian": 0, "stopped": 0}

    for g_idx in range(args.games):
        print(f"\n" + "-" * 80)
        print(f"GAME {g_idx + 1} of {args.games}".center(80))
        print("-" * 80)
        
        board = generate_random_board(words_pool)
        words, key = board["words"], board["key"]
        
        print("\nSECRET KEY VIEW:")
        print_grid(words, key, set(), show_key=True)
        
        # Get Codemaster Clue
        cm_msgs = [
            {"role": "system", "content": oneshot_codemaster_system()},
            {"role": "user", "content": oneshot_codemaster_request(words, key)}
        ]
        
        print("\nQuerying Codemaster for clue...")
        try:
            content = game.chat(cm_client, args.codemaster, cm_msgs, temps["codemaster"], game.CODEMASTER_MAX_TOKENS)
            clue, number, cm_reasoning = game.parse_clue(content)
        except Exception as e:
            print(f"\033[91mCodemaster Error: {e}\033[0m")
            games_log.append({
                "game_index": g_idx,
                "error": f"Codemaster Error: {e}",
                "score": 0,
                "correct_guesses": 0,
                "ended_on": "error"
            })
            continue

        print(f"\n\033[1mCodemaster Clue:\033[0m \033[92m{clue} {number}\033[0m")
        print(f"\033[1mCodemaster Reasoning:\033[0m {cm_reasoning}")

        # Get Guesser Guesses
        g_msgs = oneshot_guesser_messages(words, clue, number)
        print("\nQuerying Guesser...")
        try:
            g_content = game.chat(g_client, args.guesser, g_msgs, temps["guesser"], game.GUESSER_MAX_TOKENS)
            guesses, g_reasoning = game.parse_guesses(g_content, set(words))
        except Exception as e:
            print(f"\033[91mGuesser Error: {e}\033[0m")
            games_log.append({
                "game_index": g_idx,
                "clue": clue,
                "number": number,
                "codemaster_reasoning": cm_reasoning,
                "error": f"Guesser Error: {e}",
                "score": 0,
                "correct_guesses": 0,
                "ended_on": "error"
            })
            continue

        print(f"\033[1mGuesser Reasoning:\033[0m {g_reasoning}")
        print(f"\033[1mGuesses chosen:\033[0m {guesses}")

        # Evaluate Guesses
        revealed = set()
        correct_count = 0
        ended_on = "stopped"  # default if they stop early without errors
        
        guesses_outcome = []
        for guess in guesses[:9]:  # Limit to 9 guesses maximum
            role = key[guess]
            is_correct = (role == "red")
            revealed.add(guess)
            
            guesses_outcome.append({
                "word": guess,
                "role": role,
                "correct": is_correct
            })
            
            if is_correct:
                correct_count += 1
                print(f"  - {guess:<12} (Role: {role.upper():<9} -> \033[92mCORRECT!\033[0m)")
                if correct_count == 9:
                    ended_on = "win"
                    break
            else:
                ended_on = role
                print(f"  - {guess:<12} (Role: {role.upper():<9} -> \033[91mWRONG!\033[0m)")
                break

        # Score calculation
        # score will be based on: -10 if the guesser hits the assassin.
        # and 1 point for each correct guess (even before hitting assassin)
        # and -1 if the guesser ended on hitting the enemy
        # and 0 if the guesser ended on hitting a bystander
        # and +10 if the guesser won the game
        score = correct_count
        if ended_on == "win":
            score += 10
        elif ended_on == "assassin":
            score -= 10
        elif ended_on == "blue":
            score -= 1

        print("\nUPDATED BOARD VIEW (Revealed words):")
        print_grid(words, key, revealed, show_key=False)

        print(f"\nGame Results: Outcome={ended_on.upper()} | Correct Guesses={correct_count}/9 | Score={score}")
        
        # Track statistics
        if ended_on == "win":
            wins += 1
        total_score += score
        total_correct += correct_count
        ending_breakdown[ended_on] += 1

        games_log.append({
            "game_index": g_idx,
            "board": board,
            "clue": clue,
            "number": number,
            "codemaster_reasoning": cm_reasoning,
            "guesser_reasoning": g_reasoning,
            "guesses": guesses_outcome,
            "correct_guesses": correct_count,
            "ended_on": ended_on,
            "score": score
        })
        
        # Small delay to respect rate limits on free tier
        time.sleep(1.0)

    # Calculate overall stats
    valid_games = len([g for g in games_log if "error" not in g])
    avg_score = total_score / valid_games if valid_games > 0 else 0
    avg_correct = total_correct / valid_games if valid_games > 0 else 0
    win_percentage = (wins / valid_games * 100) if valid_games > 0 else 0

    stats = {
        "experiments_meta": {
            "total_games": args.games,
            "valid_games": valid_games,
            "codemaster_model": args.codemaster,
            "guesser_model": args.guesser,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "statistics": {
            "oneshotted_count": wins,
            "oneshotted_percentage": win_percentage,
            "average_score": avg_score,
            "average_correct_guesses": avg_correct,
            "ending_breakdown": ending_breakdown
        },
        "games": games_log
    }

    # Write output to results/
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / "oneshot_stats.json"
    out_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n")

    print("\n" + "=" * 80)
    print("EXPERIMENT COMPLETE - SUMMARY STATS".center(80))
    print("=" * 80)
    print(f"Total Games Played:           {args.games}")
    print(f"Successfully Oneshotted (Wins): {wins} / {valid_games} ({win_percentage:.1f}%)")
    print(f"Average Score:                 {avg_score:.2f}")
    print(f"Average Correct Guesses:       {avg_correct:.2f} / 9")
    print("\nEnding Conditions Breakdown:")
    for cond, count in ending_breakdown.items():
        print(f"  - {cond.upper():<10}: {count}")
    print(f"\nDetailed logs saved to: {out_path.relative_to(ROOT)}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
