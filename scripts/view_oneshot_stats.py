#!/usr/bin/env python3
"""Visualization helper for Codenames One-shot Experiment.

This script parses results/oneshot_stats.json and generates a plot of ending
conditions and game-by-game scores.

Usage:
    py scripts/view_oneshot_stats.py
"""

import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def view_oneshot_stats(json_path="results/oneshot_stats.json", output_path="results/oneshot_stats.png"):
    """Reads Codenames oneshot stats JSON, creates a plot, and saves it as an image."""
    json_path = ROOT / json_path
    output_path = ROOT / output_path
    
    if not json_path.exists():
        print(f"Error: {json_path} does not exist. Run the oneshot experiment first!")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    stats = data["statistics"]
    meta = data["experiments_meta"]
    games = data["games"]
    
    # Filter valid games
    valid_games = [g for g in games if "error" not in g]
    games_idx = [g["game_index"] + 1 for g in valid_games]
    scores = [g["score"] for g in valid_games]
    corrects = [g["correct_guesses"] for g in valid_games]
    
    breakdown = stats["ending_breakdown"]
    
    # Setup plotting styles
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"Codenames One-shot Experiment (Model: {meta['codemaster_model']})", fontsize=14, fontweight="bold")
    
    # Subplot 1: Ending Conditions Breakdown
    categories = [cat.upper() for cat in breakdown.keys()]
    counts = list(breakdown.values())
    
    # Mapping color scheme
    # WIN: green, ASSASSIN: purple/black, BLUE: blue, CIVILIAN: gray, STOPPED: orange
    colors = ['#2ca02c', '#9467bd', '#1f77b4', '#7f7f7f', '#ff7f0e']
    
    axes[0].bar(categories, counts, color=colors, edgecolor='black', alpha=0.8, width=0.6)
    axes[0].set_title("Ending Conditions Breakdown", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Number of Games")
    axes[0].set_ylim(0, max(counts) + 1 if counts else 10)
    axes[0].grid(axis='y', linestyle='--', alpha=0.5)
    for i, v in enumerate(counts):
        axes[0].text(i, v + 0.1, str(v), ha='center', va='bottom', fontweight='bold')
        
    # Subplot 2: Score vs Correct Guesses per Game
    x = np.arange(len(games_idx))
    width = 0.35
    clues = [g.get("clue", "N/A") for g in valid_games]
    x_labels = [f"G{idx}\n{clue}" for idx, clue in zip(games_idx, clues)]
    
    axes[1].bar(x - width/2, corrects, width, label='Correct Guesses', color='#17becf', alpha=0.8, edgecolor='black')
    axes[1].bar(x + width/2, scores, width, label='Score', color='#ff7f0e', alpha=0.8, edgecolor='black')
    axes[1].set_title("Score & Correct Guesses per Game", fontsize=11, fontweight="bold")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(x_labels, rotation=15, ha='center', fontsize=8)
    axes[1].set_xlabel("Game (Clue Word)")
    axes[1].set_ylabel("Value")
    axes[1].legend(loc='upper right')
    axes[1].grid(axis='y', linestyle='--', alpha=0.5)
    
    # Summary Box
    summary_text = (
        f"Total Games: {meta['total_games']}   |   "
        f"Successfully Oneshotted (Wins): {stats['oneshotted_count']} ({stats['oneshotted_percentage']:.1f}%)   |   "
        f"Avg Correct Guesses: {stats['average_correct_guesses']:.2f} / 9   |   "
        f"Avg Score: {stats['average_score']:.2f}"
    )
    fig.text(0.5, 0.02, summary_text, ha='center', bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', edgecolor='gray', alpha=0.8), fontsize=10)
    
    plt.tight_layout(rect=[0, 0.12, 1, 0.95])
    plt.savefig(output_path, dpi=300)
    print(f"Stats visualization image saved successfully to: {output_path.relative_to(ROOT)}")
    
    # Non-blocking show if run in GUI environment
    try:
        plt.show(block=True)
    except Exception:
        pass


if __name__ == "__main__":
    view_oneshot_stats()
