#!/usr/bin/env python3
"""
Factorio 2.0 / Space Age - Speed & Upcycling Calculator

Cenário Específico Solicitado:
- Foundry [F]: 4P (4 Produtividade 3 Épico) + 8S em Beacons (8 Velocidade 3 Épicos)
- Reciclador [R]: 4Q (4 Qualidade 3 Épico, 19.0% chance qual, 25% yield)
- Planta Eletromagnética [EP]: Variações de Q e P (5Q, 4Q1P, 3Q2P, 2Q3P, 1Q4P, 0Q5P) sem beacons.
"""

import sys
import argparse
from typing import Dict, List, Tuple
from rich.console import Console
from rich.table import Table

QUALITY_NAMES = ["Normal", "Uncommon", "Rare", "Epic", "Legendary"]
QUALITY_TO_TIER = {name: i for i, name in enumerate(QUALITY_NAMES)}
QUALITY_MULT = {"Normal": 1.0, "Uncommon": 1.3, "Rare": 1.6, "Epic": 1.9, "Legendary": 2.5}
MODULE_BASE_CHANCE = {1: 0.010, 2: 0.020, 3: 0.025}
PROD_MODULE_BASE = {1: 0.04, 2: 0.06, 3: 0.10}

BUILDING_BASE_SPEEDS = {
    "Foundry": 4.0,
    "EP": 2.0,
    "Recycler": 0.5,
    "Assembler3": 1.25
}

SPEED_PENALTY_PROD_3_EPIC = -0.15
SPEED_PENALTY_QUAL_3_EPIC = -0.05
SPEED_MODULE_3_EPIC_BONUS = 0.95

console = Console()


def get_transition_matrix(Q: float) -> List[List[float]]:
    T = [[0.0] * 5 for _ in range(5)]
    for in_tier in range(5):
        if in_tier == 4:
            T[in_tier][4] = 1.0
            continue
        
        T[in_tier][in_tier] = 1.0 - Q
        curr_p = Q
        curr_tier = in_tier + 1
        while curr_tier < 4:
            T[in_tier][curr_tier] = curr_p * 0.90
            curr_p *= 0.10
            curr_tier += 1
        T[in_tier][4] = curr_p
        
    return T


def simulate_foundry_4p_beacons_loop(ep_q: int, ep_p: int, input_molten: float = 100.0) -> Dict[str, float]:
    """
    Foundry: 4P (Prod = +76% + 50% nato = 226%). Qualidade = 0% (Beacons 8S zeraram a qualidade).
    Reciclador: 4Q (Qualidade = 19%, Yield = 25%).
    EP: ep_q Módulos Q + ep_p Módulos P (Qualidade = ep_q * 4.75%, Prod = 150% + ep_p * 19%).
    """
    # 1. Foundry: Faz itens 100% NORMGAIS (0% qualidade) com 226% prod
    f_prod = 1.0 + 0.50 + (4 * 0.19)  # 2.26x
    initial_items_normal = input_molten * f_prod
    
    legendary_gears_cables = 0.0
    legendary_plates = 0.0
    
    gears_to_recycle = {name: 0.0 for name in QUALITY_NAMES[:4]}
    plates_to_ep = {name: 0.0 for name in QUALITY_NAMES[:4]}
    
    gears_to_recycle["Normal"] = initial_items_normal
    
    Q_recyc = 4 * 0.025 * 1.9  # 19.0%
    T_recyc = get_transition_matrix(Q_recyc)
    
    Q_ep = ep_q * 0.025 * 1.9
    P_ep = (1.0 + 0.50 + (ep_p * 0.19)) / 2.0  # Para engrenagem (2 placas -> 1 engrenagem)
    T_ep = get_transition_matrix(Q_ep)
    
    iteration = 0
    max_iterations = 1000
    tolerance = 1e-7
    
    while iteration < max_iterations:
        active = sum(gears_to_recycle.values()) + sum(plates_to_ep.values())
        if active < tolerance:
            break
            
        next_gears_to_recycle = {name: 0.0 for name in QUALITY_NAMES[:4]}
        next_plates_to_ep = {name: 0.0 for name in QUALITY_NAMES[:4]}
        
        # A. Reciclador (4Q, 25% yield)
        for q_name, qty in gears_to_recycle.items():
            if qty <= 0.0:
                continue
            in_t = QUALITY_TO_TIER[q_name]
            for out_t, out_q_name in enumerate(QUALITY_NAMES):
                amount_ret = qty * 2.0 * 0.25 * T_recyc[in_t][out_t]
                if out_q_name == "Legendary":
                    legendary_plates += amount_ret
                else:
                    next_plates_to_ep[out_q_name] += amount_ret
                    
        # B. EP (ep_q, ep_p)
        for q_name, qty in plates_to_ep.items():
            if qty <= 0.0:
                continue
            in_t = QUALITY_TO_TIER[q_name]
            for out_t, out_q_name in enumerate(QUALITY_NAMES):
                amount_crafted = qty * P_ep * T_ep[in_t][out_t]
                if out_q_name == "Legendary":
                    legendary_gears_cables += amount_crafted
                else:
                    next_gears_to_recycle[out_q_name] += amount_crafted
                    
        gears_to_recycle = next_gears_to_recycle
        plates_to_ep = next_plates_to_ep
        iteration += 1
        
    total_legendary = legendary_gears_cables + legendary_plates
    raw_per_legendary = input_molten / total_legendary if total_legendary > 0 else float('inf')
    
    # Cálculos de Velocidade (Foundry 4P com 8S Beacons = 32.0x velocidade!)
    foundry_effective_speed = 4.0 * (1.0 - 0.60 + (8 * SPEED_MODULE_3_EPIC_BONUS))  # 32.0x
    crafts_per_sec = foundry_effective_speed / 0.5  # 64.0 crafts/sec
    
    legendary_per_foundry_craft = total_legendary / input_molten
    legendary_per_sec = crafts_per_sec * legendary_per_foundry_craft
    seconds_per_legendary = 1.0 / legendary_per_sec if legendary_per_sec > 0 else float('inf')
    
    return {
        "legendary_products": round(total_legendary, 5),
        "raw_per_legendary": round(raw_per_legendary, 5),
        "foundry_speed": round(foundry_effective_speed, 2),
        "crafts_per_sec": round(crafts_per_sec, 2),
        "legendary_per_sec": round(legendary_per_sec, 5),
        "seconds_per_legendary": round(seconds_per_legendary, 5)
    }


