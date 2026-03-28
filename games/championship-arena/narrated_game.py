#!/usr/bin/env python3
"""Narrated game output for Championship Arena."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulate_game import run_narrated_game


def main():
    with open(os.path.join(os.path.dirname(__file__), "config.json")) as f:
        config = json.load(f)

    # Run a 3-player narrated game
    gs, narration = run_narrated_game(3, config)
    print(narration)

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "narrated_game_output.txt")
    with open(output_path, "w") as f:
        f.write(narration)
    print(f"\n[Narrated game saved to: {output_path}]")


if __name__ == "__main__":
    main()
