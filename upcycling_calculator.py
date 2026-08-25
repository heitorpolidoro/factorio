#!/usr/bin/env python3
"""
Factorio 2.0 / Space Age - Upcycling Calculator: Circuito de Ferro (Iron Gear Wheel + Iron Plate)

Fluxo de Ferro em Vulcanus:
1. Lava + Calcita -> Foundry (4 slots, +50% Prod Nato): Molten Iron -> Engrenagem de Ferro (Iron Gear Wheel).
2. Engrenagens não-lendárias -> Reciclador (4x Q3 Épico, 25% yield) -> Devolve Placa de Ferro (Iron Plate).
   * Nota: 1 Engrenagem é feita de 2 Placas. Reciclar 1 Engrenagem devolve 2 * 25% = 0.50 Placas de Ferro!
3. Placas de ferro não-lendárias -> EP / Montadora (5 slots, +50% Prod Nato): Iron Plate -> Iron Gear Wheel.
4. Engrenagens não-lendárias da EP -> Voltam para o Reciclador!
5. Produtos Finais Coletados: Engrenagens Lendárias e Placas de Ferro Lendárias.
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

console = Console()


def get_quality_chance(count: int) -> float:
    if count <= 0:
        return 0.0
    return 0.025 * 1.9 * count


def get_prod_bonus(count: int) -> float:
    if count <= 0:
        return 0.0
    return 0.10 * 1.9 * count


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


def craft_step_foundry_iron(input_amount: float, input_quality: str, q_count: int, p_count: int) -> Dict[str, float]:
    in_tier = QUALITY_TO_TIER.get(input_quality.capitalize(), 0)
    Q_craft = get_quality_chance(q_count)
    P_craft = 1.0 + 0.50 + get_prod_bonus(p_count)
    T_craft = get_transition_matrix(Q_craft)
    
    outputs = {q_name: 0.0 for q_name in QUALITY_NAMES}
    for out_tier, q_name in enumerate(QUALITY_NAMES):
        outputs[q_name] = input_amount * P_craft * T_craft[in_tier][out_tier]
    return outputs


def craft_step_ep_iron(input_amount: float, input_quality: str, q_count: int, p_count: int) -> Dict[str, float]:
    """1 Engrenagem requer 2 Placas de Ferro. Com produtividade P_craft, 1 Placa produz P_craft / 2 Engrenagens."""
    in_tier = QUALITY_TO_TIER.get(input_quality.capitalize(), 0)
    Q_craft = get_quality_chance(q_count)
    P_craft = 1.0 + 0.50 + get_prod_bonus(p_count)
    T_craft = get_transition_matrix(Q_craft)
    
    outputs = {q_name: 0.0 for q_name in QUALITY_NAMES}
    for out_tier, q_name in enumerate(QUALITY_NAMES):
        outputs[q_name] = (input_amount / 2.0) * P_craft * T_craft[in_tier][out_tier]
    return outputs


def recycle_step_iron_gear(input_amount: float, input_quality: str) -> Dict[str, float]:
    """1 Engrenagem reciclada devolve 2 Placas * 25% yield = 0.50 Placas de Ferro."""
    in_tier = QUALITY_TO_TIER.get(input_quality.capitalize(), 0)
    Q_recyc = get_quality_chance(4)
    T_recyc = get_transition_matrix(Q_recyc)
    recycler_efficiency = 0.25
    
    outputs = {q_name: 0.0 for q_name in QUALITY_NAMES}
    for out_tier, q_name in enumerate(QUALITY_NAMES):
        outputs[q_name] = input_amount * 2.0 * recycler_efficiency * T_recyc[in_tier][out_tier]
    return outputs


def simulate_vulcanus_iron_loop(
    foundry_q_count: int,
    foundry_p_count: int,
    ep_q_count: int,
    ep_p_count: int,
    input_molten_iron: float = 100.0,
    tolerance: float = 1e-7,
    max_iterations: int = 1000
) -> Dict[str, float]:
    gears_to_recycle = {name: 0.0 for name in QUALITY_NAMES[:4]}
    plates_to_ep = {name: 0.0 for name in QUALITY_NAMES[:4]}
    
    initial_gears = craft_step_foundry_iron(input_molten_iron, "Normal", foundry_q_count, foundry_p_count)
    
    legendary_gears = initial_gears["Legendary"]
    legendary_plates = 0.0
    
    for q_name in QUALITY_NAMES[:4]:
        gears_to_recycle[q_name] += initial_gears[q_name]
        
    iteration = 0
    while iteration < max_iterations:
        active_items = sum(gears_to_recycle.values()) + sum(plates_to_ep.values())
        if active_items < tolerance:
            break
            
        next_gears_to_recycle = {name: 0.0 for name in QUALITY_NAMES[:4]}
        next_plates_to_ep = {name: 0.0 for name in QUALITY_NAMES[:4]}
        
        # A. Reciclagem de engrenagens -> Placas de Ferro
        for q_name, qty in gears_to_recycle.items():
            if qty <= 0.0:
                continue
            recycled = recycle_step_iron_gear(qty, q_name)
            legendary_plates += recycled["Legendary"]
            for ret_q in QUALITY_NAMES[:4]:
                next_plates_to_ep[ret_q] += recycled[ret_q]
                
        # B. Fabricação de Placas de Ferro -> Engrenagens na EP
        for q_name, qty in plates_to_ep.items():
            if qty <= 0.0:
                continue
            ep_crafted = craft_step_ep_iron(qty, q_name, ep_q_count, ep_p_count)
            legendary_gears += ep_crafted["Legendary"]
            for ret_q in QUALITY_NAMES[:4]:
                next_gears_to_recycle[ret_q] += ep_crafted[ret_q]
                
        gears_to_recycle = next_gears_to_recycle
        plates_to_ep = next_plates_to_ep
        iteration += 1
        
    total_legendary = legendary_gears + legendary_plates
    raw_per_legendary = input_molten_iron / total_legendary if total_legendary > 0 else float('inf')
    
    return {
        "legendary_gears": round(legendary_gears, 5),
        "legendary_plates": round(legendary_plates, 5),
        "total_legendary_products": round(total_legendary, 5),
        "raw_iron_per_legendary_product": round(raw_per_legendary, 5)
    }


def display_iron_optimization():
    table = Table(
        title="[bold yellow]FACTORIO 2.0 - CIRCUITO DE FERRO: ENGRENAGEM (IRON GEAR) + PLACA DE FERRO (IRON PLATE)[/bold yellow]\n[dim]Foundry (4 Slots, +50% Prod) -> Reciclador (4x Q3 Épico, 25% yield) -> EP (5 Slots, +50% Prod)[/dim]",
        header_style="bold magenta",
        border_style="bright_yellow"
    )
    
    table.add_column("Módulos Foundry (4 slots)", style="bold cyan", width=25)
    table.add_column("Módulos EP (5 slots)", style="bold green", width=25)
    table.add_column("Engrenagens Lend.", justify="right", style="cyan")
    table.add_column("Placas Lend.", justify="right", style="cyan")
    table.add_column("Total Lend.", justify="right", style="bold green")
    table.add_column("Ferro Base / 1 Lendário", justify="right", style="bold yellow", width=26)

    results = []
    min_val = float('inf')
    best_combo = None

    for f_p in range(5):
        f_q = 4 - f_p
        for ep_p in range(6):
            ep_q = 5 - ep_p
            
            res = simulate_vulcanus_iron_loop(f_q, f_p, ep_q, ep_p, input_molten_iron=100.0)
            val = res["raw_iron_per_legendary_product"]
            results.append((f_q, f_p, ep_q, ep_p, res, val))
            if val < min_val:
                min_val = val
                best_combo = (f_q, f_p, ep_q, ep_p)

    results.sort(key=lambda x: x[5])

    for f_q, f_p, ep_q, ep_p, res, val in results[:10]:
        is_best = ((f_q, f_p, ep_q, ep_p) == best_combo)
        tag = " 🏆 (VENCEDOR!)" if is_best else ""
        
        f_str = f"{f_q}Q3 + {f_p}P3"
        ep_str = f"{ep_q}Q3 + {ep_p}P3{tag}"
        gears_str = f"{res['legendary_gears']:.2f}"
        plates_str = f"{res['legendary_plates']:.2f}"
        total_str = f"{res['total_legendary_products']:.2f}"
        val_str = f"{val:.5f}"
        
        style_row = "bold gold1" if is_best else None
        table.add_row(f_str, ep_str, gears_str, plates_str, total_str, val_str, style=style_row)

    console.print(table)


if __name__ == "__main__":
    display_iron_optimization()