def display_foundry_4p_beacons_analysis():
    console.print("\n[bold yellow]FACTORIO 2.0 - ANÁLISE DO CENÁRIO: FOUNDRY 4P + 8S BEACONS | RECICLADOR 4Q | EP VARIAÇÕES[/bold yellow]")
    console.print("[dim]Foundry com 4 Produtividade + 8 Módulos de Velocidade Épicos em Beacons (Qualidade na Foundry = 0% por causa das penalidades dos Beacons)[/dim]\n")

    ep_variations = [
        ("EP: 5Q + 0P", 5, 0),
        ("EP: 4Q + 1P", 4, 1),
        ("🏆 EP: 3Q + 2P", 3, 2),
        ("EP: 2Q + 3P", 2, 3),
        ("EP: 1Q + 4P", 1, 4),
        ("EP: 0Q + 5P", 0, 5),
    ]

    table = Table(
        title="[bold cyan]Resultados do Circuito para 1 Foundry (4P + 8S Beacons)[/bold cyan]",
        header_style="bold magenta",
        border_style="bright_blue"
    )
    table.add_column("Configuração da EP", style="bold white", width=22)
    table.add_column("Vel. Foundry", justify="right", style="cyan", width=14)
    table.add_column("Crafts / sec", justify="right", style="cyan", width=12)
    table.add_column("Lendários / sec", justify="right", style="bold green", width=16)
    table.add_column("Tempo / Lendário", justify="right", style="bold yellow", width=16)
    table.add_column("Custo Matéria-Prima", justify="right", style="magenta", width=20)

    for name, ep_q, ep_p in ep_variations:
        res = simulate_foundry_4p_beacons_loop(ep_q, ep_p, input_molten=100.0)
        
        style_row = "bold gold1" if ep_q == 3 and ep_p == 2 else None
        table.add_row(
            name,
            f"{res['foundry_speed']:.2f}x",
            f"{res['crafts_per_sec']:.1f}/s",
            f"{res['legendary_per_sec']:.5f}/s",
            f"{res['seconds_per_legendary']:.2f} s",
            f"{res['raw_per_legendary']:.2f} ferros",
            style=style_row
        )

    console.print(table)
    console.print()


def main():
    display_foundry_4p_beacons_analysis()


if __name__ == "__main__":
    main()
