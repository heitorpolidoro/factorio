#!/usr/bin/env python3
"""
Factorio 2.0 / Space Age - Quality Probability & Upcycling Calculator

Calculates the probabilities of item quality upgrades based on Factorio Wiki rules:
- Module Quality Multiplier: Normal=1.0, Uncommon=1.3, Rare=1.6, Epic=1.9, Legendary=2.5
- Base Quality Module Chances (at Normal Quality):
    * Quality Module 1: +1.0%
    * Quality Module 2: +2.0%
    * Quality Module 3: +2.5%
- Upgrade Roll Mechanics:
    * First roll: success chance Q (sum of all module quality chances in machine).
    * Subsequent rolls (up to Legendary): fixed 10% success chance per tier upgrade.
"""

import sys
import argparse
from typing import Dict, List

QUALITY_NAMES = ["Normal", "Uncommon", "Rare", "Epic", "Legendary"]
QUALITY_MULT = {
    "Normal": 1.0,
    "Uncommon": 1.3,
    "Rare": 1.6,
    "Epic": 1.9,
    "Legendary": 2.5
}

MODULE_BASE_CHANCE = {
    1: 0.010,  # Quality Module 1 (+1.0%)
    2: 0.020,  # Quality Module 2 (+2.0%)
    3: 0.025   # Quality Module 3 (+2.5%)
}


def calculate_module_chance(module_tier: int, module_quality: str, count: int = 1) -> float:
    """Calculate total quality chance (Q) for a set of identical quality modules."""
    base = MODULE_BASE_CHANCE.get(module_tier, 0.025)
    mult = QUALITY_MULT.get(module_quality.capitalize(), 2.5)
    return base * mult * count


def get_output_probabilities(Q: float, input_tier: int) -> Dict[str, float]:
    """
    Given total Quality chance Q (0.0 to 1.0) and input item quality tier (0..4),
    returns a dictionary mapping output quality names to probabilities.
    """
    probs = {name: 0.0 for name in QUALITY_NAMES}
    
    if input_tier >= 4:
        probs["Legendary"] = 1.0
        return probs
    
    # Probability of NOT upgrading
    probs[QUALITY_NAMES[input_tier]] = 1.0 - Q
    
    # If initial roll succeeds with prob Q:
    current_p = Q
    curr_tier = input_tier + 1
    
    while curr_tier < 4:
        # Fails next 10% roll (90% chance to stop at curr_tier)
        probs[QUALITY_NAMES[curr_tier]] = current_p * 0.90
        # Succeeds next 10% roll to continue to next tier
        current_p *= 0.10
        curr_tier += 1
        
    # Highest tier (Legendary = tier 4) takes all remaining success probability
    probs[QUALITY_NAMES[4]] = current_p
    
    return probs


def print_probability_table(title: str, Q: float):
    """Print formatted matrix of Input Quality vs Output Quality probabilities."""
    print("=" * 78)
    print(f" {title}")
    print(f" Total Quality Chance (Q): {Q * 100:.3f}% ({Q:.5f})")
    print("=" * 78)
    
    header = f"{'Input Quality':<15} | " + " | ".join(f"{q:>10}" for q in QUALITY_NAMES)
    print(header)
    print("-" * 78)
    
    for in_tier, in_name in enumerate(QUALITY_NAMES):
        probs = get_output_probabilities(Q, in_tier)
        row_str = f"{in_name:<15} | "
        cols = []
        for out_name in QUALITY_NAMES:
            p = probs[out_name]
            if p == 0.0:
                cols.append(f"{'-':>10}")
            else:
                cols.append(f"{p * 100:>9.4f}%")
        row_str += " | ".join(cols)
        print(row_str)
    print("=" * 78)
    print()


def print_legendary_modules_summary():
    """Prints tables for 1 Legendary Quality Module (Tiers 1, 2, 3)."""
    print("\n" + "#" * 78)
    print(" FACTORIO WIKI QUALITY PROBABILITIES: 1 LEGENDARY QUALITY MODULE")
    print("#" * 78 + "\n")
    
    for tier in [1, 2, 3]:
        Q = calculate_module_chance(tier, "Legendary", count=1)
        title = f"1x Legendary Quality Module {tier}"
        print_probability_table(title, Q)


def main():
    parser = argparse.ArgumentParser(description="Factorio Quality Probability Calculator")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=3, help="Module tier (1, 2, or 3)")
    parser.add_argument("--quality", type=str, default="Legendary", 
                        choices=["Normal", "Uncommon", "Rare", "Epic", "Legendary"],
                        help="Module quality level")
    parser.add_argument("--count", type=int, default=1, help="Number of modules in machine")
    parser.add_argument("--all-legendary", action="store_true", help="Show summary for 1x Legendary Module of each tier")
    
    args = parser.parse_args()
    
    if args.all_legendary or len(sys.argv) == 1:
        print_legendary_modules_summary()
    else:
        Q = calculate_module_chance(args.tier, args.quality, args.count)
        title = f"{args.count}x {args.quality.capitalize()} Quality Module {args.tier}"
        print_probability_table(title, Q)


if __name__ == "__main__":
    main()
